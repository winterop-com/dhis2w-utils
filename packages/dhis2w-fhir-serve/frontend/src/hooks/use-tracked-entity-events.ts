import { useEffect, useState } from 'react'

import { apiFetch, FACADE_BASE_PATH, FhirRequestError } from '@/lib/api'
import {
    bundleResources,
    canonicalId,
    trackerEnrollmentOf,
    type Bundle,
    type OperationOutcome,
    type QuestionnaireResponse,
    type QuestionnaireResponseItem,
} from '@/lib/fhir'

/**
 * What one tracked entity has been through, as `GET /facade/tracked-entities/{uid}/events` answers it.
 *
 * ONE QUESTIONNAIRERESPONSE PER DHIS2 EVENT, of every enrollment the entity holds - the record
 * beside the identity `/{resource}/{uid}` answers and the enrollments
 * `/facade/tracked-entities/{uid}/enrollments` answers. `/metadata` names the address under the
 * register's own resource and `/facade/openapi.json` describes it in full.
 *
 * WHAT A ROW CARRIES. The two facts that place an event - which stage form it answered, and when it
 * happened - and the answers themselves, in the tree the document states them in. The two facts are
 * what a reader scans a record by; the answers are what the record is, and an event that could only
 * be read by leaving the record for a page of its own would be a record nobody reads.
 */

/** One DHIS2 event of one tracked entity: which form it answered, when, inside which enrollment, and what it answered. */
export interface TrackedEntityEvent {
    /** The DHIS2 event uid, which is the served response's own id. */
    eventUid: string
    /** The published form the event answered, by the id its canonical names, or null when it names none. */
    formId: string | null
    /** When DHIS2 dates the event, as `authored` states it, or null when the instance stated none. */
    occurredAt: string | null
    /** The DHIS2 enrollment the event belongs to, or null when the served response names none. */
    enrollmentUid: string | null
    /** The answered items of the served response, as it nests them; empty when it carries none. */
    items: QuestionnaireResponseItem[]
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

/** What one read answered, stamped with the tracked entity it was read for. */
export interface AnsweredTrackedEntityEvents {
    /** The entity the answer is about, or null for the answer that is about nobody. */
    trackedEntityUid: string | null
    error: string | null
    events: TrackedEntityEvent[]
    total: number | null
}

/** Nothing read, which is what the hook holds until an answer lands and what asking about nobody leaves. */
export const NO_EVENTS_ANSWERED: AnsweredTrackedEntityEvents = {
    trackedEntityUid: null,
    error: null,
    events: [],
    total: null,
}

/**
 * How a held answer reads against the tracked entity being asked about now.
 *
 * AN ANSWER BELONGS TO THE ENTITY IT WAS READ FOR, and a read that has not landed is in flight
 * rather than empty. An effect runs after the render that starts it, so state that began settled
 * hands the first paint a settled nought - and the summary line under the record then states "0
 * events" over three rows of them, which is what a reader sees before the answer lands. The same
 * render happens again whenever the uid changes under a mounted component, where the held answer is
 * another entity's. So the answer carries the uid it answered about, and one that is not the uid
 * being asked about is reported as the read it actually is: in flight, with nothing to show.
 *
 * ASKING ABOUT NOBODY IS NOT A READ IN FLIGHT. A null uid is what a caller hands this on a run that
 * answers no record and what a page holds before its route has resolved, and there is no request to
 * wait for - so it reads settled and empty, and a section drawn from it never spins.
 */
export function trackedEntityEventsState(
    answered: AnsweredTrackedEntityEvents,
    trackedEntityUid: string | null,
): TrackedEntityEventsState {
    const wanted = eventsReadFor(trackedEntityUid)
    if (answered.trackedEntityUid !== wanted) {
        return { loading: wanted !== null, error: null, events: [], total: null }
    }
    return { loading: false, error: answered.error, events: answered.events, total: answered.total }
}

/**
 * Read what one tracked entity has been through.
 *
 * A read of its own rather than part of the entity read, for the reason the enrollments are: this
 * costs the DHIS2 instance a request and it answers about the one entity somebody has opened, so it
 * happens when they open one and never before. An empty uid reads nothing, which is the state the
 * page is in before the route has resolved and what a run that answers no record hands in - see
 * `lib/uiconfig.trackedEntityRecordOffered`.
 */
export function useTrackedEntityEvents(trackedEntityUid: string | null): TrackedEntityEventsState {
    const [answered, setAnswered] = useState<AnsweredTrackedEntityEvents>(NO_EVENTS_ANSWERED)

    useEffect(() => {
        const wanted = eventsReadFor(trackedEntityUid)
        if (wanted === null) {
            setAnswered(NO_EVENTS_ANSWERED)
            return () => undefined
        }
        let cancelled = false
        readTrackedEntityEvents(wanted)
            .then((bundle) => {
                if (cancelled) return
                setAnswered({
                    trackedEntityUid: wanted,
                    error: null,
                    events: bundleResources<QuestionnaireResponse>(bundle).map(trackedEntityEvent),
                    total: bundle.total ?? null,
                })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setAnswered({
                    trackedEntityUid: wanted,
                    error: failure instanceof Error ? failure.message : String(failure),
                    events: [],
                    total: null,
                })
            })
        return () => {
            cancelled = true
        }
    }, [trackedEntityUid])

    return trackedEntityEventsState(answered, trackedEntityUid)
}

/** The entity a read is for, with every way of naming nobody spelled as the one that reads nothing. */
function eventsReadFor(trackedEntityUid: string | null): string | null {
    return trackedEntityUid === null || trackedEntityUid === '' ? null : trackedEntityUid
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

/** One served response read as the facts that place an event, the enrollment it sits in, and its answers. */
function trackedEntityEvent(response: QuestionnaireResponse): TrackedEntityEvent {
    return {
        eventUid: response.id ?? '',
        formId: canonicalId(response.questionnaire),
        occurredAt: response.authored ?? null,
        enrollmentUid: trackerEnrollmentOf(response),
        items: response.item ?? [],
    }
}
