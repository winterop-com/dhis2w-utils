import type { ReactNode } from 'react'
import { Loader2, ServerCrash } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'

/**
 * The three states every listing lands in, rendered the same way everywhere.
 *
 * The point is not the markup - it is that "loading", "the server refused", and
 * "the server answered with nothing" stay three distinct states all the way to
 * the screen. Collapsing the last two into one empty table is how a project that
 * has not run `make sushi` yet gets told it has no forms, when what it has is no
 * compiled IG.
 */
export function PageState({
    loading,
    error,
    empty,
    emptyMessage,
    emptyRender,
    children,
}: {
    loading: boolean
    error: string | null
    empty: boolean
    /** The one line the default empty card states. Omitted when `emptyRender` supplies the card. */
    emptyMessage?: string
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
                        <p className="text-sm font-medium">The server refused this read</p>
                        <p className="text-muted-foreground font-mono text-xs break-words">{error}</p>
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
