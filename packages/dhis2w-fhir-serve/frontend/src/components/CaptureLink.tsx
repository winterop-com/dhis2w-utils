import { ExternalLink } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { captureEnrollmentUrl } from '@/lib/dhis2'
import type { PatientEnrollment } from '@/lib/patients'
import { cn } from '@/lib/utils'

/**
 * The way from one enrollment on this page into that enrollment in the DHIS2 instance.
 *
 * The same mark and the same manners as `MaintenanceLink`, pointed at the other app: a person is
 * not metadata, so the screen that opens one is Capture's enrollment dashboard rather than a
 * Maintenance edit form. It renders nothing when the server named no instance - the ordinary state
 * of a run that resolved no profile - and nothing when the enrollment names no program, because
 * Capture answers a program-less address with a chooser rather than with the person's record.
 *
 * THE ACCESSIBLE NAME SAYS WHERE IT GOES, in full and in words, for the same reason it does on the
 * Maintenance link: a bare icon beside a row of uids says nothing on its own, and a link must state
 * that it leaves this page before it is followed. The same sentence is the tooltip.
 */
export function CaptureLink({
    baseUrl,
    trackedEntityUid,
    enrollment,
    className,
}: {
    /** The DHIS2 instance's address, as `/uiconfig` states it, or null when the run resolved none. */
    baseUrl: string | null
    /** The person's DHIS2 tracked entity uid - the same uid this page is already showing. */
    trackedEntityUid: string
    enrollment: PatientEnrollment
    className?: string
}) {
    const href = captureEnrollmentUrl(baseUrl, trackedEntityUid, enrollment)
    if (href === null) return null
    const label = `Open the enrollment ${enrollment.enrollment_uid} in this DHIS2 instance's Capture app`

    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <a
                    href={href}
                    target="_blank"
                    rel="noreferrer noopener"
                    aria-label={label}
                    data-testid="capture-link"
                    className={cn(
                        'text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 inline-flex shrink-0 items-center rounded focus-visible:ring-[3px] focus-visible:outline-none',
                        className,
                    )}
                >
                    <ExternalLink className="size-3.5" aria-hidden />
                </a>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
        </Tooltip>
    )
}
