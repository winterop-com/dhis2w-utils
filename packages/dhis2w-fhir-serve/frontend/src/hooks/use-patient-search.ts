import { useEffect, useState } from 'react'

import { searchRegister } from '@/lib/api'
import {
    bundleOutcome,
    bundleResources,
    REGISTER_IDENTIFIER_SEARCH_PARAMETER,
    type Patient,
    type RegisterSearchKey,
} from '@/lib/fhir'
import {
    patientProjection,
    patientSearchQuery,
    projectionAsOfLine,
    PATIENT_SEARCH_DEBOUNCE_MS,
    type PatientProjection,
} from '@/lib/patients'
import { PEOPLE_RESOURCE_TYPE } from '@/lib/uiconfig'

/** What a patient search is currently answering, in the states a result list has to tell apart. */
export interface PatientSearchState {
    /** The query the last answer is about, or null when nothing has been asked yet. */
    query: string | null
    /** True while a request is in flight, including a re-ask of the same query. */
    searching: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
    /** Every person the instance holds under the searched value, in the server's order. */
    results: PatientProjection[]
    /** How old the copy that answered is, when it was a synced one - see `projectionAsOfLine`. */
    asOf: string | null
}

/** Nothing asked, nothing found - which is what a control holds before anyone has typed. */
const NOTHING_ASKED: PatientSearchState = {
    query: null,
    searching: false,
    error: null,
    results: [],
    asOf: null,
}

/**
 * Search the DHIS2 instance for what somebody typed, once the typing stops.
 *
 * WHAT THE TYPED VALUE IS SEARCHED AGAINST IS THE SERVER'S TO DECIDE. `key` is the search parameter
 * `/metadata` declared for this register - `identifier` on a facade that asks DHIS2 directly, and
 * `_content` where the project keeps a synced copy that can match a substring of any value a person
 * holds. `lib/fhir.registerSearchKey` makes that reading; this hook only sends what it was handed.
 *
 * A NAMED TRACKED ENTITY TYPE NARROWS THE SEARCH TOO. One resource is one register over the union of
 * the types the published map takes onto it, so a register narrowed to one type is narrowed for
 * everything it answers - a search that ignored the narrowing would answer about people the table
 * beneath it is not showing. The tag rides the request as `_tag`; see `lib/api.searchRegister`.
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
export function usePatientSearch(
    typed: string,
    enabled: boolean,
    resource: string = PEOPLE_RESOURCE_TYPE,
    key: RegisterSearchKey = REGISTER_IDENTIFIER_SEARCH_PARAMETER,
    trackedEntityTypeUid: string | null = null,
): PatientSearchState {
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
            searchRegister(resource, query, key, trackedEntityTypeUid)
                .then((answer) => {
                    if (cancelled) return
                    setState({
                        query,
                        searching: false,
                        error: null,
                        results: bundleResources<Patient>(answer.bundle).map(patientProjection),
                        asOf: projectionAsOfLine(answer.projectionAsOf, bundleOutcome(answer.bundle)),
                    })
                })
                .catch((failure: unknown) => {
                    if (cancelled) return
                    setState({
                        query,
                        searching: false,
                        error: failure instanceof Error ? failure.message : String(failure),
                        results: [],
                        asOf: null,
                    })
                })
        }, PATIENT_SEARCH_DEBOUNCE_MS)
        return () => {
            cancelled = true
            clearTimeout(timer)
        }
    }, [key, query, resource, trackedEntityTypeUid])

    return state
}
