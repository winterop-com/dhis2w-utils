import { useEffect, useSyncExternalStore } from 'react'

import { apiFetch } from '@/lib/api'
import {
    authSnapshot,
    issuerFromSecurity,
    postureFromSecurity,
    setAuthPosture,
    subscribeToAuth,
    type AuthPosture,
    type AuthState,
} from '@/lib/auth'
import type { CapabilityStatement } from '@/lib/fhir'

/**
 * Who this server serves, and who this tab is.
 *
 * A module-level store read through `useSyncExternalStore`, for the reason `use-server-status` is
 * one: several components look at the same fact - the shell decides whether to draw a page, the
 * header names whoever is signed in, the panel asks - and the posture is read once for all of them.
 *
 * THE POSTURE IS READ OFF `/metadata`, which is the one address open under every posture. Reading it
 * anywhere else would mean a document this server may refuse deciding whether to ask for
 * credentials, which is a question no refusal can answer.
 *
 * A read that fails leaves the posture unresolved rather than guessing at `none`. The shell renders
 * nothing but its own frame until it is known: guessing `none` would fire the app's reads at a
 * server that will refuse them, and guessing a posture would ask for credentials no server wanted.
 */
export function useAuth(): AuthState {
    const state = useSyncExternalStore(subscribeToAuth, authSnapshot, authSnapshot)

    useEffect(() => {
        if (state.posture !== null) return
        let cancelled = false
        void readPosture().then((declared) => {
            if (!cancelled && declared !== null) setAuthPosture(declared.posture, declared.issuer)
        })
        return () => {
            cancelled = true
        }
    }, [state.posture])

    return state
}

/**
 * Read the posture off the conformance document, without raising.
 *
 * Deliberately not `readCapabilityStatement`: this runs before anything else in the app and its
 * failure is not a page's failure. An unreachable server answers null, the shell keeps waiting, and
 * the status menu is what says the server is not there.
 *
 * The issuer comes off the same read because it comes off the same element, and because it is what
 * the JWT posture's prompt has to name. It is null under every other posture.
 */
async function readPosture(): Promise<{ posture: AuthPosture; issuer: string | null } | null> {
    try {
        const response = await apiFetch('/metadata', { cache: 'no-store' })
        if (!response.ok) return null
        const statement = (await response.json()) as CapabilityStatement
        const security = statement.rest?.[0]?.security
        return { posture: postureFromSecurity(security), issuer: issuerFromSecurity(security) }
    } catch {
        return null
    }
}
