import { describe, expect, it } from 'vitest'

import { domainFormKind, domainLabel } from '@/components/KindBadge'
import { FORM_TYPES } from '@/lib/fhir'

/**
 * Which hue a DHIS2 domain type borrows.
 *
 * The point of borrowing rather than inventing is that a reader learns five tints on the Overview
 * and spends them everywhere else, so the answer has to be one of those five and no new colour can
 * appear here without somebody deciding it is worth a sixth.
 */
describe('the hue a domain type borrows', () => {
    it('answers a published form kind for each domain the guide states', () => {
        expect(domainFormKind('aggregate')).toBe('aggregate')
        expect(domainFormKind('tracker')).toBe('tracker')
    })

    it('never answers a kind the stylesheet does not paint', () => {
        for (const domain of ['aggregate', 'tracker']) {
            const kind = domainFormKind(domain)
            expect(kind, domain).not.toBeNull()
            expect(FORM_TYPES).toContain(kind)
        }
    })

    it('leaves a domain nobody has published unhued rather than guessing one', () => {
        expect(domainFormKind('tracker-event')).toBeNull()
        expect(domainFormKind('AGGREGATE')).toBeNull()
        expect(domainFormKind('')).toBeNull()
    })
})

/**
 * How a domain type is spelled on its chip.
 *
 * A published domain is an ordinary noun and reads as one; anything else is a machine spelling this
 * app has no better word for, and sentence-casing it would claim a reading nobody checked.
 */
describe('what a domain chip says', () => {
    it('says the two published domains as words', () => {
        expect(domainLabel('aggregate')).toBe('Aggregate')
        expect(domainLabel('tracker')).toBe('Tracker')
    })

    it('states an unrecognised domain verbatim', () => {
        expect(domainLabel('SOMETHING_ELSE')).toBe('SOMETHING_ELSE')
    })
})
