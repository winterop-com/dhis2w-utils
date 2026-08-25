import type { ReactNode } from 'react'

import { CaptureLink } from '@/components/CaptureLink'
import { Badge } from '@/components/ui/badge'
import type { PatientEnrollmentsState } from '@/hooks/use-patient-enrollments'
import { enrollmentStatusLabel, isCompletedEnrollment, type PatientEnrollment } from '@/lib/patients'
import { formatInstant } from '@/lib/spool'

/**
 * What a completed enrollment means for anything filed against it.
 *
 * DHIS2 accepts an event into a completed enrollment with no error and no warning (BUGS.md 70), so
 * nothing downstream will ever tell a person that what they captured went into a closed episode.
 * This sentence is the only place it is said, which is why it is one exported string rather than
 * two paraphrases in two components.
 */
export const COMPLETED_ENROLLMENT_NOTE =
    'DHIS2 accepts new events into a completed enrollment without complaint, so nothing downstream will question one.'

/** The same fact where the enrollment is a choice, so the consequence lands on the person choosing. */
export const COMPLETED_ENROLLMENT_CHOICE_NOTE =
    'This enrollment is completed. DHIS2 accepts new events into a completed enrollment without complaint, so choosing it is deliberate.'

/**
 * The programs one person is already enrolled in, as this DHIS2 instance holds them.
 *
 * READ-ONLY, AND ON A REGISTRATION FORM ON PURPOSE. A registration files a new enrollment; whether
 * the person is already in this program, or in three others, is context nobody can act on from
 * here - but it is the context that tells a person whether they are about to enrol somebody twice.
 * So the listing states what is there and asks nothing.
 *
 * A program outside this project's selection gets no name rather than a guessed one, and its uid is
 * what the row leads with - the guide publishes no name for it, and inventing one would claim a
 * join that was never made.
 *
 * THE LINK OUT IS OPTIONAL AND OFF BY DEFAULT. On a capture form this listing is context beside the
 * questions and a link leaving mid-submission is the last thing it should offer; on a person's own
 * page it is the obvious next question. So the two arguments a Capture address needs are passed by
 * the page that wants the link, and a caller that passes neither gets the listing alone.
 */
export function PatientEnrollmentList({
    state,
    trackedEntityUid = null,
    dhis2BaseUrl = null,
}: {
    state: PatientEnrollmentsState
    /** The person these enrollments belong to; with a base url, each row links into Capture. */
    trackedEntityUid?: string | null
    /** The DHIS2 instance's address, as `/uiconfig` states it, or null when the run resolved none. */
    dhis2BaseUrl?: string | null
}) {
    if (state.loading) {
        return <p className="text-muted-foreground text-xs">Reading this person's enrollments</p>
    }
    if (state.error !== null) {
        return <p className="text-destructive text-xs">This person's enrollments could not be read: {state.error}</p>
    }
    if (state.enrollments.length === 0) {
        return (
            <p className="text-muted-foreground text-xs">
                This DHIS2 instance holds no enrollment for this person.
            </p>
        )
    }
    return (
        <div className="grid gap-2">
            <h4 className="text-sm font-medium">Enrollments this DHIS2 instance holds</h4>
            <ul data-testid="patient-enrollments" className="grid gap-2">
                {state.enrollments.map((enrollment) => (
                    <li key={enrollment.enrollment_uid} className="grid gap-1 rounded-md border p-2">
                        <EnrollmentFacts enrollment={enrollment}>
                            {trackedEntityUid !== null && (
                                <CaptureLink
                                    baseUrl={dhis2BaseUrl}
                                    trackedEntityUid={trackedEntityUid}
                                    enrollment={enrollment}
                                />
                            )}
                        </EnrollmentFacts>
                        {isCompletedEnrollment(enrollment) && (
                            <p className="text-status-received text-xs">{COMPLETED_ENROLLMENT_NOTE}</p>
                        )}
                    </li>
                ))}
            </ul>
        </div>
    )
}

/**
 * One enrollment as a line: which program, what state it is in, when it began, and where.
 *
 * The status is one human spelling of one fact - the wire carries `ACTIVE` and a matching `active`
 * boolean, and rendering both would be the same thing in two casings - with what `active` means
 * for a submission said in words beside it rather than repeated as a second badge.
 */
export function EnrollmentFacts({
    enrollment,
    children,
}: {
    enrollment: PatientEnrollment
    /** Anything the row carries beside the facts - the link out, where a page offers one. */
    children?: ReactNode
}) {
    return (
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-medium">{enrollment.program_name ?? enrollment.program_uid}</span>
            {children}
            <Badge variant="outline" className="text-muted-foreground">
                {enrollmentStatusLabel(enrollment.status)}
            </Badge>
            {enrollment.active && <span className="text-muted-foreground text-xs">open to new events</span>}
            {enrollment.enrolled_at !== null && (
                <span className="text-muted-foreground text-xs">{formatInstant(enrollment.enrolled_at)}</span>
            )}
            {enrollment.organisation_unit_name !== null && (
                <span className="text-muted-foreground text-xs">{enrollment.organisation_unit_name}</span>
            )}
            <span className="machine-identifier text-xs">{enrollment.enrollment_uid}</span>
        </span>
    )
}
