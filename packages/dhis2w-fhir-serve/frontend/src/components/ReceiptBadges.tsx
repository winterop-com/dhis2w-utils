import { TriangleAlert } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FORM_TYPE_LABELS } from '@/lib/fhir'
import { LIFECYCLE_LABELS, LIFECYCLE_TINTS, type SpoolResponseSummary } from '@/lib/spool'

/**
 * The two badges a receipt is recognised by, wherever it is rendered.
 *
 * The listing and the receipt page both state a receipt's lifecycle and its form kind, and the
 * tint carries meaning - the status tokens are shared with the rest of the app - so the two
 * spellings have to be one spelling. A page that tinted `rejected` its own way would be saying
 * something slightly different about the same file on disk.
 */

/** Which spool directory the receipt is in, tinted by the shared lifecycle tokens. */
export function LifecycleBadge({
    summary,
    showWarnings = true,
}: {
    summary: SpoolResponseSummary
    /** Off where the warnings get a section of their own, so the icon is not a second copy. */
    showWarnings?: boolean
}) {
    return (
        <span className="flex items-center gap-1.5">
            <Badge variant="outline" className={LIFECYCLE_TINTS[summary.lifecycle].badge}>
                {LIFECYCLE_LABELS[summary.lifecycle]}
            </Badge>
            {showWarnings && summary.warnings.length > 0 && (
                <Tooltip>
                    <TooltipTrigger asChild>
                        <TriangleAlert
                            className="text-status-refused size-3.5 shrink-0"
                            aria-label={`${summary.warnings.length} ${summary.warnings.length === 1 ? 'warning' : 'warnings'} recorded on capture`}
                        />
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                        {summary.warnings.length}{' '}
                        {summary.warnings.length === 1 ? 'warning' : 'warnings'} recorded when this
                        was captured
                    </TooltipContent>
                </Tooltip>
            )}
        </span>
    )
}

/** The DHIS2 object kind the receipt was validated as, or a stated absence. */
export function FormKindBadge({ kind }: { kind: string }) {
    const known = (FORM_TYPE_LABELS as Record<string, string | undefined>)[kind]
    if (!known) {
        return (
            <Badge variant="outline" className="text-muted-foreground">
                {kind || 'no form type'}
            </Badge>
        )
    }
    return <Badge variant="secondary">{known}</Badge>
}
