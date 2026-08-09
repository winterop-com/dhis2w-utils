import { describe, expect, it } from 'vitest'

import {
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    captureContext,
    formatInstant,
    lifecyclesPresent,
    rejectionSummary,
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

describe('formatInstant', () => {
    it('renders a FHIR instant as something a person reads', () => {
        const rendered = formatInstant('2026-08-09T09:30:00Z')
        expect(rendered).not.toBe('2026-08-09T09:30:00Z')
        expect(rendered).toContain('2026')
    })

    it('shows an unparseable value verbatim rather than as Invalid Date', () => {
        expect(formatInstant('not an instant')).toBe('not an instant')
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

describe('lifecyclesPresent', () => {
    it('reports only the states this project actually has receipts in', () => {
        const listing: SpoolListing = {
            total: 3,
            counts: { received: 2, forwarded: 0, rejected: 1 },
            responses: [],
        }
        expect(lifecyclesPresent(listing)).toEqual(['received', 'rejected'])
    })
})
