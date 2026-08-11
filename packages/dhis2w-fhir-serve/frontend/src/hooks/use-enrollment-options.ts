import { useCallback, useEffect, useState } from 'react'

import { readResource, readSpool, searchResources } from '@/lib/api'
import {
    enrollmentOptionOf,
    registrationFormForProgram,
    registrationReceiptsFor,
    type EnrollmentOption,
} from '@/lib/enrollments'
import { bundleResources, formIdentifier, formTypeOf, programOf, type Questionnaire, type QuestionnaireResponse } from '@/lib/fhir'

/** What a stage form can answer against, in the states a picker needs to tell apart. */
export interface EnrollmentOfferState {
    /** Whether this form answers against an enrollment at all - false for every non-stage form. */
    active: boolean
    loading: boolean
    /** The refusal a read stated, already reduced to its message. */
    error: string | null
    /** Every enrollment this server knows for the form's program, newest first. */
    options: EnrollmentOption[]
    /** The served id of the program's registration form, for the "capture one first" link. */
    registrationFormId: string | null
    reload: () => void
}

/** An offer that offers nothing - every non-stage form, and a stage form before its reads land. */
const NO_OFFER: Omit<EnrollmentOfferState, 'active' | 'loading' | 'reload'> = {
    error: null,
    options: [],
    registrationFormId: null,
}

/**
 * The enrollments a stage form can answer for, read off this server's own spool.
 *
 * WHY THE SPOOL AND NOT DHIS2. The facade never talks to DHIS2 - `d2w fhir forward` does - so
 * the enrollments it can honestly offer are the ones its own registration receipts minted. That
 * is also the set that matters: a stage capture on this server follows a registration on this
 * server, and the lifecycle state on each option says whether DHIS2 has the pair yet.
 *
 * WHY IT RELOADS ON FOCUS, like use-spool and for the same reason: `d2w fhir forward` is another
 * process renaming receipt files, and the realistic sequence is "forward in the other terminal,
 * come back to the browser" - at which moment a received option should start reading as
 * forwarded without anything being restarted.
 *
 * The per-receipt reads are what fetch the enrollment date - the spool listing derives the pair
 * but never `D2EnrolledAt` - and a read that fails degrades that one option to a dateless row
 * rather than failing the offer.
 */
export function useEnrollmentOptions(questionnaire: Questionnaire | null): EnrollmentOfferState {
    const programUid =
        questionnaire !== null && formTypeOf(questionnaire) === 'tracker-event' ? programOf(questionnaire) : null
    const [options, setOptions] = useState<EnrollmentOption[]>([])
    const [registrationFormId, setRegistrationFormId] = useState<string | null>(null)
    const [loading, setLoading] = useState(programUid !== null)
    const [error, setError] = useState<string | null>(null)
    const [nonce, setNonce] = useState(0)

    const reload = useCallback(() => setNonce((value) => value + 1), [])

    useEffect(() => {
        if (programUid === null) {
            setOptions([])
            setRegistrationFormId(null)
            setLoading(false)
            setError(null)
            return
        }
        let cancelled = false
        setLoading(true)
        readOffer(programUid)
            .then((offer) => {
                if (cancelled) return
                setOptions(offer.options)
                setRegistrationFormId(offer.registrationFormId)
                setError(null)
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setError(failure instanceof Error ? failure.message : String(failure))
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [programUid, nonce])

    useEffect(() => {
        if (programUid === null) return
        const onFocus = () => reload()
        window.addEventListener('focus', onFocus)
        return () => window.removeEventListener('focus', onFocus)
    }, [programUid, reload])

    if (programUid === null) {
        return { active: false, loading: false, reload, ...NO_OFFER }
    }
    return { active: true, loading, error, options, registrationFormId, reload }
}

/** The three reads an offer is made of: the forms, the spool, and each registration receipt. */
async function readOffer(
    programUid: string,
): Promise<{ options: EnrollmentOption[]; registrationFormId: string | null }> {
    const [bundle, spool] = await Promise.all([searchResources<Questionnaire>('Questionnaire'), readSpool()])
    const registrationForm = registrationFormForProgram(bundleResources(bundle), programUid)
    if (registrationForm === null) return { options: [], registrationFormId: null }
    const receipts = registrationReceiptsFor(spool.responses, registrationForm)
    const options = await Promise.all(
        receipts.map(async (summary) => {
            const stored = await readResource<QuestionnaireResponse>(
                'QuestionnaireResponse',
                summary.response_id,
            ).catch(() => null)
            return enrollmentOptionOf(summary, stored)
        }),
    )
    const registrationFormId = formIdentifier(registrationForm)
    return {
        options: options.filter((option): option is EnrollmentOption => option !== null),
        registrationFormId: registrationFormId === '' ? null : registrationFormId,
    }
}
