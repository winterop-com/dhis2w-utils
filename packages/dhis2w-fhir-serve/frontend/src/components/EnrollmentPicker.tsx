import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { COMPLETED_ENROLLMENT_CHOICE_NOTE, EnrollmentFacts } from '@/components/PatientEnrollments'
import { PatientSearch } from '@/components/PatientSearch'
import { ChosenPerson } from '@/components/PersonPicker'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import type { EnrollmentOfferState } from '@/hooks/use-enrollment-options'
import { usePatientEnrollments } from '@/hooks/use-patient-enrollments'
import type { PatientSearchSupport } from '@/hooks/use-patient-search-support'
import type { EnrollmentOption } from '@/lib/enrollments'
import {
    enrollmentsInProgram,
    isCompletedEnrollment,
    type PatientEnrollment,
    type PatientProjection,
} from '@/lib/patients'
import { formatInstant, LIFECYCLE_LABELS, LIFECYCLE_TINTS } from '@/lib/spool'

/** The one control on a stage form whose id is fixed, so its label and its trigger find each other. */
const CONTROL_ID = 'answering-enrollment'

/** The radio ids of the two places an enrollment can come from. */
const SPOOL_SOURCE_ID = 'enrollment-source-spool'
const INSTANCE_SOURCE_ID = 'enrollment-source-instance'

/** Where the enrollment a stage submission answers for was found. */
export type EnrollmentSource = 'spool' | 'instance'

/**
 * Which enrollment a stage submission answers for.
 *
 * WHY THIS IS NOT A QUESTION. A tracker event hangs off a tracked entity and an enrollment, and
 * nothing in the response's `item` tree carries either - they ride the envelope, beside the
 * organisation unit. So the control sits above the form with the other envelope facts.
 *
 * WHY THE USER PICKS IT AND THE SERVER ONLY PROPOSES. The `$generate` skeleton adopts the pair
 * of the newest spooled registration for this program - forwarded preferred - and mints a pair
 * naming nothing only when no registration receipt exists, in which case the submission is
 * refused at forward time (`E1079`/`E1313` - the enrollment does not exist). Which person is
 * being followed up is a fact the person filling the form brought with them - exactly the
 * argument the attribute option combo makes - so the proposal is theirs to override.
 *
 * WHY EVERY OPTION STATES ITS LIFECYCLE. A pair from a forwarded registration names objects
 * DHIS2 already holds, so a submission against it lands. A pair from a received one exists only
 * in this spool until `d2w fhir forward` runs - still pickable, because capturing the visit now
 * and forwarding both in order is a legitimate morning, but the wait is said out loud rather
 * than discovered at forward time.
 *
 * WHY THERE IS A SECOND SOURCE. Everything above is about people registered *on this server*, and
 * a real programme has a great many people registered long before it. When the server publishes
 * patient search - a live process over a project that publishes a registration form - the person
 * can be found in the DHIS2 instance instead, and the enrollments offered are their enrollments in
 * this form's own program: DHIS2 refuses an event filed against an enrollment in another one, so
 * offering the rest would be offering submissions that cannot import. The spool receipts stay the
 * default, because they are the pairs this server minted and is answerable for.
 */
export function EnrollmentPicker({
    offer,
    selected,
    source,
    support,
    programUid,
    onChange,
}: {
    offer: EnrollmentOfferState
    selected: EnrollmentOption | null
    source: EnrollmentSource
    support: PatientSearchSupport
    /** The DHIS2 program uid this stage belongs to, which is the one an instance enrollment must be in. */
    programUid: string | null
    onChange: (source: EnrollmentSource, option: EnrollmentOption | null) => void
}) {
    const offersInstance = support === 'supported'

    return (
        <div className="grid gap-2 rounded-lg border p-4">
            {/* The label names the control the spool source renders; the instance source has a
                search box and a list of choices rather than one select, so there is nothing for a
                `for` to point at and a dangling one would name an element that is not there. */}
            <Label htmlFor={source === 'spool' ? CONTROL_ID : undefined}>Answering for</Label>
            <p className="text-muted-foreground text-sm">
                The enrollment this event reports against. A registration captured on this server
                mints it, and DHIS2 refuses an event against an enrollment it does not hold.
            </p>

            {offersInstance && (
                <fieldset className="grid gap-2">
                    <legend className="text-muted-foreground text-xs">Where this enrollment comes from</legend>
                    <div className="flex flex-wrap items-center gap-4">
                        <div className="flex items-center gap-2">
                            <input
                                id={SPOOL_SOURCE_ID}
                                type="radio"
                                name="enrollment-source"
                                className="accent-primary size-4"
                                checked={source === 'spool'}
                                onChange={() => onChange('spool', null)}
                            />
                            <label htmlFor={SPOOL_SOURCE_ID} className="text-sm">
                                Registrations captured on this server
                            </label>
                        </div>
                        <div className="flex items-center gap-2">
                            <input
                                id={INSTANCE_SOURCE_ID}
                                type="radio"
                                name="enrollment-source"
                                className="accent-primary size-4"
                                checked={source === 'instance'}
                                onChange={() => onChange('instance', null)}
                            />
                            <label htmlFor={INSTANCE_SOURCE_ID} className="text-sm">
                                Enrollments in this DHIS2 instance
                            </label>
                        </div>
                    </div>
                </fieldset>
            )}

            {source === 'spool' ? (
                <SpoolOffer offer={offer} selected={selected} onChange={(option) => onChange('spool', option)} />
            ) : (
                <InstanceOffer
                    programUid={programUid}
                    selected={selected}
                    onChange={(option) => onChange('instance', option)}
                />
            )}
        </div>
    )
}

/** The pairs this server's own registration receipts minted, which is the default path. */
function SpoolOffer({
    offer,
    selected,
    onChange,
}: {
    offer: EnrollmentOfferState
    selected: EnrollmentOption | null
    onChange: (option: EnrollmentOption) => void
}) {
    return (
        <>
            <div className="flex items-center gap-2">
                <Select
                    value={selected?.enrollment ?? ''}
                    disabled={offer.loading || offer.options.length === 0}
                    onValueChange={(enrollment) => {
                        const option = offer.options.find((candidate) => candidate.enrollment === enrollment)
                        if (option !== undefined) onChange(option)
                    }}
                >
                    <SelectTrigger id={CONTROL_ID} className="w-full max-w-md">
                        <SelectValue placeholder={placeholder(offer.loading, offer.options.length)} />
                    </SelectTrigger>
                    <SelectContent>
                        {offer.options.map((option) => (
                            // The three facts on the row are said as three: read off the elements
                            // alone they are one word, "EnMinted00109 Aug 2026, 09:30Received".
                            <SelectItem
                                key={option.enrollment}
                                value={option.enrollment}
                                aria-label={optionLabel(option)}
                            >
                                <span className="font-mono text-xs">{option.enrollment}</span>
                                {option.enrolledAt !== null && (
                                    <span className="text-muted-foreground text-xs">
                                        {formatInstant(option.enrolledAt)}
                                    </span>
                                )}
                                <Badge variant="outline" className={LIFECYCLE_TINTS[option.lifecycle].badge}>
                                    {LIFECYCLE_LABELS[option.lifecycle]}
                                </Badge>
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {offer.loading && (
                    <Loader2 className="text-muted-foreground size-4 shrink-0 animate-spin" aria-hidden />
                )}
            </div>

            {offer.error !== null && (
                <p className="text-destructive text-xs">
                    The enrollments this server knows could not be read: {offer.error}
                </p>
            )}
            {offer.error === null && !offer.loading && offer.options.length === 0 && (
                <p className="text-muted-foreground text-xs">
                    No registration has been captured for this program yet, so this submission uses
                    the generated draft's synthetic identifiers and will not import into DHIS2.{' '}
                    {offer.registrationFormId === null ? (
                        'Capture a registration first.'
                    ) : (
                        <Link to={`/forms/${offer.registrationFormId}`} className="underline underline-offset-2">
                            Capture a registration first.
                        </Link>
                    )}
                </p>
            )}
            {offer.options.length > 0 && selected === null && (
                <p className="text-muted-foreground text-xs">
                    Nothing is chosen, so this submission answers for the newest captured
                    registration - one not yet sent to DHIS2. Pick an enrollment above to answer
                    for a different one.
                </p>
            )}
            {selected !== null && selected.lifecycle === 'received' && (
                <p className="text-status-received text-xs">
                    DHIS2 has not received this registration yet. Run{' '}
                    <code className="font-mono">d2w fhir forward</code> so the registration lands
                    first - until then this submission cannot import.
                </p>
            )}
        </>
    )
}

/**
 * A person found in the DHIS2 instance, and their enrollments in this form's own program.
 *
 * The pair a chosen row sets is real on both halves - the tracked entity uid and the enrollment uid
 * are both DHIS2's own - so a submission built from it imports with no forwarder run standing
 * between it and DHIS2. That is the one thing the spool source can never say, and the reason this
 * source exists.
 */
function InstanceOffer({
    programUid,
    selected,
    onChange,
}: {
    programUid: string | null
    selected: EnrollmentOption | null
    onChange: (option: EnrollmentOption) => void
}) {
    const [patient, setPatient] = useState<PatientProjection | null>(null)
    const enrollments = usePatientEnrollments(patient?.trackedEntityUid ?? null)
    const inProgram = enrollmentsInProgram(enrollments.enrollments, programUid)

    return (
        <div className="grid gap-2">
            {patient === null ? (
                <PatientSearch
                    controlId="answering-identifier"
                    enabled
                    onChoose={(chosen) => setPatient(chosen)}
                />
            ) : (
                <div className="grid gap-2">
                    <ChosenPerson person={patient} />
                    <div>
                        <Button type="button" variant="outline" size="sm" onClick={() => setPatient(null)}>
                            Choose a different person
                        </Button>
                    </div>

                    {enrollments.loading && (
                        <p className="text-muted-foreground text-xs">Reading this person's enrollments</p>
                    )}
                    {enrollments.error !== null && (
                        <p className="text-destructive text-xs">
                            This person's enrollments could not be read: {enrollments.error}
                        </p>
                    )}
                    {!enrollments.loading && enrollments.error === null && inProgram.length === 0 && (
                        <p className="text-muted-foreground text-xs">
                            This DHIS2 instance holds no enrollment in this program for this person.
                            Only this program's enrollments are offered, because DHIS2 refuses an
                            event filed against an enrollment in another one.
                        </p>
                    )}
                    {inProgram.length > 0 && (
                        <ul data-testid="instance-enrollments" className="grid gap-1">
                            {inProgram.map((enrollment) => (
                                <li key={enrollment.enrollment_uid} className="grid gap-1">
                                    <Button
                                        type="button"
                                        variant={
                                            selected?.enrollment === enrollment.enrollment_uid
                                                ? 'secondary'
                                                : 'outline'
                                        }
                                        aria-label={`Answer for the enrollment ${enrollment.enrollment_uid}`}
                                        className="h-auto w-full justify-start px-3 py-2 text-left"
                                        onClick={() =>
                                            onChange(instanceOption(enrollment, patient.trackedEntityUid))
                                        }
                                    >
                                        <EnrollmentFacts enrollment={enrollment} />
                                    </Button>
                                    {isCompletedEnrollment(enrollment) && (
                                        <p className="text-status-received text-xs">
                                            {COMPLETED_ENROLLMENT_CHOICE_NOTE}
                                        </p>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    )
}

/**
 * One instance enrollment as the choice a submission is built from.
 *
 * `lifecycle` reads `forwarded` because that is what the field means - DHIS2 holds this pair - and
 * `responseId` is empty because no receipt on this server minted it. `receivedAt` carries the
 * enrollment date when DHIS2 stated one: the field orders the spool's offer by recency, and an
 * instance enrollment has no capture instant of its own to order by.
 */
function instanceOption(enrollment: PatientEnrollment, trackedEntity: string): EnrollmentOption {
    return {
        responseId: '',
        enrollment: enrollment.enrollment_uid,
        trackedEntity,
        enrolledAt: enrollment.enrolled_at,
        lifecycle: 'forwarded',
        receivedAt: enrollment.enrolled_at ?? '',
    }
}

/** One offered enrollment as a sentence: the pair's handle, when it began, and where it stands. */
function optionLabel(option: EnrollmentOption): string {
    const began = option.enrolledAt === null ? [] : [`enrolled ${formatInstant(option.enrolledAt)}`]
    return [option.enrollment, ...began, LIFECYCLE_LABELS[option.lifecycle]].join(', ')
}

/** What the trigger says while there is nothing to pick from yet. */
function placeholder(loading: boolean, optionCount: number): string {
    if (loading) return 'Reading the enrollments this server knows'
    return optionCount === 0 ? 'No enrollments captured' : 'Not chosen'
}
