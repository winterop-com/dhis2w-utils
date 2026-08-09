import { describe, expect, it } from 'vitest'

import generateAggregateFixture from '@/lib/__fixtures__/generate-BfMAe6Itzgt.json'
import generateEventFixture from '@/lib/__fixtures__/generate-EVTsupVis01.json'
import generateTemporalFixture from '@/lib/__fixtures__/generate-PrTemporal1.json'
import generateTrackerFixture from '@/lib/__fixtures__/generate-ZzYYXq4fJie.json'
import temporalQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrTemporal1.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import { bundleResources, questionCount, type Bundle, type Questionnaire, type QuestionnaireResponse } from '@/lib/fhir'
import {
    answersFromResponse,
    answersReducer,
    buildQuestionnaireResponse,
    dateTimeInputValue,
    enabledLinkIds,
    EMPTY_SLOT,
    flattenQuestionnaire,
    initialAnswers,
    isAnswered,
    normaliseDateTime,
    normaliseTime,
    slotAnswer,
    unansweredRequiredLinkIds,
    type AnswerState,
} from '@/lib/questionnaire'

/**
 * The renderer's reading of a form, checked against forms the server really serves.
 *
 * Every fixture here was harvested from an in-process `d2w fhir serve` over the capture project
 * the Python suite serves (packages/dhis2w-fhir-serve/tests/conftest.py, `capture_project`),
 * which is built from the committed dhis2w-fhir goldens. The `generate-*.json` files are
 * `GET /Questionnaire/{id}/$generate` responses verbatim - the same bytes
 * `test_a_generated_response_posts_back_201` asserts this server accepts - so the round-trip
 * test below is the real contract: refill a generated response through the reducer, rebuild it,
 * and the item tree that comes out has to be the one that went in.
 *
 * The enableWhen questionnaires are hand-written, and deliberately so: the DHIS2 emitter writes
 * no `enableWhen` at all, so there is no golden to harvest. They state the R4 semantics the
 * evaluator implements rather than a shape the server produces.
 */

const questionnaires = new Map(
    bundleResources(questionnaireBundleFixture as unknown as Bundle<Questionnaire>).map((questionnaire) => [
        questionnaire.id ?? '',
        questionnaire,
    ]),
)

const temporalQuestionnaire = temporalQuestionnaireFixture as unknown as Questionnaire

/** One served form by its DHIS2 uid, failing loudly rather than testing against undefined. */
function servedForm(id: string): Questionnaire {
    const questionnaire = questionnaires.get(id)
    if (questionnaire === undefined) throw new Error(`the fixture bundle serves no Questionnaire ${id}`)
    return questionnaire
}

/** Every form kind, paired with the `$generate` response the server answered it with. */
const ROUND_TRIPS: { id: string; questionnaire: Questionnaire; generated: QuestionnaireResponse }[] = [
    {
        id: 'BfMAe6Itzgt',
        questionnaire: servedForm('BfMAe6Itzgt'),
        generated: generateAggregateFixture as unknown as QuestionnaireResponse,
    },
    {
        id: 'EVTsupVis01',
        questionnaire: servedForm('EVTsupVis01'),
        generated: generateEventFixture as unknown as QuestionnaireResponse,
    },
    {
        id: 'ZzYYXq4fJie',
        questionnaire: servedForm('ZzYYXq4fJie'),
        generated: generateTrackerFixture as unknown as QuestionnaireResponse,
    },
    {
        id: 'PrTemporal1',
        questionnaire: temporalQuestionnaire,
        generated: generateTemporalFixture as unknown as QuestionnaireResponse,
    },
]

describe('flattening a compiled Questionnaire', () => {
    it('reads every item of every served form kind, in document order', () => {
        for (const { id, questionnaire } of ROUND_TRIPS) {
            const spec = flattenQuestionnaire(questionnaire)
            expect(spec.questionLinkIds.length, id).toBe(questionCount(questionnaire.item))
            expect(spec.rootLinkIds, id).toEqual((questionnaire.item ?? []).map((item) => item.linkId))
            expect(new Set(spec.nodes.map((node) => node.linkId)).size, id).toBe(spec.nodes.length)
        }
    })

    it('nests an aggregate form three deep: section, data element, disaggregated cell', () => {
        const spec = flattenQuestionnaire(servedForm('BfMAe6Itzgt'))
        const section = spec.byLinkId.get(spec.rootLinkIds[0])
        const dataElement = spec.byLinkId.get(section?.childLinkIds[0] ?? '')
        const cell = spec.byLinkId.get(dataElement?.childLinkIds[0] ?? '')

        expect(section?.type).toBe('group')
        expect(section?.depth).toBe(0)
        expect(dataElement?.type).toBe('group')
        expect(dataElement?.depth).toBe(1)
        expect(cell?.type).toBe('integer')
        expect(cell?.depth).toBe(2)
        expect(cell?.parentLinkId).toBe(dataElement?.linkId)
        expect(cell?.ancestorLinkIds).toEqual([section?.linkId, dataElement?.linkId])
        // A cell's link id is `{dataElement}.{categoryOptionCombo}`, and its own code is the
        // combo - the data element's uid is on the group above it.
        expect(cell?.linkId.startsWith(`${dataElement?.linkId}.`)).toBe(true)
        expect(cell?.code?.code).toBe(cell?.linkId.split('.')[1])
    })

    it('carries the DHIS2 coding, the option-set binding, and the item type of a tracker question', () => {
        const spec = flattenQuestionnaire(servedForm('ZzYYXq4fJie'))
        const feeding = spec.byLinkId.get('X8zyunlgUfM')

        expect(feeding?.type).toBe('choice')
        expect(feeding?.answerElement).toBe('valueCoding')
        expect(feeding?.fillable).toBe(true)
        expect(feeding?.code).toEqual({
            code: 'X8zyunlgUfM',
            system: 'http://localhost:8080/fhir/CodeSystem/d2-de-cs',
            display: 'MCH Infant Feeding',
        })
        expect(feeding?.answerValueSet).toBe('http://localhost:8080/fhir/ValueSet/d2-os-x31y45jvIQL-vs')
    })

    it('reads required and the minValue extension off the one golden that carries them', () => {
        const spec = flattenQuestionnaire(servedForm('PsAncVisit1'))
        const visitNumber = spec.byLinkId.get('DeAncVisNo1')

        expect(visitNumber?.required).toBe(true)
        expect(visitNumber?.minimum).toBe(1)
        expect(visitNumber?.maximum).toBeNull()
        expect(spec.byLinkId.get('DeAncBpSys1')?.required).toBe(false)
    })

    it('reads repeats and both bounds off the temporal form', () => {
        const spec = flattenQuestionnaire(temporalQuestionnaire)

        expect(spec.byLinkId.get('DeSymptoms01')?.repeats).toBe(true)
        expect(spec.byLinkId.get('DeVisitTime1')?.repeats).toBe(false)
        expect(spec.byLinkId.get('DeCoverage01')?.minimum).toBe(0)
        expect(spec.byLinkId.get('DeCoverage01')?.maximum).toBe(100)
    })

    it('maps each item type onto the value[x] the capture validator demands', () => {
        const spec = flattenQuestionnaire(temporalQuestionnaire)
        const elements = Object.fromEntries(
            spec.questionLinkIds.map((linkId) => [linkId, spec.byLinkId.get(linkId)?.answerElement]),
        )

        expect(elements).toEqual({
            DeVisitDate1: 'valueDate',
            DeVisitTime1: 'valueTime',
            DeVisitStamp: 'valueDateTime',
            DeVisitLink1: 'valueUri',
            DeSymptoms01: 'valueCoding',
            DeCoverage01: 'valueDecimal',
            DeOpenBind01: 'valueCoding',
        })
    })
})

/**
 * A form with a condition on every operator, so the truth table below is one document.
 *
 * `q-boolean`, `q-integer`, `q-date` and `q-coding` are the questions conditions read; every
 * `d-*` item is a dependent whose visibility the table asserts.
 */
const CONDITIONAL_FORM: Questionnaire = {
    resourceType: 'Questionnaire',
    id: 'conditional',
    url: 'http://example.org/fhir/Questionnaire/conditional',
    status: 'active',
    item: [
        { linkId: 'q-boolean', type: 'boolean', text: 'A boolean' },
        { linkId: 'q-integer', type: 'integer', text: 'An integer' },
        { linkId: 'q-date', type: 'date', text: 'A date' },
        { linkId: 'q-coding', type: 'choice', text: 'A concept' },
        {
            linkId: 'd-exists',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: 'exists', answerBoolean: true }],
        },
        {
            linkId: 'd-missing',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: 'exists', answerBoolean: false }],
        },
        {
            linkId: 'd-equals',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: '=', answerInteger: 5 }],
        },
        {
            linkId: 'd-not-equals',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: '!=', answerInteger: 5 }],
        },
        {
            linkId: 'd-greater',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: '>', answerInteger: 5 }],
        },
        {
            linkId: 'd-at-least',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: '>=', answerInteger: 5 }],
        },
        {
            linkId: 'd-less',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: '<', answerInteger: 5 }],
        },
        {
            linkId: 'd-at-most',
            type: 'string',
            enableWhen: [{ question: 'q-integer', operator: '<=', answerInteger: 5 }],
        },
        {
            linkId: 'd-after',
            type: 'string',
            enableWhen: [{ question: 'q-date', operator: '>', answerDate: '2026-07-01' }],
        },
        {
            linkId: 'd-boolean-true',
            type: 'string',
            enableWhen: [{ question: 'q-boolean', operator: '=', answerBoolean: true }],
        },
        {
            linkId: 'd-coded',
            type: 'string',
            enableWhen: [
                {
                    question: 'q-coding',
                    operator: '=',
                    answerCoding: { system: 'http://example.org/cs', code: 'YES' },
                },
            ],
        },
        {
            linkId: 'd-any',
            type: 'string',
            enableBehavior: 'any',
            enableWhen: [
                { question: 'q-boolean', operator: '=', answerBoolean: true },
                { question: 'q-integer', operator: '>', answerInteger: 100 },
            ],
        },
        {
            linkId: 'd-all',
            type: 'string',
            enableBehavior: 'all',
            enableWhen: [
                { question: 'q-boolean', operator: '=', answerBoolean: true },
                { question: 'q-integer', operator: '>', answerInteger: 100 },
            ],
        },
        {
            linkId: 'd-unknown-question',
            type: 'string',
            enableWhen: [{ question: 'q-not-a-question', operator: 'exists', answerBoolean: true }],
        },
        {
            linkId: 'g-conditional',
            type: 'group',
            enableWhen: [{ question: 'q-boolean', operator: '=', answerBoolean: true }],
            item: [{ linkId: 'd-in-group', type: 'string' }],
        },
    ],
}

const conditionalSpec = flattenQuestionnaire(CONDITIONAL_FORM)

/** Answers as literals, which is what a control writes and the reducer holds. */
function answersOf(literals: Record<string, string>): AnswerState {
    return Object.fromEntries(
        Object.entries(literals).map(([linkId, text]) => [linkId, [{ text, coding: null }]]),
    )
}

describe('enableWhen', () => {
    it('asks an unconditional question whatever has been answered', () => {
        expect(enabledLinkIds(conditionalSpec, {}).has('q-integer')).toBe(true)
    })

    const truthTable: { name: string; answers: AnswerState; enabled: string[]; disabled: string[] }[] = [
        {
            name: 'nothing answered',
            answers: {},
            enabled: ['d-missing'],
            disabled: [
                'd-exists',
                'd-equals',
                'd-not-equals',
                'd-greater',
                'd-at-least',
                'd-less',
                'd-at-most',
                'd-after',
                'd-boolean-true',
                'd-coded',
                'd-any',
                'd-all',
                'd-in-group',
            ],
        },
        {
            name: 'the integer is 5',
            answers: answersOf({ 'q-integer': '5' }),
            enabled: ['d-exists', 'd-equals', 'd-at-least', 'd-at-most'],
            disabled: ['d-missing', 'd-not-equals', 'd-greater', 'd-less'],
        },
        {
            name: 'the integer is 4',
            answers: answersOf({ 'q-integer': '4' }),
            enabled: ['d-exists', 'd-not-equals', 'd-less', 'd-at-most'],
            disabled: ['d-equals', 'd-greater', 'd-at-least'],
        },
        {
            name: 'the integer is 200',
            answers: answersOf({ 'q-integer': '200' }),
            enabled: ['d-greater', 'd-at-least', 'd-any'],
            disabled: ['d-less', 'd-at-most', 'd-all'],
        },
        {
            name: 'a blank integer is no answer at all',
            answers: answersOf({ 'q-integer': '' }),
            enabled: ['d-missing'],
            disabled: ['d-exists', 'd-equals'],
        },
        {
            name: 'the date is after the threshold',
            answers: answersOf({ 'q-date': '2026-07-02' }),
            enabled: ['d-after'],
            disabled: [],
        },
        {
            name: 'the date is the threshold itself',
            answers: answersOf({ 'q-date': '2026-07-01' }),
            enabled: [],
            disabled: ['d-after'],
        },
        {
            name: 'the boolean is true',
            answers: answersOf({ 'q-boolean': 'true' }),
            enabled: ['d-boolean-true', 'd-any', 'g-conditional', 'd-in-group'],
            disabled: ['d-all'],
        },
        {
            name: 'the boolean is false',
            answers: answersOf({ 'q-boolean': 'false' }),
            enabled: [],
            disabled: ['d-boolean-true', 'd-any', 'g-conditional', 'd-in-group'],
        },
        {
            name: 'the boolean is true and the integer is over a hundred',
            answers: { ...answersOf({ 'q-boolean': 'true' }), ...answersOf({ 'q-integer': '200' }) },
            enabled: ['d-any', 'd-all'],
            disabled: [],
        },
    ]

    for (const row of truthTable) {
        it(`decides the form when ${row.name}`, () => {
            const enabled = enabledLinkIds(conditionalSpec, row.answers)
            for (const linkId of row.enabled) expect(enabled.has(linkId), `${linkId} enabled`).toBe(true)
            for (const linkId of row.disabled) expect(enabled.has(linkId), `${linkId} disabled`).toBe(false)
        })
    }

    it('matches a coded condition on code and system together', () => {
        const matching = { 'q-coding': [{ text: '', coding: { system: 'http://example.org/cs', code: 'YES' } }] }
        const wrongSystem = { 'q-coding': [{ text: '', coding: { system: 'http://other.org/cs', code: 'YES' } }] }
        const wrongCode = { 'q-coding': [{ text: '', coding: { system: 'http://example.org/cs', code: 'NO' } }] }

        expect(enabledLinkIds(conditionalSpec, matching).has('d-coded')).toBe(true)
        expect(enabledLinkIds(conditionalSpec, wrongSystem).has('d-coded')).toBe(false)
        expect(enabledLinkIds(conditionalSpec, wrongCode).has('d-coded')).toBe(false)
    })

    it('hides an item whose condition names a question the form does not ask', () => {
        expect(enabledLinkIds(conditionalSpec, {}).has('d-unknown-question')).toBe(false)
    })

    it('disables a group’s children even when the child itself is unconditional', () => {
        const enabled = enabledLinkIds(conditionalSpec, answersOf({ 'q-boolean': 'false' }))

        expect(enabled.has('d-in-group')).toBe(false)
        expect(conditionalSpec.byLinkId.get('d-in-group')?.enableWhen).toEqual([])
    })

    it('keeps a disabled item’s answers in state but writes none of them', () => {
        const answers = { ...answersOf({ 'q-boolean': 'false' }), ...answersOf({ 'd-in-group': 'typed earlier' }) }

        const built = buildQuestionnaireResponse(conditionalSpec, answers, CONDITIONAL_FORM, null)

        expect(answers['d-in-group']).toHaveLength(1)
        expect(JSON.stringify(built.item ?? [])).not.toContain('typed earlier')
    })
})

describe('the answers reducer', () => {
    const spec = flattenQuestionnaire(temporalQuestionnaire)

    it('starts a form with no answers when no item declares an initial value', () => {
        expect(initialAnswers(spec)).toEqual({})
    })

    it('starts a form on the initial values its items declare', () => {
        const withInitial: Questionnaire = {
            resourceType: 'Questionnaire',
            status: 'active',
            item: [{ linkId: 'greeting', type: 'string', initial: [{ valueString: 'hello' }] }],
        }

        expect(initialAnswers(flattenQuestionnaire(withInitial))).toEqual({
            greeting: [{ text: 'hello', coding: null }],
        })
    })

    it('sets a slot that does not exist yet rather than asking to be given one first', () => {
        const next = answersReducer({}, {
            kind: 'set',
            linkId: 'DeCoverage01',
            index: 0,
            slot: { text: '42', coding: null },
        })

        expect(next).toEqual({ DeCoverage01: [{ text: '42', coding: null }] })
    })

    it('leaves the state it was given untouched', () => {
        const before: AnswerState = { DeCoverage01: [{ text: '1', coding: null }] }

        answersReducer(before, { kind: 'set', linkId: 'DeCoverage01', index: 0, slot: { text: '2', coding: null } })

        expect(before).toEqual({ DeCoverage01: [{ text: '1', coding: null }] })
    })

    it('clears one question without touching its neighbours', () => {
        const before = answersOf({ DeCoverage01: '42', DeVisitLink1: 'https://example.invalid' })

        const next = answersReducer(before, { kind: 'clear', linkId: 'DeCoverage01' })

        expect(next).toEqual(answersOf({ DeVisitLink1: 'https://example.invalid' }))
    })

    it('returns the same state when clearing a question that was never answered', () => {
        const before = answersOf({ DeCoverage01: '42' })

        expect(answersReducer(before, { kind: 'clear', linkId: 'DeVisitLink1' })).toBe(before)
    })

    it('adds and removes repeat rows, dropping the question once the last row goes', () => {
        const one = answersReducer({}, { kind: 'add-repeat', linkId: 'DeSymptoms01' })
        const two = answersReducer(one, { kind: 'add-repeat', linkId: 'DeSymptoms01' })
        const filled = answersReducer(two, {
            kind: 'set',
            linkId: 'DeSymptoms01',
            index: 1,
            slot: { text: '', coding: { code: 'OpCough0001' } },
        })

        expect(one.DeSymptoms01).toEqual([EMPTY_SLOT])
        expect(two.DeSymptoms01).toHaveLength(2)
        expect(filled.DeSymptoms01?.[1]).toEqual({ text: '', coding: { code: 'OpCough0001' } })

        const afterFirstRemoved = answersReducer(filled, {
            kind: 'remove-repeat',
            linkId: 'DeSymptoms01',
            index: 0,
        })

        expect(afterFirstRemoved.DeSymptoms01).toEqual([{ text: '', coding: { code: 'OpCough0001' } }])

        const afterLastRemoved = answersReducer(afterFirstRemoved, {
            kind: 'remove-repeat',
            linkId: 'DeSymptoms01',
            index: 0,
        })

        expect('DeSymptoms01' in afterLastRemoved).toBe(false)
    })

    it('replaces the whole state, which is what filling with test data does', () => {
        const generated = answersFromResponse(spec, generateTemporalFixture as unknown as QuestionnaireResponse)

        const next = answersReducer(answersOf({ DeCoverage01: '1' }), { kind: 'replace', answers: generated })

        expect(next).toBe(generated)
        expect(next.DeCoverage01).toEqual([{ text: '58.3', coding: null }])
    })
})

describe('what counts as an answer', () => {
    const spec = flattenQuestionnaire(temporalQuestionnaire)

    it('reads a slot as the value[x] its question answers on', () => {
        const decimal = spec.byLinkId.get('DeCoverage01')
        const date = spec.byLinkId.get('DeVisitDate1')

        expect(slotAnswer(decimal!, { text: '58.3', coding: null })).toEqual({ valueDecimal: 58.3 })
        expect(slotAnswer(decimal!, { text: '', coding: null })).toBeNull()
        expect(slotAnswer(decimal!, { text: 'banana', coding: null })).toBeNull()
        expect(slotAnswer(date!, { text: '2026-07-22', coding: null })).toEqual({ valueDate: '2026-07-22' })
    })

    it('refuses a non-whole number on a question that answers as integer', () => {
        const ancSpec = flattenQuestionnaire(servedForm('PsAncVisit1'))
        const visitNumber = ancSpec.byLinkId.get('DeAncVisNo1')

        expect(slotAnswer(visitNumber!, { text: '3', coding: null })).toEqual({ valueInteger: 3 })
        expect(slotAnswer(visitNumber!, { text: '3.5', coding: null })).toBeNull()
    })

    it('holds false as an answer, and nothing as none', () => {
        const trackerSpec = flattenQuestionnaire(servedForm('ZzYYXq4fJie'))
        const measles = trackerSpec.byLinkId.get('FqlgKAG8HOu')

        expect(slotAnswer(measles!, { text: 'false', coding: null })).toEqual({ valueBoolean: false })
        expect(isAnswered(measles!, { FqlgKAG8HOu: [{ text: 'false', coding: null }] })).toBe(true)
        expect(isAnswered(measles!, { FqlgKAG8HOu: [EMPTY_SLOT] })).toBe(false)
    })

    it('writes an open-choice free text as a string, and a closed choice as nothing', () => {
        const openForm: Questionnaire = {
            resourceType: 'Questionnaire',
            status: 'active',
            item: [
                { linkId: 'open', type: 'open-choice' },
                { linkId: 'closed', type: 'choice' },
            ],
        }
        const openSpec = flattenQuestionnaire(openForm)

        expect(slotAnswer(openSpec.byLinkId.get('open')!, { text: 'other', coding: null })).toEqual({
            valueString: 'other',
        })
        expect(slotAnswer(openSpec.byLinkId.get('closed')!, { text: 'other', coding: null })).toBeNull()
    })

    it('names every required question the form is still waiting on', () => {
        const ancSpec = flattenQuestionnaire(servedForm('PsAncVisit1'))

        expect(unansweredRequiredLinkIds(ancSpec, {})).toEqual(['DeAncVisNo1'])
        expect(unansweredRequiredLinkIds(ancSpec, answersOf({ DeAncVisNo1: '2' }))).toEqual([])
    })
})

describe('the temporal normalisers', () => {
    it('completes what a datetime-local input gives into an R4 dateTime', () => {
        expect(normaliseDateTime('2026-07-11T02:00')).toBe('2026-07-11T02:00:00Z')
        expect(normaliseDateTime('2026-07-11T02:00:30')).toBe('2026-07-11T02:00:30Z')
        expect(normaliseDateTime('2026-07-11T02:00:00Z')).toBe('2026-07-11T02:00:00Z')
        expect(normaliseDateTime('2026-07-11T02:00:00+02:00')).toBe('2026-07-11T02:00:00+02:00')
        expect(normaliseDateTime('2026-07-11')).toBe('2026-07-11')
        expect(normaliseDateTime('  ')).toBeNull()
    })

    it('completes what a time input gives into an R4 time, which has mandatory seconds', () => {
        expect(normaliseTime('20:00')).toBe('20:00:00')
        expect(normaliseTime('20:00:00')).toBe('20:00:00')
        expect(normaliseTime('')).toBeNull()
    })

    it('hands a stored dateTime back in the shape the input will accept', () => {
        expect(dateTimeInputValue('2026-07-11T02:00:00Z')).toBe('2026-07-11T02:00:00')
        expect(dateTimeInputValue('2026-07-11T02:00:00+02:00')).toBe('2026-07-11T02:00:00')
    })
})

describe('rebuilding a QuestionnaireResponse', () => {
    for (const { id, questionnaire, generated } of ROUND_TRIPS) {
        it(`reproduces the item tree of the ${id} $generate response exactly`, () => {
            const spec = flattenQuestionnaire(questionnaire)

            const rebuilt = buildQuestionnaireResponse(
                spec,
                answersFromResponse(spec, generated),
                questionnaire,
                generated,
            )

            expect(rebuilt.item).toEqual(generated.item)
        })

        it(`keeps the ${id} envelope the server built, and drops the seed identifier`, () => {
            const spec = flattenQuestionnaire(questionnaire)

            const rebuilt = buildQuestionnaireResponse(spec, {}, questionnaire, generated)

            expect(rebuilt.resourceType).toBe('QuestionnaireResponse')
            expect(rebuilt.status).toBe('completed')
            expect(rebuilt.meta).toEqual(generated.meta)
            expect(rebuilt.extension).toEqual(generated.extension)
            expect(rebuilt.subject).toEqual(generated.subject)
            expect(rebuilt.authored).toBe(generated.authored)
            expect(rebuilt.questionnaire).toBe(questionnaire.url)
            expect(rebuilt.identifier).toBeUndefined()
            expect(rebuilt.item).toBeUndefined()
        })
    }

    it('mirrors the questionnaire’s nesting, answered branches only', () => {
        const questionnaire = servedForm('BfMAe6Itzgt')
        const spec = flattenQuestionnaire(questionnaire)
        const section = spec.byLinkId.get(spec.rootLinkIds[0])
        const dataElement = spec.byLinkId.get(section?.childLinkIds[0] ?? '')
        const cell = dataElement?.childLinkIds[1] ?? ''

        const built = buildQuestionnaireResponse(spec, answersOf({ [cell]: '12' }), questionnaire, null)

        // One answered cell yields one branch: the whole rest of a 200-question form is absent,
        // and the two groups above the cell are there only because it is.
        expect(built.item).toEqual([
            {
                linkId: section?.linkId,
                item: [{ linkId: dataElement?.linkId, item: [{ linkId: cell, answer: [{ valueInteger: 12 }] }] }],
            },
        ])
    })

    it('writes one answer per repeat row, in row order', () => {
        const spec = flattenQuestionnaire(temporalQuestionnaire)
        const answers: AnswerState = {
            DeSymptoms01: [
                { text: '', coding: { system: 'http://example.org/cs', code: 'OpFever0001', display: 'Fever' } },
                { text: '', coding: { system: 'http://example.org/cs', code: 'OpCough0001', display: 'Cough' } },
            ],
        }

        const built = buildQuestionnaireResponse(spec, answers, temporalQuestionnaire, null)

        expect(built.item).toEqual([
            {
                linkId: 'DeSymptoms01',
                answer: [
                    { valueCoding: { system: 'http://example.org/cs', code: 'OpFever0001', display: 'Fever' } },
                    { valueCoding: { system: 'http://example.org/cs', code: 'OpCough0001', display: 'Cough' } },
                ],
            },
        ])
    })

    it('writes nothing for a question this UI has no control for', () => {
        const unfillable: Questionnaire = {
            resourceType: 'Questionnaire',
            status: 'active',
            item: [{ linkId: 'photo', type: 'attachment' }],
        }
        const spec = flattenQuestionnaire(unfillable)

        expect(spec.byLinkId.get('photo')?.fillable).toBe(false)
        expect(buildQuestionnaireResponse(spec, answersOf({ photo: 'anything' }), unfillable, null).item).toBeUndefined()
    })

    it('assembles a response with no envelope rather than refusing to build one', () => {
        const questionnaire = servedForm('EVTsupVis01')
        const spec = flattenQuestionnaire(questionnaire)

        const built = buildQuestionnaireResponse(spec, answersOf({ s46m5MS0hxu: '148' }), questionnaire, null)

        expect(built).toEqual({
            resourceType: 'QuestionnaireResponse',
            questionnaire: questionnaire.url,
            status: 'completed',
            item: [{ linkId: 's46m5MS0hxu', answer: [{ valueInteger: 148 }] }],
        })
    })
})
