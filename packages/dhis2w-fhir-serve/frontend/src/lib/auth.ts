/**
 * Who this server asks the browser to be, and the credential this tab holds.
 *
 * WHERE THE POSTURE COMES FROM. `/metadata` is the only document that is open under every posture -
 * a server that refused to say how to authenticate to it would be one nobody could authenticate to -
 * so the shell reads `rest.security` off the CapabilityStatement, and never learns the posture from
 * a document it might be refused. `/uiconfig` carries the same fact under `auth.posture` for a
 * caller that is already through the door, and the Server page reads it from there.
 *
 * WHAT DECIDES WHICH PROMPT. `security.service` is R4's own way of naming schemes. The DHIS2 posture
 * names `Basic` by its code in R4's value set, so the prompt is a username and a password; the token
 * posture names a scheme the value set has no code for, so the server states it as text, and the
 * prompt is one field. The JWT posture names `OAuth` by its code and states `JWT bearer token` as
 * text, and its prompt is one field too - for a token this server did not issue. Those strings are a
 * contract with `dhis2w_fhir_serve.capability.build_security` and are asserted on both sides.
 *
 * THE JWT POSTURE ALSO CARRIES AN ISSUER, and it has to: a person told to present a token cannot get
 * one without being told whose. R4 has no element for it - `service` names schemes and an issuer is
 * not a scheme - so the server puts it in an extension on `security`, and `issuerFromSecurity` is
 * what reads it back. Never a key, never an audience: the issuer alone.
 *
 * WHERE THE CREDENTIAL LIVES. `sessionStorage`, under one key, as the whole `Authorization` value.
 * A tab, not a browser: closing the tab ends the session, and a second tab signs in on its own.
 * Nothing here is written to `localStorage`, which would outlive the person at the keyboard.
 *
 * WHAT IS STORED IS THE HEADER. Under the DHIS2 posture that is `Basic <base64 of user:password>`,
 * which is the password in a form anything can decode - that is what HTTP Basic is, and it is why
 * this is a per-tab store rather than a durable one. The alternative is a token exchange the DHIS2
 * instance behind this facade cannot yet offer (BUGS.md 96).
 *
 * NOTHING IS STORED UNTIL THE SERVER HAS NAMED THE CALLER. The panel asks `GET /whoami` with what
 * was typed, and only an answer naming somebody reaches `signIn`. Storing first and finding out
 * later is what a scope of `write` makes unbearable: every read is open, so the first thing that
 * would have refused a wrong password is a submission somebody spent minutes filling in. The
 * username this app shows is the server's answer rather than what was typed into the box, which is
 * the same rule the receipts follow.
 */

/** The four postures this server can be in, as `/uiconfig` and this module spell them. */
export type AuthPosture = 'none' | 'token' | 'dhis2' | 'jwt'

/** How much of the surface the posture covers, as `/uiconfig` spells it. */
export type AuthScope = 'write' | 'all'

/** R4's own code system for the schemes a `rest.security` may name, and the two codes this server uses. */
export const SECURITY_SERVICE_SYSTEM = 'http://terminology.hl7.org/CodeSystem/restful-security-service'
export const BASIC_SECURITY_CODE = 'Basic'
export const OAUTH_SECURITY_CODE = 'OAuth'

/** What each bearer posture states where the value set has no code, matching the Python side exactly. */
export const BEARER_TOKEN_SECURITY_TEXT = 'Bearer token'
export const JWT_BEARER_TOKEN_SECURITY_TEXT = 'JWT bearer token'

/** Where the JWT posture states which issuer it takes tokens from - see this module's own note. */
export const JWT_ISSUER_EXTENSION_URL =
    'https://winterop-com.github.io/dhis2w-utils/fhir/StructureDefinition/serve-jwt-issuer'

/** Where this tab keeps the `Authorization` value it signs its requests with. */
export const CREDENTIAL_STORAGE_KEY = 'd2w-fhir-serve-authorization'

/** Where it keeps the name to show for whoever is signed in, which is the username under `dhis2`. */
export const IDENTITY_STORAGE_KEY = 'd2w-fhir-serve-identity'

/**
 * What `GET /whoami` answers a caller this server accepts.
 *
 * The server's own words for who it just decided the caller is. `username` is the DHIS2 username
 * under the DHIS2 posture and the claim the server read out of the token under the JWT one; it is
 * null under the token posture, which names a deployment rather than a person. `name` is what the
 * server would call the caller in a sentence, and this app reads it for nothing: a screen names a
 * person or names nobody, and the server's constant for "the bearer of a token" is not a person.
 */
export interface AuthenticatedCaller {
    posture: AuthPosture
    username: string | null
    name: string
}

/** The shape `rest.security` arrives in - only the parts this module reads. */
export interface CapabilitySecurity {
    cors?: boolean
    extension?: { url?: string; valueString?: string }[]
    service?: { coding?: { system?: string; code?: string }[]; text?: string }[]
    description?: string
}

/**
 * Which posture one CapabilityStatement declares.
 *
 * A statement with no `security` at all is read as `none`, which is the safe reading for a UI: it
 * draws no prompt and lets the server answer for itself. This server always states the element,
 * `none` included, so silence means something in front of it rewrote the document.
 *
 * `JWT bearer token` is checked before `Bearer token` because the first contains the second: read in
 * the other order, every JWT server would draw the deployment-token prompt.
 */
export function postureFromSecurity(security: CapabilitySecurity | null | undefined): AuthPosture {
    const services = security?.service ?? []
    if (services.length === 0) return 'none'
    const named = new Set<string>()
    for (const service of services) {
        if (service.text) named.add(service.text)
        for (const coding of service.coding ?? []) if (coding.code) named.add(coding.code)
    }
    if (named.has(BASIC_SECURITY_CODE)) return 'dhis2'
    if (named.has(JWT_BEARER_TOKEN_SECURITY_TEXT) || named.has(OAUTH_SECURITY_CODE)) return 'jwt'
    if (named.has(BEARER_TOKEN_SECURITY_TEXT)) return 'token'
    return 'none'
}

/**
 * Which issuer one CapabilityStatement says its tokens come from, or null where it says none.
 *
 * Only the JWT posture states it, and only that posture's prompt reads it. Null is what every other
 * posture answers, and what a JWT statement something rewrote would answer - the panel says so in
 * plainer words rather than naming an issuer nobody declared.
 */
export function issuerFromSecurity(security: CapabilitySecurity | null | undefined): string | null {
    for (const extension of security?.extension ?? []) {
        if (extension.url === JWT_ISSUER_EXTENSION_URL && extension.valueString) return extension.valueString
    }
    return null
}

/** One username and password as HTTP Basic sends them. */
export function basicAuthorization(username: string, password: string): string {
    return `Basic ${btoa(`${username}:${password}`)}`
}

/** One deployment token as this server's `token` posture takes it. */
export function bearerAuthorization(token: string): string {
    return `Bearer ${token}`
}

/** What this tab is currently signing its requests with, or null when it holds nothing. */
export function storedAuthorization(): string | null {
    try {
        return sessionStorage.getItem(CREDENTIAL_STORAGE_KEY)
    } catch {
        return null
    }
}

/** Who this tab is signed in as, for the header to name - the DHIS2 username, or null. */
export function storedIdentity(): string | null {
    try {
        return sessionStorage.getItem(IDENTITY_STORAGE_KEY)
    } catch {
        return null
    }
}

/** What the shell knows about who this server serves and who this tab is. */
export interface AuthState {
    /** The posture read off `/metadata`, or null until that read lands. */
    posture: AuthPosture | null
    /** The issuer that same document named, under the JWT posture, and null under every other. */
    issuer: string | null
    /** The `Authorization` value this tab holds, or null. */
    authorization: string | null
    /** Who that credential is, where the credential names anybody. */
    identity: string | null
    /** True once something was refused with 401, which is what opens the prompt. */
    refused: boolean
}

let state: AuthState = {
    posture: null,
    issuer: null,
    authorization: storedAuthorization(),
    identity: storedIdentity(),
    refused: false,
}
const listeners = new Set<() => void>()

function publish(next: AuthState): void {
    state = next
    for (const listener of listeners) listener()
}

/** Subscribe a component to the shared authentication state. */
export function subscribeToAuth(listener: () => void): () => void {
    listeners.add(listener)
    return () => {
        listeners.delete(listener)
    }
}

/** The authentication state as of this instant. */
export function authSnapshot(): AuthState {
    return state
}

/** Record which posture this server declared, and whose tokens it takes, once `/metadata` has been read. */
export function setAuthPosture(posture: AuthPosture, issuer: string | null = null): void {
    publish({ ...state, posture, issuer })
}

/**
 * Record that this tab signs its requests with one credential the server has already accepted.
 *
 * `identity` is what the header names, and is only ever a username the SERVER answered with: under
 * the token posture there is nobody to name, and a screen that invented one would be naming a
 * deployment secret's owner.
 */
export function signIn(authorization: string, identity: string | null): void {
    try {
        sessionStorage.setItem(CREDENTIAL_STORAGE_KEY, authorization)
        if (identity === null) sessionStorage.removeItem(IDENTITY_STORAGE_KEY)
        else sessionStorage.setItem(IDENTITY_STORAGE_KEY, identity)
    } catch {
        // A tab with storage denied still works for as long as it is open; the credential lives in
        // the module either way, and the only thing lost is surviving a reload.
    }
    publish({ ...state, authorization, identity, refused: false })
}

/** Forget the credential this tab held, which is what signing out is. */
export function signOut(): void {
    try {
        sessionStorage.removeItem(CREDENTIAL_STORAGE_KEY)
        sessionStorage.removeItem(IDENTITY_STORAGE_KEY)
    } catch {
        // Nothing to clear that anything else can read.
    }
    publish({ ...state, authorization: null, identity: null, refused: false })
}

/**
 * Record that this server refused a request for want of a credential it accepts.
 *
 * Called by the one function in this app that reaches the network, so a 401 raised anywhere - a
 * read, a submission, a listing - is what opens the prompt. The credential this tab was holding is
 * dropped with it: a credential the server has just refused is not one to keep signing with.
 */
export function reportUnauthenticated(): void {
    try {
        sessionStorage.removeItem(CREDENTIAL_STORAGE_KEY)
        sessionStorage.removeItem(IDENTITY_STORAGE_KEY)
    } catch {
        // As above.
    }
    publish({ ...state, authorization: null, identity: null, refused: true })
}

/**
 * Whether the shell asks who this is before it draws a page.
 *
 * True when the server named a posture and this tab holds nothing. The alternative - browsing until
 * something is refused - would mean sending a request this server answers 401 to, and a browser
 * meeting a 401 on a request it made itself may open a credential dialog of its own over ours. So
 * the app asks first and reaches nothing until it has an answer.
 */
export function signInIsRequired(current: AuthState): boolean {
    return current.posture !== null && current.posture !== 'none' && current.authorization === null
}

/** What the sign-in panel is headed with, per posture. Say the fact, not the verb. */
export const SIGN_IN_HEADINGS: Record<Exclude<AuthPosture, 'none' | 'jwt'>, string> = {
    token: 'This server takes a token',
    dhis2: 'This server takes your DHIS2 credentials',
}

/** What the JWT posture is headed with, which has to name the issuer the token comes from. */
export const UNNAMED_ISSUER_HEADING = 'This server takes a token from an identity provider'

/**
 * What one posture heads its prompt with, naming the issuer where there is one to name.
 *
 * An unnamed issuer is not a case this server produces - it declares the issuer in every `jwt`
 * statement it writes - so it is what a rewritten document reads as, and the honest heading for it
 * says a token is wanted without inventing whose.
 */
export function signInHeading(posture: Exclude<AuthPosture, 'none'>, issuer: string | null): string {
    if (posture !== 'jwt') return SIGN_IN_HEADINGS[posture]
    return issuer === null ? UNNAMED_ISSUER_HEADING : `This server takes a token from ${issuer}`
}

/** What it says under that heading, per posture. */
export const SIGN_IN_NOTES: Record<Exclude<AuthPosture, 'none'>, string> = {
    token: 'The token is the one this deployment issued you. It is held for this browser tab only.',
    dhis2:
        'The username and password are the ones you sign in to DHIS2 with. This server checks them ' +
        'against the instance and records your username on everything you capture. They are held ' +
        'for this browser tab only.',
    jwt:
        'Getting a token is the identity provider’s business, not this server’s: sign in ' +
        'there the way you normally do and paste the token it gives you. This server checks the ' +
        'signature against the keys that provider publishes and records your username on everything ' +
        'you capture. The token is held for this browser tab only.',
}

/** What the control that ends a session is called, and what the one that starts it is called. */
export const SIGN_IN_LABEL = 'Sign in'
export const SIGN_OUT_LABEL = 'Sign out'

/**
 * What the panel says above the fields when a credential was refused, per posture.
 *
 * Name the actual subject: under the DHIS2 posture the refusal came from the DHIS2 instance this
 * server checks against, and saying "this server" would point a person at the wrong machine. Under
 * the other two the refusal is this server's own, and it is a token that was not accepted.
 *
 * The same sentence covers both ways a credential is refused - the check the panel makes before it
 * holds on to anything, and a 401 met later by a read or a submission - because they are the same
 * fact about the same credential, and two spellings of it would only invite the reader to look for
 * a difference that is not there.
 */
export const SIGN_IN_REFUSALS: Record<Exclude<AuthPosture, 'none'>, string> = {
    token: 'This server did not accept this token.',
    dhis2: 'DHIS2 did not accept this username and password.',
    jwt: 'This server did not accept this token.',
}

/**
 * What the panel says when the check could not be made at all.
 *
 * Distinct from a refusal on purpose, and the distinction is the whole reason the check is worth
 * making: credentials that were never checked are not credentials that were rejected, and a person
 * told the wrong one of those retypes a password that was right all along.
 */
export const SIGN_IN_UNREACHABLE = 'This server could not be reached, so nothing was checked.'
