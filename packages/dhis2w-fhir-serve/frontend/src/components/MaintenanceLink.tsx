import { ExternalLink } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { MAINTENANCE_OBJECT_LABELS, maintenanceUrl, type MaintenanceObject } from '@/lib/dhis2'
import { cn } from '@/lib/utils'

/**
 * The way out of this guide and into the instance it was generated from.
 *
 * A small external-link mark beside an identity - an organisation unit's name, a form's title, a
 * data element's row - opening that object's own page in the DHIS2 instance's Metadata Management
 * app. It renders nothing at all when the server named no instance, which is the ordinary state of
 * a compiled guide served on a machine that resolved no profile: no address, no link, and no
 * affordance suggesting there is one.
 *
 * THE ACCESSIBLE NAME SAYS WHERE IT GOES, in full and in words - which object, of which kind, and
 * into which application - because a bare icon in a table of eleven-character uids says nothing on
 * its own, and "opens elsewhere" is exactly the thing a link must state before it is followed. The
 * same sentence is the tooltip, so a pointer and a screen reader are told the same thing.
 *
 * `noreferrer noopener` on a new tab: the instance is another origin, and a page this one opened
 * has no business holding a handle back to it.
 */
export function MaintenanceLink({
    baseUrl,
    object,
    uid,
    subject,
    className,
}: {
    /** The DHIS2 instance's address, as `/facade/uiconfig` states it, or null when the run resolved none. */
    baseUrl: string | null
    object: MaintenanceObject
    /** The object's DHIS2 uid - the same uid this page is already showing. */
    uid: string | null
    /** What the object is called here, so the link's own name states its subject rather than a uid. */
    subject: string
    className?: string
}) {
    const href = maintenanceUrl(baseUrl, object, uid)
    if (href === null) return null
    // THE APP IS NAMED BECAUSE THE LINK OPENS IT. Every kind this component takes has a by-uid edit
    // route in Metadata Management, so there is one app to name and no kind left behind on the
    // retired Maintenance screens - see `METADATA_MANAGEMENT_COLLECTIONS` for what was checked.
    const label = `Open the ${MAINTENANCE_OBJECT_LABELS[object]} ${subject} in this DHIS2 instance's Metadata Management app`

    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <a
                    href={href}
                    target="_blank"
                    rel="noreferrer noopener"
                    aria-label={label}
                    data-testid="maintenance-link"
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
