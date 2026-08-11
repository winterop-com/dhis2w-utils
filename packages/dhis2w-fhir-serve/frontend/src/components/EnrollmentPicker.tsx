import { Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import type { EnrollmentOfferState } from '@/hooks/use-enrollment-options'
import type { EnrollmentOption } from '@/lib/enrollments'
import { formatInstant, LIFECYCLE_LABELS, LIFECYCLE_TINTS } from '@/lib/spool'

/** The one control on a stage form whose id is fixed, so its label and its trigger find each other. */
const CONTROL_ID = 'answering-enrollment'

/**
 * Which enrollment a stage submission answers for.
 *
 * WHY THIS IS NOT A QUESTION. A tracker event hangs off a tracked entity and an enrollment, and
 * nothing in the response's `item` tree carries either - they ride the envelope, beside the
 * organisation unit. So the control sits above the form with the other envelope facts.
 *
 * WHY THE USER PICKS IT AND THE SERVER DOES NOT. This is the one piece of envelope context the
 * `$generate` skeleton gets *wrong* rather than merely proposes: it mints synthetic uids that
 * name nothing in any DHIS2, so an unassisted stage submission is refused at forward time
 * (`E1079`/`E1313` - the enrollment does not exist). The real enrollments are the ones this
 * server's own registration receipts minted, and which person is being followed up is a fact the
 * person filling the form brought with them - exactly the argument the attribute option combo
 * makes.
 *
 * WHY EVERY OPTION STATES ITS LIFECYCLE. A pair from a forwarded registration names objects
 * DHIS2 already holds, so a submission against it lands. A pair from a received one exists only
 * in this spool until `d2w fhir forward` runs - still pickable, because capturing the visit now
 * and forwarding both in order is a legitimate morning, but the wait is said out loud rather
 * than discovered at forward time.
 */
export function EnrollmentPicker({
    offer,
    selected,
    onChange,
}: {
    offer: EnrollmentOfferState
    selected: EnrollmentOption | null
    onChange: (option: EnrollmentOption) => void
}) {
    return (
        <div className="grid gap-2 rounded-lg border p-4">
            <Label htmlFor={CONTROL_ID}>Answering for</Label>
            <p className="text-muted-foreground text-sm">
                The enrollment this event reports against. A registration captured on this server
                mints it, and DHIS2 refuses an event against an enrollment it does not hold.
            </p>
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
                            <SelectItem key={option.enrollment} value={option.enrollment}>
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
                    Nothing is chosen, so this submission keeps the generated draft's synthetic
                    identifiers and will not import into DHIS2. Pick an enrollment above.
                </p>
            )}
            {selected !== null && selected.lifecycle === 'received' && (
                <p className="text-status-received text-xs">
                    DHIS2 has not received this registration yet. Run{' '}
                    <code className="font-mono">d2w fhir forward</code> so the registration lands
                    first - until then this submission cannot import.
                </p>
            )}
        </div>
    )
}

/** What the trigger says while there is nothing to pick from yet. */
function placeholder(loading: boolean, optionCount: number): string {
    if (loading) return 'Reading the enrollments this server knows'
    return optionCount === 0 ? 'No enrollments captured' : 'Not chosen'
}
