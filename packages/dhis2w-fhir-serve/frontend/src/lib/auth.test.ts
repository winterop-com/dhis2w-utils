import { beforeEach, describe, expect, it } from 'vitest'

import {
    authSnapshot,
    basicAuthorization,
    bearerAuthorization,
    BASIC_SECURITY_CODE,
    BEARER_TOKEN_SECURITY_TEXT,
    CREDENTIAL_STORAGE_KEY,
    IDENTITY_STORAGE_KEY,
    postureFromSecurity,
    reportUnauthenticated,
    SECURITY_SERVICE_SYSTEM,
    setAuthPosture,
    signIn,
    signInIsRequired,
    signOut,
    storedAuthorization,
    storedIdentity,
    subscribeToAuth,
    SIGN_IN_HEADINGS,
    SIGN_IN_NOTES,
    type AuthState,
} from '@/lib/auth'

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

    it('is gone once signed out', () => {
        signIn(bearerAuthorization('a-token'), null)
        signOut()

        expect(storedAuthorization()).toBeNull()
        expect(authSnapshot().authorization).toBeNull()
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
    return { posture: null, authorization: null, identity: null, refused: false, ...over }
}
