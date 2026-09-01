import { describe, expect, it } from 'vitest'

import generateAggregateFixture from '@/lib/__fixtures__/generate-BfMAe6Itzgt.json'
import generateEventFixture from '@/lib/__fixtures__/generate-EVTsupVis01.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import { answeredItemTree, answerValue, type AnsweredItem } from '@/lib/answers'
import {
    bundleResources,
    type Bundle,
    type Questionnaire,
    type QuestionnaireResponse,
    type QuestionnaireResponseItem,
} from '@/lib/fhir'
import { flattenQuestionnaire } from '@/lib/questionnaire'

/**
 * The read side of an answer, against documents a real server produced.
 *
 * The fixtures are the ones the fill side and the receipt page are tested with: `$generate`
 * responses harvested verbatim from an in-process `d2w fhir serve` over the committed goldens, and
 * the Questionnaires those responses answer. A served event reads back in exactly that shape - the
 * facade's own projection builds the document a client could have written - so the tree this suite
 * proves is the tree a tracked entity's record unfolds.
 */

const questionnaires = new Map(
    bundleResources(questionnaireBundleFixture as unknown as Bundle<Questionnaire>).map((questionnaire) => [
        questionnaire.id ?? '',
        questionnaire,
    ]),
)

/** One served form by its DHIS2 uid, failing loudly rather than testing against undefined. */
function servedForm(id: string): Questionnaire {
    const questionnaire = questionnaires.get(id)
    if (questionnaire === undefined) throw new Error(`the fixture bundle serves no Questionnaire ${id}`)
    return questionnaire
}

const aggregateResponse = generateAggregateFixture as unknown as QuestionnaireResponse
const eventResponse = generateEventFixture as unknown as QuestionnaireResponse

/** The tree one document reads back as, against the form it answers. */
function treeFor(formId: string, response: QuestionnaireResponse): AnsweredItem[] {
    return answeredItemTree(response.item ?? [], flattenQuestionnaire(servedForm(formId)))
}

/** Every item of a tree, depth first, so a single value can be found without walking by hand. */
function everyItem(items: AnsweredItem[]): AnsweredItem[] {
    return items.flatMap((item) => [item, ...everyItem(item.children)])
}

/** The one item a link id names, failing loudly rather than testing against undefined. */
function itemNamed(items: AnsweredItem[], linkId: string): AnsweredItem {
    const found = everyItem(items).find((item) => item.linkId === linkId)
    if (found === undefined) throw new Error(`the tree carries no item ${linkId}`)
    return found
}

describe('one answer read as the value a screen shows', () => {
    it('carries a string as it stands', () => {
        expect(answerValue({ valueString: 'Kobe' })).toEqual({ kind: 'text', text: 'Kobe' })
    })

    it('spells a whole number and a decimal as themselves', () => {
        expect(answerValue({ valueInteger: 12 })).toEqual({ kind: 'text', text: '12' })
        expect(answerValue({ valueDecimal: 38.4 })).toEqual({ kind: 'text', text: '38.4' })
    })

    it('answers a yes/no question in the words it was asked in', () => {
        expect(answerValue({ valueBoolean: true })).toEqual({ kind: 'text', text: 'Yes' })
        expect(answerValue({ valueBoolean: false })).toEqual({ kind: 'text', text: 'No' })
    })

    it('carries a date, a dateTime, and a time verbatim', () => {
        expect(answerValue({ valueDate: '2026-02-14' })).toEqual({ kind: 'text', text: '2026-02-14' })
        expect(answerValue({ valueDateTime: '2026-02-14T09:30:00+07:00' })).toEqual({
            kind: 'text',
            text: '2026-02-14T09:30:00+07:00',
        })
        expect(answerValue({ valueTime: '09:30:00' })).toEqual({ kind: 'text', text: '09:30:00' })
    })

    it('keeps a measurement and the word it is measured in together', () => {
        expect(answerValue({ valueQuantity: { value: 3.2, unit: 'kg' } })).toEqual({ kind: 'text', text: '3.2 kg' })
        expect(answerValue({ valueQuantity: { value: 40, code: 'Cel', comparator: '>' } })).toEqual({
            kind: 'text',
            text: '> 40 Cel',
        })
        // A quantity with no number is not a measurement, and nothing is invented to stand for one.
        expect(answerValue({ valueQuantity: { unit: 'kg' } })).toBeNull()
    })

    it('keeps both halves of a coding - the name a person reads and the code DHIS2 stores', () => {
        expect(
            answerValue({
                valueCoding: { system: 'http://localhost/CodeSystem/d2-os-OsSymptom01-cs', code: 'OpFever0001', display: 'Fever' },
            }),
        ).toEqual({
            kind: 'coding',
            display: 'Fever',
            code: 'OpFever0001',
            system: 'http://localhost/CodeSystem/d2-os-OsSymptom01-cs',
        })
    })

    it('falls back to the code when a coding carries no display', () => {
        expect(answerValue({ valueCoding: { code: 'OpFever0001' } })).toEqual({
            kind: 'coding',
            display: 'OpFever0001',
            code: 'OpFever0001',
            system: null,
        })
    })

    it('keeps an organisation unit reference and the uid inside it apart', () => {
        expect(answerValue({ valueReference: { reference: 'Location/DiszpKrYNg8', display: 'Ngelehun CHC' } })).toEqual({
            kind: 'reference',
            display: 'Ngelehun CHC',
            reference: 'Location/DiszpKrYNg8',
            unitId: 'DiszpKrYNg8',
        })
    })

    it('reads nothing out of an answer carrying no value at all', () => {
        expect(answerValue({})).toBeNull()
    })
})

describe('a served document read as the tree it was answered in', () => {
    it('keeps the nesting the document states, down to the cell', () => {
        const tree = treeFor('BfMAe6Itzgt', aggregateResponse)
        expect(tree.map((item) => item.linkId)).toEqual(['Y2rk0vzgvAx', 'vtOr8PTJVxS'])
        expect(tree[0].values).toEqual([])
        const section = itemNamed(tree, 's46m5MS0hxu')
        expect(tree[0].children).toContain(section)
        expect(section.children.map((child) => child.linkId)).toContain('s46m5MS0hxu.Prlt0C1RF0s')
    })

    it('names every item the way the served form asks it', () => {
        const tree = treeFor('BfMAe6Itzgt', aggregateResponse)
        const spec = flattenQuestionnaire(servedForm('BfMAe6Itzgt'))
        for (const item of everyItem(tree)) {
            expect(item.text).toBe(spec.byLinkId.get(item.linkId)?.text ?? null)
            expect(item.text).not.toBeNull()
        }
    })

    it('answers a cell with the value the document typed onto it', () => {
        const cell = itemNamed(treeFor('BfMAe6Itzgt', aggregateResponse), 's46m5MS0hxu.Prlt0C1RF0s')
        expect(cell.children).toEqual([])
        expect(cell.values).toHaveLength(1)
        expect(cell.values[0].kind).toBe('text')
    })

    it('reads a flat event document as one item per question', () => {
        const tree = treeFor('EVTsupVis01', eventResponse)
        expect(tree.every((item) => item.children.length === 0)).toBe(true)
        expect(tree.every((item) => item.values.length > 0)).toBe(true)
    })

    it('keeps the link id of an item no served form declares', () => {
        const items: QuestionnaireResponseItem[] = [{ linkId: 'DeSomethingElse', answer: [{ valueString: 'kept' }] }]
        const spec = flattenQuestionnaire(servedForm('EVTsupVis01'))
        expect(answeredItemTree(items, spec)).toEqual([
            { linkId: 'DeSomethingElse', text: null, values: [{ kind: 'text', text: 'kept' }], children: [] },
        ])
    })

    it('takes the text the document echoes over the one the form asks', () => {
        const items: QuestionnaireResponseItem[] = [
            { linkId: 's46m5MS0hxu', text: 'As the document states it', answer: [{ valueInteger: 4 }] },
        ]
        const spec = flattenQuestionnaire(servedForm('EVTsupVis01'))
        expect(answeredItemTree(items, spec)[0].text).toBe('As the document states it')
    })

    it('lists every answer to one item, in the order the document states them', () => {
        const items: QuestionnaireResponseItem[] = [
            {
                linkId: 'DeSymptoms',
                answer: [
                    { valueCoding: { code: 'OpFever0001', display: 'Fever' } },
                    { valueCoding: { code: 'OpCough0001', display: 'Cough' } },
                ],
            },
        ]
        expect(answeredItemTree(items, null)[0].values).toEqual([
            { kind: 'coding', display: 'Fever', code: 'OpFever0001', system: null },
            { kind: 'coding', display: 'Cough', code: 'OpCough0001', system: null },
        ])
    })

    it('leaves out a branch that reaches no answer at all', () => {
        const items: QuestionnaireResponseItem[] = [
            { linkId: 'EmptySection', item: [{ linkId: 'EmptyQuestion' }] },
            { linkId: 'DeAnswered', answer: [{ valueString: 'here' }] },
        ]
        expect(answeredItemTree(items, null).map((item) => item.linkId)).toEqual(['DeAnswered'])
    })

    it('reads a follow-up question nested under the answer it follows up on', () => {
        const items: QuestionnaireResponseItem[] = [
            {
                linkId: 'DeFever',
                answer: [{ valueBoolean: true, item: [{ linkId: 'DeFeverDays', answer: [{ valueInteger: 3 }] }] }],
            },
        ]
        const tree = answeredItemTree(items, null)
        expect(tree[0].values).toEqual([{ kind: 'text', text: 'Yes' }])
        expect(tree[0].children).toEqual([
            { linkId: 'DeFeverDays', text: null, values: [{ kind: 'text', text: '3' }], children: [] },
        ])
    })

    it('reads a document with no answered item as an empty tree', () => {
        expect(answeredItemTree([], null)).toEqual([])
    })
})
