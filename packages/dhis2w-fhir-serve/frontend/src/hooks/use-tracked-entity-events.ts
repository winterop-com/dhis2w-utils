import { useEffect, useState } from 'react'

import { apiFetch, FACADE_BASE_PATH, FhirRequestError } from '@/lib/api'
import {
    bundleResources,
    canonicalId,
    trackerEnrollmentOf,
    type Bundle,
    type OperationOutcome,
    type QuestionnaireResponse,
} from '@/lib/fhir'

/**
 * What one tracked entity has been through, as `GET /facade/tracked-entities/{uid}/events` answers it.
 *
 * ONE QUESTIONNAIRERESPONSE PER DHIS2 EVENT, of every enrollment the entity holds - the record
 * beside the identity `/{resource}/{uid}` answers and the enrollments
 * `/facade/tracked-entities/{uid}/enrollments` answers. `/metadata` names the address under the
 * register's own resource and `/facade/openapi.json` describes it in full.
 *
 * WHY THE ROWS ARE NOT THE RESPONSES. A served event carries its answers, and a page listing what
 * somebody has been through wants the two facts that place an event - which stage form it answered,
 * and when it happened. So the Bundle is read into that pair here, and the answers stay where they
 * are: opening one is the response page's job, not this listing's.
 */

/** One DHIS2 event of one tracked entity: which form it answered, when, and inside which enrollment. */
export interface TrackedEntityEvent {
    /** The DHIS2 event uid, which is the served response's own id. */
    eventUid: string
    /** The published form the event answered, by the id its canonical names, or null when it names none. */
    formId: string | null
    /** When DHIS2 dates the event, as `authored` states it, or null when the instance stated none. */
    occurredAt: string | null
    /** The DHIS2 enrollment the event belongs to, or null when the served response names none. */
    enrollmentUid: string | null
}

/** One entity's record in the states a section has to tell apart. */
export interface TrackedEntityEventsState {
    loading: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
    /** The events on the first page the server answered, in the order it answered them. */
    events: TrackedEntityEvent[]
    /** How many the instance holds in all, or null when it stated no total. */
    total: number | null
}

/** How many events one page of the record asks for. */
export const TRACKED_ENTITY_EVENT_PAGE_SIZE = 20

/**
 * Read what one tracked entity has been through.
 *
 * A read of its own rather than part of the entity read, for the reason the enrollments are: this
 * costs the DHIS2 instance a request and it answers about the one entity somebody has opened, so it
 * happens when they open one and never before. An empty uid reads nothing, which is the state the
 * page is in before the route has resolved.
 */
export function useTrackedEntityEvents(trackedEntityUid: string | null): TrackedEntityEventsState {
    const [events, setEvents] = useState<TrackedEntityEvent[]>([])
    const [total, setTotal] = useState<number | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (trackedEntityUid === null || trackedEntityUid === '') {
            setEvents([])
            setTotal(null)
            setLoading(false)
            setError(null)
            return
        }
        let cancelled = false
        setLoading(true)
        setError(null)
        readTrackedEntityEvents(trackedEntityUid)
            .then((bundle) => {
                if (cancelled) return
                setEvents(bundleResources<QuestionnaireResponse>(bundle).map(trackedEntityEvent))
                setTotal(bundle.total ?? null)
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setEvents([])
                setTotal(null)
                setError(failure instanceof Error ? failure.message : String(failure))
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [trackedEntityUid])

    return { loading, error, events, total }
}

/**
 * The read itself, through the app's one guarded fetch.
 *
 * Sent with `cache: 'no-store'` for the reason the enrollment listing is: this is an answer about
 * the DHIS2 instance at this moment, and an event captured a minute ago must not be missing from a
 * record because a cached answer was still warm.
 */
async function readTrackedEntityEvents(trackedEntityUid: string): Promise<Bundle<QuestionnaireResponse>> {
    const path =
        `${FACADE_BASE_PATH}/tracked-entities/${encodeURIComponent(trackedEntityUid)}/events` +
        `?_count=${String(TRACKED_ENTITY_EVENT_PAGE_SIZE)}`
    const response = await apiFetch(path, { cache: 'no-store' })
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) throw new FhirRequestError(response.status, body as OperationOutcome | null, path)
    return body as Bundle<QuestionnaireResponse>
}

/** One served response read as the two facts that place an event, and the enrollment it sits in. */
function trackedEntityEvent(response: QuestionnaireResponse): TrackedEntityEvent {
    return {
        eventUid: response.id ?? '',
        formId: canonicalId(response.questionnaire),
        occurredAt: response.authored ?? null,
        enrollmentUid: trackerEnrollmentOf(response),
    }
}
