import { useEffect, useState } from 'react'

import { FhirRequestError, readResource } from '@/lib/api'

/** One read in its three honest states, so a detail page never has to guess which it is in. */
export interface FhirResourceState<T> {
    resource: T | null
    loading: boolean
    /** The refusal the server stated, already reduced to its OperationOutcome diagnostics. */
    error: string | null
    /** The HTTP status behind the error, so a page can head a 404 as the absence it is. */
    status: number | null
}

/** What one read answered, stamped with the type and id it was made for. */
interface KeyedRead<T> extends FhirResourceState<T> {
    key: string
}

/** The type and id as one value, which is what decides whether a held answer is still this read's. */
function readKey(resourceType: string, resourceId: string): string {
    return `${resourceType}/${resourceId}`
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
 *
 * An empty id reads nothing. That is the state a page is in while the id is still being derived
 * from another read - the receipt page learns which form to read from the receipt - and asking
 * for `/{type}/` would be a request whose answer is known to be useless.
 *
 * AN ANSWER BELONGS TO THE ARGUMENTS IT WAS READ FOR. A detail route that changes id keeps the same
 * component mounted, so the render after the change happens before the effect that starts the new
 * read - and state alone would hand that render the previous document, under the new address. That
 * one render is long enough for a child to publish something about it: the terminology page's
 * status line stamped "Showing 11 of 11 concepts" with the id of a resource this server holds
 * nothing under, and the line then stood because nothing published over it. So the held answer
 * carries the key it was read for, and an answer whose key is not the current one is reported as
 * the read it actually is - in flight, with nothing to show.
 */
export function useFhirResource<T>(resourceType: string, resourceId: string): FhirResourceState<T> {
    const key = readKey(resourceType, resourceId)
    const [read, setRead] = useState<KeyedRead<T>>({
        key,
        resource: null,
        loading: resourceId !== '',
        error: null,
        status: null,
    })

    useEffect(() => {
        const wanted = readKey(resourceType, resourceId)
        if (resourceId === '') {
            setRead({ key: wanted, resource: null, loading: false, error: null, status: null })
            return () => undefined
        }
        let cancelled = false
        setRead({ key: wanted, resource: null, loading: true, error: null, status: null })
        readResource<T>(resourceType, resourceId)
            .then((answer) => {
                if (cancelled) return
                setRead({ key: wanted, resource: answer, loading: false, error: null, status: null })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setRead({
                    key: wanted,
                    resource: null,
                    loading: false,
                    error: failure instanceof Error ? failure.message : String(failure),
                    status: failure instanceof FhirRequestError ? failure.status : null,
                })
            })
        return () => {
            cancelled = true
        }
    }, [resourceType, resourceId])

    if (read.key !== key) {
        return { resource: null, loading: resourceId !== '', error: null, status: null }
    }
    return { resource: read.resource, loading: read.loading, error: read.error, status: read.status }
}
