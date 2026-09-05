import { useEffect, useState } from 'react'

import { readTrackedEntityEnrollments } from '@/lib/api'
import type { PatientEnrollment } from '@/lib/patients'

/** What one person's enrollments are answering, in the states a listing has to tell apart. */
export interface PatientEnrollmentsState {
    loading: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
    /** Every program this person is enrolled in, in the order DHIS2 returned them. */
    enrollments: PatientEnrollment[]
}

/** What one read answered, stamped with the tracked entity it was read for. */
export interface AnsweredEnrollments {
    /** The entity the answer is about, or null for the answer that is about nobody. */
    trackedEntityUid: string | null
    error: string | null
    enrollments: PatientEnrollment[]
}

/** Nothing read, which is what the hook holds until an answer lands and what asking about nobody leaves. */
export const NO_ENROLLMENTS_ANSWERED: AnsweredEnrollments = {
    trackedEntityUid: null,
    error: null,
    enrollments: [],
}

/**
 * How a held answer reads against the tracked entity being asked about now.
 *
 * AN ANSWER BELONGS TO THE ENTITY IT WAS READ FOR, and a read that has not landed is in flight
 * rather than empty. An effect runs after the render that starts it, so state that began settled
 * hands the first paint a settled nought - and a summary line counting what it is given then states
 * "0 enrollments" about a person the very next paint shows three of. The same render happens again
 * whenever the uid changes under a mounted component, where the held answer is another entity's.
 * So the answer carries the uid it answered about, and one that is not the uid being asked about is
 * reported as the read it actually is: in flight, with nothing to count.
 *
 * ASKING ABOUT NOBODY IS NOT A READ IN FLIGHT. An empty uid is the state a picker is in before
 * anyone has chosen and the state a control is in with nothing to read for, and there is no request
 * to wait for - so it reads settled and empty, and nothing drawn from it spins.
 */
export function patientEnrollmentsState(
    answered: AnsweredEnrollments,
    trackedEntityUid: string | null,
): PatientEnrollmentsState {
    const wanted = enrollmentsReadFor(trackedEntityUid)
    if (answered.trackedEntityUid !== wanted) {
        return { loading: wanted !== null, error: null, enrollments: [] }
    }
    return { loading: false, error: answered.error, enrollments: answered.enrollments }
}

/**
 * Read which programs one person is enrolled in.
 *
 * WHY IT IS A SECOND READ RATHER THAN PART OF THE SEARCH. A search answers about several people
 * and this answers about one, and the one is whoever was chosen - so asking for it during the
 * search would cost one DHIS2 round trip per result, for a listing nobody has asked to see. It is
 * read when a person is chosen and never before.
 *
 * An empty tracked-entity uid reads nothing, which is the state a control is in before anyone has
 * chosen: asking for `/tracked-entities//enrollments` would be a request whose answer is known to be
 * useless.
 */
export function usePatientEnrollments(trackedEntityUid: string | null): PatientEnrollmentsState {
    const [answered, setAnswered] = useState<AnsweredEnrollments>(NO_ENROLLMENTS_ANSWERED)

    useEffect(() => {
        const wanted = enrollmentsReadFor(trackedEntityUid)
        if (wanted === null) return () => undefined
        let cancelled = false
        readTrackedEntityEnrollments(wanted)
            .then((listing) => {
                if (cancelled) return
                setAnswered({ trackedEntityUid: wanted, error: null, enrollments: listing.enrollments })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setAnswered({
                    trackedEntityUid: wanted,
                    error: failure instanceof Error ? failure.message : String(failure),
                    enrollments: [],
                })
            })
        return () => {
            cancelled = true
        }
    }, [trackedEntityUid])

    return patientEnrollmentsState(answered, trackedEntityUid)
}

/** The entity a read is for, with every way of naming nobody spelled as the one that reads nothing. */
function enrollmentsReadFor(trackedEntityUid: string | null): string | null {
    return trackedEntityUid === null || trackedEntityUid === '' ? null : trackedEntityUid
}
