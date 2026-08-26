import { describe, expect, it } from 'vitest'

import type { CapabilityStatement } from '@/lib/fhir'
import {
    AUTHORIZATION_PLACEHOLDER,
    authorizationScheme,
    curlCommand,
    EVALUATE_EXAMPLE_BODY,
    formatHref,
    NO_SAMPLES,
    OPERATIONS_GROUP,
    playgroundPresets,
    prettyBody,
    presetShelves,
    READS_GROUP,
    requestTarget,
    RESOURCE_ID_PLACEHOLDER,
    type PlaygroundRequest,
    type ServerSamples,
    declaredParameters,
} from '@/lib/playground'

/**
 * What the Playground would actually send, and what it would tell somebody to type.
 *
 * TWO THINGS ARE WORTH ASSERTING WITHOUT A BROWSER, and they are the two the screen cannot show a
 * reader is wrong. The first is the address a method, a path and a handful of rows add up to: an
 * encoding bug there is invisible until a search comes back with nothing and the reason is a
 * literal `&` in a value. The second is the curl command, which leaves this app entirely - it is
 * pasted into a terminal, a ticket, a chat window - so it has to survive quoting, and it must never
 * carry the credential the browser is holding.
 *
 * THE PRESETS ARE ASSERTED AS A READING OF ONE DOCUMENT. The panel claims to be this server's own
 * declaration rather than a written-down list, and that claim is only true if a statement declaring
 * nothing produces no rows about ConceptMaps.
 */

/** A conformance document shaped like the one this facade publishes, cut to what the presets read. */
const CAPABILITY: CapabilityStatement = {
    resourceType: 'CapabilityStatement',
    status: 'active',
    kind: 'instance',
    rest: [
        {
            mode: 'server',
            operation: [{ name: 'evaluate' }],
            resource: [
                {
                    type: 'Questionnaire',
                    interaction: [{ code: 'read' }, { code: 'search-type' }],
                    operation: [{ name: 'generate' }],
                },
                {
                    type: 'ConceptMap',
                    interaction: [{ code: 'read' }, { code: 'search-type' }],
                    operation: [{ name: 'translate' }],
                },
                // Read but never searched, so it earns no search preset.
                { type: 'Binary', interaction: [{ code: 'read' }] },
            ],
        },
    ],
}

/** What one server was found to hold, so the three presets that name a resource can answer. */
const SAMPLES: ServerSamples = {
    questionnaireId: 'eaDHS084uMp',
    concept: { system: 'http://example.org/fhir/CodeSystem/d2-tet-cs', code: 'We9I19a3vO1' },
}

/** One request, with everything but the named parts left as the builder opens them. */
function request(parts: Partial<PlaygroundRequest>): PlaygroundRequest {
    return { method: 'GET', path: '/metadata', parameters: [], body: '', ...parts }
}

describe('formatHref holds the origin', () => {
    const origin = 'http://localhost:8095'

    it('degrades a protocol-relative path to the origin instead of leaving it', () => {
        const request = { method: 'GET' as const, path: '//evil.example/x', parameters: [], body: '' }
        expect(formatHref(origin, request)).toBe(origin)
    })

    it('reads a pasted absolute URL as a path on this origin, never as a destination', () => {
        // requestTarget roots every typed path with a leading slash, so an absolute URL becomes an
        // odd-looking but same-origin path rather than a link that leaves this server.
        const request = { method: 'GET' as const, path: 'https://evil.example/x', parameters: [], body: '' }
        expect(formatHref(origin, request).startsWith(`${origin}/`)).toBe(true)
        expect(new URL(formatHref(origin, request)).origin).toBe(origin)
    })
})

describe('the address a request adds up to', () => {
    it('is the path alone when no parameter has been filled in', () => {
        expect(requestTarget(request({ path: '/metadata' }))).toBe('/metadata')
    })

    it('roots a path somebody typed without its leading slash', () => {
        expect(requestTarget(request({ path: 'Questionnaire' }))).toBe('/Questionnaire')
    })

    it('appends the rows to the query the path already carries', () => {
        const target = requestTarget(
            request({ path: '/Questionnaire?_count=5', parameters: [{ name: 'url', value: 'http://x/y' }] }),
        )
        expect(target).toBe('/Questionnaire?_count=5&url=http%3A%2F%2Fx%2Fy')
    })

    it('leaves out a row that has been added and not named yet', () => {
        const target = requestTarget(
            request({ path: '/Patient', parameters: [{ name: '', value: 'ignored' }, { name: '_tag', value: 'abc' }] }),
        )
        expect(target).toBe('/Patient?_tag=abc')
    })

    it('keeps two rows that share a name, because a search may legitimately repeat one', () => {
        const target = requestTarget(
            request({
                path: '/Patient',
                parameters: [
                    { name: '_tag', value: 'one' },
                    { name: '_tag', value: 'two' },
                ],
            }),
        )
        expect(target).toBe('/Patient?_tag=one&_tag=two')
    })

    it('encodes a value that would otherwise end the query string early', () => {
        const target = requestTarget(request({ path: '/Patient', parameters: [{ name: 'identifier', value: 'a&b=c' }] }))
        expect(target).toBe('/Patient?identifier=a%26b%3Dc')
    })
})

describe('the address a GET opens in a new tab', () => {
    it('asks for JSON in the URL, since the header is not a browser navigation to give', () => {
        expect(formatHref('http://localhost:8095', request({ path: '/metadata' }))).toBe(
            'http://localhost:8095/metadata?_format=json',
        )
    })

    it('keeps the parameters that were already there', () => {
        const href = formatHref('http://localhost:8095', request({ path: '/Questionnaire', parameters: [{ name: '_count', value: '5' }] }))
        expect(href).toBe('http://localhost:8095/Questionnaire?_count=5&_format=json')
    })

    it('leaves a format the request already names alone', () => {
        const href = formatHref('http://localhost:8095', request({ path: '/metadata?_format=xml' }))
        expect(href).toBe('http://localhost:8095/metadata?_format=xml')
    })
})

describe('the curl command', () => {
    it('states the media type this server answers, and nothing else, for a plain read', () => {
        expect(curlCommand('http://localhost:8095', request({ path: '/metadata' }), null)).toBe(
            "curl 'http://localhost:8095/metadata' \\\n  -H 'Accept: application/fhir+json'",
        )
    })

    it('names the method, the content type and the body for a POST', () => {
        const command = curlCommand(
            'http://localhost:8095',
            request({ method: 'POST', path: '/$evaluate', body: '{"language":"fhirpath"}' }),
            null,
        )
        expect(command).toContain("curl -X POST 'http://localhost:8095/$evaluate'")
        expect(command).toContain("-H 'Content-Type: application/fhir+json'")
        expect(command).toContain('-d \'{"language":"fhirpath"}\'')
    })

    it('names the authorization header and elides the credential', () => {
        const command = curlCommand('http://localhost:8095', request({ path: '/Patient' }), 'Basic')
        expect(command).toContain(`-H 'Authorization: Basic ${AUTHORIZATION_PLACEHOLDER}'`)
    })

    it('never carries the credential itself, whatever the browser is holding', () => {
        const command = curlCommand(
            'http://localhost:8095',
            request({ path: '/Patient' }),
            authorizationScheme('Basic YWRtaW46ZGlzdHJpY3Q='),
        )
        expect(command).not.toContain('YWRtaW46ZGlzdHJpY3Q=')
        expect(command).toContain("-H 'Authorization: Basic <your credential>'")
    })

    it('closes, escapes and reopens a single quote inside a body, which is what a shell reads', () => {
        const command = curlCommand(
            'http://localhost:8095',
            request({ method: 'POST', path: '/$evaluate', body: `{"source":"Patient.telecom.where(system = 'email')"}` }),
            null,
        )
        expect(command).toContain(String.raw`'\''email'\''`)
    })

    it('leaves the body out of a POST that carries none', () => {
        expect(curlCommand('http://localhost:8095', request({ method: 'POST', path: '/$evaluate' }), null)).not.toContain(
            ' -d ',
        )
    })
})

describe('the scheme a stored credential signs with', () => {
    it('is the first word of the header value and nothing after it', () => {
        expect(authorizationScheme('Bearer abc.def.ghi')).toBe('Bearer')
        expect(authorizationScheme('Basic YWRtaW4=')).toBe('Basic')
    })

    it('is nothing at all when this browser holds nothing', () => {
        expect(authorizationScheme(null)).toBeNull()
    })
})

describe('the presets this server earns', () => {
    it('opens with the conformance document, which every run answers', () => {
        expect(playgroundPresets(CAPABILITY, SAMPLES)[0].request.path).toBe('/metadata')
    })

    it('offers one search per type the statement says answers a search', () => {
        const labels = playgroundPresets(CAPABILITY, SAMPLES).map((preset) => preset.label)
        expect(labels).toContain('GET /Questionnaire')
        expect(labels).toContain('GET /ConceptMap')
        // Declared read-only, so a search row would name an interaction this server refuses.
        expect(labels).not.toContain('GET /Binary')
    })

    it('fills the addresses that name a resource with one this server was found to hold', () => {
        const presets = playgroundPresets(CAPABILITY, SAMPLES)
        const read = presets.find((preset) => preset.id === 'read:by-id')
        const generate = presets.find((preset) => preset.id === 'operation:generate')
        const translate = presets.find((preset) => preset.id === 'operation:translate')
        expect(read?.request.path).toBe('/Questionnaire/eaDHS084uMp')
        expect(generate?.request.path).toBe('/Questionnaire/eaDHS084uMp/$generate')
        expect(translate?.request.parameters).toEqual([
            { name: 'system', value: SAMPLES.concept?.system },
            { name: 'code', value: SAMPLES.concept?.code },
        ])
        expect([read, generate, translate].every((preset) => preset?.runnable)).toBe(true)
    })

    it('offers the same addresses as templates when this server was found to hold neither', () => {
        const presets = playgroundPresets(CAPABILITY, NO_SAMPLES)
        const read = presets.find((preset) => preset.id === 'read:by-id')
        expect(read?.request.path).toBe(`/Questionnaire/${RESOURCE_ID_PLACEHOLDER}`)
        expect(read?.runnable).toBe(false)
        expect(presets.find((preset) => preset.id === 'operation:generate')?.runnable).toBe(false)
        expect(presets.find((preset) => preset.id === 'operation:translate')?.runnable).toBe(false)
    })

    it('posts the evaluation example to the system-level address, which answers as it stands', () => {
        const evaluate = playgroundPresets(CAPABILITY, SAMPLES).find((preset) => preset.id === 'operation:evaluate')
        expect(evaluate?.request.method).toBe('POST')
        expect(evaluate?.request.path).toBe('/$evaluate')
        expect(evaluate?.request.body).toBe(EVALUATE_EXAMPLE_BODY)
        expect(evaluate?.runnable).toBe(true)
    })

    it('declares nothing about an operation this server does not declare', () => {
        const bare: CapabilityStatement = {
            resourceType: 'CapabilityStatement',
            status: 'active',
            kind: 'instance',
            rest: [{ mode: 'server', resource: [] }],
        }
        const labels = playgroundPresets(bare, SAMPLES).map((preset) => preset.label)
        expect(labels).toEqual(['GET /metadata', `GET /Questionnaire/${SAMPLES.questionnaireId ?? ''}`])
    })

    it('still offers the reads when the server has not answered /metadata yet', () => {
        expect(playgroundPresets(null, NO_SAMPLES).map((preset) => preset.label)).toEqual([
            'GET /metadata',
            `GET /Questionnaire/${RESOURCE_ID_PLACEHOLDER}`,
        ])
    })

    it('shelves the reads and the operations, in the order they were built', () => {
        const shelves = presetShelves(playgroundPresets(CAPABILITY, SAMPLES))
        expect(shelves.map((shelf) => shelf.group)).toEqual([READS_GROUP, OPERATIONS_GROUP])
    })

    it('carries an example body that is the JSON this facade evaluates', () => {
        expect(JSON.parse(EVALUATE_EXAMPLE_BODY)).toMatchObject({
            language: 'fhirpath',
            source: 'Patient.name.given',
            context: { kind: 'inline' },
        })
    })
})

describe('the body as the response box shows it', () => {
    it('pretty-prints what the server answered', () => {
        expect(prettyBody('{"resourceType":"CapabilityStatement"}')).toBe(
            '{\n  "resourceType": "CapabilityStatement"\n}',
        )
    })

    it('shows the bytes as they arrived when they are not JSON at all', () => {
        expect(prettyBody('<!doctype html>')).toBe('<!doctype html>')
    })
})

describe('declaredParameters offers what the path answers', () => {
    const capability = {
        rest: [{
            resource: [{
                type: 'Questionnaire',
                searchParam: [
                    { name: '_id', documentation: 'The logical id.' },
                    { name: 'url', documentation: 'The canonical.' },
                ],
            }],
        }],
    } as never

    it('lists the declared parameters plus the universal pair for a typed path', () => {
        const names = declaredParameters(capability, '/Questionnaire/abc').map((parameter) => parameter.name)
        expect(names).toEqual(['_id', 'url', '_count', '_format'])
    })

    it('offers only _format outside the declared types', () => {
        const names = declaredParameters(capability, '/$evaluate').map((parameter) => parameter.name)
        expect(names).toEqual(['_format'])
    })

    it('answers nothing-plus-_format with no capability yet', () => {
        expect(declaredParameters(null, '/Questionnaire').map((parameter) => parameter.name)).toEqual(['_format'])
    })
})
