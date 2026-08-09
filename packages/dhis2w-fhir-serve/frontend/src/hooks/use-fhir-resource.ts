import { useEffect, useState } from 'react'

import { readResource } from '@/lib/api'

/** One read in its three honest states, so a detail page never has to guess which it is in. */
export interface FhirResourceState<T> {
    resource: T | null
    loading: boolean
    /** The refusal the server stated, already reduced to its OperationOutcome diagnostics. */
    error: string | null
}

/**
 * Read one resource by type and id.
 *
 * The search sibling loads a whole type; this loads one document, which is what a detail route
 * wants: a code system with several thousand concepts has no business being fetched as part of
 * a listing that only needs its count.
 *
 * Nothing is cached. `d2w fhir serve` answers off a store loaded once at startup, so a re-read
 * costs one request against an in-memory dict and is always what the server currently holds -
 * which is the behaviour a page wants after the server has been restarted under it.
 */
export function useFhirResource<T>(resourceType: string, resourceId: string): FhirResourceState<T> {
    const [resource, setResource] = useState<T | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        setResource(null)
        readResource<T>(resourceType, resourceId)
            .then((read) => {
                if (cancelled) return
                setResource(read)
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setError(failure instanceof Error ? failure.message : String(failure))
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [resourceType, resourceId])

    return { resource, loading, error }
}
