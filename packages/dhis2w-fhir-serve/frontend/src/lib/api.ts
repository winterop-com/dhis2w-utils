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
 * is no /fhir prefix - and then mounts the built UI at "/" *after* them, so
 * anything the routers do not claim falls through to the SPA shell. That is
 * exactly the arrangement in which a mistyped path returns 200 text/html and a
 * caller spends an afternoon on "why is my Bundle a string". The guard is the
 * router table of `dhis2w_fhir_serve.routes` written down, and that table has
 * three families at the root: /metadata and the resource types the read
 * catch-alls answer for (ConceptMap being both a read type and the one the
 * type-level $translate hangs off), /cds-services, and the /facade mount.
 * Anything else is a programming error and is refused here rather than by the
 * server.
 *
 * TWO SURFACES, TWO PREFIXES. The root is FHIR's, and its contract is the
 * CapabilityStatement at /metadata. Everything this server answers about
 * *itself* - the receipts, the settings it was started with, who it decided the
 * caller is, the evaluator, the vocabularies, the register listings it reads
 * from DHIS2 - is a different API under `/facade`, with its own OpenAPI document
 * at `/facade/openapi.json`. `FACADE_BASE_PATH` is that prefix and every read
 * below composes it rather than spelling it, so the mount is stated once.
 * `dhis2w_fhir_serve.routes.spool` argues why those answers are not FHIR.
 *
 * /cds-services is the third family and is at the root beside FHIR rather than
 * under the mount, because CDS Hooks fixes discovery at {base}/cds-services the
 * way FHIR fixes {base}/metadata. Nothing in this bundle calls it; it is guarded
 * because this server claims it ahead of the static mount, and a guard that let
 * a path through would be a guard that let a typo land on the SPA shell.
 *
 * SOME OF WHAT IS GUARDED ANSWERS FROM DHIS2 RATHER THAN FROM THE STORE.
 * The register's own resource types at the root, and the tracked entity
 * listings under the mount, are answered only by a live process; a compiled one
 * refuses them by saying so - which is a refusal a caller reads and renders, not
 * a path that escaped the guard. Everything else on this surface is answered
 * from a store loaded once at startup.
 *
 * WHY NO QUERY LIBRARY. There is no react-query, swr, or zustand in this app on
 * purpose. The server answers whole Bundles off a store loaded once at startup,
 * so there is nothing to cache that the server is not already caching, and no
 * invalidation problem to solve. Pages hold their own `useState`; anything that
 * genuinely spans pages (reachability) is a module-level store read through
 * `useSyncExternalStore`.
 */

import type { EvaluationOutcome } from '@/lib/evaluate'
import type { MetadataHealth } from '@/lib/health'
import {
    REGISTER_IDENTIFIER_SEARCH_PARAMETER,
    REGISTER_TAG_SEARCH_PARAMETER,
    type Bundle,
    type CapabilityStatement,
    type OperationOutcome,
    type Parameters,
    type Patient,
    type QuestionnaireResponse,
    type RegisterSearchKey,
} from '@/lib/fhir'
import {
    PATIENT_COUNT_PARAMETER,
    PATIENT_PAGE_PARAMETER,
    REGISTER_ATTRIBUTE_SEARCH_PARAMETER,
    type PatientEnrollments,
} from '@/lib/patients'
import { authSnapshot, reportUnauthenticated, type AuthenticatedCaller } from '@/lib/auth'
import type { SpoolListing } from '@/lib/spool'
import type { UiConfig } from '@/lib/uiconfig'

/** The media type every FHIR request and response on this server carries. */
export const FHIR_JSON_MEDIA_TYPE = 'application/fhir+json'

/**
 * Where this server's own API is mounted, beside the FHIR base URL.
 *
 * The Python side spells the same string in `dhis2w_fhir_serve.routes`, where it
 * is the path a FastAPI sub-application is mounted at. Every read of that API
 * below composes this constant, so the prefix is written down once.
 */
export const FACADE_BASE_PATH = '/facade'

/**
 * Every lowercase path `d2w fhir serve` claims ahead of the UI mount.
 *
 * Kept as a list rather than only a regex so the set is greppable from the
 * Python side: this must stay equal to `/metadata`, `/cds-services`, and the
 * `/facade` mount. Three segments is the whole of it, because everything this
 * server answers about itself is inside the third one. The vite dev-server proxy
 * in vite.config.ts proxies the same list, plus the `/$evaluate` operation
 * `SERVICE_BASE_OPERATION_PATTERN_SOURCE` lets through.
 *
 * The FHIR resource types are not in it, and cannot be. The read catch-all
 * answers `/{ResourceType}` for the types the store holds, and the register
 * answers it for every resource the published `D2TET_CM` names - which is a
 * property of the guide this server loaded rather than of this bundle. So the
 * guard recognises the *shape* of a resource type instead of enumerating them,
 * and a type this server does not serve comes back as its own OperationOutcome
 * saying so, which is a better answer than a client-side refusal guessing.
 */
export const GUARDED_PATH_SEGMENTS = ['metadata', 'cds-services', 'facade'] as const

/**
 * Where the server names whoever is calling, which is how a credential is checked before it is kept.
 *
 * A fixed path rather than something discovered off `/metadata` or the settings document: this
 * bundle is served same-origin by the very process that answers it, so the two are one deployment
 * and there is nothing for a discovery step to resolve. The Python side spells the same string in
 * `dhis2w_fhir_serve.routes.whoami`, relative to the mount.
 */
export const WHOAMI_PATH = `${FACADE_BASE_PATH}/whoami`

/** How FHIR spells a resource type: an initial capital, then letters, and nothing else. */
export const RESOURCE_TYPE_PATTERN_SOURCE = '[A-Z][A-Za-z]*'

/**
 * How FHIR spells an operation the service base answers: a `$`, then the operation's name.
 *
 * `POST /$evaluate` is the one this server mounts, ahead of the read catch-alls for the reason
 * `dhis2w_fhir_serve.routes.evaluate_operation` states - `/{resource_type}` matches `/$evaluate`
 * just as happily. A resource type's own operations need no rule of their own: they hang off a
 * type, so `/ConceptMap/$translate` passes as a ConceptMap path already.
 */
export const SERVICE_BASE_OPERATION_PATTERN_SOURCE = String.raw`\$[a-z]+`

/**
 * The guard itself.
 *
 * A path passes when it is exactly one of the fixed segments, a FHIR resource
 * type, or a system-level operation, or continues with `/` (a resource id, an
 * operation) or `?` (a search).
 * Everything the UI is served from - `/`, `/index.html`, `/assets/...` - is
 * lowercase and unlisted, which is what the guard is for: a request that would
 * otherwise be answered with the shell instead of with JSON.
 */
export const GUARDED_PATH_PATTERN = new RegExp(
    `^/(${[...GUARDED_PATH_SEGMENTS, RESOURCE_TYPE_PATTERN_SOURCE, SERVICE_BASE_OPERATION_PATTERN_SOURCE].join('|')})([/?]|$)`,
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
 * default posture serves every caller and binds loopback, so the UI it serves
 * reaches it by relative path. `configureApi` exists for the two cases that are
 * not that: a UI running under `pnpm dev` against a server on another port, and
 * a deployment that has put a token-checking proxy in front. What a person
 * signed in with is `lib/auth`'s, held per tab and attached by `apiFetch`.
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
 * `fetch` against the served FHIR surface, with the credential attached and the path guarded.
 *
 * The Accept header is set here rather than per call, because every route on
 * this server answers `application/fhir+json` - including its errors, which are
 * OperationOutcomes.
 *
 * THE CREDENTIAL IS THIS TAB'S, when it holds one: `lib/auth` keeps the whole
 * `Authorization` value, which is `Basic ...` under the DHIS2 posture and
 * `Bearer ...` under the token posture. It is read off the auth state rather
 * than out of storage, so the credential a request is signed with is the one
 * the app's own screens are drawn from, and a tab whose storage is denied signs
 * its requests like any other. `configureApi({token})` stays for the
 * case it was always for - something in front of this server wanting a bearer
 * token - and the signed-in credential wins over it, because a person who signed
 * in is a more specific answer than a deployment default.
 *
 * A 401 IS RECORDED AS IT PASSES. One choke point means one place where "this
 * server does not know who you are" becomes a prompt, whichever read or write
 * met it. The response is still returned and still raised by the caller, so a
 * page renders the server's own OperationOutcome as it renders every other
 * refusal.
 */
export async function apiFetch(path: string, init: RequestInit = {}, signing: SigningOptions = {}): Promise<Response> {
    if (!GUARDED_PATH_PATTERN.test(path)) throw new UnguardedPathError(path)
    const headers = new Headers(init.headers)
    if (!headers.has('Accept')) headers.set('Accept', FHIR_JSON_MEDIA_TYPE)
    const credential = signing.authorization ?? authSnapshot().authorization
    if (credential) headers.set('Authorization', credential)
    else if (configuration.token) headers.set('Authorization', `Bearer ${configuration.token}`)
    const response = await fetch(`${configuration.baseUrl}${path}`, { ...init, headers })
    if (response.status === 401 && signing.reportsRefusal !== false) reportUnauthenticated()
    return response
}

/** How one request is signed, for the single caller that signs with something this tab does not hold. */
export interface SigningOptions {
    /** The `Authorization` value to use in place of what this tab holds, if any. */
    authorization?: string
    /** Whether a 401 on this request opens the sign-in prompt. Defaults to true. */
    reportsRefusal?: boolean
}

/** What asking the server who a credential belongs to answered. */
export type CredentialCheck =
    | { outcome: 'accepted'; username: string | null }
    | { outcome: 'refused' }
    | { outcome: 'unreachable' }

/**
 * Ask the server to name the caller one credential belongs to, without this tab keeping it.
 *
 * WHY IT DOES NOT REPORT ITS OWN 401. Every other request routes a refusal through
 * `reportUnauthenticated`, which drops the stored credential and opens the prompt - the right
 * behaviour for a read or a submission that met one. This call IS the prompt asking, with a
 * credential nothing has stored yet, so reporting it would clear a session somebody else's typing
 * has nothing to do with and put the panel's own message underneath a second one saying the same
 * thing. The panel renders the verdict itself.
 *
 * THREE OUTCOMES, NOT TWO. A refusal and an unreachable server are different sentences to a person
 * at a keyboard: one means retype the password, the other means the password was never looked at.
 * Anything the server answers that is neither 200 nor 401 is read as unreachable, which is the
 * honest reading - a 502 from something in front of this facade says nothing about the credential.
 */
export async function checkCredential(authorization: string): Promise<CredentialCheck> {
    let response: Response
    try {
        response = await apiFetch(
            WHOAMI_PATH,
            { cache: 'no-store' },
            { authorization, reportsRefusal: false },
        )
    } catch {
        return { outcome: 'unreachable' }
    }
    if (response.status === 401) return { outcome: 'refused' }
    if (!response.ok) return { outcome: 'unreachable' }
    const caller = (await response.json().catch(() => null)) as AuthenticatedCaller | null
    if (caller === null) return { outcome: 'unreachable' }
    return { outcome: 'accepted', username: caller.username ?? null }
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

/** What a read of `/metadata` says when the body that came back is some other document. */
export const NOT_A_CAPABILITY_STATEMENT = '/metadata answered with something other than a CapabilityStatement'

/**
 * The served IG's conformance document.
 *
 * THE DOCUMENT IS CHECKED, NOT ASSUMED. `/metadata` is a path a reverse proxy, a captive portal, or
 * a differently-configured server can all answer 200 to, and a cast turns any of those bodies into
 * a CapabilityStatement with every field undefined - which the Server page then renders as a card
 * of dashes and a table with no rows, under a header saying "Connected". A raise here is what puts
 * that answer in the state the page already has words for: the server answered, but not with this
 * document.
 */
export async function readCapabilityStatement(): Promise<CapabilityStatement> {
    const body = await readJson<unknown>('/metadata')
    if (!isCapabilityStatement(body)) throw new Error(NOT_A_CAPABILITY_STATEMENT)
    return body
}

/** Whether a parsed body is the conformance document, which is what its `resourceType` says. */
function isCapabilityStatement(body: unknown): body is CapabilityStatement {
    return (
        typeof body === 'object' &&
        body !== null &&
        (body as { resourceType?: unknown }).resourceType === 'CapabilityStatement'
    )
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

/** What an accepted capture answered with - the receipt it was stored as, and what the server noted. */
export interface CaptureReceipt {
    /** The receipt id, off the `Location` the create interaction states. Null when it stated none. */
    responseId: string | null
    /** The information and warning issues the accepted capture still carried. */
    outcome: OperationOutcome | null
}

/**
 * Submit one filled-in form.
 *
 * The server answers 201 with an OperationOutcome, or a 4xx OperationOutcome naming every question
 * it refused - and an accepted capture can still carry warnings, which is why the caller gets the
 * parsed body rather than a boolean.
 *
 * THE RECEIPT ID IS IN THE HEADER, NOT IN THE BODY. R4 says a create states where the created
 * resource is served from in `Location`, and this server does exactly that: the 201 body is the
 * outcome, so a caller reading the body for an `id` finds none and can only say "a new receipt" for
 * something that has a name. `receiptIdOf` is the one place that header is read.
 */
export async function postQuestionnaireResponse(response: QuestionnaireResponse): Promise<CaptureReceipt> {
    const path = '/QuestionnaireResponse'
    const answer = await apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': FHIR_JSON_MEDIA_TYPE },
        body: JSON.stringify(response),
    })
    const body: unknown = await answer.json().catch(() => null)
    if (!answer.ok) throw new FhirRequestError(answer.status, body as OperationOutcome | null, path)
    return {
        responseId: receiptIdOf(answer.headers.get('Location')),
        outcome: body as OperationOutcome | null,
    }
}

/** The receipt id a create interaction's `Location` names: its last path segment, or null for none. */
export function receiptIdOf(location: string | null): string | null {
    if (location === null) return null
    const segments = location.split(/[?#]/)[0].split('/').filter((segment) => segment !== '')
    const last = segments.at(-1) ?? ''
    return last === '' ? null : last
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
export async function searchRegister(
    resource: string,
    query: string,
    key: RegisterSearchKey = REGISTER_IDENTIFIER_SEARCH_PARAMETER,
    trackedEntityTypeUid: string | null = null,
    attributeFilter: string | null = null,
): Promise<RegisterAnswer> {
    return readRegisterBundle(resource, registerSearchParameters(key, query, trackedEntityTypeUid, attributeFilter))
}

/** Everything one register search puts on the wire, assembled once for the request and the link alike. */
function registerSearchParameters(
    key: RegisterSearchKey,
    query: string,
    trackedEntityTypeUid: string | null,
    attributeFilter: string | null,
): Record<string, string> {
    return {
        [key]: query,
        ...typeTag(trackedEntityTypeUid),
        ...attributeValueFilter(attributeFilter),
    }
}

/**
 * The path one register search reads, without reading it - what the browser would fetch, as a string.
 *
 * It exists so a screen can show the query it is showing the answer to. The parameters come from the
 * same builder the request uses, so the two cannot drift: a filter the search sends and the link
 * omits would be a link that answers a different question than the page.
 */
export function registerSearchPath(
    resource: string,
    query: string,
    key: RegisterSearchKey = REGISTER_IDENTIFIER_SEARCH_PARAMETER,
    trackedEntityTypeUid: string | null = null,
    attributeFilter: string | null = null,
): string {
    return registerPath(resource, registerSearchParameters(key, query, trackedEntityTypeUid, attributeFilter))
}

/** The path one page of a register listing reads, without reading it - the link beside the table. */
export function registerListingPath(
    resource: string,
    pageToken: string | null,
    count: number,
    trackedEntityTypeUid: string | null = null,
    attributeFilter: string | null = null,
): string {
    return registerPath(resource, registerListingParameters(pageToken, count, trackedEntityTypeUid, attributeFilter))
}

/**
 * The `d2-attribute` a request filtered to one attribute value carries, or nothing when it filters none.
 *
 * The token is `{trackedEntityAttributeUid}|{value}` and it goes on the wire exactly as the address
 * carried it - see `lib/patients.registerAttributeToken`, which is where the two halves are joined.
 * The server matches the value exactly, which is what the control saying so on screen is about.
 */
function attributeValueFilter(token: string | null): Record<string, string> {
    if (token === null || token === '') return {}
    return { [REGISTER_ATTRIBUTE_SEARCH_PARAMETER]: token }
}

/**
 * The `_tag` a request narrowed to one tracked entity type carries, or nothing when it narrowed none.
 *
 * The uid alone rather than `{system}|{uid}`: a register resource states one tag, so a bare code has
 * no ambiguity to fall into, and the system is this project's canonical - a string this UI would have
 * to derive to say something the server already knows.
 */
function typeTag(trackedEntityTypeUid: string | null): Record<string, string> {
    if (trackedEntityTypeUid === null || trackedEntityTypeUid === '') return {}
    return { [REGISTER_TAG_SEARCH_PARAMETER]: trackedEntityTypeUid }
}

/**
 * The header a projection-served answer states its own age on.
 *
 * `dhis2w_fhir_serve.projection.serving` spells the same string. The value is the instant the sync
 * last read the DHIS2 instance, on the instance's own clock, or the word `never` for a copy nothing
 * has filled yet.
 */
export const PROJECTION_AS_OF_HEADER = 'X-DHIS2W-Projection-As-Of'

/**
 * One register answer: the Bundle, and how old the copy that answered it is.
 *
 * WHY THE HEADER TRAVELS WITH THE BODY. A register search under the projection backend is answered
 * from a synced copy of the DHIS2 instance rather than from the instance, and how stale that copy is
 * is a fact about every row on the page - so it cannot be read later, out of band, by a component
 * that happens to want it. It arrives with the rows or it is not known. `null` is the ordinary case:
 * a facade searching DHIS2 directly states no such header, because its answer is as old as the
 * request.
 */
export interface RegisterAnswer {
    bundle: Bundle<Patient>
    projectionAsOf: string | null
}

/** One register route with its query on it, which is the string the request and the link both name. */
function registerPath(resource: string, parameters: Record<string, string>): string {
    const query = new URLSearchParams(parameters).toString()
    return `/${resource}${query ? `?${query}` : ''}`
}

/** One register read, with the projection's own statement of when it was last filled. */
async function readRegisterBundle(
    resource: string,
    parameters: Record<string, string>,
): Promise<RegisterAnswer> {
    const path = registerPath(resource, parameters)
    const response = await apiFetch(path, { cache: 'no-store' })
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) throw new FhirRequestError(response.status, body as OperationOutcome | null, path)
    return {
        bundle: body as Bundle<Patient>,
        projectionAsOf: response.headers.get(PROJECTION_AS_OF_HEADER),
    }
}

/**
 * One page of everyone the DHIS2 instance behind a live facade holds.
 *
 * The same route with no search parameter on it, which is what makes it a listing rather than a
 * lookup. `page` is the token the previous answer's own link carried and is sent back verbatim -
 * this server mints it and this server reads it, and a caller that took it apart would be deciding
 * how the instance is paged. Null asks for the first page, which is the state a browser opens in.
 *
 * A deployment can publish the search and decline the listing, so callers ask `/facade/uiconfig` first and
 * never offer the table at all in that case.
 *
 * A named tracked entity type rides every page of the walk, not only its first: the token locates a
 * page inside a scope and the tag is what the scope is, so a `next` sent without it would step out
 * of the type the walk started in.
 */
export async function listRegister(
    resource: string,
    pageToken: string | null,
    count: number,
    trackedEntityTypeUid: string | null = null,
    attributeFilter: string | null = null,
): Promise<RegisterAnswer> {
    return readRegisterBundle(
        resource,
        registerListingParameters(pageToken, count, trackedEntityTypeUid, attributeFilter),
    )
}

/** Everything one page of a register listing puts on the wire, for the request and the link alike. */
function registerListingParameters(
    pageToken: string | null,
    count: number,
    trackedEntityTypeUid: string | null,
    attributeFilter: string | null,
): Record<string, string> {
    const parameters: Record<string, string> = {
        [PATIENT_COUNT_PARAMETER]: String(count),
        ...typeTag(trackedEntityTypeUid),
        ...attributeValueFilter(attributeFilter),
    }
    if (pageToken !== null) parameters[PATIENT_PAGE_PARAMETER] = pageToken
    return parameters
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
 * Sent with `cache: 'no-store'`, like the receipts listing and for the same class of reason: this is
 * an answer about the DHIS2 instance at this moment, and somebody enrolled in a program a minute ago
 * must not be reported as not enrolled because a cached answer was still warm.
 */
export async function readTrackedEntityEnrollments(trackedEntityUid: string): Promise<PatientEnrollments> {
    const path = `${FACADE_BASE_PATH}/tracked-entities/${encodeURIComponent(trackedEntityUid)}/enrollments`
    return readJson<PatientEnrollments>(path, { cache: 'no-store' })
}

/**
 * The run-time settings this UI acts on - today, which tiles the org-unit map draws.
 *
 * Read once by the page that needs it. There is nothing to poll: the settings are resolved when
 * the process starts, so a server that changed its mind about them would have restarted.
 */
export async function readUiConfig(): Promise<UiConfig> {
    return readJson<UiConfig>(`${FACADE_BASE_PATH}/uiconfig`)
}

/**
 * What the DHIS2 instance behind a live run holds that the guide cannot carry cleanly.
 *
 * The `d2w fhir validate` analysis plus the translation coverage, in one read. Sent with
 * `cache: 'no-store'`: this is an answer about the instance as it is now, and somebody who has just
 * renamed an object in DHIS2 must not be shown the name they replaced.
 *
 * A compiled run answers 200 with `available: false` and the reason there is nothing to report, so
 * a caller reads the body rather than catching - the page renders the server's own sentence.
 */
export async function readMetadataHealth(): Promise<MetadataHealth> {
    return readJson<MetadataHealth>(`${FACADE_BASE_PATH}/metadata-health`, { cache: 'no-store' })
}

/**
 * Ask the server to evaluate one expression over one resource it serves.
 *
 * Plain `application/json`, not FHIR: the answer carries typed results and the line and column a
 * parser stopped on, neither of which a `Parameters` resource has anywhere to put.
 *
 * A bad expression is not a failure of this call. It answers 200 with its diagnostics, exactly as
 * `$translate` answers a concept its maps say nothing about, so a caller reads the outcome rather
 * than catching. What throws is a request this facade cannot serve at all - a stored resource it
 * does not hold, a register it does not publish - which arrives as an OperationOutcome.
 */
export async function evaluateExpression(request: Record<string, unknown>): Promise<EvaluationOutcome> {
    return readJson<EvaluationOutcome>(`${FACADE_BASE_PATH}/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    })
}

/** How many receipts one page of the spool walk asks for - the server's own ceiling per request. */
const SPOOL_PAGE_SIZE = 500

/**
 * Every stored receipt with the lifecycle state its file is currently in.
 *
 * The server re-reads the spool directory to answer this, so a `d2w fhir
 * forward` run in another terminal shows up on the next call with nothing
 * restarted. That is what makes a reload button on the Responses page honest.
 *
 * WHY THIS FOLLOWS LINKS. The listing is paged, so one request is one page of the
 * receipts. The Responses page filters and sorts across the whole spool, so it
 * needs the whole spool, and the honest way to get it is to follow the `next`
 * link the server hands out rather than to compose a page parameter of our own -
 * the cursor is the server's business and its shape is not a contract.
 *
 * The counts come off the first page and are left alone: they are the whole
 * spool on every page, so summing them across pages would multiply them.
 *
 * Sent with `cache: 'no-store'`: this is the one read in the app whose answer
 * changes without anything in the browser having done something.
 */
export async function readSpool(): Promise<SpoolListing> {
    const path = `${FACADE_BASE_PATH}/spool?_count=${SPOOL_PAGE_SIZE}`
    const first = await readJson<SpoolListing>(path, { cache: 'no-store' })
    const responses = [...first.responses]
    let next = first.next_url
    while (next !== null && next !== undefined) {
        // A cursor walk is sequential by construction: the link to the next page is on the page
        // before it, so there is nothing to run in parallel.
        // oxlint-disable-next-line eslint/no-await-in-loop
        const page = await readJson<SpoolListing>(pathAndQuery(next), { cache: 'no-store' })
        responses.push(...page.responses)
        next = page.next_url
    }
    return { ...first, responses }
}

/** One absolute link the server minted, as this app asks for it again - same origin, so path only. */
function pathAndQuery(url: string): string {
    const parsed = new URL(url, window.location.origin)
    return `${parsed.pathname}${parsed.search}`
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
