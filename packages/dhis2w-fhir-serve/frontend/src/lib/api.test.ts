import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
    GUARDED_PATH_PATTERN,
    UnguardedPathError,
    apiConfiguration,
    apiFetch,
    checkCredential,
    checkReachability,
    configureApi,
    listRegister,
    NOT_A_CAPABILITY_STATEMENT,
    outcomeMessage,
    readCapabilityStatement,
    receiptIdOf,
    searchRegister,
    translateCode,
} from '@/lib/api'
import { authSnapshot, basicAuthorization, bearerAuthorization, signIn, signOut, storedAuthorization } from '@/lib/auth'

/**
 * The wire layer, tested against a stubbed `fetch`.
 *
 * The guard is the interesting half. `d2w fhir serve --ui` mounts the SPA at "/"
 * behind every FHIR route, so an unguarded path does not 404 - it returns the
 * HTML shell with a 200. These tests are what keeps that failure impossible.
 */

const originalFetch = globalThis.fetch

beforeEach(() => {
    sessionStorage.clear()
    signOut()
})

afterEach(() => {
    globalThis.fetch = originalFetch
    configureApi({ baseUrl: '', token: null })
    sessionStorage.clear()
    signOut()
    vi.restoreAllMocks()
})

/** Stub `fetch`, recording the URL and init every call was made with. */
function stubFetch(response: Response): { calls: { url: string; init: RequestInit }[] } {
    const calls: { url: string; init: RequestInit }[] = []
    globalThis.fetch = ((url: string, init: RequestInit = {}) => {
        calls.push({ url, init })
        return Promise.resolve(response)
    }) as unknown as typeof fetch
    return { calls }
}

/** A FHIR JSON response with the given status and body. */
function fhirResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/fhir+json' },
    })
}

describe('the guarded-path pattern', () => {
    it('admits every path the server mounts ahead of the UI', () => {
        const served = [
            '/metadata',
            '/Questionnaire',
            '/Questionnaire?_id=BfMAe6Itzgt',
            '/Questionnaire/BfMAe6Itzgt',
            '/Questionnaire/BfMAe6Itzgt/$generate',
            '/Questionnaire/BfMAe6Itzgt/$generate?seed=7',
            '/QuestionnaireResponse',
            '/QuestionnaireResponse/receipt-1',
            '/CodeSystem',
            '/CodeSystem/d2-de-cs',
            '/ValueSet',
            '/ConceptMap',
            '/ConceptMap/d2-os-OsSymptom01-cm',
            '/ConceptMap/$translate?code=x',
            '/Location/ImspTQPwCqd',
            '/Organization',
            // The ones a live process answers from the DHIS2 instance rather than from its store.
            '/Patient?identifier=12345678',
            '/Patient/TeiPerson01',
            '/Specimen?identifier=LAB-0001',
            '/Specimen/TeiSample01',
            '/tracked-entities/TeiPerson01/enrollments',
        ]
        for (const path of served) {
            expect(GUARDED_PATH_PATTERN.test(path), path).toBe(true)
        }
    })

    it('refuses anything the server does not serve', () => {
        const unserved = [
            '/',
            '/index.html',
            '/assets/index-abc123.js',
            '/api/dataValueSets',
            '/fhir/Questionnaire',
            '/metadataX',
            'Questionnaire',
            'https://elsewhere.example/Questionnaire',
        ]
        for (const path of unserved) {
            expect(GUARDED_PATH_PATTERN.test(path), path).toBe(false)
        }
    })

    it('guards a resource type by its shape, since the register serves as many as the guide names', () => {
        // Which resource types the register answers is what the published map says, so the guard
        // recognises the spelling rather than a list this bundle could never keep current. A type
        // this server does not serve is refused by the server, in its own words.
        expect(GUARDED_PATH_PATTERN.test('/Specimen?identifier=LAB-0001')).toBe(true)
        expect(GUARDED_PATH_PATTERN.test('/QuestionnaireResponse/receipt-1')).toBe(true)
        expect(GUARDED_PATH_PATTERN.test('/Group')).toBe(true)
        // Not a resource type: lowercase is how this server spells everything the UI is served from.
        expect(GUARDED_PATH_PATTERN.test('/assets/index-abc123.js')).toBe(false)
        expect(GUARDED_PATH_PATTERN.test('/Questionnaire9')).toBe(false)
    })
})

describe('apiFetch', () => {
    it('refuses an unguarded path before it reaches the network', async () => {
        const { calls } = stubFetch(fhirResponse({}))
        await expect(apiFetch('/api/dataValueSets')).rejects.toBeInstanceOf(UnguardedPathError)
        expect(calls).toHaveLength(0)
    })

    it('asks for FHIR JSON and sends no credentials by default', async () => {
        const { calls } = stubFetch(fhirResponse({}))
        await apiFetch('/metadata')
        expect(calls[0].url).toBe('/metadata')
        const headers = new Headers(calls[0].init.headers)
        expect(headers.get('Accept')).toBe('application/fhir+json')
        expect(headers.has('Authorization')).toBe(false)
    })

    it('leaves an explicit Accept alone', async () => {
        const { calls } = stubFetch(fhirResponse({}))
        await apiFetch('/metadata', { headers: { Accept: 'application/json' } })
        expect(new Headers(calls[0].init.headers).get('Accept')).toBe('application/json')
    })

    it('signs with what this tab holds, and drops it the moment the server refuses it', async () => {
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        const { calls } = stubFetch(fhirResponse({ resourceType: 'OperationOutcome' }, 401))

        await apiFetch('/QuestionnaireResponse', { method: 'POST' })

        expect(new Headers(calls[0].init.headers).get('Authorization')).toBe(basicAuthorization('clerk', 'secret'))
        expect(storedAuthorization()).toBeNull()
        expect(authSnapshot().refused).toBe(true)
    })

    it('leaves a request that succeeds signed in, so nothing is dropped for a 200', async () => {
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        stubFetch(fhirResponse({}))

        await apiFetch('/metadata')

        expect(storedAuthorization()).toBe(basicAuthorization('clerk', 'secret'))
    })
})

describe('checkCredential', () => {
    it('asks who a credential belongs to, signing with that credential and not with this tabs', async () => {
        signIn(bearerAuthorization('an-old-token'), null)
        const { calls } = stubFetch(fhirResponse({ posture: 'dhis2', username: 'clerk', name: 'clerk' }))

        const checked = await checkCredential(basicAuthorization('clerk', 'secret'))

        expect(calls[0].url).toBe('/whoami')
        expect(new Headers(calls[0].init.headers).get('Authorization')).toBe(basicAuthorization('clerk', 'secret'))
        expect(checked).toEqual({ outcome: 'accepted', username: 'clerk' })
    })

    it('answers with the username the server named, never with what was typed', async () => {
        stubFetch(fhirResponse({ posture: 'dhis2', username: 'Clerk', name: 'Clerk' }))

        expect(await checkCredential(basicAuthorization('clerk', 'secret'))).toEqual({
            outcome: 'accepted',
            username: 'Clerk',
        })
    })

    it('names nobody where the server names nobody, which is the token posture', async () => {
        stubFetch(fhirResponse({ posture: 'token', username: null, name: 'the bearer of a token' }))

        expect(await checkCredential(bearerAuthorization('a-token'))).toEqual({ outcome: 'accepted', username: null })
    })

    it('reads a 401 as a refusal', async () => {
        stubFetch(fhirResponse({ resourceType: 'OperationOutcome' }, 401))

        expect(await checkCredential(basicAuthorization('clerk', 'wrong'))).toEqual({ outcome: 'refused' })
    })

    it('leaves the session this tab already holds alone, because the panel is asking about another', async () => {
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        stubFetch(fhirResponse({ resourceType: 'OperationOutcome' }, 401))

        await checkCredential(basicAuthorization('someone', 'else'))

        expect(storedAuthorization()).toBe(basicAuthorization('clerk', 'secret'))
        expect(authSnapshot().refused).toBe(false)
    })

    it('reads a dead socket as unreachable, which is not the same as a refusal', async () => {
        globalThis.fetch = (() => Promise.reject(new TypeError('failed to fetch'))) as unknown as typeof fetch

        expect(await checkCredential(basicAuthorization('clerk', 'secret'))).toEqual({ outcome: 'unreachable' })
    })

    it('reads anything that is neither 200 nor 401 as unreachable, since it says nothing about the credential', async () => {
        stubFetch(fhirResponse({}, 502))

        expect(await checkCredential(basicAuthorization('clerk', 'secret'))).toEqual({ outcome: 'unreachable' })
    })
})

describe('translateCode', () => {
    it('asks the type-level operation, spelling the target parameter R4s way', async () => {
        const { calls } = stubFetch(fhirResponse({ resourceType: 'Parameters' }))
        await translateCode(
            'http://localhost:8080/fhir/CodeSystem/d2-os-OsSymptom01-cs',
            'OpFever0001',
            'http://dhis2.org/fhir/id/option-code',
        )
        // Lower-case `targetsystem` is what R4 defines; the server reads both, but
        // what leaves this UI is the spelling in the specification.
        expect(calls[0].url).toBe(
            '/ConceptMap/$translate?system=http%3A%2F%2Flocalhost%3A8080%2Ffhir%2FCodeSystem%2Fd2-os-OsSymptom01-cs&code=OpFever0001&targetsystem=http%3A%2F%2Fdhis2.org%2Ffhir%2Fid%2Foption-code',
        )
    })

    it('leaves the target system off when none is asked for', async () => {
        const { calls } = stubFetch(fhirResponse({ resourceType: 'Parameters' }))
        await translateCode('http://x/CodeSystem/y', 'CODE')
        expect(calls[0].url).toBe('/ConceptMap/$translate?system=http%3A%2F%2Fx%2FCodeSystem%2Fy&code=CODE')
    })

    it('raises the OperationOutcome when the call itself is refused', async () => {
        stubFetch(
            fhirResponse(
                {
                    resourceType: 'OperationOutcome',
                    issue: [
                        {
                            severity: 'error',
                            code: 'invalid',
                            diagnostics: '`$translate` needs a `code` parameter',
                        },
                    ],
                },
                400,
            ),
        )
        await expect(translateCode('http://x/CodeSystem/y', 'CODE')).rejects.toThrow('needs a `code`')
    })
})

describe('configureApi', () => {
    it('defaults to same-origin with no token', () => {
        expect(apiConfiguration()).toEqual({ baseUrl: '', token: null })
    })

    it('prefixes the base url and strips its trailing slash', async () => {
        const { calls } = stubFetch(fhirResponse({}))
        configureApi({ baseUrl: 'http://127.0.0.1:8080/' })
        await apiFetch('/Questionnaire')
        expect(calls[0].url).toBe('http://127.0.0.1:8080/Questionnaire')
    })

    it('attaches a bearer token once one is configured', async () => {
        const { calls } = stubFetch(fhirResponse({}))
        configureApi({ token: 'secret-token' })
        await apiFetch('/metadata')
        expect(new Headers(calls[0].init.headers).get('Authorization')).toBe('Bearer secret-token')
    })

    it('leaves the token alone when only the base url is given', () => {
        configureApi({ token: 'secret-token' })
        configureApi({ baseUrl: 'http://elsewhere.test' })
        expect(apiConfiguration().token).toBe('secret-token')
    })

    it('clears the token when one is explicitly nulled', () => {
        configureApi({ token: 'secret-token' })
        configureApi({ token: null })
        expect(apiConfiguration().token).toBeNull()
    })
})

describe('checkReachability', () => {
    it('probes /metadata and reports ok when the server answers', async () => {
        const { calls } = stubFetch(fhirResponse({ resourceType: 'CapabilityStatement' }))
        await expect(checkReachability()).resolves.toBe('ok')
        expect(calls[0].url).toBe('/metadata')
        expect(calls[0].init.cache).toBe('no-store')
    })

    it('reports unreachable when the socket is dead', async () => {
        globalThis.fetch = (() => Promise.reject(new TypeError('fetch failed'))) as unknown as typeof fetch
        await expect(checkReachability()).resolves.toBe('unreachable')
    })

    it('reports unreachable when something answers that is not the facade', async () => {
        stubFetch(new Response('<!doctype html>', { status: 502 }))
        await expect(checkReachability()).resolves.toBe('unreachable')
    })
})

describe('readCapabilityStatement', () => {
    it('answers the document when /metadata serves one', async () => {
        stubFetch(fhirResponse({ resourceType: 'CapabilityStatement', status: 'active', kind: 'instance' }))
        await expect(readCapabilityStatement()).resolves.toMatchObject({
            resourceType: 'CapabilityStatement',
        })
    })

    it('refuses a 200 that is some other resource, rather than casting it into one', async () => {
        // A cast here rendered the Server page as a card of dashes and an empty table, under a
        // header saying "Connected" - a hollow page explaining itself with a cause that cannot be
        // true. A raise puts it in the state the page already has words for.
        stubFetch(fhirResponse({ resourceType: 'Basic' }))
        await expect(readCapabilityStatement()).rejects.toThrow(NOT_A_CAPABILITY_STATEMENT)
    })

    it('refuses a body that is not a resource at all', async () => {
        stubFetch(fhirResponse(['not', 'a', 'document']))
        await expect(readCapabilityStatement()).rejects.toThrow(NOT_A_CAPABILITY_STATEMENT)
    })

    it('raises what the server said when /metadata is turned down', async () => {
        stubFetch(
            fhirResponse(
                {
                    resourceType: 'OperationOutcome',
                    issue: [{ severity: 'error', code: 'security', diagnostics: 'this read needs a token' }],
                },
                401,
            ),
        )
        await expect(readCapabilityStatement()).rejects.toThrow('this read needs a token')
    })
})

describe('outcomeMessage', () => {
    it('reads the diagnostics off the first issue', () => {
        // Verbatim from tests/golden/outcome-answers-refused.json.
        const outcome = {
            resourceType: 'OperationOutcome' as const,
            issue: [
                {
                    severity: 'error' as const,
                    code: 'structure',
                    diagnostics:
                        '`GQY2lXrypjO` answers as `decimal`, so it carries `valueDecimal`, not `valueString`',
                },
            ],
        }
        expect(outcomeMessage(outcome)).toContain('valueDecimal')
    })

    it('falls back to severity and code when an issue carries no prose', () => {
        expect(
            outcomeMessage({
                resourceType: 'OperationOutcome',
                issue: [{ severity: 'error', code: 'not-found' }],
            }),
        ).toBe('error: not-found')
    })

    it('answers null for no outcome at all', () => {
        expect(outcomeMessage(null)).toBeNull()
    })
})

/**
 * Narrowing a register to one of the tracked entity types it is served over.
 *
 * `_tag` is R4's own token search over `meta.tag`, which is where a served register resource already
 * states its DHIS2 tracked entity type. It has to ride BOTH reads: the listing and the search answer
 * about the same register, and a search that ignored the narrowing would answer about entities the
 * table beneath it is not showing.
 */
describe('a register narrowed to one tracked entity type', () => {
    const emptyBundle = { resourceType: 'Bundle', type: 'searchset', entry: [] }

    it('tags the listing, and keeps the tag on the page the walk moves to', async () => {
        const { calls } = stubFetch(fhirResponse(emptyBundle))
        await listRegister('Device', null, 25, 'TetFridge01')
        await listRegister('Device', 'a-token-the-server-minted', 25, 'TetFridge01')

        expect(calls[0].url).toBe('/Device?_count=25&_tag=TetFridge01')
        // The token names a place inside a scope, so a `next` sent without the tag would step out of
        // the type the walk started in.
        expect(calls[1].url).toBe('/Device?_count=25&_tag=TetFridge01&page=a-token-the-server-minted')
    })

    it('tags the search under whichever key this server declared for the register', async () => {
        const { calls } = stubFetch(fhirResponse(emptyBundle))
        await searchRegister('Device', 'FR-2026-11', 'identifier', 'TetFridge01')
        await searchRegister('Device', 'fridge', '_content', 'TetFridge01')

        expect(calls[0].url).toBe('/Device?identifier=FR-2026-11&_tag=TetFridge01')
        expect(calls[1].url).toBe('/Device?_content=fridge&_tag=TetFridge01')
    })

    it('sends no tag at all when nothing narrowed the register', async () => {
        const { calls } = stubFetch(fhirResponse(emptyBundle))
        await listRegister('Patient', null, 25)
        await searchRegister('Patient', '19850312-4471')

        expect(calls[0].url).toBe('/Patient?_count=25')
        expect(calls[1].url).toBe('/Patient?identifier=19850312-4471')
    })
})

/**
 * Where an accepted capture says its receipt is served from.
 *
 * The 201 body is an OperationOutcome, so the id is only ever in the `Location` header - and the
 * toast that names the receipt is only honest while this reads that header the way R4 writes it.
 */
describe('the receipt id a create interaction states', () => {
    it('takes the last path segment of the Location the server stated', () => {
        expect(receiptIdOf('http://127.0.0.1:8000/QuestionnaireResponse/9be51a978d8d4ba98635ea4c817c6caa')).toBe(
            '9be51a978d8d4ba98635ea4c817c6caa',
        )
    })

    it('reads a relative Location the same way', () => {
        expect(receiptIdOf('/QuestionnaireResponse/abc123')).toBe('abc123')
    })

    it('ignores a query or fragment riding after the id', () => {
        expect(receiptIdOf('/QuestionnaireResponse/abc123?_format=json')).toBe('abc123')
    })

    it('says nothing where the server stated no Location at all', () => {
        expect(receiptIdOf(null)).toBeNull()
        expect(receiptIdOf('')).toBeNull()
    })
})
