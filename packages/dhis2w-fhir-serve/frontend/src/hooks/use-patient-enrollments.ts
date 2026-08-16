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
    const [enrollments, setEnrollments] = useState<PatientEnrollment[]>([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (trackedEntityUid === null || trackedEntityUid === '') {
            setEnrollments([])
            setLoading(false)
            setError(null)
            return
        }
        let cancelled = false
        setLoading(true)
        setError(null)
        readTrackedEntityEnrollments(trackedEntityUid)
            .then((listing) => {
                if (cancelled) return
                setEnrollments(listing.enrollments)
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setEnrollments([])
                setError(failure instanceof Error ? failure.message : String(failure))
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [trackedEntityUid])

    return { loading, error, enrollments }
}
