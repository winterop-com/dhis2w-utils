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
 * router table of `dhis2w_fhir_serve.routes` written down: /metadata and /spool,
 * plus the seven read types and QuestionnaireResponse the catch-alls answer for -
 * ConceptMap being both a read type and the one the type-level $translate hangs
 * off. Anything else is a programming error and is refused here rather than by
 * the server.
 *
 * TWO OF THE GUARDED PREFIXES ANSWER FROM DHIS2 RATHER THAN FROM THE STORE.
 * The register's own resource types and `/tracked-entities/{uid}/enrollments`
 * are mounted only by a live process, and a compiled one refuses both by saying
 * so - which is a refusal a caller reads and renders, not a path that escaped
 * the guard. Everything else on this surface is answered from a store loaded
 * once at startup.
 *
 * THREE PATHS HERE ARE NOT FHIR. `/spool` answers plain JSON, not
 * `application/fhir+json`: it serves the receipt *envelopes* - when the facade
 * accepted each submission, which of its three lifecycle directories the file
 * now sits in, and what DHIS2 said when it refused one - and none of those are
 * QuestionnaireResponse elements. `/uiconfig` is the second, and answers the
 * handful of run-time settings this UI has to act on - today the map's tile
 * template, which is a property of how the process was started rather than of
 * anything the guide published. `/tracked-entities/{uid}/enrollments` is the third, and
 * lowercase for the same reason `/spool` is: whether a DHIS2 enrollment is an
 * `EpisodeOfCare` or a `CarePlan` is an open decision, and answering a picker's
 * feed as a FHIR resource would settle it by accident.
 * `dhis2w_fhir_serve.routes.spool` argues the shape in full, and
 * `routes.uiconfig` and `routes.enrollments` inherit it. All three still go
 * through this guard, because the reason for the guard is the SPA fallback, and
 * that applies to every path alike.
 *
 * WHY NO QUERY LIBRARY. There is no react-query, swr, or zustand in this app on
 * purpose. The server answers whole Bundles off a store loaded once at startup,
 * so there is nothing to cache that the server is not already caching, and no
 * invalidation problem to solve. Pages hold their own `useState`; anything that
 * genuinely spans pages (reachability) is a module-level store read through
 * `useSyncExternalStore`.
 */

import {
    PATIENT_IDENTIFIER_SEARCH_PARAMETER,
    type Bundle,
    type CapabilityStatement,
    type OperationOutcome,
    type Parameters,
    type Patient,
    type QuestionnaireResponse,
} from '@/lib/fhir'
import { PATIENT_COUNT_PARAMETER, PATIENT_PAGE_PARAMETER, type PatientEnrollments } from '@/lib/patients'
import type { SpoolListing } from '@/lib/spool'
import type { UiConfig } from '@/lib/uiconfig'

/** The media type every FHIR request and response on this server carries. */
export const FHIR_JSON_MEDIA_TYPE = 'application/fhir+json'

/**
 * Every lowercase path `d2w fhir serve` claims ahead of the UI mount.
 *
 * Kept as a list rather than only a regex so the set is greppable from the
 * Python side: this must stay equal to `/metadata`, `/spool`, `/uiconfig`, and
 * the `/tracked-entities/{uid}/enrollments` listing. The vite dev-server proxy
 * in vite.config.ts proxies the same list.
 *
 * The FHIR resource types are not in it, and cannot be. The read catch-all
 * answers `/{ResourceType}` for the types the store holds, and the register
 * answers it for every resource the published `D2TET_CM` names - which is a
 * property of the guide this server loaded rather than of this bundle. So the
 * guard recognises the *shape* of a resource type instead of enumerating them,
 * and a type this server does not serve comes back as its own OperationOutcome
 * saying so, which is a better answer than a client-side refusal guessing.
 */
export const GUARDED_PATH_SEGMENTS = ['metadata', 'spool', 'uiconfig', 'tracked-entities'] as const

/** How FHIR spells a resource type: an initial capital, then letters, and nothing else. */
export const RESOURCE_TYPE_PATTERN_SOURCE = '[A-Z][A-Za-z]*'

/**
 * The guard itself.
 *
 * A path passes when it is exactly one of the fixed segments or a FHIR resource
 * type, or continues with `/` (a resource id, an operation) or `?` (a search).
 * Everything the UI is served from - `/`, `/index.html`, `/assets/...` - is
 * lowercase and unlisted, which is what the guard is for: a request that would
 * otherwise be answered with the shell instead of with JSON.
 */
export const GUARDED_PATH_PATTERN = new RegExp(
    `^/(${[...GUARDED_PATH_SEGMENTS, RESOURCE_TYPE_PATTERN_SOURCE].join('|')})([/?]|$)`,
)

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
 * Ask what the published maps take one concept to.
 *
 * The type-level `$translate`, which is the only terminology operation this
 * server answers - there is no `$expand` and no `$lookup`. `targetSystem` is
 * optional and selects one group of the maps instead of all of them; R4 spells
 * the parameter `targetsystem`, all lower case, which is what goes on the wire.
 *
 * A concept the maps say nothing about is not an error: the operation answers
 * 200 with `result` false and a `message` naming what was not found, so the
 * caller reads the Parameters rather than catching.
 */
export async function translateCode(
    system: string,
    code: string,
    targetSystem?: string,
): Promise<Parameters> {
    const parameters = new URLSearchParams({ system, code })
    if (targetSystem !== undefined && targetSystem !== '') parameters.set('targetsystem', targetSystem)
    return readJson<Parameters>(`/ConceptMap/$translate?${parameters.toString()}`)
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

/**
 * Search the DHIS2 instance behind a live facade for the people one identifier value names.
 *
 * The bare-value token form, which names no key: the server tries the tracked entity uid and every
 * attribute DHIS2 declares unique, and folds the matches into one searchset deduplicated by person.
 * That is the right form for a control someone types an identifier into - the person holding the
 * card in front of them does not know which of the instance's attributes it is a value of.
 *
 * A compiled process refuses this with a `not-supported` OperationOutcome, which arrives here as a
 * `FhirRequestError` carrying the server's own words. Callers ask `/metadata` first and never offer
 * the control at all in that case; the refusal is what a race against a restart reads as.
 */
export async function searchRegister(resource: string, identifier: string): Promise<Bundle<Patient>> {
    return searchResources<Patient>(resource, { [PATIENT_IDENTIFIER_SEARCH_PARAMETER]: identifier })
}

/**
 * One page of everyone the DHIS2 instance behind a live facade holds.
 *
 * The same route with no search parameter on it, which is what makes it a listing rather than a
 * lookup. `page` is the token the previous answer's own link carried and is sent back verbatim -
 * this server mints it and this server reads it, and a caller that took it apart would be deciding
 * how the instance is paged. Null asks for the first page, which is the state a browser opens in.
 *
 * A deployment can publish the search and decline the listing, so callers ask `/uiconfig` first and
 * never offer the table at all in that case.
 */
export async function listRegister(
    resource: string,
    pageToken: string | null,
    count: number,
): Promise<Bundle<Patient>> {
    const parameters: Record<string, string> = { [PATIENT_COUNT_PARAMETER]: String(count) }
    if (pageToken !== null) parameters[PATIENT_PAGE_PARAMETER] = pageToken
    return searchResources<Patient>(resource, parameters)
}

/** One tracked entity the DHIS2 instance holds, under the FHIR resource its type is registered as. */
export async function readRegisteredEntity(resource: string, trackedEntityUid: string): Promise<Patient> {
    return readResource<Patient>(resource, trackedEntityUid)
}

/**
 * Which programs one tracked entity is enrolled in, as the picker's feed states it.
 *
 * The path names a tracked entity rather than a patient because DHIS2 enrols tracked entities, and
 * what a project tracks is its own business - a listing spelt `/patients/` would be a lie the moment
 * a type is published as something other than a person.
 *
 * Sent with `cache: 'no-store'`, like `/spool` and for the same class of reason: this is an answer
 * about the DHIS2 instance at this moment, and somebody enrolled in a program a minute ago must not
 * be reported as not enrolled because a cached answer was still warm.
 */
export async function readTrackedEntityEnrollments(trackedEntityUid: string): Promise<PatientEnrollments> {
    return readJson<PatientEnrollments>(`/tracked-entities/${encodeURIComponent(trackedEntityUid)}/enrollments`, {
        cache: 'no-store',
    })
}

/**
 * The run-time settings this UI acts on - today, which tiles the org-unit map draws.
 *
 * Read once by the page that needs it. There is nothing to poll: the settings are resolved when
 * the process starts, so a server that changed its mind about them would have restarted.
 */
export async function readUiConfig(): Promise<UiConfig> {
    return readJson<UiConfig>('/uiconfig')
}

/**
 * Every stored receipt with the lifecycle state its file is currently in.
 *
 * The server re-reads the spool directory to answer this, so a `d2w fhir
 * forward` run in another terminal shows up on the next call with nothing
 * restarted. That is what makes a reload button on the Responses page honest.
 *
 * Sent with `cache: 'no-store'`: this is the one read in the app whose answer
 * changes without anything in the browser having done something.
 */
export async function readSpool(): Promise<SpoolListing> {
    return readJson<SpoolListing>('/spool', { cache: 'no-store' })
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
