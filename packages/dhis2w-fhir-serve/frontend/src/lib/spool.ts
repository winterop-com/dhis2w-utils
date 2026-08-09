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
    received: 'Captured and queued. `d2w fhir forward` is what drains it.',
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
    rejection?: SpoolRejection | null
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
        ['Organisation unit', summary.organisation_unit],
        ['Tracked entity', summary.tracked_entity],
        ['Enrollment', summary.tracker_enrollment],
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

/** Every lifecycle state present in one listing, in the canonical order. */
export function lifecyclesPresent(listing: SpoolListing): ResponseLifecycle[] {
    return RESPONSE_LIFECYCLES.filter((lifecycle) => listing.counts[lifecycle] > 0)
}
