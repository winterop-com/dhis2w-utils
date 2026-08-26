import { Link } from 'react-router-dom'
import { useStatusBarLine } from '@/hooks/use-status-bar'

/**
 * The slim bar that closes the content area of every page.
 *
 * WHY IT IS OUTSIDE THE SCROLL. A listing running flush against the bottom of the window says
 * nothing about how much of it is on screen, and the answer to that is the same shape on every
 * page: how many of how many. So the bar sits under the scroll container rather than inside it -
 * the page moves behind it, the line stays - and it lines up with the foot of the navigation rail,
 * which is where the eye already goes for the state of the window rather than the state of the
 * page.
 *
 * WHAT GOES ON IT. The left side is the page's own summary, in numbers. The right side is the one
 * thing that would otherwise have to be inferred from the numbers being smaller than expected -
 * the filter that is on. Both are the page's words: this component holds none of its own, and a
 * page that has published nothing draws the frame empty rather than a skeleton, because a count
 * nobody has yet is not a count arriving.
 */
export function StatusBar() {
    const line = useStatusBarLine()
    const right = line?.right ?? null

    return (
        <footer
            data-testid="status-bar"
            className="bg-card text-muted-foreground flex h-[46px] shrink-0 items-center gap-6 border-t px-4 text-[13px] md:px-8"
        >
            <span data-testid="status-bar-summary" className="min-w-0 flex-1 truncate tabular-nums">
                {line?.trail !== undefined && line.trail.length > 0
                    ? line.trail.map((segment, position) => (
                          <span key={`${segment.label}-${String(position)}`}>
                              {position > 0 && <span aria-hidden> / </span>}
                              {segment.to === null ? (
                                  <span>{segment.label}</span>
                              ) : (
                                  <Link to={segment.to} className="interactive-link">
                                      {segment.label}
                                  </Link>
                              )}
                          </span>
                      ))
                    : (line?.left ?? '')}
            </span>
            {right !== null && right !== '' && (
                <span data-testid="status-bar-note" className="min-w-0 shrink-0 truncate tabular-nums">
                    {right}
                </span>
            )}
        </footer>
    )
}
