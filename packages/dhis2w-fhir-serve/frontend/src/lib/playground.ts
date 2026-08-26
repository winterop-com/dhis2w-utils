/**
 * Everything the Playground knows about a request, as data.
 *
 * ONE REQUEST IS A VALUE, AND THE PAGE IS A RENDERER. A method, a path, a list of query parameters
 * and a body - that is the whole of what the builder holds, what a preset fills it with, what the
 * history remembers, and what the curl command is written from. Keeping it here rather than in the
 * component is what lets the two things that are easy to get subtly wrong - the query string a
 * request is actually sent to, and the curl a reader pastes into a terminal - be asserted on with no
 * browser in scope.
 *
 * THE CURL NAMES THE CREDENTIAL AND NEVER CARRIES IT. A playground that printed the value of the
 * `Authorization` header would put a live credential on the clipboard, into a chat window, and into
 * whatever the reader pastes it beside. So the command states the scheme the header would carry and
 * a placeholder in place of the secret: the reader learns that the header is required and what shape
 * it takes, and the secret stays in the browser that holds it.
 *
 * THE HISTORY IS THIS BROWSER'S AND NOTHING ELSE'S. It lives in `localStorage`, holds the last
 * `HISTORY_LIMIT` requests, and every read and write of it is guarded - a private window, a browser
 * with site data switched off, and a quota that filled up are all states in which the page still has
 * to work, with no history rather than with an exception.
 */

import { FHIR_JSON_MEDIA_TYPE } from '@/lib/api'
import { declaredOperations, type CapabilityStatement } from '@/lib/fhir'

/** The two methods this facade answers, which is what the picker offers and nothing more. */
export const PLAYGROUND_METHODS = ['GET', 'POST'] as const

/** One of the two methods a request can carry. */
export type PlaygroundMethod = (typeof PLAYGROUND_METHODS)[number]

/** One key and value of the query string, as the editor holds a row of it. */
export interface QueryParameter {
    name: string
    value: string
}

/** One request as the builder holds it: everything that decides what goes on the wire. */
export interface PlaygroundRequest {
    method: PlaygroundMethod
    /** The path relative to the service base, which is this page's own origin. May carry a query. */
    path: string
    /** The rows of the query editor, appended to whatever query the path already carries. */
    parameters: QueryParameter[]
    /** The JSON body, for a POST. Ignored under GET, which this facade answers with no body at all. */
    body: string
}

/** What the builder opens with: the one read every other page starts from. */
export const OPENING_REQUEST: PlaygroundRequest = {
    method: 'GET',
    path: '/metadata',
    parameters: [],
    body: '',
}

/** An empty row, which is what the editor adds when somebody asks for another parameter. */
export function emptyParameter(): QueryParameter {
    return { name: '', value: '' }
}

/**
 * The path and query one request is actually sent to.
 *
 * The rows are appended to the query the path already carries rather than replacing it, because both
 * are things the reader typed: a path pasted whole out of a log line arrives with its query on it,
 * and a row added afterwards is a second parameter rather than a correction of the first. A row with
 * no name is not a parameter yet and is left out, so an empty row waiting to be filled in never
 * changes what would be sent.
 */
export function requestTarget(request: PlaygroundRequest): string {
    const typed = request.path.trim()
    const split = typed.indexOf('?')
    const path = split === -1 ? typed : typed.slice(0, split)
    const query = new URLSearchParams(split === -1 ? '' : typed.slice(split + 1))
    for (const parameter of request.parameters) {
        const name = parameter.name.trim()
        if (name !== '') query.append(name, parameter.value)
    }
    const serialized = query.toString()
    const rooted = path.startsWith('/') ? path : `/${path}`
    return serialized === '' ? rooted : `${rooted}?${serialized}`
}

/** How FHIR asks for JSON in the address bar, which is how a browser tab gets the answer this page got. */
export const FORMAT_PARAMETER = '_format'
export const JSON_FORMAT = 'json'

/**
 * The whole address one GET can be opened at, with the format asked for in the URL.
 *
 * A browser navigating to a FHIR path sends whatever `Accept` header it likes, and this server
 * answers `application/fhir+json` to all of it - but `_format=json` is what a caller states in the
 * address when the header is not theirs to set, and a link that omitted it would be teaching the
 * shorter thing rather than the true one. A path that already names a format keeps the one it names.
 */
export function formatHref(origin: string, request: PlaygroundRequest): string {
    const target = requestTarget(request)
    const split = target.indexOf('?')
    const path = split === -1 ? target : target.slice(0, split)
    const query = new URLSearchParams(split === -1 ? '' : target.slice(split + 1))
    if (!query.has(FORMAT_PARAMETER)) query.set(FORMAT_PARAMETER, JSON_FORMAT)
    return `${origin}${path}?${query.toString()}`
}

/** What stands in the copied command where the credential would be - see this module's own note. */
export const AUTHORIZATION_PLACEHOLDER = '<your credential>'

/**
 * The scheme one stored `Authorization` value signs with, or null when this browser holds none.
 *
 * The first word and nothing after it: `Basic` under the DHIS2 posture, `Bearer` under the two token
 * ones. That word is the part a caller has to reproduce; the rest is the secret.
 */
export function authorizationScheme(authorization: string | null): string | null {
    if (authorization === null) return null
    const scheme = authorization.trim().split(/\s+/)[0]
    return scheme === '' ? null : scheme
}

/**
 * The current request as a command that runs in a terminal.
 *
 * SINGLE QUOTES THROUGHOUT, because everything quoted here is a thing a reader typed: a URL with an
 * ampersand in it, a JSON body full of double quotes, a FHIRPath expression carrying its own single
 * quotes. One quoting rule that survives all three is worth more than a shorter command that breaks
 * on the first search parameter. A single quote inside the text is closed, escaped, and reopened,
 * which is the only way a POSIX shell lets one through.
 */
export function curlCommand(
    origin: string,
    request: PlaygroundRequest,
    /** The scheme this browser would sign with, or null when it signs with nothing. */
    scheme: string | null,
): string {
    const lines = [
        `curl${request.method === 'POST' ? ' -X POST' : ''} ${shellQuoted(`${origin}${requestTarget(request)}`)}`,
        `  -H ${shellQuoted(`Accept: ${FHIR_JSON_MEDIA_TYPE}`)}`,
    ]
    if (request.method === 'POST') lines.push(`  -H ${shellQuoted(`Content-Type: ${FHIR_JSON_MEDIA_TYPE}`)}`)
    if (scheme !== null) {
        lines.push(`  -H ${shellQuoted(`Authorization: ${scheme} ${AUTHORIZATION_PLACEHOLDER}`)}`)
    }
    if (request.method === 'POST' && request.body.trim() !== '') {
        lines.push(`  -d ${shellQuoted(request.body)}`)
    }
    return lines.join(' \\\n')
}

/** One string as a POSIX shell reads it literally, quotes inside it included. */
function shellQuoted(value: string): string {
    return `'${value.replaceAll("'", String.raw`'\''`)}'`
}

/** One request this browser sent, and what came back of it. */
export interface SentRequest {
    /** The request itself, so choosing the row puts the body and the parameters back too. */
    request: PlaygroundRequest
    /** The status the server answered with, or null when nothing answered at all. */
    status: number | null
}

/** How many sent requests are kept. Enough to find this morning's, short enough to read at a glance. */
export const HISTORY_LIMIT = 20

/** Where the sent requests are kept - this browser's own storage, and nowhere on the server. */
export const HISTORY_STORAGE_KEY = 'playground-history'

/** What this browser has sent, newest first, or nothing at all when storage is blocked or empty. */
export function readHistory(): SentRequest[] {
    try {
        const kept: unknown = JSON.parse(window.localStorage.getItem(HISTORY_STORAGE_KEY) ?? '[]')
        if (!Array.isArray(kept)) return []
        return kept.filter(isSentRequest).slice(0, HISTORY_LIMIT)
    } catch {
        return []
    }
}

/** Remember one sent request, newest first, dropping whatever falls off the end. */
export function rememberSent(history: SentRequest[], sent: SentRequest): SentRequest[] {
    const next = [sent, ...history].slice(0, HISTORY_LIMIT)
    try {
        window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next))
    } catch {
        // A private window forgets; the list still holds for as long as the page is open.
    }
    return next
}

/**
 * Whether one parsed entry is a request this page can put back in the builder.
 *
 * Checked rather than cast: what comes out of storage was written by some version of this page and
 * is read by this one, and an entry missing its method would refill the builder with `undefined`
 * showing in the picker. A row that does not check out is dropped and the rest of the list stands.
 */
function isSentRequest(entry: unknown): entry is SentRequest {
    if (typeof entry !== 'object' || entry === null) return false
    const candidate = entry as { request?: unknown; status?: unknown }
    if (typeof candidate.request !== 'object' || candidate.request === null) return false
    const request = candidate.request as { method?: unknown; path?: unknown; parameters?: unknown; body?: unknown }
    return (
        (request.method === 'GET' || request.method === 'POST') &&
        typeof request.path === 'string' &&
        Array.isArray(request.parameters) &&
        typeof request.body === 'string' &&
        (candidate.status === null || typeof candidate.status === 'number')
    )
}

/** One request the panel offers, ready to be put in the builder. */
export interface PlaygroundPreset {
    /** Stable across rebuilds of the list, so the panel can key on it. */
    id: string
    /** The shelf it sits on. Presets keep the order they are built in. */
    group: string
    /** The method and path, in the machine spelling - this is a list of addresses, so it reads as one. */
    label: string
    /** What the request answers, in one line. */
    hint: string
    request: PlaygroundRequest
    /**
     * True when the request answers as it stands, false when a placeholder has to be filled in first.
     *
     * A preset that carries a placeholder is still worth offering - it is the shape of the address,
     * which is the thing a reader cannot guess - but the panel says so under the row rather than
     * letting somebody find out by pressing Send. The label is where the placeholder itself is
     * visible, so the panel states that one has to be replaced and never repeats which.
     */
    runnable: boolean
}

/** The two shelves the presets sit on: what this server can be read, and what it declares. */
export const READS_GROUP = 'Reads'
export const OPERATIONS_GROUP = 'Declared operations'

/**
 * What stands where a value has to be filled in before the request answers.
 *
 * Braces, because that is how every FHIR specification page and every path in this codebase's own
 * prose writes the part of an address the caller supplies - `/{ResourceType}/{id}` is a shape a
 * reader has already met by the time they arrive here.
 */
export const RESOURCE_ID_PLACEHOLDER = '{id}'
export const SYSTEM_PLACEHOLDER = '{system}'
export const CODE_PLACEHOLDER = '{code}'

/**
 * What this particular server was found to hold, which is what turns three presets from a shape into
 * a request that answers.
 *
 * The read-by-id address, `$generate` and `$translate` all name something the guide published, and
 * none of the three can be guessed from the conformance document alone - it declares that the
 * operations exist, not which resources they would answer over. So the page reads one of each and
 * hands them here. Null is the ordinary case for a guide that publishes neither, and the presets
 * are then offered as the templates they are.
 */
export interface ServerSamples {
    /** One Questionnaire this server holds, for the read and `$generate` presets. */
    questionnaireId: string | null
    /** One concept the published maps take somewhere, for the `$translate` preset. */
    concept: { system: string; code: string } | null
}

/** The samples before anything has been read - every preset a template, which is what a first paint shows. */
export const NO_SAMPLES: ServerSamples = { questionnaireId: null, concept: null }

/**
 * The body the `$evaluate` preset posts.
 *
 * The Evaluate screen's own first example, as a request: one FHIRPath expression over one Patient
 * carried in the body. It answers against any served guide, including one that publishes nothing,
 * because the resource it runs over travels with it - which is exactly the property that makes it
 * the right preset for a screen a reader meets this server through.
 */
export const EVALUATE_EXAMPLE_BODY = JSON.stringify(
    {
        language: 'fhirpath',
        source: 'Patient.name.given',
        context: {
            kind: 'inline',
            resource: {
                resourceType: 'Patient',
                id: 'example',
                name: [{ given: ['Ada', 'Byron'], family: 'Lovelace' }],
            },
        },
    },
    null,
    2,
)

/** How many rows a search preset asks for - a page short enough to read, long enough to be a listing. */
const PRESET_SEARCH_COUNT = '5'

/**
 * Every preset this server's own conformance document earns.
 *
 * THE LIST IS THE DOCUMENT, READ BACK AS ADDRESSES. `/metadata` first, because it is what every
 * other row here was derived from and the one read that answers on every run; then one search per
 * type the statement says answers a `search-type` interaction; then the read address, which is the
 * one shape a search result does not teach; then one row per declared operation. A guide that
 * publishes no ConceptMaps declares no `$translate` and is offered none - the panel states what this
 * server does rather than what a DHIS2 capture server generally can.
 */
export function playgroundPresets(
    capability: CapabilityStatement | null,
    samples: ServerSamples,
): PlaygroundPreset[] {
    const resources = capability?.rest?.[0]?.resource ?? []
    const searchable = resources.filter(
        (resource) => resource.interaction?.some((interaction) => interaction.code === 'search-type') === true,
    )
    const questionnaire = samples.questionnaireId ?? RESOURCE_ID_PLACEHOLDER
    return [
        {
            id: 'read:metadata',
            group: READS_GROUP,
            label: 'GET /metadata',
            hint: 'The conformance document every row on this panel was built from.',
            request: { method: 'GET', path: '/metadata', parameters: [], body: '' },
            runnable: true,
        },
        ...searchable.map((resource) => ({
            id: `search:${resource.type}`,
            group: READS_GROUP,
            label: `GET /${resource.type}`,
            hint: `A searchset Bundle of the ${resource.type} resources this server answers for.`,
            request: {
                method: 'GET' as const,
                path: `/${resource.type}`,
                parameters: [{ name: '_count', value: PRESET_SEARCH_COUNT }],
                body: '',
            },
            runnable: true,
        })),
        {
            id: 'read:by-id',
            group: READS_GROUP,
            label: `GET /Questionnaire/${questionnaire}`,
            hint: 'One resource of this guide, read by type and id.',
            request: { method: 'GET', path: `/Questionnaire/${questionnaire}`, parameters: [], body: '' },
            runnable: samples.questionnaireId !== null,
        },
        ...declaredOperations(capability).map((operation) =>
            operationPreset(operation.name, operation.on, operation.documentation, samples),
        ),
    ]
}

/**
 * One declared operation as an address a reader can send.
 *
 * The three this server declares are known by name here, because each has a different shape - a
 * system-level POST carrying its own body, a type-level GET taking two parameters, an instance-level
 * GET hanging off one resource - and none of those can be derived from the name in the statement.
 * An operation this file has never heard of still gets a row: FHIR says where an operation is
 * answered from what it is declared on, so the address is known even when nothing else about it is,
 * and the row says it has to be filled in.
 */
function operationPreset(
    name: string,
    /** The resource type the operation hangs off, or null for one the service base answers. */
    on: string | null,
    documentation: string | undefined,
    samples: ServerSamples,
): PlaygroundPreset {
    if (name === 'evaluate' && on === null) {
        return {
            id: 'operation:evaluate',
            group: OPERATIONS_GROUP,
            label: 'POST /$evaluate',
            hint: 'Runs one FHIRPath expression over the Patient carried in the body, and answers a Parameters resource.',
            request: { method: 'POST', path: '/$evaluate', parameters: [], body: EVALUATE_EXAMPLE_BODY },
            runnable: true,
        }
    }
    if (name === 'generate' && on !== null) {
        const questionnaire = samples.questionnaireId ?? RESOURCE_ID_PLACEHOLDER
        return {
            id: 'operation:generate',
            group: OPERATIONS_GROUP,
            label: `GET /${on}/${questionnaire}/$generate`,
            hint: 'A synthetic response against one published form, reproducible from the seed.',
            request: {
                method: 'GET',
                path: `/${on}/${questionnaire}/$generate`,
                parameters: [{ name: 'seed', value: '1' }],
                body: '',
            },
            runnable: samples.questionnaireId !== null,
        }
    }
    if (name === 'translate' && on !== null) {
        const concept = samples.concept
        return {
            id: 'operation:translate',
            group: OPERATIONS_GROUP,
            label: `GET /${on}/$translate`,
            hint: 'What the published maps take one concept of this guide to.',
            request: {
                method: 'GET',
                path: `/${on}/$translate`,
                parameters: [
                    { name: 'system', value: concept?.system ?? SYSTEM_PLACEHOLDER },
                    { name: 'code', value: concept?.code ?? CODE_PLACEHOLDER },
                ],
                body: '',
            },
            runnable: concept !== null,
        }
    }
    const path = on === null ? `/$${name}` : `/${on}/$${name}`
    return {
        id: `operation:${on ?? 'base'}:${name}`,
        group: OPERATIONS_GROUP,
        label: `GET ${path}`,
        hint: documentation ?? 'An operation this server declares. Name its parameters below before sending.',
        request: { method: 'GET', path, parameters: [], body: '' },
        runnable: false,
    }
}

/** The presets shelved, keeping the order they were built in. */
export function presetShelves(presets: PlaygroundPreset[]): { group: string; presets: PlaygroundPreset[] }[] {
    const shelves: { group: string; presets: PlaygroundPreset[] }[] = []
    for (const preset of presets) {
        const shelf = shelves.find((candidate) => candidate.group === preset.group)
        if (shelf === undefined) shelves.push({ group: preset.group, presets: [preset] })
        else shelf.presets.push(preset)
    }
    return shelves
}

/**
 * One body pretty-printed, or the bytes as they arrived when they are not JSON.
 *
 * Everything this server answers is JSON, its refusals included - but a proxy in front of it, a
 * captive portal, or a path that fell through to the SPA shell answers HTML, and a reader chasing
 * that needs to see what actually came back rather than a parse error standing in for it.
 */
export function prettyBody(body: string): string {
    try {
        return JSON.stringify(JSON.parse(body), null, 2)
    } catch {
        return body
    }
}
