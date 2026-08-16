import { describe, expect, it } from 'vitest'

import {
    EMPTY_SPOOL,
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    captureContext,
    formatInstant,
    lifecyclesPresent,
    rejectionSummary,
    topRejectionCause,
    type SpoolListing,
    type SpoolResponseSummary,
} from '@/lib/spool'

/**
 * The pure half of the Responses page.
 *
 * The listing shapes are what `GET /spool` sends, so these fixtures are written
 * in the wire's own snake_case: a rename here and nowhere else is exactly the
 * bug this file is meant to catch.
 */

/** One listing row, with only the fields a given test cares about set. */
function summary(overrides: Partial<SpoolResponseSummary> = {}): SpoolResponseSummary {
    return {
        response_id: 'abc123',
        received_at: '2026-08-09T09:30:00Z',
        lifecycle: 'received',
        form_kind: 'aggregate',
        questionnaire: 'http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt',
        questionnaire_id: 'BfMAe6Itzgt',
        answer_count: 12,
        warnings: [],
        ...overrides,
    }
}

describe('the lifecycle vocabulary', () => {
    it('names the three states the spool has directories for', () => {
        // The order is the order of the loop itself, and the filter renders in it.
        expect([...RESPONSE_LIFECYCLES]).toEqual(['received', 'forwarded', 'rejected'])
    })

    it('gives every state a tint, as full class names Tailwind can see', () => {
        for (const lifecycle of RESPONSE_LIFECYCLES) {
            const tint = LIFECYCLE_TINTS[lifecycle]
            expect(tint.dot).toBe(`bg-status-${lifecycle}`)
            expect(tint.badge).toContain(`text-status-${lifecycle}`)
        }
    })
})

/**
 * The environment this suite's own zone is set in.
 *
 * Reached through `globalThis` because the app's TypeScript configuration types a browser and these
 * tests run in Node: `TZ` is real at runtime and simply not declared here.
 */
const nodeEnvironment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env

/**
 * Read one instant while the runtime stands in a given zone.
 *
 * The zone is the whole subject of the rule under test, and Node resolves it from `TZ` each time a
 * date is formatted - so the variable is set, the reading taken, and the previous value put back
 * before the next test runs in whatever zone the suite was started in.
 */
function inTimeZone(timeZone: string, read: () => string): string {
    if (nodeEnvironment === undefined) return read()
    const started = nodeEnvironment.TZ
    nodeEnvironment.TZ = timeZone
    try {
        return read()
    } finally {
        nodeEnvironment.TZ = started
    }
}

/** The wall clock a rendering states, as `Intl` writes those fields with no zone arithmetic on them. */
function wallClock(year: number, month: number, day: number, hour: number, minute: number): string {
    return new Date(Date.UTC(year, month - 1, day, hour, minute)).toLocaleString(undefined, {
        timeZone: 'UTC',
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

describe('formatInstant', () => {
    it('renders the wall clock the wire carries, digit for digit', () => {
        expect(formatInstant('2026-08-09T09:30:00Z')).toBe(wallClock(2026, 8, 9, 9, 30))
    })

    it('reads a zoned value and a zone-less one as the same wall clock', () => {
        // The two spellings DHIS2 sends for one moment. A rule that applied the offset would put
        // them under different hours on one screen.
        expect(formatInstant('2026-08-09T09:30:00Z')).toBe(formatInstant('2026-08-09T09:30:00'))
        expect(formatInstant('2026-08-09T09:30:00+05:00')).toBe(formatInstant('2026-08-09T09:30:00'))
    })

    it('renders one instant the same wherever the browser stands', () => {
        // Half past eleven at night, which is the reading a zone shift moves to another day.
        const late = '2026-08-09T23:30:00Z'
        // The two zones are a day apart on this instant, so the reading below is a real comparison
        // rather than one taken twice in the same zone.
        expect(inTimeZone('Pacific/Kiritimati', () => new Date(late).toLocaleString())).not.toBe(
            inTimeZone('Pacific/Honolulu', () => new Date(late).toLocaleString()),
        )
        expect(inTimeZone('Pacific/Kiritimati', () => formatInstant(late))).toBe(
            inTimeZone('Pacific/Honolulu', () => formatInstant(late)),
        )
        expect(inTimeZone('Pacific/Honolulu', () => formatInstant(late))).toBe(wallClock(2026, 8, 9, 23, 30))
    })

    it('renders a date with no time of day as that date', () => {
        expect(formatInstant('2026-08-09')).toBe(wallClock(2026, 8, 9, 0, 0))
    })

    it('shows an unparseable value verbatim rather than as Invalid Date', () => {
        expect(formatInstant('not an instant')).toBe('not an instant')
    })

    it('shows a date nobody has verbatim, rather than rolling it into a real one', () => {
        expect(formatInstant('2026-02-30')).toBe('2026-02-30')
        expect(formatInstant('2026-08-09T25:30:00Z')).toBe('2026-08-09T25:30:00Z')
    })

    it('shows a value that is only shaped like an instant at its head verbatim', () => {
        expect(formatInstant('2026-08-09 and then some')).toBe('2026-08-09 and then some')
    })
})

describe('captureContext', () => {
    it('states an aggregate receipt as its period and where it was reported', () => {
        const facts = captureContext(
            summary({ period: '202607', period_type: 'Monthly', organisation_unit: 'ImspTQPwCqd' }),
        )
        expect(facts).toEqual([
            { label: 'Period', value: '202607' },
            { label: 'Period type', value: 'Monthly' },
            { label: 'Organisation unit', value: 'ImspTQPwCqd' },
        ])
    })

    it('states a tracker receipt as its entity and enrollment', () => {
        const facts = captureContext(
            summary({
                form_kind: 'tracker-event',
                organisation_unit: 'ImspTQPwCqd',
                tracked_entity: 'tPpcmcRWO0g',
                tracker_enrollment: 'gxMz7Qje7pk',
                authored: '2026-07-14T15:00:00Z',
            }),
        )
        expect(facts.map((fact) => fact.label)).toEqual([
            'Organisation unit',
            'Tracked entity',
            'Enrollment',
            'Authored',
        ])
    })

    it('leaves out what the receipt does not carry rather than showing empty cells', () => {
        expect(captureContext(summary())).toEqual([])
    })
})

describe('rejectionSummary', () => {
    it('leads with the first issue, because DHIS2 states the rule once', () => {
        const line = rejectionSummary({
            status: 'ERROR',
            created: 0,
            updated: 0,
            ignored: 2,
            issues: [
                { error_code: 'E1120', subject: 'ImspTQPwCqd', message: 'Data element not found' },
                { error_code: 'E1120', subject: 'O6uvpzGd5pu', message: 'Data element not found' },
            ],
        })
        expect(line).toBe('E1120 Data element not found (+1 more)')
    })

    it('does not imply there was only one when there were several', () => {
        const line = rejectionSummary({
            created: 0,
            updated: 0,
            ignored: 0,
            issues: [{ error_code: 'E1121' }, { error_code: 'E1122' }, { error_code: 'E1123' }],
        })
        expect(line).toContain('+2 more')
    })

    it('falls back to what the report said when it named no issues at all', () => {
        expect(
            rejectionSummary({ status: 'ERROR', message: 'Import failed', created: 0, updated: 0, ignored: 0, issues: [] }),
        ).toBe('Import failed')
    })

    it('says so when DHIS2 gave nothing to go on', () => {
        expect(rejectionSummary({ created: 0, updated: 0, ignored: 0, issues: [] })).toBe(
            'DHIS2 gave no reason',
        )
    })
})

describe('topRejectionCause', () => {
    /** One refused receipt, with the codes its stored import report named. */
    function rejected(codes: string[], message?: string): SpoolResponseSummary {
        return summary({
            lifecycle: 'rejected',
            rejection: {
                status: 'ERROR',
                created: 0,
                updated: 0,
                ignored: codes.length,
                issues: codes.map((code) => ({ error_code: code, message: message ?? null })),
            },
        })
    }

    it('names the code the most refused receipts share', () => {
        const cause = topRejectionCause([
            rejected(['E1029'], 'Organisation unit is not assigned'),
            rejected(['E8023'], 'Attribute option combo not in category combo'),
            rejected(['E1029'], 'Organisation unit is not assigned'),
        ])
        expect(cause).toEqual({
            code: 'E1029',
            message: 'Organisation unit is not assigned',
            receipts: 2,
        })
    })

    it('counts receipts rather than issues, so one bad submission cannot outweigh the rest', () => {
        // DHIS2 states a rule once and then names every object that broke it, so a single
        // receipt can carry forty rows of the same code. That is one stuck submission.
        const cause = topRejectionCause([
            rejected(Array.from({ length: 40 }, () => 'E1029')),
            rejected(['E8023']),
            rejected(['E8023']),
        ])
        expect(cause?.code).toBe('E8023')
        expect(cause?.receipts).toBe(2)
    })

    it('counts a receipt once towards each distinct code it carries', () => {
        const cause = topRejectionCause([rejected(['E1029', 'E8023', 'E1029'])])
        expect(cause).toEqual({ code: 'E1029', message: null, receipts: 1 })
    })

    it('breaks a tie on the newest, because the listing arrives newest first', () => {
        expect(topRejectionCause([rejected(['E8023']), rejected(['E1029'])])?.code).toBe('E8023')
    })

    it('says nothing when the reports named no error code at all', () => {
        expect(topRejectionCause([rejected([])])).toBeNull()
    })

    it('says nothing when nothing was refused', () => {
        expect(topRejectionCause([summary(), summary({ lifecycle: 'forwarded' })])).toBeNull()
    })
})

describe('lifecyclesPresent', () => {
    it('reports only the states this project actually has receipts in', () => {
        const listing: SpoolListing = {
            ...EMPTY_SPOOL,
            total: 3,
            counts: { received: 2, forwarded: 0, rejected: 1, malformed: 0 },
        }
        expect(lifecyclesPresent(listing)).toEqual(['received', 'rejected'])
    })
})
