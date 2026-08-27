import { useEffect, useState } from 'react'

import { readSpool, searchResources } from '@/lib/api'
import { bundleResources, type Questionnaire } from '@/lib/fhir'
import { EMPTY_SPOOL, type SpoolResponseSummary } from '@/lib/spool'

/** What the palette can offer beyond the pages: the forms this server serves, the receipts it holds. */
export interface PaletteCatalogue {
    forms: Questionnaire[]
    receipts: SpoolResponseSummary[]
}

/** The last answer, shared by every mounting of the dialog - see the note below. */
let held: PaletteCatalogue = { forms: [], receipts: EMPTY_SPOOL.responses }

/** Whether the guide's forms have been read in this tab. They cannot change under a running server. */
let formsRead = false

/**
 * The forms served and the receipts held, read the first time the palette is opened.
 *
 * NOTHING IS READ UNTIL THE PALETTE IS OPENED. These two reads exist so a person can type four
 * characters and land on a form; making them on every page load would put a `/Questionnaire` search
 * and a `/facade/spool` walk behind every navigation in the app, for a feature most page views never use.
 * So the hook takes `enabled` and does nothing until it goes true - which is the moment the dialog
 * mounts.
 *
 * THE ANSWERS OUTLIVE THE DIALOG, in module state. The palette is opened, dismissed, and opened
 * again constantly by anyone who uses it, and a per-open fetch would empty the list for a frame each
 * time - so the last answer is held and rendered immediately, and the read that runs behind it
 * replaces it when it lands. This is the same reasoning the auth store is built on: a fact several
 * mountings share is read once for all of them.
 *
 * THE TWO ARE RE-READ ON DIFFERENT SCHEDULES BECAUSE THEY GO STALE DIFFERENTLY. The forms come out
 * of the guide this server loaded at startup - re-reading them can only return the same bytes, so
 * they are read exactly once per tab. The spool is another process renaming receipt files while this
 * tab is open (`d2w fhir forward` is the one doing it), so it is re-read on every open, over
 * whatever the last read produced.
 *
 * A READ THAT FAILS LEAVES THE PREVIOUS ANSWER STANDING and states nothing. There is no error state
 * here on purpose: a palette that rendered a refusal where its rows go would be a worse palette than
 * one that offers pages and no forms, and every one of these rows has a page behind it that reports
 * its own failures properly.
 */
export function usePaletteCatalogue(enabled: boolean): PaletteCatalogue {
    const [catalogue, setCatalogue] = useState<PaletteCatalogue>(held)

    useEffect(() => {
        if (!enabled) return
        let cancelled = false

        if (!formsRead) {
            formsRead = true
            searchResources<Questionnaire>('Questionnaire', {})
                .then((bundle) => {
                    held = { ...held, forms: bundleResources(bundle) }
                    if (!cancelled) setCatalogue(held)
                })
                .catch(() => {
                    // Read again the next time the palette opens: a server that was not there yet
                    // is one this tab may well reach later.
                    formsRead = false
                })
        }

        readSpool()
            .then((listing) => {
                held = { ...held, receipts: listing.responses }
                if (!cancelled) setCatalogue(held)
            })
            .catch(() => {
                // As above: the rows this tab already has stay, and the Responses page is where a
                // spool that cannot be read is reported.
            })

        return () => {
            cancelled = true
        }
    }, [enabled])

    return catalogue
}
