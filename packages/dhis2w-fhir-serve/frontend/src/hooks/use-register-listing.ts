import { useCallback, useEffect, useState } from 'react'

import { listRegister } from '@/lib/api'
import { NO_PATIENT_PAGE, PATIENT_PAGE_SIZE, patientPage, type PatientPage } from '@/lib/patients'

/** One page of the listing, and the two moves that are available from it. */
export interface RegisterListingState {
    page: PatientPage
    loading: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
    /** Ask for the page the current one's `next` link names; does nothing when it names none. */
    showNext: () => void
    /** Ask for the page the current one's `previous` link names; does nothing when it names none. */
    showPrevious: () => void
}

/**
 * Page through the tracked entities one served FHIR resource covers.
 *
 * WHY THE RESOURCE IS AN ARGUMENT. The register is one page per resource the published map names,
 * because DHIS2 tracks whatever a project tracks and a section that mixed people with samples would
 * be paging two different things through one cursor. `/uiconfig` states the resources; each section
 * on screen holds one of these.
 *
 * WHY THE TOKEN IS THE WHOLE STATE. There is no page number here and no offset arithmetic: the
 * server states where the neighbours are and this hook holds the one token it was handed. Moving is
 * therefore always a move the server said was available, and a token is never constructed - which
 * is what makes this UI survive any change to how DHIS2 pages, because it never claimed to know.
 *
 * The consequence is that "previous" is the server's `previous` link rather than a history of what
 * this browser has seen. Those are the same sequence in practice and different in principle, and
 * the link is the one that is true whatever the instance did between two reads.
 *
 * The answer is only accepted while it is still the answer to the token that is current, so a slow
 * first page landing after Next was clicked is dropped rather than replacing the page on screen.
 */
export function useRegisterListing(resource: string, enabled: boolean): RegisterListingState {
    const [token, setToken] = useState<string | null>(null)
    const [page, setPage] = useState<PatientPage>(NO_PATIENT_PAGE)
    const [loading, setLoading] = useState(enabled)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!enabled) {
            setPage(NO_PATIENT_PAGE)
            setLoading(false)
            setError(null)
            return
        }
        let cancelled = false
        setLoading(true)
        setError(null)
        listRegister(resource, token, PATIENT_PAGE_SIZE)
            .then((bundle) => {
                if (cancelled) return
                setPage(patientPage(bundle))
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setPage(NO_PATIENT_PAGE)
                setError(failure instanceof Error ? failure.message : String(failure))
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [enabled, resource, token])

    const showNext = useCallback(() => {
        setToken((current) => page.next ?? current)
    }, [page.next])

    const showPrevious = useCallback(() => {
        setToken((current) => page.previous ?? current)
    }, [page.previous])

    return { page, loading, error, showNext, showPrevious }
}
