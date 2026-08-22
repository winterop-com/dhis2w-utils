import { describe, expect, it } from 'vitest'

import {
    EXAMPLE_BUNDLE,
    EXAMPLE_CLINICAL_BUNDLE,
    EXAMPLE_ELM,
    EXAMPLE_HOUSEHOLD_BUNDLE,
    EXAMPLE_PATIENT,
    EXAMPLE_RESPONSE,
    GUIDE_PRESET_GROUP,
    NO_CONTEXT,
    caretUnder,
    exampleGroups,
    cellText,
    diagnosticHeadline,
    elementFor,
    evaluationContext,
    evaluationRequest,
    genericExamples,
    guidePresets,
    isPrimitive,
    matchSummary,
    presetSource,
    resultShape,
    sourceLine,
    whyNotReady,
    type EvaluationForm,
    type EvaluationLanguage,
} from '@/lib/evaluate'

/**
 * The reading and building rules behind the Evaluate screen.
 *
 * Two things are worth pinning here rather than in the browser. The examples are a promise - every
 * one of them has to be runnable as it stands, on a guide that publishes nothing at all - and the
 * request builder is where the context union is chosen, which is the one place a wrong choice would
 * send an expression at data the reader did not name.
 */

const LANGUAGES: EvaluationLanguage[] = ['fhirpath', 'cql', 'elm']

/** Whether a string holds anything written outside the Latin letters ASCII covers. */
const beyondAscii = (text: string): boolean =>
    [...text].some((character) => (character.codePointAt(0) ?? 0) > 127)

describe('the generic examples', () => {
    it('offers at least one for every language, so no language opens empty', () => {
        for (const language of LANGUAGES) {
            expect(genericExamples(language).length).toBeGreaterThan(0)
        }
    })

    it('carries its own data, so every one of them runs on a guide that publishes nothing', () => {
        for (const language of LANGUAGES) {
            for (const example of genericExamples(language)) {
                expect(example.form.source.trim()).not.toBe('')
                expect(example.form.context.kind).not.toBe('stored')
                expect(example.form.context.kind).not.toBe('registered')
                expect(whyNotReady(example.form)).toBeNull()
            }
        }
    })

    it('loads a form whose language is the one it was asked for', () => {
        for (const language of LANGUAGES) {
            expect(genericExamples(language).map((example) => example.form.language)).toEqual(
                genericExamples(language).map(() => language),
            )
        }
    })

    it('pastes resources that are the JSON they claim to be', () => {
        expect(JSON.parse(EXAMPLE_PATIENT).resourceType).toBe('Patient')
        expect(JSON.parse(EXAMPLE_BUNDLE).resourceType).toBe('Bundle')
        expect(JSON.parse(EXAMPLE_CLINICAL_BUNDLE).resourceType).toBe('Bundle')
        expect(JSON.parse(EXAMPLE_HOUSEHOLD_BUNDLE).resourceType).toBe('Bundle')
        expect(JSON.parse(EXAMPLE_RESPONSE).resourceType).toBe('QuestionnaireResponse')
        expect(JSON.parse(EXAMPLE_ELM).library.identifier.id).toBe('Example')
    })

    it('offers a dozen or more for every language, because one of each teaches nothing', () => {
        for (const language of LANGUAGES) {
            expect(genericExamples(language).length).toBeGreaterThanOrEqual(6)
        }
        expect(genericExamples('fhirpath').length).toBeGreaterThanOrEqual(12)
        expect(genericExamples('cql').length).toBeGreaterThanOrEqual(12)
    })

    it('names every example once, so loading one by id can only load one', () => {
        const seen = new Set<string>()
        for (const language of LANGUAGES) {
            for (const example of genericExamples(language)) {
                expect(seen.has(example.id)).toBe(false)
                seen.add(example.id)
            }
        }
    })

    it('puts every example on a named shelf, so the picker has something to group by', () => {
        for (const language of LANGUAGES) {
            for (const example of genericExamples(language)) {
                expect(example.group.trim()).not.toBe('')
            }
        }
    })

    it('pastes a context that is one JSON object, wherever it pastes one at all', () => {
        for (const language of LANGUAGES) {
            for (const example of genericExamples(language)) {
                if (example.form.context.kind !== 'inline') continue
                const parsed: unknown = JSON.parse(example.form.context.resource)
                expect(typeof parsed).toBe('object')
                expect(Array.isArray(parsed)).toBe(false)
            }
        }
    })

    it('writes every ELM example as the JSON the endpoint parses before the engine sees it', () => {
        for (const example of genericExamples('elm')) {
            // Every one has to be a JSON object - including the one that is an example OF a refusal,
            // which is refused for having no identifier rather than for being unreadable.
            const parsed = JSON.parse(example.form.source) as Record<string, unknown>
            expect(typeof parsed).toBe('object')
            expect(Object.keys(parsed)).toContain('library')
        }
    })

    it('writes every CQL example as a library, because a bare expression is not one', () => {
        for (const example of genericExamples('cql')) {
            expect(example.form.source.startsWith('library ')).toBe(true)
        }
    })

    it('asks for every define, so an example never opens narrowed to one a reader did not choose', () => {
        for (const language of LANGUAGES) {
            for (const example of genericExamples(language)) {
                expect(example.form.expressionName).toBe('')
            }
        }
    })
})

describe('the shelves the examples sit on', () => {
    it('keeps every example, on the shelf it named', () => {
        for (const language of LANGUAGES) {
            const examples = genericExamples(language)
            const shelves = exampleGroups(examples)
            expect(shelves.flatMap((shelf) => shelf.examples)).toHaveLength(examples.length)
            for (const shelf of shelves) {
                for (const example of shelf.examples) expect(example.group).toBe(shelf.group)
            }
        }
    })

    it('names each shelf once, in the order it was first declared', () => {
        const shelves = exampleGroups(genericExamples('fhirpath'))
        const names = shelves.map((shelf) => shelf.group)
        expect(new Set(names).size).toBe(names.length)
        expect(names[0]).toBe(genericExamples('fhirpath')[0].group)
    })

    it('puts the guide presets on their own shelf, under the generic ones', () => {
        const examples = [
            ...genericExamples('fhirpath'),
            ...guidePresets('fhirpath', [
                { resourceType: 'Questionnaire', resourceId: 'q1', title: 'Antenatal care' },
            ]),
        ]
        const shelves = exampleGroups(examples)
        expect(shelves.at(-1)?.group).toBe(GUIDE_PRESET_GROUP)
        expect(shelves.at(-1)?.examples).toHaveLength(1)
    })
})

describe('the household Bundle the realistic examples ask', () => {
    interface Entry {
        resource: { resourceType: string; [element: string]: unknown }
    }

    const bundle = JSON.parse(EXAMPLE_HOUSEHOLD_BUNDLE) as { type: string; entry: Entry[] }
    const held = (resourceType: string): Entry['resource'][] =>
        bundle.entry.map((entry) => entry.resource).filter((resource) => resource.resourceType === resourceType)

    it('is a collection, because nothing in it is the answer to a search', () => {
        expect(bundle.type).toBe('collection')
    })

    it('holds a population rather than one person, so an "everyone" question has an answer', () => {
        expect(held('Patient')).toHaveLength(2)
    })

    it('holds enough measurements, across enough codes, for a filter to leave rows behind', () => {
        const observations = held('Observation')
        expect(observations.length).toBeGreaterThanOrEqual(4)
        const codes = new Set(
            observations.map(
                (observation) =>
                    (observation.code as { coding: { code: string }[] }).coding[0].code,
            ),
        )
        expect(codes.size).toBeGreaterThanOrEqual(2)
    })

    it('spreads those measurements over time, so latest-by-date is a question worth asking', () => {
        const taken = held('Observation').map((observation) => String(observation.effectiveDateTime))
        expect(new Set(taken).size).toBe(taken.length)
        expect(new Set(taken.map((moment) => moment.slice(0, 7))).size).toBeGreaterThanOrEqual(3)
    })

    it('numbers the doses of one vaccine, so counting a series is a question worth asking', () => {
        const doses = held('Immunization').map(
            (immunization) =>
                (immunization.protocolApplied as { doseNumberPositiveInt: number }[])[0].doseNumberPositiveInt,
        )
        expect(doses).toEqual([1, 2, 3])
    })

    it('carries the record around the readings - a Condition, an Encounter, and identifiers', () => {
        expect(held('Condition')).toHaveLength(1)
        expect(held('Encounter')).toHaveLength(1)
        const identifiers = held('Patient').flatMap(
            (patient) => (patient.identifier ?? []) as { value: string }[],
        )
        expect(identifiers.length).toBeGreaterThanOrEqual(2)
    })

    it('writes a name in the script the family writes it in, not only in Latin letters', () => {
        const names = held('Patient').flatMap((patient) => patient.name as { family: string }[])
        // Latin-only would make "the same names in their own script" an example with nothing to show.
        expect(names.some((name) => beyondAscii(name.family))).toBe(true)
    })
})

describe('the shelves that ask the household Bundle', () => {
    const REALISTIC_SHELVES: Record<EvaluationLanguage, string> = {
        fhirpath: 'Ask a Bundle',
        cql: 'A population in a Bundle',
        elm: 'A compiled library over a Bundle',
    }

    const shelved = (language: EvaluationLanguage) =>
        genericExamples(language).filter((example) => example.group === REALISTIC_SHELVES[language])

    it('offers one for every language, because the gap was every language asking a single Patient', () => {
        expect(shelved('fhirpath').length).toBeGreaterThanOrEqual(8)
        expect(shelved('cql').length).toBeGreaterThanOrEqual(6)
        expect(shelved('elm').length).toBeGreaterThanOrEqual(1)
    })

    it('attaches the same Bundle to every one of them, pasted whole', () => {
        for (const language of LANGUAGES) {
            for (const example of shelved(language)) {
                expect(example.form.context.kind).toBe('inline')
                expect(example.form.context.resource).toBe(EXAMPLE_HOUSEHOLD_BUNDLE)
            }
        }
    })

    it('builds a request carrying the Bundle itself, not the text of it', () => {
        const [first] = shelved('fhirpath')
        expect(evaluationRequest(first.form)).toMatchObject({
            language: 'fhirpath',
            context: { kind: 'inline', resource: JSON.parse(EXAMPLE_HOUSEHOLD_BUNDLE) },
        })
    })

    it('asks each language what that language is for - resources, a population, a compiled library', () => {
        const asked = (language: EvaluationLanguage) => shelved(language).map((example) => example.form.source).join('\n')
        expect(asked('fhirpath')).toContain('ofType(Observation)')
        expect(asked('cql')).toContain('[Immunization]')
        // The coercion the CQL shelf is written on: a birth date compared without ToDate around it.
        expect(asked('cql')).toContain('P.birthDate > @2020-01-01')
        expect(asked('elm')).toContain('{http://hl7.org/fhir}Patient')
    })
})

describe('the guide presets', () => {
    const served = [{ resourceType: 'Questionnaire', resourceId: 'BfMAe6Itzgt', title: 'Child Health' }]

    it('names the resource this server actually holds, in the label and in the context alike', () => {
        const [preset] = guidePresets('fhirpath', served)

        expect(preset.label).toBe('Every question asked by Child Health')
        expect(preset.form.context).toMatchObject({
            kind: 'stored',
            resourceType: 'Questionnaire',
            resourceId: 'BfMAe6Itzgt',
        })
        expect(preset.form.source).toBe('Questionnaire.item.linkId')
    })

    it('falls back to the id when the resource states no title, rather than to an empty label', () => {
        const [preset] = guidePresets('fhirpath', [
            { resourceType: 'CodeSystem', resourceId: 'd2-de-cs', title: null },
        ])

        expect(preset.label).toBe('Every code in d2-de-cs')
    })

    it('writes a CQL retrieve over the same type', () => {
        expect(presetSource('cql', 'Questionnaire')).toContain('define Served: [Questionnaire]')
    })

    it('offers none for ELM, which is compiled JSON with no short form to write', () => {
        expect(guidePresets('elm', served)).toEqual([])
    })

    it('offers none at all when this server was found to hold nothing', () => {
        expect(guidePresets('fhirpath', [])).toEqual([])
    })

    it('reads an element every instance of the type carries, and an id for one it does not know', () => {
        expect(elementFor('Questionnaire')).toBe('item.linkId')
        expect(elementFor('Location')).toBe('name')
        expect(elementFor('Whatever')).toBe('id')
    })
})

describe('building the request', () => {
    const form: EvaluationForm = {
        language: 'fhirpath',
        source: 'Patient.name.given',
        expressionName: '',
        context: { ...NO_CONTEXT, kind: 'inline', resource: EXAMPLE_PATIENT },
    }

    it('parses the pasted context into the object the server takes', () => {
        expect(evaluationRequest(form)).toEqual({
            language: 'fhirpath',
            source: 'Patient.name.given',
            context: { kind: 'inline', resource: JSON.parse(EXAMPLE_PATIENT) },
        })
    })

    it('names a stored resource by type and id, in the wire spelling', () => {
        expect(
            evaluationContext({ ...NO_CONTEXT, kind: 'stored', resourceType: 'Questionnaire', resourceId: 'X' }),
        ).toEqual({ kind: 'stored', resource_type: 'Questionnaire', resource_id: 'X' })
    })

    it('names a register person by the resource this run serves them as', () => {
        expect(
            evaluationContext({
                ...NO_CONTEXT,
                kind: 'registered',
                trackedEntityUid: 'TeiPerson01',
                registerResource: 'Specimen',
            }),
        ).toEqual({ kind: 'registered', resource_type: 'Specimen', tracked_entity_uid: 'TeiPerson01' })
    })

    it('sends no context at all for an expression that runs over no resource', () => {
        expect(evaluationRequest({ ...form, context: { ...NO_CONTEXT } })).toEqual({
            language: 'fhirpath',
            source: 'Patient.name.given',
        })
    })

    it('sends a define name only for the languages that have defines', () => {
        expect(evaluationRequest({ ...form, expressionName: 'Sum' })).not.toHaveProperty('expression_name')
        expect(evaluationRequest({ ...form, language: 'cql', expressionName: ' Sum ' })).toMatchObject({
            expression_name: 'Sum',
        })
    })
})

describe('what stops a form being sent', () => {
    const form: EvaluationForm = {
        language: 'fhirpath',
        source: 'Patient.id',
        expressionName: '',
        context: { ...NO_CONTEXT },
    }

    it('lets a complete form through', () => {
        expect(whyNotReady(form)).toBeNull()
    })

    it('says so when there is no expression to run', () => {
        expect(whyNotReady({ ...form, source: '   ' })).toBe('Write an expression, or pick an example.')
    })

    it('catches a pasted context that is not JSON before the network does', () => {
        expect(whyNotReady({ ...form, context: { ...NO_CONTEXT, kind: 'inline', resource: '{oops' } })).toBe(
            'The pasted context is not valid JSON.',
        )
    })

    it('catches valid JSON that is not one resource', () => {
        expect(whyNotReady({ ...form, context: { ...NO_CONTEXT, kind: 'inline', resource: '[1, 2]' } })).toBe(
            'The context is one FHIR resource, which is a JSON object.',
        )
    })

    it('asks for the two halves of a stored reference, and for a tracked entity', () => {
        expect(
            whyNotReady({ ...form, context: { ...NO_CONTEXT, kind: 'stored', resourceType: 'Patient' } }),
        ).toContain('resource type and the id')
        expect(whyNotReady({ ...form, context: { ...NO_CONTEXT, kind: 'registered' } })).toContain(
            'tracked entity',
        )
    })
})

describe('rendering an answer', () => {
    it('shows a collection of values as a table and anything with structure as JSON', () => {
        expect(resultShape(['Ada', 'Byron'])).toBe('table')
        expect(resultShape([true, 3, null])).toBe('table')
        expect(resultShape([{ resourceType: 'Patient' }])).toBe('json')
        expect(resultShape([])).toBe('empty')
    })

    it('knows what a table cell can hold whole', () => {
        expect(isPrimitive('a')).toBe(true)
        expect(isPrimitive(null)).toBe(true)
        expect(isPrimitive({})).toBe(false)
        expect(isPrimitive(['a'])).toBe(false)
    })

    it('writes a primitive as the text a cell shows', () => {
        expect(cellText('Ada')).toBe('Ada')
        expect(cellText(3)).toBe('3')
        expect(cellText(false)).toBe('false')
        expect(cellText(null)).toBe('null')
    })

    it('counts matches the way a person reads them', () => {
        expect(matchSummary(0)).toBe('No matches')
        expect(matchSummary(1)).toBe('1 match')
        expect(matchSummary(3)).toBe('3 matches')
    })
})

describe('a diagnostic', () => {
    it('names where the parser stopped, counting the column from one', () => {
        expect(
            diagnosticHeadline({ kind: 'parse', message: 'x', line: 2, column: 14, expression_name: null }),
        ).toBe('Parse error at line 2, column 14')
    })

    it('says only what it knows when the refusal named no position', () => {
        expect(
            diagnosticHeadline({ kind: 'evaluation', message: 'x', line: null, column: null, expression_name: null }),
        ).toBe('Evaluation refused')
        expect(
            diagnosticHeadline({ kind: 'parse', message: 'x', line: 4, column: null, expression_name: null }),
        ).toBe('Parse error at line 4')
    })

    it('finds the line it named, and nothing when the source has no such line', () => {
        expect(sourceLine('one\ntwo\nthree', 2)).toBe('two')
        expect(sourceLine('one', 9)).toBeNull()
        expect(sourceLine('one', null)).toBeNull()
    })

    it('points a caret at the column, keeping tabs so the marker lands under the character', () => {
        expect(caretUnder('Patient.name..given', 14)).toBe('             ^')
        expect(caretUnder('\tdefine X: 1 +', 2)).toBe('\t^')
        expect(caretUnder('anything', null)).toBe('')
    })
})
