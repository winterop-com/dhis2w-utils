import { describe, expect, it } from 'vitest'

import {
    NOT_ANSWERING_HEADING,
    NOTHING_UNDER_THAT_ID_HEADING,
    pageStateHeading,
    READ_REFUSED_HEADING,
} from '@/components/PageState'

/**
 * What a failed read is called on the screen.
 *
 * "Refused" is a word this app spends elsewhere: it is what the capture validator does to a
 * submission, and it is used that way on every receipt. Heading a missing form with it says the
 * server declined to answer, when the server answered that it holds no such thing - and the
 * diagnostic printed directly underneath then contradicts the heading above it.
 */
describe('the heading over a failed read', () => {
    it('calls a 404 an absence rather than a refusal', () => {
        expect(pageStateHeading(404)).toBe(NOTHING_UNDER_THAT_ID_HEADING)
        expect(pageStateHeading(404)).not.toContain('refused')
    })

    it('keeps "refused" for the statuses that are refusals', () => {
        for (const status of [400, 401, 403, 409, 422, 500, 503]) {
            expect(pageStateHeading(status), String(status)).toBe(READ_REFUSED_HEADING)
        }
    })

    it('says nobody answered when nothing did, which is not a refusal either', () => {
        expect(pageStateHeading('unreachable')).toBe(NOT_ANSWERING_HEADING)
    })

    it('falls back to the refusal for a read that kept no status', () => {
        expect(pageStateHeading(null)).toBe(READ_REFUSED_HEADING)
        expect(pageStateHeading(undefined)).toBe(READ_REFUSED_HEADING)
    })

    it('never puts the id in the heading, which the diagnostic under it already carries', () => {
        for (const heading of [NOTHING_UNDER_THAT_ID_HEADING, READ_REFUSED_HEADING, NOT_ANSWERING_HEADING]) {
            expect(heading).not.toMatch(/[`{]/)
            expect(heading.split(' ').length).toBeLessThan(9)
        }
    })
})
