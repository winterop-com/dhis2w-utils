/**
 * The receipt spool as `GET /spool` answers it - the one non-FHIR shape this UI reads.
 *
 * WHY THIS IS NOT IN lib/fhir.ts. Everything in that module is an R4 resource
 * served as `application/fhir+json`. This is not: it is the receipt *envelope*
 * the facade records around each submission - when it was accepted, which DHIS2
 * form kind it was validated as, which of the spool's three directories the file
 * now sits in, and what DHIS2 said when it refused one. None of those are
 * QuestionnaireResponse elements, and the Python side argues the choice in full
 * in `dhis2w_fhir_serve.routes.spool`. Keeping the two type sets apart is what
 * stops a reader assuming `lifecycle` is something FHIR knows about.
 *
 * The field names are snake_case because that is what the Pydantic models on the
 * other side emit. Renaming them here would put a translation layer between two
 * files that have to stay in step, and hide which name to grep for.
 *
 * Everything in this module is pure. Nothing fetches; `readSpool` in lib/api.ts
 * is the only caller of the network.
 */

/**
 * Which of the spool's three directories a receipt currently sits in.
 *
 * These are states of a *file*, and the whole reason the Responses page has a
 * reload button: `d2w fhir forward` renames receipts between the directories
 * from another process, so what this says can change with nothing happening in
 * the browser at all.
 */
export const RESPONSE_LIFECYCLES = ['received', 'forwarded', 'rejected'] as const

/** One lifecycle state a stored receipt can be in. */
export type ResponseLifecycle = (typeof RESPONSE_LIFECYCLES)[number]

/** How each state is named in the UI, and what it actually means. */
export const LIFECYCLE_LABELS: Record<ResponseLifecycle, string> = {
    received: 'Received',
    forwarded: 'Forwarded',
    rejected: 'Rejected',
}

/** One line per state, for the filter tooltips and the empty-state prose. */
export const LIFECYCLE_HINTS: Record<ResponseLifecycle, string> = {
    received: 'Captured, not yet sent to DHIS2. `d2w fhir forward` sends it.',
    forwarded: 'Translated, posted, and accepted by DHIS2.',
    rejected: 'Posted and refused by DHIS2. The import report says why.',
}

/**
 * The theme token each state is tinted with.
 *
 * The tokens are declared in index.css and shared with the rest of the app -
 * `received` is the identity blue because a receipt on disk is the resting
 * state rather than a warning, `forwarded` is the success hue, `rejected` the
 * destructive one. Kept as full class strings rather than built by
 * interpolation: Tailwind scans source text for class names, and
 * `bg-status-${state}` is a name it never sees.
 */
export const LIFECYCLE_TINTS: Record<ResponseLifecycle, { dot: string; badge: string }> = {
    received: {
        dot: 'bg-status-received',
        badge: 'border-status-received/40 text-status-received bg-status-received/10',
    },
    forwarded: {
        dot: 'bg-status-forwarded',
        badge: 'border-status-forwarded/40 text-status-forwarded bg-status-forwarded/10',
    },
    rejected: {
        dot: 'bg-status-rejected',
        badge: 'border-status-rejected/40 text-status-rejected bg-status-rejected/10',
    },
}

/** One row DHIS2 named as a reason it would not take a forwarded payload. */
export interface SpoolRejectionIssue {
    error_code?: string | null
    /** The object the row is about - a DHIS2 uid, or the conflicting object. */
    subject?: string | null
    message?: string | null
}

/** What DHIS2 said about one refused receipt, rolled up out of its stored import report. */
export interface SpoolRejection {
    status?: string | null
    message?: string | null
    created: number
    updated: number
    ignored: number
    issues: SpoolRejectionIssue[]
}

/**
 * What DHIS2 counted when it took one receipt, off its stored import report.
 *
 * No issue rows, unlike a rejection: an import DHIS2 accepted named nothing against the payload, so
 * the counts are the whole answer - and an accepted receipt that ignored every value is the case
 * they exist to make visible.
 */
export interface SpoolImport {
    status?: string | null
    message?: string | null
    created: number
    updated: number
    ignored: number
    deleted: number
}

/** One stored receipt: when it arrived, what it answers, where it is, and what DHIS2 said. */
export interface SpoolResponseSummary {
    response_id: string
    received_at: string
    lifecycle: ResponseLifecycle
    form_kind: string
    /** The canonical of the Questionnaire the submission answered. */
    questionnaire: string
    /** The last segment of that canonical - the id the form is served under. */
    questionnaire_id?: string | null
    status?: string | null
    authored?: string | null
    answer_count: number
    warnings: string[]
    /** The ISO period an aggregate submission reports for. */
    period?: string | null
    period_type?: string | null
    /** The DHIS2 organisation-unit uid the capture happened at. */
    organisation_unit?: string | null
    tracked_entity?: string | null
    tracker_enrollment?: string | null
    /** Why DHIS2 refused this receipt, on a rejected row whose report reads. */
    rejection?: SpoolRejection | null
    /** What DHIS2 counted for this receipt, on a forwarded row whose report reads. */
    imported?: SpoolImport | null
}

/** How many receipts sit in each state - the queue depth, and what became of the rest. */
export interface SpoolCounts {
    received: number
    forwarded: number
    rejected: number
}

/** Every receipt this project holds, newest first, with the per-state counts beside them. */
export interface SpoolListing {
    total: number
    counts: SpoolCounts
    responses: SpoolResponseSummary[]
}

/** An empty listing, so a page can render its table shell before the first answer arrives. */
export const EMPTY_SPOOL: SpoolListing = {
    total: 0,
    counts: { received: 0, forwarded: 0, rejected: 0 },
    responses: [],
}

/**
 * A receipt instant as a person reads it.
 *
 * The server sends a UTC `instant`; the browser shows it in local time, because
 * the person looking at the queue is standing where the capture happened. An
 * unparseable value is shown verbatim rather than as "Invalid Date" - if the
 * wire ever carries something unexpected, the raw string is the useful thing.
 */
export function formatInstant(instant: string): string {
    const parsed = new Date(instant)
    if (Number.isNaN(parsed.getTime())) return instant
    return parsed.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

/**
 * What the organisation-unit fact is labelled, exported because a page resolves that one further.
 *
 * The spool derives it as a bare DHIS2 uid, which is the only thing it can honestly say - it has no
 * registry. A page that has read the registry can name the unit, and it finds the fact to upgrade
 * by this label rather than by its position in the list.
 */
export const ORGANISATION_UNIT_FACT_LABEL = 'Organisation unit'

/**
 * What the two tracker handles are labelled, exported for the same reason the unit's label is.
 *
 * The spool derives both when it indexes a receipt, and the stored resource carries both too - a
 * registration response mints them. A page that reads the resource has to state the fact under
 * the same label the spool would have, or one receipt would show the enrollment twice under two
 * spellings.
 */
export const TRACKED_ENTITY_FACT_LABEL = 'Tracked entity'

/** What the enrollment handle is labelled, wherever it is read from. */
export const TRACKER_ENROLLMENT_FACT_LABEL = 'Enrollment'

/**
 * The DHIS2 context one receipt carries, as label/value pairs for a detail view.
 *
 * Which facts exist depends on the form kind - an aggregate response reports for
 * a period at an organisation unit, a tracker event names an entity and an
 * enrollment - so this returns only what the receipt actually has rather than a
 * fixed grid with empty cells in it.
 */
export function captureContext(summary: SpoolResponseSummary): { label: string; value: string }[] {
    const pairs: [string, string | null | undefined][] = [
        ['Period', summary.period],
        ['Period type', summary.period_type],
        [ORGANISATION_UNIT_FACT_LABEL, summary.organisation_unit],
        [TRACKED_ENTITY_FACT_LABEL, summary.tracked_entity],
        [TRACKER_ENROLLMENT_FACT_LABEL, summary.tracker_enrollment],
        ['Authored', summary.authored],
        ['Response status', summary.status],
    ]
    return pairs.flatMap(([label, value]) => (value ? [{ label, value }] : []))
}

/**
 * The one line a rejected receipt is summarised by.
 *
 * DHIS2 states a rule once and then names the objects that broke it, so the
 * first issue is nearly always the cause and the rest are its instances. The
 * count is kept in the line so a row never implies there was only one.
 */
export function rejectionSummary(rejection: SpoolRejection): string {
    const first = rejection.issues[0]
    const head = first
        ? [first.error_code, first.message ?? first.subject].filter(Boolean).join(' ')
        : (rejection.message ?? rejection.status ?? 'DHIS2 gave no reason')
    const rest = rejection.issues.length - 1
    return rest > 0 ? `${head} (+${rest} more)` : head
}

/** One DHIS2 error code, and how many refused receipts in a listing carry it. */
export interface RejectionCause {
    /** The DHIS2 error code, as the import report states it - `E1120`, `E8023`, and so on. */
    code: string
    /** What DHIS2 said the first time it used that code here, or null when it said only the code. */
    message: string | null
    /** How many receipts were refused with this code. */
    receipts: number
}

/**
 * The one thing most of this project's rejections have in common.
 *
 * COUNTED PER RECEIPT, NOT PER ISSUE. DHIS2 states a rule once and then names every object that
 * broke it, so a single refused submission can carry forty rows of `E1029`. Counting issues would
 * let one bad receipt outweigh every other cause in the spool; counting receipts answers the
 * question a summary is actually asking - how many submissions are stuck on this. A receipt that
 * carries two distinct codes counts once towards each.
 *
 * Null when nothing was refused, or when the stored reports name no error code at all - the
 * caller says "rejected" plainly rather than inventing a cause.
 */
export function topRejectionCause(responses: SpoolResponseSummary[]): RejectionCause | null {
    const causes = new Map<string, RejectionCause>()
    for (const summary of responses) {
        const rejection = summary.rejection
        if (!rejection) continue
        const codes = new Set(
            rejection.issues.flatMap((issue) => (issue.error_code ? [issue.error_code] : [])),
        )
        for (const code of codes) {
            const known = causes.get(code)
            if (known) {
                known.receipts += 1
                continue
            }
            const stated = rejection.issues.find((issue) => issue.error_code === code)
            causes.set(code, { code, message: stated?.message ?? null, receipts: 1 })
        }
    }
    // Insertion order breaks a tie, and the listing arrives newest first - so two causes with the
    // same weight resolve to the one that has bitten most recently.
    let top: RejectionCause | null = null
    for (const cause of causes.values()) {
        if (top === null || cause.receipts > top.receipts) top = cause
    }
    return top
}

/** Every lifecycle state present in one listing, in the canonical order. */
export function lifecyclesPresent(listing: SpoolListing): ResponseLifecycle[] {
    return RESPONSE_LIFECYCLES.filter((lifecycle) => listing.counts[lifecycle] > 0)
}
