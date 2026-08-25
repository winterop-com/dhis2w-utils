import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * What the bar at the foot of the content area is stating.
 *
 * `path` is carried with the words rather than beside them. The bar lives in the shell and the
 * words come from the page, so a page that has been navigated away from would otherwise leave its
 * line under the next one for as long as that one takes to load - a stale count under a screen it
 * is not about. Stamping the route the line was published from lets the bar drop it the instant
 * the address changes, without the shell having to clear anything in an effect that would race the
 * arriving page's own.
 */
export interface StatusLine {
    /** The route this line was published from. */
    path: string
    /** The statement the bar leads with - what is on screen, in numbers. */
    left: string
    /** The note on the right, or null when the page has none. */
    right: string | null
}

/** What a page publishes into, and what the bar reads out of. */
interface StatusBarHolder {
    line: StatusLine | null
    publish: (line: StatusLine) => void
}

const StatusBarContext = createContext<StatusBarHolder | null>(null)

/** Holds the one line the bar is showing, for the whole shell beneath it. */
export function StatusBarProvider({ children }: { children: ReactNode }) {
    const [line, setLine] = useState<StatusLine | null>(null)
    const held = useMemo<StatusBarHolder>(() => ({ line, publish: setLine }), [line])
    return <StatusBarContext.Provider value={held}>{children}</StatusBarContext.Provider>
}

/** The line the page on screen has published, or null while it has published nothing. */
export function useStatusBarLine(): StatusLine | null {
    const held = useContext(StatusBarContext)
    const { pathname } = useLocation()
    const line = held?.line ?? null
    if (line === null) return null
    return line.path === pathname ? line : null
}

/**
 * Publish this page's summary line into the bar.
 *
 * A `left` of null publishes nothing and clears nothing: it is the state a page is in before its
 * reads have landed, and a page whose numbers arrive one read at a time would otherwise blank the
 * bar between them. The bar draws its frame either way, so an unpublished line is an empty bar
 * rather than a missing one - there is no skeleton, because a count nobody has yet is not a count
 * that is loading somewhere on this screen.
 */
export function useStatusLine(left: string | null, right: string | null = null): void {
    const held = useContext(StatusBarContext)
    const { pathname } = useLocation()
    const publish = held?.publish
    useEffect(() => {
        if (left === null || publish === undefined) return
        publish({ path: pathname, left, right })
    }, [left, right, pathname, publish])
}
