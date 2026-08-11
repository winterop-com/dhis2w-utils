/**
 * The enrollments this server knows, joined to the stage form that answers against one.
 *
 * WHY THIS MODULE EXISTS. A tracker stage submission names a tracked entity and an enrollment.
 * The `$generate` skeleton adopts the newest spooled registration's pair for the program and
 * mints synthetic uids - a pair that names nothing real, refused by DHIS2 at forward time
 * (`E1079`/`E1313`: the enrollment does not exist) - only when no registration receipt exists.
 * The real pairs are minted by registration captures and sit in this very server's spool, and
 * which one a stage answers for is the user's call, so the join is entirely local: the stage form names its program on the
 * `{base}/id/program` identifier, the registration form of that program carries the same
 * identifier as its own identity, and every receipt answering the registration form holds one
 * minted pair. This module is that join, pure; the reads live in hooks/use-enrollment-options.ts.
 *
 * WHY THE STORED RESOURCE IS STILL READ. The spool listing derives the tracked entity and the
 * enrollment when it indexes a receipt, but never the enrollment date - `D2EnrolledAt` is a
 * QuestionnaireResponse extension the listing does not surface - and an honest option names when
 * the enrollment it offers began. So the caller reads each registration receipt's stored
 * resource and this module folds the two sources, the spool's derivation winning where both
 * answer because it is the same derivation the Responses page shows.
 */

import { enrolledAtOf, formIdentifier, formTypeOf, programOf, trackedEntityOf, trackerEnrollmentOf, type Questionnaire, type QuestionnaireResponse } from '@/lib/fhir'
import type { ResponseLifecycle, SpoolResponseSummary } from '@/lib/spool'

/**
 * One enrollment this server knows: the minted pair, when it began, and whether DHIS2 has it.
 *
 * `lifecycle` is the honesty of the offer: `forwarded` means the registration reached DHIS2 and
 * the pair names real objects, `received` means the pair exists only in this spool until
 * `d2w fhir forward` runs. `rejected` receipts never become options - DHIS2 refused the
 * registration, so its pair names nothing and never will.
 */
export interface EnrollmentOption {
    /** The receipt the pair was minted by, which is the row to open on the Responses page. */
    responseId: string
    /** The DHIS2 enrollment uid the registration minted. */
    enrollment: string
    /** The DHIS2 tracked-entity uid the registration minted. */
    trackedEntity: string
    /** When the enrollment began, or null when the stored resource could not be read. */
    enrolledAt: string | null
    lifecycle: ResponseLifecycle
    /** When the registration was captured - the recency the default rule orders by. */
    receivedAt: string
}

/**
 * The registration form of one program, out of everything the server serves, or null.
 *
 * Matched on the form kind AND the program identifier, because the program identifier alone is
 * ambiguous two ways: an event program's form carries `{base}/id/program` too (the form is the
 * program), and every stage form of the program carries it as a grouping identifier.
 */
export function registrationFormForProgram(forms: Questionnaire[], programUid: string): Questionnaire | null {
    return forms.find((form) => formTypeOf(form) === 'tracker' && programOf(form) === programUid) ?? null
}

/**
 * The spool rows that answered one registration form, in the listing's newest-first order.
 *
 * Matched on the canonical the receipt names, with the served id as the fallback for a receipt
 * recorded before the form's url was known. Rejected receipts are dropped here rather than
 * badged: DHIS2 refused the registration, so the pair it minted names nothing in DHIS2 and no
 * forwarder run will change that - offering it would be offering a submission that cannot import.
 */
export function registrationReceiptsFor(
    responses: SpoolResponseSummary[],
    registrationForm: Questionnaire,
): SpoolResponseSummary[] {
    const servedId = formIdentifier(registrationForm)
    return responses.filter(
        (summary) =>
            summary.lifecycle !== 'rejected' &&
            (summary.questionnaire === registrationForm.url ||
                (servedId !== '' && summary.questionnaire_id === servedId)),
    )
}

/**
 * One registration receipt as an offerable enrollment, or null when it holds no whole pair.
 *
 * The spool's derivation wins where both sources answer - it is what the Responses page shows,
 * and two spellings of one fact is how a page contradicts itself - and the stored resource fills
 * what the listing does not carry: the enrollment date always, and the pair itself for a receipt
 * the listing could not parse. A receipt yielding no enrollment or no tracked entity is not an
 * option at all, because a submission built from half a pair is refused just as surely as one
 * built from the synthetic draw.
 */
export function enrollmentOptionOf(
    summary: SpoolResponseSummary,
    stored: QuestionnaireResponse | null,
): EnrollmentOption | null {
    const enrollment = summary.tracker_enrollment ?? (stored === null ? null : trackerEnrollmentOf(stored))
    const trackedEntity = summary.tracked_entity ?? (stored === null ? null : trackedEntityOf(stored))
    // An empty string is as far from a DHIS2 uid as a null is - both name nothing.
    if (enrollment === null || enrollment === undefined || enrollment === '') return null
    if (trackedEntity === null || trackedEntity === undefined || trackedEntity === '') return null
    return {
        responseId: summary.response_id,
        enrollment,
        trackedEntity,
        enrolledAt: stored === null ? null : enrolledAtOf(stored),
        lifecycle: summary.lifecycle,
        receivedAt: summary.received_at,
    }
}

/**
 * What a stage form answers against before anyone chooses: the newest forwarded pair, or nothing.
 *
 * Forwarded is the bar because it is the one state in which the pair names objects DHIS2 already
 * holds - a submission against it lands. A received pair is offered but not defaulted: it will
 * import only after the forwarder runs, and a default should not quietly stake a submission on a
 * step nobody has taken yet. Null means no forwarded pair exists to default to - the skeleton
 * already answers for the newest received registration when one exists - and the page says which
 * registration the unpicked submission answers for rather than letting it look ordinary.
 *
 * The options arrive in the spool's newest-first order, so the first forwarded one is the most
 * recent registration DHIS2 has - the person most plausibly being followed up right now.
 */
export function defaultEnrollmentOption(options: EnrollmentOption[]): EnrollmentOption | null {
    return options.find((option) => option.lifecycle === 'forwarded') ?? null
}

/**
 * The selection after the offer reloads: the same enrollment re-read, else what the default says.
 *
 * A reload happens when the window regains focus - the realistic sequence being "run
 * `d2w fhir forward` in the other terminal, come back to the browser" - and the same receipt can
 * have moved from received to forwarded in between. Re-resolving by enrollment uid is what lets
 * the badge and the inline warning catch up without the choice itself moving; a chosen pair that
 * vanished from the offer entirely is kept as chosen, because dropping a person's explicit
 * choice on a background read would submit something they did not pick.
 */
export function reloadedEnrollment(
    current: EnrollmentOption | null,
    options: EnrollmentOption[],
): EnrollmentOption | null {
    if (current === null) return defaultEnrollmentOption(options)
    return options.find((option) => option.enrollment === current.enrollment) ?? current
}
