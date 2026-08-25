import { describe, expect, it } from 'vitest'

import { countedNoun, formatCount } from '@/lib/utils'

/**
 * How this app writes a number.
 *
 * One rule for every screen: a count in a table, in a heading, and in the summary bar under them
 * are the same fact, and a separator that moved with the reader's machine would spell it three
 * ways across one window.
 */
describe('a count on screen', () => {
    it('groups thousands, in one named locale rather than the reader machine one', () => {
        expect(formatCount(0)).toBe('0')
        expect(formatCount(980)).toBe('980')
        expect(formatCount(1204)).toBe('1,204')
        expect(formatCount(1_000_000)).toBe('1,000,000')
    })

    it('counts one of a thing in the singular', () => {
        expect(countedNoun(1, 'mapping')).toBe('1 mapping')
        expect(countedNoun(0, 'mapping')).toBe('0 mappings')
        expect(countedNoun(980, 'concept')).toBe('980 concepts')
    })

    it('groups the count a noun carries too', () => {
        expect(countedNoun(1204, 'concept')).toBe('1,204 concepts')
    })
})
