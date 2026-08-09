import { useCallback, useEffect, useState } from 'react'

import { searchResources } from '@/lib/api'
import { bundleResources } from '@/lib/fhir'

/** A search in one of its three honest states, so a page never has to guess which it is in. */
export interface FhirSearchState<T> {
    resources: T[]
    loading: boolean
    /** The refusal the server stated, already reduced to its OperationOutcome diagnostics. */
    error: string | null
    /** Run the search again - after a submission, or after the server came back. */
    reload: () => void
}

/**
 * Load every resource of one served type.
 *
 * `d2w fhir serve` answers a search from a store it loaded once at startup and
 * returns the whole set in one Bundle - there is no paging to follow and no
 * `_count` to honour, because there is no database behind it. So this hook is
 * deliberately not a paging abstraction: it reads the Bundle, hands over the
 * resources, and lets the page decide what to show.
 *
 * `parameters` is serialised into the dependency list rather than compared by
 * identity, so a caller can pass an object literal without re-running the search
 * on every render.
 */
export function useFhirSearch<T>(
    resourceType: string,
    parameters: Record<string, string> = {},
): FhirSearchState<T> {
    const [resources, setResources] = useState<T[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [nonce, setNonce] = useState(0)
    const parameterKey = JSON.stringify(parameters)

    const reload = useCallback(() => setNonce((value) => value + 1), [])

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        const search = JSON.parse(parameterKey) as Record<string, string>
        searchResources<T>(resourceType, search)
            .then((bundle) => {
                if (cancelled) return
                setResources(bundleResources(bundle))
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setError(failure instanceof Error ? failure.message : String(failure))
                setResources([])
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [resourceType, parameterKey, nonce])

    return { resources, loading, error, reload }
}
