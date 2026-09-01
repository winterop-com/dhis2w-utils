import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * A heading that opens what is under it.
 *
 * The chevron turns, the button carries `aria-expanded`, and the heading itself is the hit area - so
 * a closed section is one line a reader scans and an open one is the same line with its content
 * beneath. `forced` is what holds a section open against the reader's own clicks - the metadata
 * filter, while somebody is typing - and their choices come back the moment it is let go.
 *
 * THE ROW WEARS `.interactive`, WHICH IS THE WHOLE OF WHAT SAYS IT IS A CONTROL. A heading that is
 * already foreground ink cannot announce itself by darkening on hover: with nothing but the chevron
 * to go on, every row reads as a label, and the only way to find out otherwise is to click one. The
 * class is the app's own answer for a row that opens something - the same wash a card and a menu row
 * take under the pointer, the pointer cursor, and a focus ring drawn inside the row so a keyboard
 * walking the page sees one whole stop. `index.css` argues it.
 *
 * ONE IDIOM, EVERY PLACE SOMETHING UNFOLDS. Translation coverage opens a locale into its table and a
 * tracked entity's record opens an event into its answers; a reader who has learned one has learned
 * the other, which is the reason this is a component and not a shape each page draws for itself.
 */
export function Unfoldable({
    heading,
    forced = false,
    testId,
    className,
    children,
}: {
    heading: ReactNode
    /** Held open by something outside the reader's clicks - a filter, today. */
    forced?: boolean
    testId?: string
    className?: string
    children: ReactNode
}) {
    const [opened, setOpened] = useState(false)
    const unfolded = opened || forced
    return (
        <div className={cn('space-y-2', className)} data-testid={testId}>
            <button
                type="button"
                aria-expanded={unfolded}
                onClick={() => setOpened(!opened)}
                className="interactive -mx-1 flex w-full items-center gap-2 rounded px-1 py-1 text-left"
            >
                {unfolded ? (
                    <ChevronDown className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                ) : (
                    <ChevronRight className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                )}
                {heading}
            </button>
            {unfolded && children}
        </div>
    )
}
