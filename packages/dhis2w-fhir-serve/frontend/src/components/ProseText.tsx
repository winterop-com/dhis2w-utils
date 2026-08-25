/** A server-authored sentence, with the spellings it marks as a machine's set in the mono face. */
import { proseRuns } from '@/lib/reference'

/**
 * The server quotes machine spellings with backtick marks - identifiers, commands, endpoint
 * paths - and a mark is a change of typeface, never a character on the screen. Every surface
 * that prints a server-authored sentence renders it through here, so one convention holds
 * across refusals, capability prose, and diagnostics alike.
 */
export function ProseText({ text }: { text: string }) {
    return (
        <>
            {proseRuns(text).map((run, position) =>
                run.code ? (
                    <code key={`${String(position)}:${run.text}`} className="font-mono">
                        {run.text}
                    </code>
                ) : (
                    <span key={`${String(position)}:${run.text}`}>{run.text}</span>
                ),
            )}
        </>
    )
}
