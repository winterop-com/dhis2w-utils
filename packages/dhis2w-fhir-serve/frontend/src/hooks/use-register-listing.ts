import { useCallback, useEffect, useState } from 'react'

import { listRegister } from '@/lib/api'
import { bundleOutcome } from '@/lib/fhir'
import {
    NO_PATIENT_PAGE,
    PATIENT_PAGE_SIZE,
    patientPage,
    projectionAsOfLine,
    type PatientPage,
} from '@/lib/patients'

/** One page of the listing, and the two moves that are available from it. */
export interface RegisterListingState {
    page: PatientPage
    loading: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
    /** How old the copy that answered is, when it was a synced one - see `projectionAsOfLine`. */
    asOf: string | null
    /** Ask for the page the current one's `next` link names; does nothing when it names none. */
    showNext: () => void
    /** Ask for the page the current one's `previous` link names; does nothing when it names none. */
    showPrevious: () => void
}

/** Where one listing currently is: which register, narrowed to what, at which of the server's pages. */
interface ListingPlace {
    resource: string
    /** The tracked entity type the walk is inside, or null when it is over every type the register serves. */
    trackedEntityTypeUid: string | null
    /** The `{uid}|{value}` the walk is filtered by, or null when it is over every value the register holds. */
    attributeFilter: string | null
    token: string | null
}

/**
 * Page through the tracked entities one served FHIR resource covers.
 *
 * WHY THE RESOURCE IS AN ARGUMENT. The register is one page per resource the published map names,
 * because DHIS2 tracks whatever a project tracks and a section that mixed people with samples would
 * be paging two different things through one cursor. `/uiconfig` states the resources; each section
 * on screen holds one of these.
 *
 * WHY THE TYPE IS ANOTHER. One resource is one register over the union of the tracked entity types
 * the published map takes onto it, and `_tag` is how a caller asks that register about one of them.
 * A narrowing is a different scope rather than a filter over the page on screen, so choosing one
 * starts the walk again at the server's first page: a token names a place inside a scope, and it
 * means nothing in the scope next door.
 *
 * WHY THE ATTRIBUTE VALUE FILTER IS A THIRD. `d2-attribute={uid}|{value}` narrows the register to
 * whoever holds that value exactly, and it is a scope for the same reason the tag is: a token names a
 * place inside a scope, so changing what is being filtered for starts the walk at the server's first
 * page rather than at a page of a set nobody is looking at any more.
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
export function useRegisterListing(
    resource: string,
    enabled: boolean,
    trackedEntityTypeUid: string | null = null,
    attributeFilter: string | null = null,
): RegisterListingState {
    const [place, setPlace] = useState<ListingPlace>({
        resource,
        trackedEntityTypeUid,
        attributeFilter,
        token: null,
    })
    const [page, setPage] = useState<PatientPage>(NO_PATIENT_PAGE)
    const [loading, setLoading] = useState(enabled)
    const [error, setError] = useState<string | null>(null)
    const [asOf, setAsOf] = useState<string | null>(null)
    // The scope the caller is asking about now, with the token dropped when it is a different one -
    // read rather than written, so a new narrowing asks for its first page in the same render
    // instead of asking for the old scope's token first and correcting itself.
    const at: ListingPlace =
        place.resource === resource &&
        place.trackedEntityTypeUid === trackedEntityTypeUid &&
        place.attributeFilter === attributeFilter
            ? place
            : { resource, trackedEntityTypeUid, attributeFilter, token: null }
    const token = at.token

    useEffect(() => {
        if (!enabled) {
            setPage(NO_PATIENT_PAGE)
            setLoading(false)
            setError(null)
            setAsOf(null)
            return
        }
        let cancelled = false
        setLoading(true)
        setError(null)
        listRegister(resource, token, PATIENT_PAGE_SIZE, trackedEntityTypeUid, attributeFilter)
            .then((answer) => {
                if (cancelled) return
                setPage(patientPage(answer.bundle))
                setAsOf(projectionAsOfLine(answer.projectionAsOf, bundleOutcome(answer.bundle)))
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setPage(NO_PATIENT_PAGE)
                setError(failure instanceof Error ? failure.message : String(failure))
                setAsOf(null)
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [attributeFilter, enabled, resource, token, trackedEntityTypeUid])

    const showNext = useCallback(() => {
        if (page.next === null) return
        setPlace({ resource, trackedEntityTypeUid, attributeFilter, token: page.next })
    }, [attributeFilter, page.next, resource, trackedEntityTypeUid])

    const showPrevious = useCallback(() => {
        if (page.previous === null) return
        setPlace({ resource, trackedEntityTypeUid, attributeFilter, token: page.previous })
    }, [attributeFilter, page.previous, resource, trackedEntityTypeUid])

    return { page, loading, error, asOf, showNext, showPrevious }
}
