import { useCallback, useEffect, useState } from 'react'

import { readSpool } from '@/lib/api'
import { EMPTY_SPOOL, type SpoolListing } from '@/lib/spool'

/** The spool listing in one of its three honest states, plus the way to ask for it again. */
export interface SpoolState {
    listing: SpoolListing
    loading: boolean
    /** The refusal the server stated, already reduced to its OperationOutcome diagnostics. */
    error: string | null
    /** Whether a refresh is in flight over a listing that is already on screen. */
    refreshing: boolean
    reload: () => void
}

/**
 * Read the spool, and read it again when the window comes back.
 *
 * WHY THIS ONE PAGE REFETCHES AND THE OTHERS DO NOT. Every other read in this
 * app answers from a store loaded once at startup - re-reading it can only
 * return the same bytes. The spool is the opposite: `d2w fhir forward` is
 * another process renaming receipt files while this page is open, so what is on
 * screen goes stale with nothing in the browser having done anything.
 *
 * A focus listener rather than a poll, and no query library to bring one. The
 * realistic sequence is "run the forwarder in the other terminal, come back to
 * the browser", and a focus event catches exactly that at the moment a person
 * looks - where a timer would either lag behind them or hammer a loopback
 * server nobody is watching. The reload button covers the rest.
 *
 * A refresh keeps the previous listing on screen while it runs, so returning to
 * the tab does not blank the table for a frame.
 *
 * WHAT THIS DOES NOT DO. A window left open and unfocused stays as it was until
 * it regains focus, however long a forwarder run takes in the meantime; nothing
 * here polls. `reload` is the way a page asks for a read of its own - the
 * Responses page calls it on every arrival at the route, and its Reload button
 * is the one a person presses while looking straight at the table.
 */
export function useSpool(): SpoolState {
    const [nonce, setNonce] = useState(0)
    const [answered, setAnswered] = useState<AnsweredSpool | null>(null)

    const reload = useCallback(() => setNonce((value) => value + 1), [])

    useEffect(() => {
        const wanted = nonce
        let cancelled = false
        readSpool()
            .then((next) => {
                if (cancelled) return
                setAnswered({ nonce: wanted, listing: next, error: null })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                const message = failure instanceof Error ? failure.message : String(failure)
                setAnswered((held) => ({ nonce: wanted, listing: held?.listing ?? null, error: message }))
            })
        return () => {
            cancelled = true
        }
    }, [nonce])

    useEffect(() => {
        const onFocus = () => reload()
        window.addEventListener('focus', onFocus)
        return () => window.removeEventListener('focus', onFocus)
    }, [reload])

    const inFlight = answered === null || answered.nonce !== nonce
    const loaded = answered !== null && answered.listing !== null
    return {
        listing: answered?.listing ?? EMPTY_SPOOL,
        loading: inFlight && !loaded,
        error: answered?.error ?? null,
        refreshing: inFlight && loaded,
        reload,
    }
}

/** What one read answered, stamped with the reload it answered - null listing until one has landed. */
interface AnsweredSpool {
    nonce: number
    listing: SpoolListing | null
    error: string | null
}
