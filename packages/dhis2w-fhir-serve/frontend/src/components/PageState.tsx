import type { ReactNode } from 'react'
import { Loader2, ServerCrash } from 'lucide-react'

import { ProseText } from '@/components/ProseText'
import { Card, CardContent } from '@/components/ui/card'

/** What the card is headed when the server turned a read down. */
export const READ_REFUSED_HEADING = 'The server refused this read'

/** What it is headed when the read reached the server and there was nothing under the id. */
export const NOTHING_UNDER_THAT_ID_HEADING = 'This server has nothing under that id'

/** What it is headed when nothing answered the request at all. */
export const NOT_ANSWERING_HEADING = 'This server is not answering'

/** What the read came back as, when the caller kept it: an HTTP status, or no answer at all. */
export type ReadOutcome = number | 'unreachable'

/**
 * The heading over a failed read, by what the server answered.
 *
 * A 404 IS NOT A REFUSAL. "Refused" is what this app calls a submission the capture validator turned
 * down, and it is used that way on every other screen - so heading a missing form with it says the
 * server declined to answer, when what it did was answer that it holds no such thing. A request
 * nothing answered is not a refusal either: there was nobody there to refuse it. Every other status
 * is a refusal and keeps the word.
 *
 * The id is never in the heading. The diagnostic underneath already carries it, and the page above
 * already names what was asked for - three copies of one identifier is not three facts.
 */
export function pageStateHeading(outcome: ReadOutcome | null | undefined): string {
    if (outcome === 'unreachable') return NOT_ANSWERING_HEADING
    if (outcome === 404) return NOTHING_UNDER_THAT_ID_HEADING
    return READ_REFUSED_HEADING
}

/**
 * The three states every listing lands in, rendered the same way everywhere.
 *
 * The point is not the markup - it is that "loading", "the server refused", and
 * "the server answered with nothing" stay three distinct states all the way to
 * the screen. Collapsing the last two into one empty table is how a project that
 * has not run the compile step yet gets told it has no forms, when what it has
 * is no compiled implementation guide.
 *
 * WHY THE TWO MESSAGES ARE NODES AND NOT STRINGS. Both of them name commands,
 * paths, and settings - and a command inside a sentence is set in the mono face,
 * which a string cannot carry. A caller writing one spells the machine parts as
 * `<code className="font-mono">` the way prose elsewhere in the app does, rather
 * than as backticks a browser renders as the characters they are.
 */
export function PageState({
    loading,
    error,
    status,
    empty,
    emptyMessage,
    emptyRender,
    children,
}: {
    loading: boolean
    /**
     * What the server said when it refused, or the sentence to state in place of it.
     *
     * A bare string is the server's own diagnostic, arriving as the server wrote it - a sentence
     * that marks its machine spellings with backticks - so it is drawn through `ProseText`, which
     * is what turns a mark into a change of face. A node is prose the caller has already spelled,
     * and is rendered as written.
     */
    error: ReactNode
    /**
     * How the read came back, when the caller kept that. Decides the heading over the card.
     *
     * Optional because several reads reach this having already reduced their failure to a sentence.
     * A caller that still holds the status passes it, and a 404 is then headed as the absence it is
     * rather than as a refusal - see `pageStateHeading`.
     */
    status?: ReadOutcome | null
    empty: boolean
    /** The one line the default empty card states. Omitted when `emptyRender` supplies the card. */
    emptyMessage?: ReactNode
    /**
     * An empty state that is more than a sentence.
     *
     * Some empties are an invitation rather than a report - "nothing captured yet" is most useful
     * with the way to capture the first thing next to it. Those get the whole card, in place of
     * the sentence, rather than a paragraph that names an action a reader then has to go and find.
     */
    emptyRender?: ReactNode
    children: ReactNode
}) {
    if (loading) {
        return (
            <Card>
                <CardContent className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    Reading from the server
                </CardContent>
            </Card>
        )
    }
    if (error) {
        return (
            <Card>
                <CardContent className="flex items-start gap-3 py-8">
                    <ServerCrash className="text-destructive mt-0.5 size-4 shrink-0" aria-hidden />
                    <div className="space-y-1">
                        <p className="text-sm font-medium">{pageStateHeading(status)}</p>
                        <p className="text-muted-foreground text-xs break-words">
                            {typeof error === 'string' ? <ProseText text={error} /> : error}
                        </p>
                    </div>
                </CardContent>
            </Card>
        )
    }
    if (empty) {
        if (emptyRender !== undefined) return <>{emptyRender}</>
        return (
            <Card>
                <CardContent className="text-muted-foreground py-8 text-sm">{emptyMessage}</CardContent>
            </Card>
        )
    }
    return <>{children}</>
}

/** A page's heading and one line saying what the page is for. */
export function PageHeader({ title, description }: { title: string; description: string }) {
    return (
        <div className="mb-6 space-y-1">
            <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
            <p className="text-muted-foreground text-sm">{description}</p>
        </div>
    )
}
