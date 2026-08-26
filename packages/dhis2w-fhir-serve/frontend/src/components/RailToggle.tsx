import { PanelRightClose, PanelRightOpen } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/**
 * The collapse control every right-hand rail wears, anchored so it never moves.
 *
 * ONE TOGGLE, ONE CORNER. The control is `absolute top-1 right-1` inside a `relative` rail, and
 * every rail column sits flush with the page's right edge - which is what makes the collapsed and
 * expanded positions the same pixel. A page never places this control itself: it renders the rail
 * `relative`, mounts this at the top, and pads its own content below (`pt-10` clears it). That
 * rule living here is what keeps the next rail from re-deriving it slightly differently.
 */
export function RailToggle({
    open,
    railName,
    onToggle,
}: {
    /** Whether the rail is expanded, which decides the icon and the spoken direction. */
    open: boolean
    /** What the rail holds, spoken in the label: "the details panel", "the examples panel". */
    railName: string
    onToggle: () => void
}) {
    const label = `${open ? 'Collapse' : 'Expand'} ${railName}`
    return (
        <div className="absolute top-1 right-1 z-10">
            <Tooltip>
                <TooltipTrigger asChild>
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={onToggle}
                        aria-label={label}
                        className="text-muted-foreground hover:text-foreground"
                    >
                        {open ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
                    </Button>
                </TooltipTrigger>
                <TooltipContent side="left">{label}</TooltipContent>
            </Tooltip>
        </div>
    )
}
