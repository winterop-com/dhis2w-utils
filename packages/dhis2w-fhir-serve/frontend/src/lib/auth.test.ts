import { beforeEach, describe, expect, it } from 'vitest'

import {
    authSnapshot,
    basicAuthorization,
    bearerAuthorization,
    BASIC_SECURITY_CODE,
    BEARER_TOKEN_SECURITY_TEXT,
    CREDENTIAL_STORAGE_KEY,
    IDENTITY_STORAGE_KEY,
    issuerFromSecurity,
    JWT_BEARER_TOKEN_SECURITY_TEXT,
    JWT_ISSUER_EXTENSION_URL,
    OAUTH_SECURITY_CODE,
    postureFromSecurity,
    reportUnauthenticated,
    SECURITY_SERVICE_SYSTEM,
    setAuthPosture,
    signIn,
    signInHeading,
    signInIsRequired,
    signOut,
    storedAuthorization,
    storedIdentity,
    subscribeToAuth,
    SIGN_IN_HEADINGS,
    SIGN_IN_NOTES,
    SIGN_IN_REFUSALS,
    SIGN_IN_UNREACHABLE,
    UNNAMED_ISSUER_HEADING,
    type AuthState,
} from '@/lib/auth'

/** The identity provider a `jwt`-posture server federates with, as it declares it. */
const ISSUER = 'https://idp.example.org/realms/health'

/** What the JWT posture declares - `OAuth` by its code, the scheme as text, and the issuer as an extension. */
const JWT_SECURITY = {
    cors: false,
    extension: [{ url: JWT_ISSUER_EXTENSION_URL, valueString: ISSUER }],
    service: [
        {
            coding: [{ system: SECURITY_SERVICE_SYSTEM, code: OAUTH_SECURITY_CODE }],
            text: JWT_BEARER_TOKEN_SECURITY_TEXT,
        },
    ],
}

/** The `rest.security` a `none` posture declares: stated, and naming no scheme. */
const NO_AUTHENTICATION = {
    cors: false,
    description: 'This server authenticates nobody: every caller is served.',
}

/** What the token posture declares - a scheme R4's value set has no code for, stated as text. */
const TOKEN_SECURITY = { cors: false, service: [{ text: BEARER_TOKEN_SECURITY_TEXT }] }

/** What the DHIS2 posture declares - Basic by its code, and the personal access token as text. */
const DHIS2_SECURITY = {
    cors: false,
    service: [
        { coding: [{ system: SECURITY_SERVICE_SYSTEM, code: BASIC_SECURITY_CODE }], text: BASIC_SECURITY_CODE },
        { text: 'DHIS2 personal access token' },
    ],
}

beforeEach(() => {
    sessionStorage.clear()
    signOut()
    setAuthPosture('none')
})

describe('reading the posture off a conformance document', () => {
    it('reads a stated `none` as authenticating nobody', () => {
        expect(postureFromSecurity(NO_AUTHENTICATION)).toBe('none')
    })

    it('reads a missing element as authenticating nobody, so no prompt is invented', () => {
        expect(postureFromSecurity(undefined)).toBe('none')
        expect(postureFromSecurity(null)).toBe('none')
    })

    it('reads the scheme R4 has no code for as the token posture', () => {
        expect(postureFromSecurity(TOKEN_SECURITY)).toBe('token')
    })

    it("reads R4's own Basic code as the DHIS2 posture", () => {
        expect(postureFromSecurity(DHIS2_SECURITY)).toBe('dhis2')
    })

    it('reads a scheme it does not know as authenticating nobody rather than guessing a prompt', () => {
        expect(postureFromSecurity({ service: [{ text: 'Kerberos' }] })).toBe('none')
    })

    it('reads a JWT bearer token as its own posture rather than as the deployment-token one', () => {
        expect(postureFromSecurity(JWT_SECURITY)).toBe('jwt')
    })

    it('reads the OAuth code as the JWT posture even where the text was rewritten', () => {
        expect(
            postureFromSecurity({ service: [{ coding: [{ code: OAUTH_SECURITY_CODE }], text: 'Bearer token' }] }),
        ).toBe('jwt')
    })
})

describe('the issuer a JWT server names', () => {
    it('is read off the extension the server states it in', () => {
        expect(issuerFromSecurity(JWT_SECURITY)).toBe(ISSUER)
    })

    it('is null wherever no posture states one, so no issuer is invented', () => {
        expect(issuerFromSecurity(TOKEN_SECURITY)).toBeNull()
        expect(issuerFromSecurity(DHIS2_SECURITY)).toBeNull()
        expect(issuerFromSecurity(undefined)).toBeNull()
    })

    it('is null for an extension that carries no value, rather than an empty name', () => {
        expect(issuerFromSecurity({ extension: [{ url: JWT_ISSUER_EXTENSION_URL }] })).toBeNull()
    })
})

describe('the credential this tab holds', () => {
    it('sends a username and a password as HTTP Basic', () => {
        expect(basicAuthorization('clerk', 'secret')).toBe(`Basic ${btoa('clerk:secret')}`)
    })

    it('sends a deployment token as a bearer token', () => {
        expect(bearerAuthorization('a-token')).toBe('Bearer a-token')
    })

    it('is held for this tab and read back from it', () => {
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')

        expect(sessionStorage.getItem(CREDENTIAL_STORAGE_KEY)).toBe(basicAuthorization('clerk', 'secret'))
        expect(storedAuthorization()).toBe(basicAuthorization('clerk', 'secret'))
        expect(storedIdentity()).toBe('clerk')
    })

    it('names nobody under the token posture, because a deployment token is not a person', () => {
        signIn(bearerAuthorization('a-token'), null)

        expect(sessionStorage.getItem(IDENTITY_STORAGE_KEY)).toBeNull()
        expect(authSnapshot().identity).toBeNull()
    })

    it('is gone once signed out, storage and snapshot alike', () => {
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        signOut()

        expect(sessionStorage.getItem(CREDENTIAL_STORAGE_KEY)).toBeNull()
        expect(sessionStorage.getItem(IDENTITY_STORAGE_KEY)).toBeNull()
        expect(storedAuthorization()).toBeNull()
        expect(storedIdentity()).toBeNull()
        expect(authSnapshot().authorization).toBeNull()
        expect(authSnapshot().identity).toBeNull()
    })

    it('asks who this is again the moment it is signed out, which is what the control is for', () => {
        setAuthPosture('dhis2')
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        expect(signInIsRequired(authSnapshot())).toBe(false)

        signOut()

        expect(signInIsRequired(authSnapshot())).toBe(true)
    })

    it('tells every listener it was signed out, so the shell that drew the header redraws it', () => {
        setAuthPosture('dhis2')
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        const seen: (string | null)[] = []
        const stop = subscribeToAuth(() => seen.push(authSnapshot().identity))

        signOut()
        stop()

        expect(seen).toEqual([null])
    })

    it('publishes a new snapshot object, which is what a subscribed component compares on', () => {
        signIn(basicAuthorization('clerk', 'secret'), 'clerk')
        const before = authSnapshot()

        signOut()

        expect(authSnapshot()).not.toBe(before)
    })

    it('is dropped when the server refuses it, rather than signed with again', () => {
        signIn(basicAuthorization('clerk', 'wrong'), 'clerk')
        reportUnauthenticated()

        expect(storedAuthorization()).toBeNull()
        expect(authSnapshot().refused).toBe(true)
    })

    it('clears the refusal the moment a new credential is given', () => {
        reportUnauthenticated()
        signIn(bearerAuthorization('a-token'), null)

        expect(authSnapshot().refused).toBe(false)
    })
})

describe('when the shell asks who this is', () => {
    it('asks nothing of a server that authenticates nobody', () => {
        expect(signInIsRequired(stateWith({ posture: 'none' }))).toBe(false)
    })

    it('asks nothing until the posture has been read, so no prompt flickers past', () => {
        expect(signInIsRequired(stateWith({ posture: null }))).toBe(false)
    })

    it('asks whenever a posture is named and this tab holds nothing', () => {
        expect(signInIsRequired(stateWith({ posture: 'token' }))).toBe(true)
        expect(signInIsRequired(stateWith({ posture: 'dhis2' }))).toBe(true)
    })

    it('stops asking once this tab holds a credential', () => {
        expect(signInIsRequired(stateWith({ posture: 'dhis2', authorization: 'Basic x' }))).toBe(false)
    })
})

describe('what the prompt says', () => {
    it('names the fact rather than the command that produced it', () => {
        expect(SIGN_IN_HEADINGS.token).toBe('This server takes a token')
        expect(SIGN_IN_HEADINGS.dhis2).toBe('This server takes your DHIS2 credentials')
    })

    it('says where the credential goes and how long it is kept', () => {
        expect(SIGN_IN_NOTES.token).toContain('this browser tab only')
        expect(SIGN_IN_NOTES.dhis2).toContain('this browser tab only')
        expect(SIGN_IN_NOTES.dhis2).toContain('records your username')
    })

    it('names the identity provider a token has to come from', () => {
        expect(signInHeading('jwt', ISSUER)).toBe(`This server takes a token from ${ISSUER}`)
    })

    it('asks for a token without inventing an issuer where none was declared', () => {
        expect(signInHeading('jwt', null)).toBe(UNNAMED_ISSUER_HEADING)
    })

    it('ignores an issuer under the postures that have none', () => {
        expect(signInHeading('token', ISSUER)).toBe(SIGN_IN_HEADINGS.token)
        expect(signInHeading('dhis2', ISSUER)).toBe(SIGN_IN_HEADINGS.dhis2)
    })

    it('says getting the token is the provider\'s business, not this server\'s', () => {
        expect(SIGN_IN_NOTES.jwt).toContain('identity provider')
        expect(SIGN_IN_NOTES.jwt).toContain('this browser tab only')
        expect(SIGN_IN_NOTES.jwt).toContain('records your username')
    })

    it('names DHIS2 as the thing that refused a username and password, since it is', () => {
        expect(SIGN_IN_REFUSALS.dhis2).toBe('DHIS2 did not accept this username and password.')
    })

    it('names this server as the thing that refused a token, since it is', () => {
        expect(SIGN_IN_REFUSALS.token).toBe('This server did not accept this token.')
        expect(SIGN_IN_REFUSALS.jwt).toBe('This server did not accept this token.')
    })

    it('says an unreachable server checked nothing, which is not the same as refusing', () => {
        expect(SIGN_IN_UNREACHABLE).toContain('could not be reached')
        expect(SIGN_IN_UNREACHABLE).not.toContain('accept')
    })
})

describe('what a JWT server asks of a tab', () => {
    it('asks for a token whenever this tab holds none', () => {
        expect(signInIsRequired(stateWith({ posture: 'jwt' }))).toBe(true)
        expect(signInIsRequired(stateWith({ posture: 'jwt', authorization: 'Bearer x' }))).toBe(false)
    })

    it('holds the issuer beside the posture, because the prompt names it', () => {
        setAuthPosture('jwt', ISSUER)

        expect(authSnapshot().posture).toBe('jwt')
        expect(authSnapshot().issuer).toBe(ISSUER)
    })

    it('sends a pasted token as a bearer token, naming nobody until the server reads the claim', () => {
        signIn(bearerAuthorization('a.b.c'), null)

        expect(storedAuthorization()).toBe('Bearer a.b.c')
        expect(authSnapshot().identity).toBeNull()
    })
})

describe('the shared store', () => {
    it('tells every listener the moment the state changes', () => {
        let heard = 0
        const stop = subscribeToAuth(() => {
            heard += 1
        })

        signIn(bearerAuthorization('a-token'), null)
        signOut()
        stop()
        signIn(bearerAuthorization('another'), null)

        expect(heard).toBe(2)
    })
})

function stateWith(over: Partial<AuthState>): AuthState {
    return { posture: null, issuer: null, authorization: null, identity: null, refused: false, ...over }
}
