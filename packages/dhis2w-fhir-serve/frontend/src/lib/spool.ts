/**
 * The receipt spool as `GET /spool` answers it - the one non-FHIR shape this UI reads.
 *
 * WHY THIS IS NOT IN lib/fhir.ts. Everything in that module is an R4 resource
 * served as `application/fhir+json`. This is not: it is the receipt *envelope*
 * the facade records around each submission - when it was accepted, which DHIS2
 * form kind it was validated as, which of the spool's four directories the file
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
 * Which of the spool's four directories a receipt currently sits in.
 *
 * These are states of a *file*, and the whole reason the Responses page has a
 * reload button: `d2w fhir forward` renames receipts between the directories
 * from another process, so what this says can change with nothing happening in
 * the browser at all. `d2w fhir withdraw` is the second such process, and the
 * state it files a receipt into is the one nothing moves it back out of.
 */
export const RESPONSE_LIFECYCLES = ['received', 'forwarded', 'rejected', 'withdrawn'] as const

/** One lifecycle state a stored receipt can be in. */
export type ResponseLifecycle = (typeof RESPONSE_LIFECYCLES)[number]

/** How each state is named in the UI, and what it actually means. */
export const LIFECYCLE_LABELS: Record<ResponseLifecycle, string> = {
    received: 'Received',
    forwarded: 'Forwarded',
    rejected: 'Rejected',
    withdrawn: 'Withdrawn',
}

/** One line per state, for the filter tooltips and the empty-state prose. */
export const LIFECYCLE_HINTS: Record<ResponseLifecycle, string> = {
    received: 'Captured, not yet sent to DHIS2. `d2w fhir forward` sends it.',
    forwarded: 'Translated, posted, and accepted by DHIS2.',
    rejected: 'Posted and refused by DHIS2. The import report says why.',
    withdrawn:
        'Accepted by DHIS2, then withdrawn from it by `d2w fhir withdraw`. The instance keeps a hidden copy.',
}

/**
 * The theme token each state is tinted with.
 *
 * The tokens are declared in index.css and shared with the rest of the app -
 * `received` is the identity blue because a receipt on disk is the resting
 * state rather than a warning, `forwarded` is the success hue, `rejected` the
 * destructive one, and `withdrawn` a muted violet: it is neither a failure nor
 * a queue, it is a fact that has been taken back. Kept as full class strings
 * rather than built by interpolation: Tailwind scans source text for class
 * names, and `bg-status-${state}` is a name it never sees.
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
    withdrawn: {
        dot: 'bg-status-withdrawn',
        badge: 'border-status-withdrawn/40 text-status-withdrawn bg-status-withdrawn/10',
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
 * The last committing drain's refusal of one still-queued receipt.
 *
 * Not a DHIS2 answer: the receipt never reached the instance. The forward run that posts receipts
 * writes this beside a receipt it could not convert and left queued, so a reader can tell it from
 * a receipt no drain has looked at. The reasons reuse the rejection-issue row shape - which rule,
 * which object, what it said - because that is what a reader wants of either.
 */
export interface SpoolRefusal {
    /** The instant the last committing forward run refused the receipt. */
    refused_at: string
    /** How many committing forward runs have refused it so far. */
    attempt_count: number
    reasons: SpoolRejectionIssue[]
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

/**
 * What DHIS2 answered when it was asked to take one receipt's event back.
 *
 * Written by `d2w fhir withdraw` beside the receipt it files under `withdrawn/`.
 * The note is the record's own sentence and is rendered rather than rephrased:
 * DHIS2 soft-deletes, so the row stays in the instance carrying its value and is
 * gone from every ordinary read, and a screen that said "deleted" would be
 * claiming more than the toolkit can stand behind.
 */
export interface SpoolWithdrawal {
    /** The instant the withdrawal was posted. */
    withdrawn_at: string
    /** The DHIS2 event the withdrawal named. */
    event_uid: string
    /** What remains in the instance, in the record's own words. */
    note: string
    status?: string | null
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
    /** The last forward run's refusal, on a received row that has a record beside it. */
    refusal?: SpoolRefusal | null
    /** What DHIS2 answered the retraction, on a withdrawn row whose record reads. */
    withdrawal?: SpoolWithdrawal | null
}

/** How many receipts sit in each state - the queue depth, and what became of the rest. */
export interface SpoolCounts {
    received: number
    forwarded: number
    rejected: number
    /** Landed in DHIS2 and withdrawn from it afterwards. Terminal: nothing leaves this state. */
    withdrawn: number
    /** Files that do not read as receipts. Not a lifecycle state - a holding pen beside the four. */
    malformed: number
}

/** One file the facade moved aside because it does not read as a receipt, and what stopped it. */
export interface QuarantinedFile {
    file_name: string
    reason: string
}

/**
 * One page of this project's receipts, newest first, with the whole listing's counts beside them.
 *
 * `total` and `counts` are the whole spool on every page of a walk; `responses` is the page.
 * `readSpool` in lib/api.ts follows `next_url` and hands back every page's rows in one listing.
 */
export interface SpoolListing {
    total: number
    counts: SpoolCounts
    responses: SpoolResponseSummary[]
    malformed: QuarantinedFile[]
    /** This page, as the server names it. */
    self_url: string
    previous_url: string | null
    next_url: string | null
}

/** An empty listing, so a page can render its table shell before the first answer arrives. */
export const EMPTY_SPOOL: SpoolListing = {
    total: 0,
    counts: { received: 0, forwarded: 0, rejected: 0, withdrawn: 0, malformed: 0 },
    responses: [],
    malformed: [],
    self_url: '/spool',
    previous_url: null,
    next_url: null,
}

/**
 * The fields of an ISO date, or of a date and a time of day: year, month, day, hour, minute, second.
 *
 * Anchored at both ends, so a string that is only shaped like an instant for its first ten
 * characters is not one - `formatInstant` shows such a value whole rather than rendering a prefix
 * of it. A zone designator is matched but captured by nothing, which is the discarding the rule
 * below argues for.
 */
const WALL_CLOCK_FIELDS =
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/

/**
 * One instant as a person reads it: the wall clock DHIS2 sent, digit for digit.
 *
 * ONE RULE, THE SAME FOR EVERY VALUE ON THE WIRE. The date and time written in the string are the
 * date and time on screen. The browser's own zone never moves them, and neither does a zone the
 * string carries: `2026-08-09T09:30:00` and `2026-08-09T09:30:00Z` both read half past nine.
 *
 * WHY THE ZONE IS DROPPED RATHER THAN APPLIED. DHIS2 keeps its instants in the clock the deployment
 * runs on, and the two spellings above are the same moment to the people using it - one endpoint
 * states the offset and its neighbour does not. A browser that honoured the offset would file a
 * receipt captured at half nine under a different hour on a laptop in another zone, and under a
 * different hour again from the enrollment date beside it on the same screen. So the fields are
 * read out of the string and rendered as they were written, and every screen in this app agrees
 * with the register the capture was written in.
 *
 * The locale still decides the shape - which month name, what order, whether the hour is written to
 * twelve or twenty-four - because that is a fact about the reader rather than about the instant.
 *
 * A value this rule cannot read is shown verbatim rather than as "Invalid Date": if the wire ever
 * carries something unexpected, the raw string is the useful thing.
 */
export function formatInstant(instant: string): string {
    const fields = WALL_CLOCK_FIELDS.exec(instant)
    if (fields === null) return instant
    const [, year, month, day, hour = '00', minute = '00', second = '00'] = fields
    // Built in UTC and rendered in UTC, which is what makes the arithmetic a no-op: the fields go in
    // and the same fields come out, whatever zone the browser stands in.
    const wallClock = new Date(
        Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second)),
    )
    // A date nobody has - the thirtieth of February, the twenty-fifth hour - rolls over into a real
    // one rather than failing, so it is caught by reading the fields back rather than by a NaN.
    if (
        wallClock.getUTCFullYear() !== Number(year) ||
        wallClock.getUTCMonth() !== Number(month) - 1 ||
        wallClock.getUTCDate() !== Number(day) ||
        wallClock.getUTCHours() !== Number(hour) ||
        wallClock.getUTCMinutes() !== Number(minute)
    ) {
        return instant
    }
    return wallClock.toLocaleString(undefined, {
        timeZone: 'UTC',
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

/**
 * The word a withdrawal note opens with, which the line around it has already said.
 *
 * The note is written for a terminal, where it stands alone and has to name what happened before it
 * says what remains. In a line that already states the withdrawal and its instant, that opening word
 * is the same fact a second time - so it is dropped, and only the opening word is dropped. Anything
 * the note goes on to say is the record's own and is rendered as written.
 */
const WITHDRAWAL_NOTE_RESTATEMENT = /^withdrawn[.:]?\s+/i

/**
 * The one line a withdrawn receipt is summarised by.
 *
 * The fact first - it was withdrawn from DHIS2, and when - then what the record says remains. Nothing
 * here paraphrases the note: the sentence is written once, in the package that posts the delete, so
 * the terminal wording and the browser's wording cannot drift apart. What is removed is the note's
 * own opening restatement, because this line has already said it: "Withdrawn from DHIS2 at 10:04.
 * Withdrawn. This DHIS2 instance keeps a hidden copy" states the withdrawal twice in two casings,
 * which is one fact wearing two costumes.
 */
export function withdrawalSummary(withdrawal: SpoolWithdrawal): string {
    const remains = withdrawal.note.replace(WITHDRAWAL_NOTE_RESTATEMENT, '')
    const stated = `Withdrawn from DHIS2 at ${formatInstant(withdrawal.withdrawn_at)}.`
    return remains === '' ? stated : `${stated} ${remains}`
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
