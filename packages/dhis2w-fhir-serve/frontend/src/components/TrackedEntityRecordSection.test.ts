import { describe, expect, it } from 'vitest'

import {
    RECORD_NOT_PICKED,
    RECORD_REGISTER_LABEL,
    RECORD_SECTION_CAPTION,
    RECORD_SECTION_HEADING,
} from '@/components/TrackedEntityRecordSection'
import { NO_RECEIPT_STORED, noReceiptStoredMessage, RECORD_READ_BELOW } from '@/pages/Responses'

/**
 * The words that tell a reader which of two sources they are looking at.
 *
 * WHY THE COPY IS UNDER TEST AND NOT ONLY THE LOGIC. This page shows two things that answer
 * different questions - what this server stored, and what the DHIS2 instance holds - and the whole
 * value of putting them on one page is lost the moment a reader cannot tell which is which. The
 * failure is not a crash, so nothing else would catch it.
 */
describe('what the record section says it is', () => {
    it('names the DHIS2 instance as the thing being read, rather than DHIS2 unqualified', () => {
        expect(RECORD_SECTION_HEADING).toContain('this DHIS2 instance')
        expect(RECORD_SECTION_CAPTION).toContain('the DHIS2 instance')
    })

    it('says where the receipts above came from, so the two sources are told apart', () => {
        expect(RECORD_SECTION_CAPTION).toContain('this server stored')
    })

    it('spells the subject out, since a shortened one is a term nobody else uses', () => {
        for (const line of [RECORD_SECTION_HEADING, RECORD_NOT_PICKED]) {
            expect(line).toContain('tracked entity')
        }
    })

    it('names no command, because a reader has none to run to make the section work', () => {
        for (const line of [RECORD_SECTION_HEADING, RECORD_SECTION_CAPTION, RECORD_NOT_PICKED]) {
            expect(line).not.toContain('d2w')
        }
    })

    it('says what picking one does, before anybody has picked one', () => {
        expect(RECORD_NOT_PICKED).toBe(
            'Pick a tracked entity above to see the events this DHIS2 instance holds for it.',
        )
    })

    it('names the choice between registers by what the choice is', () => {
        expect(RECORD_REGISTER_LABEL).toBe('Register')
    })
})

/**
 * The empty table, which must not claim more than this server can know.
 *
 * "Nothing has been captured" is a claim about a DHIS2 instance, and an empty spool is not evidence
 * for it: a submission posted straight into DHIS2 never touched this directory, and neither did one
 * this server took before somebody emptied it. So the sentence states the spool, and on a run that
 * also reads the instance it points at where the rest of the answer is.
 */
describe('what the receipts table says when it holds nothing', () => {
    it('states the spool rather than the project', () => {
        expect(NO_RECEIPT_STORED).toContain('This server has stored no receipt.')
        expect(NO_RECEIPT_STORED).not.toContain('Nothing has been captured')
    })

    it('points at the instance below where the instance is read below', () => {
        expect(noReceiptStoredMessage(true)).toContain(RECORD_READ_BELOW)
        expect(noReceiptStoredMessage(true).startsWith(NO_RECEIPT_STORED)).toBe(true)
    })

    it('points nowhere on a run with no instance behind it, since there is nothing below', () => {
        expect(noReceiptStoredMessage(false)).toBe(NO_RECEIPT_STORED)
        expect(noReceiptStoredMessage(false)).not.toContain('read below')
    })
})
