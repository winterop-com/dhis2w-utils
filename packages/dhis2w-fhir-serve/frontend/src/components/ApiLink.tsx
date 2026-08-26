import { ExternalLink } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { apiConfiguration } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * The query behind a screen, named on the screen and openable from it.
 *
 * EVERY READ THIS APP RENDERS IS A FHIR QUERY, AND THIS IS WHERE THE QUERY IS SAID OUT LOUD. The
 * page below the chip is one reading of the answer; the chip is the answer itself, in the format
 * the server publishes, at a URL an integrator can copy into their own client. That is the whole
 * argument for it: a facade whose job is to be integrated against teaches its API best by showing
 * it where the reader already is, rather than in a document beside the app.
 *
 * `_format=json` is what makes the link openable at all. The FHIR surface answers
 * `application/fhir+json` and refuses a request whose `Accept` rules JSON out, which is what a
 * browser following a bare link sends - so the parameter R4 defines for exactly this case is on
 * every href this component writes.
 */

/** The `_format` value that asks the server for the one format it answers in. */
const JSON_FORMAT_PARAMETER = '_format=json'

/** One FHIR path asking for JSON, joined with whichever separator the path has not used yet. */
export function apiHref(path: string): string {
    return `${path}${path.includes('?') ? '&' : '?'}${JSON_FORMAT_PARAMETER}`
}

/** A quiet chip naming the FHIR query a screen shows, opening the server's own JSON in a new tab. */
export function ApiLink({ path, className }: { path: string; className?: string }) {
    const href = apiHref(path)
    const query = `GET ${href}`
    return (
        // Metadata, not an action: an outline chip in muted text, the size of the identifier badges
        // it sits beside. A reader scanning the page should pass over it, and a reader looking for
        // the API should find it in the same place on every screen.
        <Badge
            asChild
            variant="outline"
            className={cn('text-muted-foreground font-normal', className)}
            data-testid="api-link"
        >
            <a
                href={`${apiConfiguration().baseUrl}${href}`}
                target="_blank"
                rel="noreferrer"
                title={query}
                aria-label={`Open ${query} in a new tab`}
            >
                API
                <ExternalLink aria-hidden />
            </a>
        </Badge>
    )
}
