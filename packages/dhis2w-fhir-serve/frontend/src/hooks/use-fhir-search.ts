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
    const [answered, setAnswered] = useState<AnsweredSearch<T> | null>(null)
    const [nonce, setNonce] = useState(0)
    const parameterKey = JSON.stringify(parameters)
    const searchKey = `${String(nonce)} ${resourceType} ${parameterKey}`

    const reload = useCallback(() => setNonce((value) => value + 1), [])

    useEffect(() => {
        const wanted = searchKey
        let cancelled = false
        const search = JSON.parse(parameterKey) as Record<string, string>
        searchResources<T>(resourceType, search)
            .then((bundle) => {
                if (cancelled) return
                setAnswered({ searchKey: wanted, resources: bundleResources(bundle), error: null })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setAnswered({
                    searchKey: wanted,
                    resources: [],
                    error: failure instanceof Error ? failure.message : String(failure),
                })
            })
        return () => {
            cancelled = true
        }
    }, [resourceType, parameterKey, searchKey])

    const landed = answered !== null && answered.searchKey === searchKey
    return {
        resources: answered?.resources ?? (NOTHING_FOUND as T[]),
        loading: !landed,
        error: landed ? answered.error : null,
        reload,
    }
}

/** Nothing found yet - one array, so a search in flight hands every render the same empty set. */
const NOTHING_FOUND: never[] = []

/**
 * What one search answered, stamped with the search it was run for.
 *
 * A search that has not landed is in flight rather than empty, and what it last answered stays on
 * screen while the next one runs - so a reload does not blank a table somebody is reading.
 */
interface AnsweredSearch<T> {
    searchKey: string
    resources: T[]
    error: string | null
}
