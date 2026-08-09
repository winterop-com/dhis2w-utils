import { useSyncExternalStore } from 'react'

import { checkReachability, readCapabilityStatement } from '@/lib/api'
import type { CapabilityStatement } from '@/lib/fhir'

/**
 * Is the server there, and which guide is it serving.
 *
 * This is the one piece of state that genuinely spans pages - the status menu
 * shows it in the header while every page renders under it - so it lives in a
 * module-level store read through `useSyncExternalStore` rather than in a
 * context provider. One probe, one CapabilityStatement read, however many
 * components are looking.
 *
 * The CapabilityStatement is fetched once and kept. That is not a cache with an
 * invalidation problem: the server renders that document at startup and serves
 * the same bytes for the life of the process, so a second read would return
 * exactly what the first one did. Refreshing it means the server restarted,
 * which `refreshServerStatus` covers.
 */
export interface ServerStatus {
    reachability: 'unknown' | 'ok' | 'unreachable'
    capability: CapabilityStatement | null
    /** True while a probe is in flight, so the header can say "checking" rather than "offline". */
    checking: boolean
}

let status: ServerStatus = { reachability: 'unknown', capability: null, checking: false }
const listeners = new Set<() => void>()

function publish(next: ServerStatus): void {
    status = next
    for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => {
        listeners.delete(listener)
    }
}

function snapshot(): ServerStatus {
    return status
}

/**
 * Probe the server and read what it serves.
 *
 * Reachability is settled first and published on its own, so the header can go
 * green the moment the socket answers rather than waiting on the conformance
 * document to parse. A failed CapabilityStatement read after a successful probe
 * leaves reachability 'ok' with no capability - the server is up but is not
 * answering as a FHIR endpoint, and saying "offline" there would be a lie.
 */
export async function refreshServerStatus(): Promise<void> {
    publish({ ...status, checking: true })
    const reachability = await checkReachability()
    if (reachability !== 'ok') {
        publish({ reachability, capability: null, checking: false })
        return
    }
    publish({ ...status, reachability, checking: true })
    try {
        const capability = await readCapabilityStatement()
        publish({ reachability, capability, checking: false })
    } catch {
        publish({ reachability, capability: null, checking: false })
    }
}

/** Subscribe a component to the shared server status. */
export function useServerStatus(): ServerStatus {
    return useSyncExternalStore(subscribe, snapshot, snapshot)
}
