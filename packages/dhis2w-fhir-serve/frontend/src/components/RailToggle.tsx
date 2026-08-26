import { PanelRightClose, PanelRightOpen } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/**
 * The collapse control every right-hand rail wears, anchored so it never moves.
 *
 * ONE TOGGLE, ONE CORNER. The control is pinned to the top right of a `relative` rail, and every
 * rail column sits flush with the page's right edge - which is what makes the collapsed and
 * expanded positions the same pixel. A page never places this control itself: it renders the rail
 * `relative`, mounts this at the top, and pads its own content below (`pt-10` clears it). That rule
 * living here is what keeps the next rail from re-deriving it slightly differently.
 *
 * THE TWO OFFSETS ARE THE PART THAT HAS TO BE EXACT, so they are stated once here rather than per
 * page. `right-0` lands the button's right edge on the same column the page's right-aligned counts
 * and headings land on - an inset of even four pixels reads as the one control on the screen that
 * missed the grid. `-top-1` raises the 32px button so its centre lands 12px into the row, which is
 * the centre of the 24px heading line the panel beside it opens with, instead of half a line below
 * the words it shares that line with.
 *
 * A COLLAPSED RAIL IS EXACTLY THIS BUTTON WIDE. `RAIL_TOGGLE_GUTTER` is the placeholder a page
 * renders in place of the panel, sized from the same button, so folding a rail away does not leave
 * the control stranded in a gutter wider than itself.
 */
export const RAIL_TOGGLE_GUTTER = 'size-8'

export function RailToggle({
    open,
    railName,
    onToggle,
}: {
    /** Whether the rail is expanded, which decides the icon and the spoken direction. */
    open: boolean
    /** What the rail holds, spoken in the label: "the organisation unit details", "the examples". */
    railName: string
    onToggle: () => void
}) {
    const label = `${open ? 'Collapse' : 'Expand'} ${railName}`
    return (
        <div className="absolute -top-1 right-0 z-10">
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
