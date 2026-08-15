import { describe, expect, it } from 'vitest'

import generateAggregateFixture from '@/lib/__fixtures__/generate-BfMAe6Itzgt.json'
import generateEventFixture from '@/lib/__fixtures__/generate-EVTsupVis01.json'
import generateScopedFixture from '@/lib/__fixtures__/generate-PrScoped001.json'
import generateTemporalFixture from '@/lib/__fixtures__/generate-PrTemporal1.json'
import generateTrackerFixture from '@/lib/__fixtures__/generate-ZzYYXq4fJie.json'
import registrationQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrAncCare01.json'
import scopedQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrScoped001.json'
import temporalQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrTemporal1.json'
import attributeComboFormFixture from '@/lib/__fixtures__/questionnaire-TuL8IOPzpHh.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import attributeComboResponseFixture from '@/lib/__fixtures__/response-TuL8IOPzpHh.json'
import {
    attributeOptionComboOf,
    bundleResources,
    enrolledAtOf,
    incidentAtOf,
    questionCount,
    trackedEntityOf,
    trackerEnrollmentOf,
    type Bundle,
    type CodeSystem,
    type Extension,
    type Questionnaire,
    type QuestionnaireResponse,
    type Reference,
} from '@/lib/fhir'
import {
    answersFromResponse,
    answersReducer,
    buildQuestionnaireResponse,
    clearedEntityLevelAnswers,
    collectsIncidentDate,
    dateTimeInputValue,
    enabledLinkIds,
    entityLevelLinkIds,
    EMPTY_SLOT,
    extensionsWithEnrolledAt,
    extensionsWithIncidentAt,
    extensionsWithReportingPeriod,
    flattenQuestionnaire,
    initialAnswers,
    isAnswered,
    normaliseDateTime,
    normaliseTime,
    NO_CAPTURE_CONTEXT,
    openedAttributeOptionCombo,
    openedReportingUnit,
    questionCodeSystemIds,
    refilledAttributeOptionCombo,
    refilledEnrollment,
    refilledReportingUnit,
    reportingPeriodOf,
    slotAnswer,
    TRUE_ONLY_VALUE_TYPE,
    unansweredRequiredLinkIds,
    valueTypesByConcept,
    type AnswerState,
} from '@/lib/questionnaire'
import { carriesUnitOnExtension, reportingUnitOf, type OrgUnitChoice } from '@/lib/orgunits'
import { marksAnExistingSubject } from '@/lib/patients'

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
const attributeComboForm = attributeComboFormFixture as unknown as Questionnaire
const attributeComboResponse = attributeComboResponseFixture as unknown as QuestionnaireResponse

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
            DeVisitUnit1: 'valueReference',
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
        Object.entries(literals).map(([linkId, text]) => [linkId, [{ ...EMPTY_SLOT, text }]]),
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
        const matching = { 'q-coding': [{ text: '', coding: { system: 'http://example.org/cs', code: 'YES' }, reference: null }] }
        const wrongSystem = { 'q-coding': [{ text: '', coding: { system: 'http://other.org/cs', code: 'YES' }, reference: null }] }
        const wrongCode = { 'q-coding': [{ text: '', coding: { system: 'http://example.org/cs', code: 'NO' }, reference: null }] }

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

        const built = buildQuestionnaireResponse(conditionalSpec, answers, CONDITIONAL_FORM, null, NO_CAPTURE_CONTEXT)

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
            greeting: [{ text: 'hello', coding: null, reference: null }],
        })
    })

    it('sets a slot that does not exist yet rather than asking to be given one first', () => {
        const next = answersReducer({}, {
            kind: 'set',
            linkId: 'DeCoverage01',
            index: 0,
            slot: { text: '42', coding: null, reference: null },
        })

        expect(next).toEqual({ DeCoverage01: [{ text: '42', coding: null, reference: null }] })
    })

    it('leaves the state it was given untouched', () => {
        const before: AnswerState = { DeCoverage01: [{ text: '1', coding: null, reference: null }] }

        answersReducer(before, { kind: 'set', linkId: 'DeCoverage01', index: 0, slot: { text: '2', coding: null, reference: null } })

        expect(before).toEqual({ DeCoverage01: [{ text: '1', coding: null, reference: null }] })
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
            slot: { text: '', coding: { code: 'OpCough0001' }, reference: null },
        })

        expect(one.DeSymptoms01).toEqual([EMPTY_SLOT])
        expect(two.DeSymptoms01).toHaveLength(2)
        expect(filled.DeSymptoms01?.[1]).toEqual({ text: '', coding: { code: 'OpCough0001' }, reference: null })

        const afterFirstRemoved = answersReducer(filled, {
            kind: 'remove-repeat',
            linkId: 'DeSymptoms01',
            index: 0,
        })

        expect(afterFirstRemoved.DeSymptoms01).toEqual([{ text: '', coding: { code: 'OpCough0001' }, reference: null }])

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
        expect(next.DeCoverage01).toEqual([{ text: '58.3', coding: null, reference: null }])
    })
})

describe('what counts as an answer', () => {
    const spec = flattenQuestionnaire(temporalQuestionnaire)

    it('reads a slot as the value[x] its question answers on', () => {
        const decimal = spec.byLinkId.get('DeCoverage01')
        const date = spec.byLinkId.get('DeVisitDate1')

        expect(slotAnswer(decimal!, { text: '58.3', coding: null, reference: null })).toEqual({ valueDecimal: 58.3 })
        expect(slotAnswer(decimal!, { text: '', coding: null, reference: null })).toBeNull()
        expect(slotAnswer(decimal!, { text: 'banana', coding: null, reference: null })).toBeNull()
        expect(slotAnswer(date!, { text: '2026-07-22', coding: null, reference: null })).toEqual({ valueDate: '2026-07-22' })
    })

    it('refuses a non-whole number on a question that answers as integer', () => {
        const ancSpec = flattenQuestionnaire(servedForm('PsAncVisit1'))
        const visitNumber = ancSpec.byLinkId.get('DeAncVisNo1')

        expect(slotAnswer(visitNumber!, { text: '3', coding: null, reference: null })).toEqual({ valueInteger: 3 })
        expect(slotAnswer(visitNumber!, { text: '3.5', coding: null, reference: null })).toBeNull()
    })

    it('holds false as an answer, and nothing as none', () => {
        const trackerSpec = flattenQuestionnaire(servedForm('ZzYYXq4fJie'))
        const measles = trackerSpec.byLinkId.get('FqlgKAG8HOu')

        expect(slotAnswer(measles!, { text: 'false', coding: null, reference: null })).toEqual({ valueBoolean: false })
        expect(isAnswered(measles!, { FqlgKAG8HOu: [{ text: 'false', coding: null, reference: null }] })).toBe(true)
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

        expect(slotAnswer(openSpec.byLinkId.get('open')!, { text: 'other', coding: null, reference: null })).toEqual({
            valueString: 'other',
        })
        expect(slotAnswer(openSpec.byLinkId.get('closed')!, { text: 'other', coding: null, reference: null })).toBeNull()
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
                NO_CAPTURE_CONTEXT,
            )

            expect(rebuilt.item).toEqual(generated.item)
        })

        it(`keeps the ${id} envelope the server built, and drops the seed identifier`, () => {
            const spec = flattenQuestionnaire(questionnaire)

            const rebuilt = buildQuestionnaireResponse(spec, {}, questionnaire, generated, NO_CAPTURE_CONTEXT)

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

        const built = buildQuestionnaireResponse(spec, answersOf({ [cell]: '12' }), questionnaire, null, NO_CAPTURE_CONTEXT)

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
                { text: '', coding: { system: 'http://example.org/cs', code: 'OpFever0001', display: 'Fever' }, reference: null },
                { text: '', coding: { system: 'http://example.org/cs', code: 'OpCough0001', display: 'Cough' }, reference: null },
            ],
        }

        const built = buildQuestionnaireResponse(spec, answers, temporalQuestionnaire, null, NO_CAPTURE_CONTEXT)

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
        expect(buildQuestionnaireResponse(spec, answersOf({ photo: 'anything' }), unfillable, null, NO_CAPTURE_CONTEXT).item).toBeUndefined()
    })

    it('assembles a response with no envelope rather than refusing to build one', () => {
        const questionnaire = servedForm('EVTsupVis01')
        const spec = flattenQuestionnaire(questionnaire)

        const built = buildQuestionnaireResponse(spec, answersOf({ s46m5MS0hxu: '148' }), questionnaire, null, NO_CAPTURE_CONTEXT)

        expect(built).toEqual({
            resourceType: 'QuestionnaireResponse',
            questionnaire: questionnaire.url,
            status: 'completed',
            item: [{ linkId: 's46m5MS0hxu', answer: [{ valueInteger: 148 }] }],
        })
    })
})

/**
 * The one piece of envelope context the user owns, and the two moments it is decided in.
 *
 * The fixtures are the wave's own artifacts: `Questionnaire-TuL8IOPzpHh` is the golden aggregate
 * form whose data set rides a non-default category combo, and the response beside it is the
 * example the emitter publishes for it - carrying the singular extension exactly as a conformant
 * capture must. So what is asserted below is the wire contract, not a spelling agreed on here.
 */
describe('the attribute option combo a submission reports for', () => {
    const spec = flattenQuestionnaire(attributeComboForm)
    const chosen = {
        system: 'http://localhost:8080/fhir/CodeSystem/d2-aoc-idcDPkDtepR-cs',
        code: 'pO5CEqK6c1s',
        display: 'Improve access to clean water',
    }

    it('writes the chosen coding onto a response built from no envelope at all', () => {
        const built = buildQuestionnaireResponse(spec, {}, attributeComboForm, null, { ...NO_CAPTURE_CONTEXT, attributeOptionCombo: chosen })

        expect(built.extension).toEqual([
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-attribute-option-combo',
                valueCoding: chosen,
            },
        ])
    })

    it('replaces the envelope`s combo in place, keeping every other piece of context', () => {
        const built = buildQuestionnaireResponse(spec, {}, attributeComboForm, attributeComboResponse, { ...NO_CAPTURE_CONTEXT, attributeOptionCombo: chosen })

        // The picker wins over the draw, on the same philosophy the answers follow - and the
        // period, the form type, and the order they were written in are the server's own.
        expect(built.extension?.map((extension) => extension.url)).toEqual(
            attributeComboResponse.extension?.map((extension) => extension.url),
        )
        expect(attributeOptionComboOf(built)).toEqual(chosen)
        expect(built.extension?.[0]).toEqual(attributeComboResponse.extension?.[0])
    })

    it('leaves the envelope untouched when nothing was chosen, which is the default-combo case', () => {
        const built = buildQuestionnaireResponse(spec, {}, attributeComboForm, attributeComboResponse, NO_CAPTURE_CONTEXT)

        expect(built.extension).toEqual(attributeComboResponse.extension)
    })

    it('writes nothing at all for a form that declares no vocabulary', () => {
        const questionnaire = servedForm('BfMAe6Itzgt')
        const built = buildQuestionnaireResponse(flattenQuestionnaire(questionnaire), {}, questionnaire, null, { ...NO_CAPTURE_CONTEXT, attributeOptionCombo: chosen })

        expect(built.extension).toBeUndefined()
    })

    it('pre-selects the drawn combo when a form opens, and never over a choice already made', () => {
        expect(openedAttributeOptionCombo(null, attributeComboResponse)).toEqual(
            attributeOptionComboOf(attributeComboResponse),
        )
        expect(openedAttributeOptionCombo(chosen, attributeComboResponse)).toEqual(chosen)
        expect(openedAttributeOptionCombo(null, null)).toBeNull()
    })

    it('takes the fresh draw on a refill, and keeps the choice when the draw states none', () => {
        expect(refilledAttributeOptionCombo(chosen, attributeComboResponse)).toEqual(
            attributeOptionComboOf(attributeComboResponse),
        )
        expect(refilledAttributeOptionCombo(chosen, generateAggregateFixture as unknown as QuestionnaireResponse)).toEqual(
            chosen,
        )
        expect(refilledAttributeOptionCombo(null, null)).toBeNull()
    })
})

/**
 * A DHIS2 `ORGANISATION_UNIT` data element, answered.
 *
 * The emitter writes that value type as a `reference` item and nothing else writes one, so the
 * whole of this case is a `Location/<stem>` on `valueReference`. `PrTemporal1` carries one -
 * `DeVisitUnit1` - and its `$generate` skeleton answers it, which is what makes the round trip
 * above a test of this slot rather than of the six that were already there.
 */
describe('a reference answer', () => {
    const spec = flattenQuestionnaire(temporalQuestionnaire)
    const node = spec.byLinkId.get('DeVisitUnit1')
    const picked: Reference = { reference: 'Location/DiszpKrYNg8', display: 'Ngelehun CHC' }

    it('is fillable, and answers on valueReference', () => {
        expect(node?.answerElement).toBe('valueReference')
        expect(node?.fillable).toBe(true)
    })

    it('carries the reference on its own slot field, never through the text a keyboard writes', () => {
        expect(slotAnswer(node!, { ...EMPTY_SLOT, reference: picked })).toEqual({ valueReference: picked })
        // A text spelling of a reference is not an answer: the capture validator reads the
        // `value[x]` the item type pins, and a `valueString` there is refused outright.
        expect(slotAnswer(node!, { ...EMPTY_SLOT, text: 'Location/DiszpKrYNg8' })).toBeNull()
        expect(slotAnswer(node!, EMPTY_SLOT)).toBeNull()
    })

    it('counts as answered only once a unit has been picked', () => {
        expect(isAnswered(node!, { DeVisitUnit1: [EMPTY_SLOT] })).toBe(false)
        expect(isAnswered(node!, { DeVisitUnit1: [{ ...EMPTY_SLOT, reference: picked }] })).toBe(true)
    })

    it('reads the drawn answer back as a pre-selection', () => {
        const answers = answersFromResponse(spec, generateTemporalFixture as unknown as QuestionnaireResponse)

        expect(answers.DeVisitUnit1?.[0]?.reference?.reference).toBe('Location/DiszpKrYNg8')
        expect(answers.DeVisitUnit1?.[0]?.text).toBe('')
        expect(answers.DeVisitUnit1?.[0]?.coding).toBeNull()
    })
})

/**
 * The other piece of envelope context the user owns, and the two places a form kind carries it.
 *
 * ONE FACT, TWO ELEMENTS. An aggregate or event response names its organisation unit as `subject`;
 * a tracker one's subject is the tracked entity, so the unit rides the `d2-organisation-unit`
 * extension instead. `dhis2w_fhir_serve.capture.validate` checks whichever of the two the declared
 * kind pins, so writing to the wrong one would be refused - which is what these assert against the
 * server's own skeletons for all three kinds.
 */
describe('the organisation unit a submission reports from', () => {
    const scopedForm = scopedQuestionnaireFixture as unknown as Questionnaire
    const scopedSkeleton = generateScopedFixture as unknown as QuestionnaireResponse
    const trackerForm = servedForm('ZzYYXq4fJie')
    const trackerSkeleton = generateTrackerFixture as unknown as QuestionnaireResponse
    const aggregateForm = servedForm('BfMAe6Itzgt')
    const aggregateSkeleton = generateAggregateFixture as unknown as QuestionnaireResponse
    const chosen: Reference = { reference: 'Location/O6uvpzGd5pu', display: 'Bo' }

    it('reads the drawn unit off whichever element the form kind carries it on', () => {
        expect(reportingUnitOf(aggregateSkeleton, 'aggregate')).toEqual({ reference: 'Location/DiszpKrYNg8' })
        expect(reportingUnitOf(scopedSkeleton, 'event')).toEqual({ reference: 'Location/DiszpKrYNg8' })
        expect(reportingUnitOf(trackerSkeleton, 'tracker-event')).toEqual({
            reference: 'Location/DiszpKrYNg8',
        })
    })

    it('rewrites an aggregate response`s subject and leaves the period where the server wrote it', () => {
        const spec = flattenQuestionnaire(aggregateForm)
        const built = buildQuestionnaireResponse(spec, {}, aggregateForm, aggregateSkeleton, {
            ...NO_CAPTURE_CONTEXT,
            reportingUnit: chosen,
        })

        expect(built.subject).toEqual(chosen)
        expect(built.extension).toEqual(aggregateSkeleton.extension)
    })

    it('rewrites an event response`s subject', () => {
        const spec = flattenQuestionnaire(scopedForm)
        const built = buildQuestionnaireResponse(spec, {}, scopedForm, scopedSkeleton, {
            ...NO_CAPTURE_CONTEXT,
            reportingUnit: chosen,
        })

        expect(built.subject).toEqual(chosen)
    })

    it('rewrites a tracker event`s extension in place and never touches its tracked-entity subject', () => {
        const spec = flattenQuestionnaire(trackerForm)
        const built = buildQuestionnaireResponse(spec, {}, trackerForm, trackerSkeleton, {
            ...NO_CAPTURE_CONTEXT,
            reportingUnit: chosen,
        })

        expect(built.subject).toEqual(trackerSkeleton.subject)
        expect(reportingUnitOf(built, 'tracker-event')).toEqual(chosen)
        // Replaced where the server wrote it: the enrollment and the form type keep their places,
        // so a rebuilt response reads as the same document rather than as a reshuffled one.
        expect(built.extension?.map((extension) => extension.url)).toEqual(
            trackerSkeleton.extension?.map((extension) => extension.url),
        )
    })

    it('keeps whatever the envelope drew when nothing was picked', () => {
        const spec = flattenQuestionnaire(trackerForm)
        const built = buildQuestionnaireResponse(spec, {}, trackerForm, trackerSkeleton, NO_CAPTURE_CONTEXT)

        expect(built.extension).toEqual(trackerSkeleton.extension)
        expect(built.subject).toEqual(trackerSkeleton.subject)
    })

    it('pre-selects the drawn unit when a form opens, and never over a choice already made', () => {
        expect(openedReportingUnit(null, scopedSkeleton, scopedForm)).toEqual({
            unit: { reference: 'Location/DiszpKrYNg8' },
            keptUnitNotAdmitted: false,
        })
        expect(openedReportingUnit(chosen, scopedSkeleton, scopedForm)).toEqual({
            unit: chosen,
            keptUnitNotAdmitted: false,
        })
        expect(openedReportingUnit(null, null, scopedForm)).toEqual({
            unit: null,
            keptUnitNotAdmitted: false,
        })
    })

    /**
     * The unit a browser tab keeps, graded against the form that is opening.
     *
     * A supervisor filing six forms reports them all from one facility, so the kept unit comes
     * before the draw - but only where the form's assignment admits it, because a submission from a
     * unit the form is not assigned to is refused when it reaches DHIS2. The offer is what says
     * which of the two it is, and while there is no offer there is nothing to grade against.
     */
    describe('the organisation unit a browser tab keeps', () => {
        const ngelehun: OrgUnitChoice = {
            id: 'DiszpKrYNg8',
            name: 'Ngelehun CHC',
            location: { resourceType: 'Location', id: 'DiszpKrYNg8', name: 'Ngelehun CHC' },
            level: null,
            parentName: 'Badjia',
        }
        const bo: OrgUnitChoice = {
            id: 'O6uvpzGd5pu',
            name: 'Bo',
            location: { resourceType: 'Location', id: 'O6uvpzGd5pu', name: 'Bo' },
            level: null,
            parentName: 'Sierra Leone',
        }
        const offer = new Map([
            [ngelehun.id, ngelehun],
            [bo.id, bo],
        ])

        it('opens on the kept unit rather than on the draw', () => {
            expect(openedReportingUnit(null, scopedSkeleton, scopedForm, bo.id, offer)).toEqual({
                unit: { reference: 'Location/O6uvpzGd5pu', display: 'Bo' },
                keptUnitNotAdmitted: false,
            })
        })

        it('falls back to the draw and states the mismatch when the form excludes the kept unit', () => {
            const elsewhere = new Map([[ngelehun.id, ngelehun]])

            expect(openedReportingUnit(null, scopedSkeleton, scopedForm, bo.id, elsewhere)).toEqual({
                unit: { reference: 'Location/DiszpKrYNg8' },
                keptUnitNotAdmitted: true,
            })
        })

        it('adopts nothing and states nothing while the offer is still being read', () => {
            expect(openedReportingUnit(null, scopedSkeleton, scopedForm, bo.id, null)).toEqual({
                unit: { reference: 'Location/DiszpKrYNg8' },
                keptUnitNotAdmitted: false,
            })
        })

        it('leaves a choice already made alone, kept unit or not', () => {
            expect(openedReportingUnit(chosen, scopedSkeleton, scopedForm, ngelehun.id, offer)).toEqual({
                unit: chosen,
                keptUnitNotAdmitted: false,
            })
        })
    })

    it('takes the fresh draw on a refill, and keeps the choice when the draw states none', () => {
        const drawnNothing: QuestionnaireResponse = { resourceType: 'QuestionnaireResponse', status: 'completed' }

        expect(refilledReportingUnit(chosen, scopedSkeleton, scopedForm)).toEqual({
            reference: 'Location/DiszpKrYNg8',
        })
        expect(refilledReportingUnit(chosen, drawnNothing, scopedForm)).toEqual(chosen)
        expect(refilledReportingUnit(null, null, scopedForm)).toBeNull()
    })
})

/**
 * A registration submission, rebuilt: the two dates ride it untouched.
 *
 * `D2EnrolledAt` and `D2IncidentAt` are the enrollment's own facts, and this page derives neither
 * - they come off the `$generate` envelope exactly as `D2Period` does for an aggregate capture,
 * and the whole contract is that a rebuild changes only what the user owns. The organisation unit
 * is what the user owns here, and the registration kind carries it on the extension rather than on
 * `subject` for the same reason a stage response does: the subject is the person.
 *
 * The documents are written from the published profile (`D2TrackerRegistrationResponse`) rather
 * than harvested, because the fixture project publishes no registration form yet; the browser
 * suite is what walks the same rebuild against a real server.
 */
describe('rebuilding a tracker registration', () => {
    const registrationForm: Questionnaire = {
        resourceType: 'Questionnaire',
        id: 'PrTracker001',
        url: 'http://localhost:8080/fhir/Questionnaire/PrTracker001',
        status: 'active',
        extension: [
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' },
        ],
        item: [{ linkId: 'TeaFirstNm1', text: 'First name', type: 'string' }],
    }

    const registrationSkeleton: QuestionnaireResponse = {
        resourceType: 'QuestionnaireResponse',
        status: 'completed',
        questionnaire: 'http://localhost:8080/fhir/Questionnaire/PrTracker001',
        subject: {
            type: 'Patient',
            identifier: { system: 'http://dhis2.org/fhir/id/tracked-entity', value: 'wJt3Qy1PxLd' },
        },
        extension: [
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-organisation-unit',
                valueReference: { reference: 'Location/DiszpKrYNg8' },
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-tracker-enrollment',
                valueIdentifier: {
                    system: 'http://dhis2.org/fhir/id/tracker-enrollment',
                    value: 'Qm4bTnPzKdE',
                },
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at',
                valueDateTime: '2026-07-21T04:00:00Z',
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-incident-at',
                valueDateTime: '2026-07-14T04:00:00Z',
            },
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' },
        ],
        item: [{ linkId: 'TeaFirstNm1', answer: [{ valueString: 'Sarah' }] }],
    }

    it('carries the unit on the extension, as the registration profile pins it', () => {
        expect(carriesUnitOnExtension('tracker')).toBe(true)
        expect(reportingUnitOf(registrationSkeleton, 'tracker')).toEqual({
            reference: 'Location/DiszpKrYNg8',
        })
    })

    it('rewrites the unit in place and leaves both enrollment dates exactly where they were', () => {
        const chosen: Reference = { reference: 'Location/O6uvpzGd5pu', display: 'Bo' }
        const spec = flattenQuestionnaire(registrationForm)
        const built = buildQuestionnaireResponse(
            spec,
            { TeaFirstNm1: [{ text: 'Amina', coding: null, reference: null }] },
            registrationForm,
            registrationSkeleton,
            { ...NO_CAPTURE_CONTEXT, reportingUnit: chosen },
        )

        expect(reportingUnitOf(built, 'tracker')).toEqual(chosen)
        // The minted subject is the server's, and so are the dates: only the unit moved.
        expect(built.subject).toEqual(registrationSkeleton.subject)
        expect(enrolledAtOf(built)).toBe('2026-07-21T04:00:00Z')
        expect(incidentAtOf(built)).toBe('2026-07-14T04:00:00Z')
        expect(trackerEnrollmentOf(built)).toBe('Qm4bTnPzKdE')
        expect(built.extension?.map((extension) => extension.url)).toEqual(
            registrationSkeleton.extension?.map((extension) => extension.url),
        )
        expect(built.item).toEqual([{ linkId: 'TeaFirstNm1', answer: [{ valueString: 'Amina' }] }])
    })

    it('leaves the whole envelope alone when no unit was picked', () => {
        const spec = flattenQuestionnaire(registrationForm)
        const built = buildQuestionnaireResponse(spec, {}, registrationForm, registrationSkeleton, NO_CAPTURE_CONTEXT)

        expect(built.extension).toEqual(registrationSkeleton.extension)
        expect(built.subject).toEqual(registrationSkeleton.subject)
    })
})

/**
 * The enrollment a stage submission answers against - the one envelope fact `$generate` gets wrong.
 *
 * The skeleton mints synthetic tracked-entity and enrollment uids, which is what makes it
 * postable at this server and refusable at DHIS2 (`E1079`/`E1313` - the enrollment does not
 * exist). Writing a real pair over it is therefore the difference between a stage capture that
 * imports and one that cannot, and the rewrite follows the combo and the unit exactly:
 * replace-in-place, the envelope's own spellings winning, the form's declarations as the
 * no-envelope fallback.
 */
describe('the enrollment a stage submission answers against', () => {
    const stageForm = servedForm('ZzYYXq4fJie')
    const generated = generateTrackerFixture as unknown as QuestionnaireResponse
    const chosen = { trackedEntity: 'TeRealPers1', enrollment: 'EnRealEnro1' }

    it('writes the chosen pair over the envelope in place, keeping every spelling', () => {
        const spec = flattenQuestionnaire(stageForm)

        const built = buildQuestionnaireResponse(spec, {}, stageForm, generated, {
            ...NO_CAPTURE_CONTEXT,
            enrollment: chosen,
        })

        expect(trackedEntityOf(built)).toBe('TeRealPers1')
        expect(trackerEnrollmentOf(built)).toBe('EnRealEnro1')
        // Only the two values moved: the subject keeps its type and identifier system, the
        // extension keeps its url, its identifier system, and its position in the list.
        expect(built.subject?.type).toBe(generated.subject?.type)
        expect(built.subject?.identifier?.system).toBe(generated.subject?.identifier?.system)
        expect(built.extension?.map((extension) => extension.url)).toEqual(
            generated.extension?.map((extension) => extension.url),
        )
        const stated = built.extension?.find((extension) => extension.url.endsWith('/d2-tracker-enrollment'))
        expect(stated?.valueIdentifier?.system).toBe('http://dhis2.org/fhir/id/tracker-enrollment')
    })

    it('keeps the draft identity when nothing is chosen', () => {
        const spec = flattenQuestionnaire(stageForm)

        const built = buildQuestionnaireResponse(spec, {}, stageForm, generated, NO_CAPTURE_CONTEXT)

        expect(built.subject).toEqual(generated.subject)
        expect(trackerEnrollmentOf(built)).toBe(trackerEnrollmentOf(generated))
    })

    it('builds the pair from the form’s own statements when there is no envelope', () => {
        // The identifier systems come off the form's `{base}/id/program` identifier and the
        // extension url off its form-type declaration - which is what keeps an explicit choice
        // on the submission even when `$generate` was refused.
        const spec = flattenQuestionnaire(stageForm)

        const built = buildQuestionnaireResponse(spec, {}, stageForm, null, {
            ...NO_CAPTURE_CONTEXT,
            enrollment: chosen,
        })

        expect(built.subject).toEqual({
            type: 'Patient',
            identifier: { system: 'http://dhis2.org/fhir/id/tracked-entity', value: 'TeRealPers1' },
        })
        expect(built.extension).toEqual([
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-tracker-enrollment',
                valueIdentifier: { system: 'http://dhis2.org/fhir/id/tracker-enrollment', value: 'EnRealEnro1' },
            },
        ])
    })

    it('ignores the choice on any form that is not a program stage', () => {
        // Only a tracker-event response names an enrollment; a choice leaking onto another kind
        // would write tracker context onto a response whose profile has no place for it.
        const aggregateForm = servedForm('BfMAe6Itzgt')
        const spec = flattenQuestionnaire(aggregateForm)
        const envelope = generateAggregateFixture as unknown as QuestionnaireResponse

        const built = buildQuestionnaireResponse(spec, {}, aggregateForm, envelope, {
            ...NO_CAPTURE_CONTEXT,
            enrollment: chosen,
        })

        expect(built.subject).toEqual(envelope.subject)
        expect(built.extension).toEqual(envelope.extension)
    })

    it('stands through a refill: the answers are the draw’s, the identity is the person’s', () => {
        // The opposite of the combo and unit refill rules, because a fresh draw's pair is
        // synthetic - adopting it would replace a real enrollment with uids that name nothing.
        expect(refilledEnrollment(chosen)).toBe(chosen)
        expect(refilledEnrollment(null)).toBeNull()
    })
})

/**
 * A registration answering for a person this DHIS2 instance already holds.
 *
 * THE THREE THINGS THAT CHANGE, and each of them is a fact rather than a preference. The subject
 * becomes the person's real tracked-entity uid, because the minted one names a person the
 * submission is no longer creating. The response carries the `D2SubjectExists` marker, so the
 * forwarder reads "this person exists" off the document rather than inferring it. And every
 * entity-level answer leaves the item tree, because DHIS2 already holds those values for this
 * person and `d2w fhir forward` refuses a submission that states its subject exists and carries
 * one anyway.
 *
 * The form is the fixture project's real registration form, which is what makes the entity-level
 * split real too: three of its four questions are entity-level and the fourth is the one the
 * program asks that the tracked entity type does not collect.
 */
describe('a registration answering for a person the instance already holds', () => {
    const registrationForm = registrationQuestionnaireFixture as unknown as Questionnaire
    const spec = flattenQuestionnaire(registrationForm)

    /** Every question answered, so what the marker takes away is a subtraction that can be seen. */
    const answered: AnswerState = {
        TeaNationId: [{ ...EMPTY_SLOT, text: '19850312-4471' }],
        TeaBirthDat: [{ ...EMPTY_SLOT, text: '1985-03-12' }],
        TeaHousehld: [{ ...EMPTY_SLOT, text: '4' }],
    }

    const skeleton: QuestionnaireResponse = {
        resourceType: 'QuestionnaireResponse',
        status: 'completed',
        questionnaire: registrationForm.url,
        subject: {
            type: 'Patient',
            identifier: { system: 'http://dhis2.org/fhir/id/tracked-entity', value: 'wJt3Qy1PxLd' },
        },
        extension: [
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-organisation-unit',
                valueReference: { reference: 'Location/DiszpKrYNg8' },
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at',
                valueDateTime: '2026-07-21T04:00:00Z',
            },
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' },
        ],
    }

    it('reads which questions DHIS2 writes onto the person, off the form’s own statement', () => {
        expect([...entityLevelLinkIds(spec)].toSorted()).toEqual(['TeaBirthDat', 'TeaNationId', 'TeaSex00001'])
    })

    it('clears exactly those answers, and keeps the state object when there is nothing to clear', () => {
        expect(clearedEntityLevelAnswers(spec, answered)).toEqual({
            TeaHousehld: [{ ...EMPTY_SLOT, text: '4' }],
        })
        const enrollmentLevelOnly: AnswerState = { TeaHousehld: [{ ...EMPTY_SLOT, text: '4' }] }
        expect(clearedEntityLevelAnswers(spec, enrollmentLevelOnly)).toBe(enrollmentLevelOnly)
    })

    it('names the real person, marks the submission, and writes no entity-level answer', () => {
        const built = buildQuestionnaireResponse(spec, answered, registrationForm, skeleton, {
            ...NO_CAPTURE_CONTEXT,
            existingSubject: { trackedEntity: 'TeiPerson001' },
        })

        expect(trackedEntityOf(built)).toBe('TeiPerson001')
        // The reference itself is kept whole: same system, same type, a different person.
        expect(built.subject?.type).toBe('Patient')
        expect(built.subject?.identifier?.system).toBe('http://dhis2.org/fhir/id/tracked-entity')
        expect(marksAnExistingSubject(built.extension)).toBe(true)
        expect(built.extension?.at(-1)).toEqual({
            url: 'http://localhost:8080/fhir/StructureDefinition/d2-subject-exists',
            valueBoolean: true,
        })
        // The one answer that rides the enrollment survives; the three that ride the person do not.
        expect(built.item).toEqual([{ linkId: 'TeaHousehld', answer: [{ valueInteger: 4 }] }])
        // The envelope is otherwise untouched - the unit and the enrollment date are the server's.
        expect(reportingUnitOf(built, 'tracker')).toEqual({ reference: 'Location/DiszpKrYNg8' })
        expect(enrolledAtOf(built)).toBe('2026-07-21T04:00:00Z')
    })

    it('changes nothing at all when the registration is about a new person', () => {
        const built = buildQuestionnaireResponse(spec, answered, registrationForm, skeleton, NO_CAPTURE_CONTEXT)

        expect(trackedEntityOf(built)).toBe('wJt3Qy1PxLd')
        expect(marksAnExistingSubject(built.extension)).toBe(false)
        expect(built.item?.map((item) => item.linkId)).toEqual(['TeaNationId', 'TeaBirthDat', 'TeaHousehld'])
    })

    it('never links a submission of a kind that registers nobody', () => {
        // A stage form names a person through the enrollment it answers for; an aggregate form is
        // about a place. The marker leaking onto either would rewrite a subject that is not
        // a person at all.
        const aggregateForm = servedForm('BfMAe6Itzgt')
        const aggregateSpec = flattenQuestionnaire(aggregateForm)
        const envelope = generateAggregateFixture as unknown as QuestionnaireResponse
        const built = buildQuestionnaireResponse(aggregateSpec, {}, aggregateForm, envelope, {
            ...NO_CAPTURE_CONTEXT,
            existingSubject: { trackedEntity: 'TeiPerson001' },
        })

        expect(built.subject).toEqual(envelope.subject)
        expect(marksAnExistingSubject(built.extension)).toBe(false)
    })

    it('stops counting a locked required question as one the form is waiting on', () => {
        // `TeaNationId` is required and entity-level, so a submission about an existing person can
        // never carry it -
        // and a screen telling a person their form is incomplete with no way to complete it is
        // worse than one that says nothing.
        expect(unansweredRequiredLinkIds(spec, {})).toEqual(['TeaNationId'])
        expect(unansweredRequiredLinkIds(spec, {}, entityLevelLinkIds(spec))).toEqual([])
    })
})

/**
 * The DHIS2 value type behind a tick, and the No a TRUE_ONLY question does not have.
 *
 * R4 spells `BOOLEAN` and `TRUE_ONLY` as one `#boolean` item type, so a form on its own cannot tell
 * the two apart - the fact is a `value-type` property on the concept the item's `code` names, in the
 * data dictionary the guide publishes beside the form. The DHIS2 difference is one value: a
 * TRUE_ONLY data element stores `true` or nothing, and `dhis2w_fhir.conversion.values` drops a
 * `false` on the way to the instance. So this asserts the whole chain - the dictionary read, the
 * value type on the node, and the answer that is never written.
 *
 * The dictionary is hand-written because the fixture goldens declare no TRUE_ONLY data element;
 * every shape here is the emitter's, as `CodeSystem-d2-de-cs.json` publishes it.
 */
describe('a TRUE_ONLY question', () => {
    const dataElements: CodeSystem = {
        resourceType: 'CodeSystem',
        status: 'active',
        url: 'http://localhost:8080/fhir/CodeSystem/d2-de-cs',
        concept: [
            {
                code: 'DeConfirmed',
                display: 'Confirmed',
                property: [{ code: 'value-type', valueCode: 'TRUE_ONLY' }],
            },
            {
                code: 'DeAncDanger',
                display: 'Danger signs present',
                property: [{ code: 'value-type', valueCode: 'BOOLEAN' }],
            },
            { code: 'DeNoTypeSaid', display: 'Stated with no value type' },
        ],
    }

    /** The other dictionary a form can draw from, holding one code the first one also holds. */
    const attributes: CodeSystem = {
        resourceType: 'CodeSystem',
        status: 'active',
        url: 'http://localhost:8080/fhir/CodeSystem/d2-tea-cs',
        concept: [
            {
                code: 'DeConfirmed',
                display: 'A different object under the same code',
                property: [{ code: 'value-type', valueCode: 'BOOLEAN' }],
            },
        ],
    }

    const form: Questionnaire = {
        resourceType: 'Questionnaire',
        status: 'active',
        item: [
            {
                linkId: 'DeConfirmed',
                text: 'Confirmed',
                type: 'boolean',
                code: [{ system: dataElements.url, code: 'DeConfirmed' }],
            },
            {
                linkId: 'DeAncDanger',
                text: 'Danger signs present',
                type: 'boolean',
                code: [{ system: dataElements.url, code: 'DeAncDanger' }],
            },
            {
                linkId: 'DeNoTypeSaid',
                text: 'Stated with no value type',
                type: 'boolean',
                code: [{ system: dataElements.url, code: 'DeNoTypeSaid' }],
            },
            { linkId: 'DeUncoded001', text: 'Coded in nothing at all', type: 'boolean' },
        ],
    }

    const valueTypes = valueTypesByConcept([dataElements, attributes])
    const spec = flattenQuestionnaire(form, valueTypes)

    it('reads the value type off the dictionary the question’s own code names', () => {
        expect(spec.byLinkId.get('DeConfirmed')?.valueType).toBe(TRUE_ONLY_VALUE_TYPE)
        expect(spec.byLinkId.get('DeAncDanger')?.valueType).toBe('BOOLEAN')
    })

    it('states none for an untyped concept, a question with no code, or a dictionary not yet read', () => {
        expect(spec.byLinkId.get('DeNoTypeSaid')?.valueType).toBeNull()
        expect(spec.byLinkId.get('DeUncoded001')?.valueType).toBeNull()
        // The state every form is in before its dictionary lands: absence means the form does not
        // say, so a boolean question keeps the three states a BOOLEAN has.
        expect(flattenQuestionnaire(form).byLinkId.get('DeConfirmed')?.valueType).toBeNull()
    })

    it('keys the dictionary by system and code, so two vocabularies sharing a code do not collide', () => {
        expect(valueTypes.get(`${dataElements.url ?? ''}|DeConfirmed`)).toBe(TRUE_ONLY_VALUE_TYPE)
        expect(valueTypes.get(`${attributes.url ?? ''}|DeConfirmed`)).toBe('BOOLEAN')
    })

    it('names the dictionaries one form is coded in, once each, and no other resource', () => {
        expect(questionCodeSystemIds(spec)).toEqual(['d2-de-cs'])
        expect(questionCodeSystemIds(flattenQuestionnaire(servedForm('PsAncVisit1')))).toEqual(['d2-de-cs'])
        // A coding into something this server does not publish as a CodeSystem names no read.
        const elsewhere: Questionnaire = {
            resourceType: 'Questionnaire',
            status: 'active',
            item: [{ linkId: 'x', type: 'boolean', code: [{ system: 'http://loinc.org', code: '1234-5' }] }],
        }
        expect(questionCodeSystemIds(flattenQuestionnaire(elsewhere))).toEqual([])
    })

    it('answers yes or nothing, and never the false DHIS2 does not store', () => {
        const trueOnly = spec.byLinkId.get('DeConfirmed')
        const boolean = spec.byLinkId.get('DeAncDanger')
        if (trueOnly === undefined || boolean === undefined) throw new Error('the form asks both questions')

        expect(slotAnswer(trueOnly, { ...EMPTY_SLOT, text: 'true' })).toEqual({ valueBoolean: true })
        expect(slotAnswer(trueOnly, { ...EMPTY_SLOT, text: 'false' })).toBeNull()
        expect(slotAnswer(trueOnly, EMPTY_SLOT)).toBeNull()
        // The plain BOOLEAN beside it is untouched: No is an answer DHIS2 stores for one.
        expect(slotAnswer(boolean, { ...EMPTY_SLOT, text: 'false' })).toEqual({ valueBoolean: false })
    })

    it('leaves a TRUE_ONLY question out of the submission rather than answering it false', () => {
        const answers: AnswerState = {
            DeConfirmed: [{ ...EMPTY_SLOT, text: 'false' }],
            DeAncDanger: [{ ...EMPTY_SLOT, text: 'false' }],
        }
        const built = buildQuestionnaireResponse(spec, answers, form, null, NO_CAPTURE_CONTEXT)
        const trueOnly = spec.byLinkId.get('DeConfirmed')
        if (trueOnly === undefined) throw new Error('the form asks the TRUE_ONLY question')

        expect(built.item).toEqual([{ linkId: 'DeAncDanger', answer: [{ valueBoolean: false }] }])
        // And it is still unanswered, because nothing anyone can type answers it false.
        expect(isAnswered(trueOnly, answers)).toBe(false)
    })
})

/**
 * The dates and the period a person states for themselves, over the ones the draft drew.
 *
 * FOUR FACTS, ONE RULE. `authored` dates an event - the forwarder derives `TrackerEvent.occurredAt`
 * from it - `D2EnrolledAt` and `D2IncidentAt` date a registration's enrollment, and `D2Period` is
 * the period an aggregate submission reports for. Each rewrite replaces what the envelope states,
 * in the slot the envelope states it in, and writes nothing where the envelope states nothing: a
 * date of a kind the response does not carry is a no-op rather than an invention.
 *
 * THE PERIOD IS THE ONE WITH A SERVER CONTRACT ATTACHED. `_period_issues` in
 * `dhis2w_fhir_serve.capture.validate` refuses a response whose `type` disagrees with the type its
 * ISO identifier parses as, and one whose `period` range disagrees with the range that identifier
 * resolves to - and the range is optional, because the ISO period is what is captured. This UI has
 * no DHIS2 period arithmetic, so an edited identifier keeps the drafted type and drops the range
 * rather than claiming a range it cannot resolve.
 */
describe('the dates and the period a submission carries', () => {
    const aggregateForm = servedForm('BfMAe6Itzgt')
    const aggregateSkeleton = generateAggregateFixture as unknown as QuestionnaireResponse
    const eventForm = scopedQuestionnaireFixture as unknown as Questionnaire
    const eventSkeleton = generateScopedFixture as unknown as QuestionnaireResponse
    const drafted: Extension[] = aggregateSkeleton.extension ?? []

    const registrationForm: Questionnaire = {
        resourceType: 'Questionnaire',
        id: 'PrTracker001',
        url: 'http://localhost:8080/fhir/Questionnaire/PrTracker001',
        status: 'active',
        extension: [
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-collects-incident-date',
                valueBoolean: true,
            },
        ],
        item: [{ linkId: 'TeaFirstNm1', text: 'First name', type: 'string' }],
    }

    const registrationSkeleton: QuestionnaireResponse = {
        resourceType: 'QuestionnaireResponse',
        status: 'completed',
        questionnaire: registrationForm.url,
        subject: {
            type: 'Patient',
            identifier: { system: 'http://dhis2.org/fhir/id/tracked-entity', value: 'wJt3Qy1PxLd' },
        },
        extension: [
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at',
                valueDateTime: '2026-07-21T04:00:00Z',
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-incident-at',
                valueDateTime: '2026-07-14T04:00:00Z',
            },
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' },
        ],
    }

    it('reads the drafted period off the aggregate skeleton, and none off any other kind', () => {
        expect(reportingPeriodOf(aggregateSkeleton)).toEqual({ iso: '202607', periodType: 'Monthly' })
        expect(reportingPeriodOf(eventSkeleton)).toBeNull()
        expect(reportingPeriodOf(null)).toBeNull()
    })

    it('passes the whole period through untouched when the drafted identifier stands', () => {
        expect(extensionsWithReportingPeriod(drafted, '202607')).toBe(drafted)
        expect(extensionsWithReportingPeriod(drafted, null)).toBe(drafted)
        // An event response carries no period at all, so there is nothing to write into.
        const eventExtensions = eventSkeleton.extension ?? []
        expect(extensionsWithReportingPeriod(eventExtensions, '202605')).toBe(eventExtensions)
    })

    it('writes an edited identifier, keeps the drafted type, and claims no date range', () => {
        const written = extensionsWithReportingPeriod(drafted, '202605')
        const period = written.find((extension) => extension.url.endsWith('/d2-period'))

        expect(period?.extension).toEqual([
            { url: 'iso', valueString: '202605' },
            { url: 'type', valueCode: 'Monthly' },
        ])
        // Replaced where the server wrote it: the form type keeps its place, so the rebuilt
        // response reads as the same document rather than as one with its context shuffled.
        expect(written.map((extension) => extension.url)).toEqual(drafted.map((extension) => extension.url))
    })

    it('carries an edited period through a whole rebuilt aggregate submission', () => {
        const spec = flattenQuestionnaire(aggregateForm)
        const built = buildQuestionnaireResponse(spec, {}, aggregateForm, aggregateSkeleton, {
            ...NO_CAPTURE_CONTEXT,
            reportingPeriodIso: '202605',
        })

        expect(reportingPeriodOf(built)).toEqual({ iso: '202605', periodType: 'Monthly' })
        expect(
            built.extension
                ?.find((extension) => extension.url.endsWith('/d2-period'))
                ?.extension?.some((sub) => sub.url === 'period'),
        ).toBe(false)
    })

    it('replaces either enrollment date in place, and writes neither where the draft states none', () => {
        const carried = registrationSkeleton.extension ?? []
        const withEnrolledAt = { ...registrationSkeleton, extension: extensionsWithEnrolledAt(carried, '2026-07-02T09:00:00Z') }
        const withIncidentAt = { ...registrationSkeleton, extension: extensionsWithIncidentAt(carried, '2026-06-30T09:00:00Z') }

        expect(enrolledAtOf(withEnrolledAt)).toBe('2026-07-02T09:00:00Z')
        expect(incidentAtOf(withIncidentAt)).toBe('2026-06-30T09:00:00Z')
        // Untouched by the other rewrite, and untouched by a date that is already the drafted one.
        expect(incidentAtOf(withEnrolledAt)).toBe('2026-07-14T04:00:00Z')
        expect(extensionsWithEnrolledAt(carried, null)).toBe(carried)
        expect(extensionsWithEnrolledAt(carried, '2026-07-21T04:00:00Z')).toBe(carried)
        // An aggregate envelope has no enrollment date to replace, so a stated one writes nothing.
        expect(extensionsWithEnrolledAt(drafted, '2026-07-02T09:00:00Z')).toBe(drafted)
    })

    it('carries both stated dates through a whole rebuilt registration', () => {
        const spec = flattenQuestionnaire(registrationForm)
        const built = buildQuestionnaireResponse(spec, {}, registrationForm, registrationSkeleton, {
            ...NO_CAPTURE_CONTEXT,
            enrolledAt: '2026-07-02T09:00:00Z',
            incidentAt: '2026-06-30T09:00:00Z',
        })

        expect(enrolledAtOf(built)).toBe('2026-07-02T09:00:00Z')
        expect(incidentAtOf(built)).toBe('2026-06-30T09:00:00Z')
        expect(built.extension?.map((extension) => extension.url)).toEqual(
            registrationSkeleton.extension?.map((extension) => extension.url),
        )
    })

    it('reads whether the program collects an incident date off the form’s own declaration', () => {
        expect(collectsIncidentDate(registrationForm)).toBe(true)
        expect(
            collectsIncidentDate({
                ...registrationForm,
                extension: [
                    {
                        url: 'http://localhost:8080/fhir/StructureDefinition/d2-collects-incident-date',
                        valueBoolean: false,
                    },
                ],
            }),
        ).toBe(false)
        expect(collectsIncidentDate(aggregateForm)).toBe(false)
    })

    it('dates an event with the stated visit date, and with the drafted one when none is stated', () => {
        const spec = flattenQuestionnaire(eventForm)

        expect(
            buildQuestionnaireResponse(spec, {}, eventForm, eventSkeleton, {
                ...NO_CAPTURE_CONTEXT,
                authored: '2026-07-02T09:00:00Z',
            }).authored,
        ).toBe('2026-07-02T09:00:00Z')
        expect(buildQuestionnaireResponse(spec, {}, eventForm, eventSkeleton, NO_CAPTURE_CONTEXT).authored).toBe(
            eventSkeleton.authored,
        )
        // With no envelope at all a stated date is still the submission's, which is all this screen
        // can say about when a capture happened once `$generate` has been refused.
        expect(
            buildQuestionnaireResponse(spec, {}, eventForm, null, {
                ...NO_CAPTURE_CONTEXT,
                authored: '2026-07-02T09:00:00Z',
            }).authored,
        ).toBe('2026-07-02T09:00:00Z')
    })

    it('stamps what a datetime-local control holds as the wall time it states', () => {
        // The one rule these controls share with the form's own date questions: the browser yields
        // no zone, and the instant a capture states is the instant it states - never shifted by
        // whichever zone the operator's laptop is in.
        expect(normaliseDateTime('2026-07-02T09:00')).toBe('2026-07-02T09:00:00Z')
        expect(dateTimeInputValue('2026-07-21T04:00:00Z')).toBe('2026-07-21T04:00:00')
        // An untouched or emptied control states nothing, and the draft's own value rides.
        expect(normaliseDateTime('')).toBeNull()
    })
})
