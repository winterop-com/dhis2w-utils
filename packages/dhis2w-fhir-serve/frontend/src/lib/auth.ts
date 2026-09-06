/**
 * Who this server asks the browser to be, and the credential this page holds.
 *
 * WHERE THE POSTURE COMES FROM. `/metadata` is the only document that is open under every posture -
 * a server that refused to say how to authenticate to it would be one nobody could authenticate to -
 * so the shell reads `rest.security` off the CapabilityStatement, and never learns the posture from
 * a document it might be refused. `/facade/uiconfig` carries the same fact under `auth.posture` for a
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
 * WHERE THE CREDENTIAL LIVES. In this module, as the whole `Authorization` value, for as long as
 * this page is loaded, and that state is the one thing a request is signed with. It is written to
 * no browser storage at all - not `sessionStorage`, not `localStorage` - so a reload asks who this
 * is again, and so does a second tab. Every posture is held the same way: a password, a deployment
 * token, and a JWT are one credential each as far as this module is concerned.
 *
 * WHAT THE CREDENTIAL IS. Under the DHIS2 posture, `Basic <base64 of user:password>` - the password
 * in a form anything can decode, which is what HTTP Basic is, and the reason a page load is the
 * longest this app keeps one. The alternative is a token exchange the DHIS2 instance behind this
 * facade cannot yet offer (BUGS.md 96).
 *
 * NOTHING IS HELD UNTIL THE SERVER HAS NAMED THE CALLER. The panel asks `GET /facade/whoami` with what
 * was typed, and only an answer naming somebody reaches `signIn`. Holding first and finding out
 * later is what a scope of `write` makes unbearable: every read is open, so the first thing that
 * would have refused a wrong password is a submission somebody spent minutes filling in. The
 * username this app shows is the server's answer rather than what was typed into the box, which is
 * the same rule the receipts follow.
 */

/** The four postures this server can be in, as `/facade/uiconfig` and this module spell them. */
export type AuthPosture = 'none' | 'token' | 'dhis2' | 'jwt'

/** How much of the surface the posture covers, as `/facade/uiconfig` spells it. */
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

/**
 * What `GET /facade/whoami` answers a caller this server accepts.
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

/** How many bytes are turned into characters at a time, so no call carries a whole credential as arguments. */
const BASE64_CHUNK_SIZE = 0x8000

/**
 * Base64 of arbitrary bytes, built a chunk at a time.
 *
 * `btoa` takes characters, one byte each, so the bytes are spelled as characters before it sees
 * them. That is done in chunks and one character at a time rather than by spreading the whole array
 * into a call, which a long password would overrun.
 */
function base64FromBytes(bytes: Uint8Array): string {
    let characters = ''
    for (let start = 0; start < bytes.length; start += BASE64_CHUNK_SIZE) {
        const end = Math.min(start + BASE64_CHUNK_SIZE, bytes.length)
        let chunk = ''
        for (let index = start; index < end; index += 1) chunk += String.fromCharCode(bytes[index])
        characters += chunk
    }
    return btoa(characters)
}

/**
 * One username and password as HTTP Basic sends them.
 *
 * The pair is encoded to UTF-8 before it is base64ed, which is the same byte sequence
 * `dhis2w_client.v42.auth.basic.BasicAuth` builds its header from, so a name with an o-slash or a
 * password in Chinese reaches DHIS2 as the same bytes from a browser as from the client library.
 * Handing the string to `btoa` directly would send different bytes for the first and raise for the
 * second.
 */
export function basicAuthorization(username: string, password: string): string {
    return `Basic ${base64FromBytes(new TextEncoder().encode(`${username}:${password}`))}`
}

/** One deployment token as this server's `token` posture takes it. */
export function bearerAuthorization(token: string): string {
    return `Bearer ${token}`
}

/** What the shell knows about who this server serves and who this page is signed in as. */
export interface AuthState {
    /** The posture read off `/metadata`, or null until that read lands. */
    posture: AuthPosture | null
    /** The issuer that same document named, under the JWT posture, and null under every other. */
    issuer: string | null
    /** The `Authorization` value this page holds, or null. */
    authorization: string | null
    /** Who that credential is, where the credential names anybody. */
    identity: string | null
    /** True once something was refused with 401, which is what opens the prompt. */
    refused: boolean
}

let state: AuthState = {
    posture: null,
    issuer: null,
    authorization: null,
    identity: null,
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
 * Record that this page signs its requests with one credential the server has already accepted.
 *
 * `identity` is what the header names, and is only ever a username the SERVER answered with: under
 * the token posture there is nobody to name, and a screen that invented one would be naming a
 * deployment secret's owner.
 */
export function signIn(authorization: string, identity: string | null): void {
    publish({ ...state, authorization, identity, refused: false })
}

/** Forget the credential this page held, which is what signing out is. */
export function signOut(): void {
    publish({ ...state, authorization: null, identity: null, refused: false })
}

/**
 * Record that this server refused a request for want of a credential it accepts.
 *
 * Called by the one function in this app that reaches the network, so a 401 raised anywhere - a
 * read, a submission, a listing - is what opens the prompt. The credential this page was holding is
 * dropped with it: a credential the server has just refused is not one to keep signing with.
 */
export function reportUnauthenticated(): void {
    publish({ ...state, authorization: null, identity: null, refused: true })
}

/**
 * Whether the shell asks who this is before it draws a page.
 *
 * True when the server named a posture and this page holds nothing. The alternative - browsing until
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
    token:
        'The token is the one this deployment issued you. It is held in this page only, so a reload ' +
        'asks for it again.',
    dhis2:
        'The username and password are the ones you sign in to DHIS2 with. This server checks them ' +
        'against the instance and records your username on everything you capture. They are held ' +
        'in this page only, so a reload asks for them again.',
    jwt:
        "Getting a token is the identity provider's business, not this server's: sign in " +
        'there the way you normally do and paste the token it gives you. This server checks the ' +
        'signature against the keys that provider publishes and records your username on everything ' +
        'you capture. The token is held in this page only, so a reload asks for it again.',
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
    dhis2: 'This DHIS2 instance did not accept this username and password.',
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

/**
 * What the panel says when what was typed could not be turned into a credential at all.
 *
 * A third thing that is neither a refusal nor an unreachable server: nothing was sent, because
 * nothing could be built to send. Any text a person can type encodes, so this is what a browser
 * without the encoder the header is built with reads as, and saying the password was wrong would
 * send somebody after a password that is right.
 */
export const SIGN_IN_UNENCODABLE = 'This username or password contains characters that cannot be sent.'
