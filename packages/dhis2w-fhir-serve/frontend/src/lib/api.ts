/**
 * The one way this UI reaches the network.
 *
 * WHY A CHOKE POINT. Everything here is credentialed and same-origin by default,
 * and the failure mode a capture UI must never have is a request that quietly
 * escapes those defaults - a hard-coded absolute URL in a page component, a
 * fetch that forgets the bearer token, a path typo that 404s into the SPA shell
 * instead of the API. So `apiFetch` is the only function in the app that calls
 * `fetch`, and every typed read below goes through it. A new endpoint cannot be
 * added without passing the guard.
 *
 * WHAT THE GUARD IS. `d2w fhir serve` mounts its FHIR routes at the root - there
 * is no /fhir or /api prefix - and then mounts the built UI at "/" *after* them,
 * so anything the FHIR routers do not claim falls through to the SPA shell. That
 * is exactly the arrangement in which a mistyped path returns 200 text/html and
 * a caller spends an afternoon on "why is my Bundle a string". The guard is the
 * router table of `dhis2w_fhir_serve.routes` written down: /metadata, plus the
 * five read types and QuestionnaireResponse the catch-alls answer for, plus
 * ConceptMap which is not a read type but carries $translate. Anything else is a
 * programming error and is refused here rather than by the server.
 *
 * WHY NO QUERY LIBRARY. There is no react-query, swr, or zustand in this app on
 * purpose. The server answers whole Bundles off a store loaded once at startup,
 * so there is nothing to cache that the server is not already caching, and no
 * invalidation problem to solve. Pages hold their own `useState`; anything that
 * genuinely spans pages (reachability) is a module-level store read through
 * `useSyncExternalStore`.
 */

import type { Bundle, CapabilityStatement, OperationOutcome, QuestionnaireResponse } from '@/lib/fhir'

/** The media type every FHIR request and response on this server carries. */
export const FHIR_JSON_MEDIA_TYPE = 'application/fhir+json'

/**
 * Every path prefix `d2w fhir serve` claims ahead of the UI mount.
 *
 * Kept as a list rather than only a regex so the set is greppable from the
 * Python side: this must stay equal to `/metadata` plus
 * `dhis2w_fhir_serve.routes.read.SERVED_RESOURCE_TYPES` plus ConceptMap. The
 * vite dev-server proxy in vite.config.ts proxies the same list.
 */
export const GUARDED_PATH_SEGMENTS = [
    'metadata',
    'Questionnaire',
    'QuestionnaireResponse',
    'CodeSystem',
    'ValueSet',
    'ConceptMap',
    'Location',
    'Organization',
] as const

/**
 * The guard itself.
 *
 * A path passes when it is exactly one of the segments above, or continues with
 * `/` (a resource id, an operation) or `?` (a search). `QuestionnaireResponse`
 * therefore does not match on the `Questionnaire` alternative, because the regex
 * requires an end, a slash, or a query right after it - which is why the longer
 * name must also be its own alternative rather than relying on prefix order.
 */
export const GUARDED_PATH_PATTERN = new RegExp(`^/(${GUARDED_PATH_SEGMENTS.join('|')})([/?]|$)`)

/** Where the API lives and what it is reached with; both have same-origin defaults. */
export interface ApiConfiguration {
    /** Origin to prefix every path with. '' means same-origin, which is how `--ui` serves. */
    baseUrl: string
    /** Bearer token, when something in front of the server wants one. */
    token: string | null
}

/**
 * The live configuration.
 *
 * Same-origin with no token is not a placeholder - it is the shipped case. The
 * facade has no authentication of its own and binds loopback by default, so the
 * UI it serves reaches it by relative path. `configureApi` exists for the two
 * cases that are not that: a UI running under `pnpm dev` against a server on
 * another port, and a deployment that has put a token-checking proxy in front.
 */
let configuration: ApiConfiguration = { baseUrl: '', token: null }

/** Point the API layer somewhere other than same-origin, or hand it a token. */
export function configureApi(next: Partial<ApiConfiguration>): void {
    configuration = {
        baseUrl: (next.baseUrl ?? configuration.baseUrl).replace(/\/$/, ''),
        token: next.token !== undefined ? next.token : configuration.token,
    }
}

/** What the API layer is currently pointed at. */
export function apiConfiguration(): ApiConfiguration {
    return configuration
}

/** A path that is not part of the served FHIR surface, refused before it reaches the network. */
export class UnguardedPathError extends Error {
    constructor(path: string) {
        super(
            `\`${path}\` is not a path this server serves. ` +
                `Guarded prefixes: ${GUARDED_PATH_SEGMENTS.join(', ')}.`,
        )
        this.name = 'UnguardedPathError'
    }
}

/** A request the server refused, carrying the OperationOutcome it refused with. */
export class FhirRequestError extends Error {
    readonly status: number
    readonly outcome: OperationOutcome | null

    constructor(status: number, outcome: OperationOutcome | null, path: string) {
        super(outcomeMessage(outcome) ?? `${path} failed with HTTP ${status}`)
        this.name = 'FhirRequestError'
        this.status = status
        this.outcome = outcome
    }
}

/** The first diagnostics line of an OperationOutcome, which is how this server states a refusal. */
export function outcomeMessage(outcome: OperationOutcome | null): string | null {
    const issue = outcome?.issue?.[0]
    if (!issue) return null
    return issue.diagnostics ?? issue.details?.text ?? `${issue.severity}: ${issue.code}`
}

/**
 * `fetch` against the served FHIR surface, with the token attached and the path guarded.
 *
 * The Accept header is set here rather than per call, because every route on
 * this server answers `application/fhir+json` - including its errors, which are
 * OperationOutcomes.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
    if (!GUARDED_PATH_PATTERN.test(path)) throw new UnguardedPathError(path)
    const headers = new Headers(init.headers)
    if (!headers.has('Accept')) headers.set('Accept', FHIR_JSON_MEDIA_TYPE)
    if (configuration.token) headers.set('Authorization', `Bearer ${configuration.token}`)
    return fetch(`${configuration.baseUrl}${path}`, { ...init, headers })
}

/**
 * Whether the server is answering at all.
 *
 * `/metadata` is the probe because it is the one path that is always mounted,
 * always cheap (the body is rendered once at startup and served verbatim), and
 * always present whatever the project publishes. Unreachable covers both a dead
 * socket and a server answering something other than a conformance document -
 * from a UI's point of view those are the same state.
 */
export async function checkReachability(): Promise<'ok' | 'unreachable'> {
    try {
        const response = await apiFetch('/metadata', { cache: 'no-store' })
        return response.ok ? 'ok' : 'unreachable'
    } catch {
        return 'unreachable'
    }
}

/** The served IG's conformance document. */
export async function readCapabilityStatement(): Promise<CapabilityStatement> {
    return readJson<CapabilityStatement>('/metadata')
}

/** Search one served resource type, answering with the searchset Bundle verbatim. */
export async function searchResources<T>(
    resourceType: string,
    parameters: Record<string, string> = {},
): Promise<Bundle<T>> {
    const query = new URLSearchParams(parameters).toString()
    return readJson<Bundle<T>>(`/${resourceType}${query ? `?${query}` : ''}`)
}

/** Read one resource by type and id. */
export async function readResource<T>(resourceType: string, resourceId: string): Promise<T> {
    return readJson<T>(`/${resourceType}/${resourceId}`)
}

/**
 * Ask the server to fill one form with synthetic answers.
 *
 * `$generate` is a custom operation of this IG, not SDC's `$populate`: the
 * answers are invented, and the seed that produced them comes back on the
 * response's identifier so the same call reproduces the same bytes. A UI's
 * "fill with test data" button is this one call.
 */
export async function generateResponse(
    questionnaireId: string,
    seed?: number,
): Promise<QuestionnaireResponse> {
    const query = seed === undefined ? '' : `?seed=${seed}`
    return readJson<QuestionnaireResponse>(`/Questionnaire/${questionnaireId}/$generate${query}`)
}

/**
 * Submit one filled-in form.
 *
 * The server answers 201 with the stored receipt, or a 4xx OperationOutcome
 * naming every question it refused - and an accepted capture can still carry
 * warnings, which is why the caller gets the parsed response rather than a
 * boolean.
 */
export async function postQuestionnaireResponse(
    response: QuestionnaireResponse,
): Promise<QuestionnaireResponse> {
    return readJson<QuestionnaireResponse>('/QuestionnaireResponse', {
        method: 'POST',
        headers: { 'Content-Type': FHIR_JSON_MEDIA_TYPE },
        body: JSON.stringify(response),
    })
}

/** One guarded request, parsed, with a refusal raised as the outcome the server sent. */
async function readJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await apiFetch(path, init)
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) {
        throw new FhirRequestError(response.status, body as OperationOutcome | null, path)
    }
    return body as T
}
