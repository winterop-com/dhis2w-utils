import { useCallback, useEffect, useState } from 'react'

import { readMetadataHealth } from '@/lib/api'
import { EMPTY_METADATA_HEALTH, type MetadataHealth } from '@/lib/health'

/** The metadata report in one of its three honest states, plus the way to ask for it again. */
export interface MetadataHealthState {
    health: MetadataHealth
    loading: boolean
    /** The refusal the server stated, already reduced to its diagnostics. */
    error: string | null
    /** Whether a refresh is in flight over a report that is already on screen. */
    refreshing: boolean
    reload: () => void
}

/**
 * Read the metadata report, and hold what came back.
 *
 * WHY IT RELOADS ON DEMAND AND NEVER ON ITS OWN. This read is about the DHIS2 instance rather than
 * about this server's own store, and the instance changes while the page is open - somebody renaming
 * a data element in Metadata Management is the whole point of the page. So there is a Reload button
 * and it means it: the server re-reads the instance to answer.
 *
 * NOTHING POLLS, AND THERE IS NO FOCUS LISTENER. The spool has one because a forwarder run in
 * another terminal moves files in seconds; this read sweeps an instance's whole metadata, which is a
 * request measured in seconds on a national instance and one nobody wants fired every time a window
 * regains focus.
 *
 * A refresh keeps the previous report on screen while it runs, so pressing Reload does not blank a
 * table somebody is reading.
 */
export function useMetadataHealth(): MetadataHealthState {
    const [nonce, setNonce] = useState(0)
    const [answered, setAnswered] = useState<AnsweredHealth | null>(null)

    const reload = useCallback(() => setNonce((value) => value + 1), [])

    useEffect(() => {
        const wanted = nonce
        let cancelled = false
        readMetadataHealth()
            .then((next) => {
                if (cancelled) return
                setAnswered({ nonce: wanted, health: next, error: null })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                const message = failure instanceof Error ? failure.message : String(failure)
                setAnswered((held) => ({ nonce: wanted, health: held?.health ?? null, error: message }))
            })
        return () => {
            cancelled = true
        }
    }, [nonce])

    const inFlight = answered === null || answered.nonce !== nonce
    const loaded = answered !== null && answered.health !== null
    return {
        health: answered?.health ?? EMPTY_METADATA_HEALTH,
        loading: inFlight && !loaded,
        error: answered?.error ?? null,
        refreshing: inFlight && loaded,
        reload,
    }
}

/** What one read answered, stamped with the reload it answered - null health until one has landed. */
interface AnsweredHealth {
    nonce: number
    health: MetadataHealth | null
    error: string | null
}
