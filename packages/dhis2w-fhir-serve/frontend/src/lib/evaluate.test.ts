import { describe, expect, it } from 'vitest'

import {
    EXAMPLE_BUNDLE,
    EXAMPLE_ELM,
    EXAMPLE_PATIENT,
    NO_CONTEXT,
    caretUnder,
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
        expect(JSON.parse(EXAMPLE_ELM).library.identifier.id).toBe('Example')
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
