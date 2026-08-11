import { useEffect, useState } from 'react'

import { searchPatients } from '@/lib/api'
import { bundleResources, type Patient } from '@/lib/fhir'
import {
    patientProjection,
    patientSearchQuery,
    PATIENT_SEARCH_DEBOUNCE_MS,
    type PatientProjection,
} from '@/lib/patients'

/** What a patient search is currently answering, in the states a result list has to tell apart. */
export interface PatientSearchState {
    /** The query the last answer is about, or null when nothing has been asked yet. */
    query: string | null
    /** True while a request is in flight, including a re-ask of the same query. */
    searching: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
    /** Every person the instance holds under the searched identifier value, in the server's order. */
    results: PatientProjection[]
}

/** Nothing asked, nothing found - which is what a control holds before anyone has typed. */
const NOTHING_ASKED: PatientSearchState = { query: null, searching: false, error: null, results: [] }

/**
 * Search the DHIS2 instance for a typed identifier value, once the typing stops.
 *
 * WHY DEBOUNCED AND NOT PER KEYSTROKE. Every call here is a request this server makes of the DHIS2
 * instance - one read plus one filtered search per unique attribute the guide publishes - which
 * makes it the only read in this app whose cost lands on somebody else's database. An eleven
 * character identifier typed straight through would be eleven of those, ten of them answering
 * about prefixes nobody holds. So the query is sent when the typing pauses, and the pause is
 * `PATIENT_SEARCH_DEBOUNCE_MS`.
 *
 * WHY A SHORT QUERY IS NOT SENT AT ALL. `patientSearchQuery` is the rule, and it is in lib/ rather
 * than here so it is testable without a timer: below two characters there is nothing worth asking,
 * and the state falls back to nothing-asked rather than to an empty result - "type more" and
 * "nobody holds that" are different things to say.
 *
 * The answer is only accepted while it is still the answer to what is typed. A slow request for
 * `123` landing after `1234` was typed is dropped, so a result list can never disagree with the
 * box above it.
 */
export function usePatientSearch(typed: string, enabled: boolean): PatientSearchState {
    const [state, setState] = useState<PatientSearchState>(NOTHING_ASKED)
    const query = enabled ? patientSearchQuery(typed) : null

    useEffect(() => {
        if (query === null) {
            setState(NOTHING_ASKED)
            return
        }
        let cancelled = false
        setState((current) => ({ ...current, searching: true }))
        const timer = setTimeout(() => {
            searchPatients(query)
                .then((bundle) => {
                    if (cancelled) return
                    setState({
                        query,
                        searching: false,
                        error: null,
                        results: bundleResources<Patient>(bundle).map(patientProjection),
                    })
                })
                .catch((failure: unknown) => {
                    if (cancelled) return
                    setState({
                        query,
                        searching: false,
                        error: failure instanceof Error ? failure.message : String(failure),
                        results: [],
                    })
                })
        }, PATIENT_SEARCH_DEBOUNCE_MS)
        return () => {
            cancelled = true
            clearTimeout(timer)
        }
    }, [query])

    return state
}
