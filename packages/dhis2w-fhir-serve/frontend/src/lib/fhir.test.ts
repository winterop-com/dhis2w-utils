import { describe, expect, it } from 'vitest'

import metadataFixture from '@/lib/__fixtures__/metadata.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import {
    bundleResources,
    canonicalId,
    declaredOperations,
    formTypeOf,
    questionCount,
    servedIgLabel,
    type Bundle,
    type CapabilityStatement,
    type Questionnaire, unescapeMarkup } from '@/lib/fhir'

/**
 * The parsing rules, checked against what the server actually answers.
 *
 * Both fixtures were harvested from a running `d2w fhir serve` over the capture
 * project the Python test suite serves (packages/dhis2w-fhir-serve/tests/
 * conftest.py, `capture_project`), which in turn is built from the committed
 * dhis2w-fhir goldens. So these are not hand-written approximations of the wire
 * shape - they are the wire shape, and a change to the emitter that breaks the
 * UI's reading of it breaks a test here.
 */

const metadata = metadataFixture as CapabilityStatement
const questionnaireBundle = questionnaireBundleFixture as unknown as Bundle<Questionnaire>

describe('a real /Questionnaire bundle', () => {
    it('yields one resource per entry', () => {
        const questionnaires = bundleResources(questionnaireBundle)
        expect(questionnaires).toHaveLength(questionnaireBundle.total ?? 0)
        expect(questionnaires.map((questionnaire) => questionnaire.id)).toEqual([
            'BfMAe6Itzgt',
            'EVTsupVis01',
            'PsAncVisit1',
            'ZzYYXq4fJie',
        ])
    })

    it('reads the form kind off the D2FormType extension', () => {
        const kinds = Object.fromEntries(
            bundleResources(questionnaireBundle).map((questionnaire) => [
                questionnaire.id,
                formTypeOf(questionnaire),
            ]),
        )
        expect(kinds).toEqual({
            BfMAe6Itzgt: 'aggregate',
            EVTsupVis01: 'event',
            // A program stage is `tracker-event`, not `tracker`; `tracker` is
            // the registration form. The goldens are the authority on that.
            PsAncVisit1: 'tracker-event',
            ZzYYXq4fJie: 'tracker-event',
        })
    })

    it('counts a question per non-group item, at every depth', () => {
        const counts = bundleResources(questionnaireBundle).map((questionnaire) => ({
            id: questionnaire.id,
            questions: questionCount(questionnaire.item),
        }))
        // Every served form asks something; a zero here would mean the walk
        // stopped at the group level.
        for (const entry of counts) expect(entry.questions, entry.id).toBeGreaterThan(0)
    })

    it('answers an empty list for a bundle with no entries', () => {
        expect(bundleResources({ resourceType: 'Bundle', type: 'searchset', total: 0 })).toEqual([])
        expect(bundleResources(undefined)).toEqual([])
    })

    it('states the absence of a form type rather than guessing one', () => {
        expect(formTypeOf({ resourceType: 'Questionnaire', status: 'draft' })).toBeNull()
        expect(
            formTypeOf({
                resourceType: 'Questionnaire',
                status: 'draft',
                extension: [{ url: 'http://example.org/other', valueCode: 'aggregate' }],
            }),
        ).toBeNull()
    })
})

describe('questionCount', () => {
    it('walks nested groups and skips display items', () => {
        expect(
            questionCount([
                { linkId: 'heading', type: 'display', text: 'Section one' },
                {
                    linkId: 'group-1',
                    type: 'group',
                    item: [
                        { linkId: 'q1', type: 'integer' },
                        {
                            linkId: 'group-2',
                            type: 'group',
                            item: [{ linkId: 'q2', type: 'choice' }],
                        },
                    ],
                },
                { linkId: 'q3', type: 'boolean' },
            ]),
        ).toBe(3)
    })

    it('answers zero for a form with no items', () => {
        expect(questionCount(undefined)).toBe(0)
        expect(questionCount([])).toBe(0)
    })
})

describe('a real /metadata document', () => {
    it('names the served guide from the description this server writes', () => {
        expect(servedIgLabel(metadata)).toBe('DHIS2 FHIR Capture IG')
    })

    it('keeps a description that carries no marker whole', () => {
        expect(servedIgLabel({ ...metadata, description: 'Something else entirely' })).toBe(
            'Something else entirely',
        )
        expect(servedIgLabel(null)).toBeNull()
    })

    it('reports the software and FHIR version the facade runs', () => {
        expect(metadata.software?.name).toBe('d2w fhir serve')
        expect(metadata.fhirVersion).toBe('4.0.1')
        expect(metadata.kind).toBe('instance')
    })

    it('collects both operation levels, saying which resource each hangs off', () => {
        const operations = declaredOperations(metadata)
        const generate = operations.find((operation) => operation.name === 'generate')
        expect(generate?.on).toBe('Questionnaire')
        // $translate is type-level, so it is declared on `rest` rather than on a
        // resource entry - and only because this fixture's store holds maps. A
        // store without them declares neither, which is what the Server page reports.
        const translate = operations.find((operation) => operation.name === 'translate')
        expect(translate?.on).toBe('server')
    })

    it('declares ConceptMap as a read type, not only as something to translate through', () => {
        const conceptMap = metadata.rest?.[0].resource?.find((resource) => resource.type === 'ConceptMap')
        expect(conceptMap?.interaction?.map((interaction) => interaction.code)).toEqual([
            'read',
            'search-type',
        ])
    })

    it('sees a rest-level operation as declared on the server', () => {
        const operations = declaredOperations({
            ...metadata,
            rest: [{ mode: 'server', operation: [{ name: 'translate' }], resource: [] }],
        })
        expect(operations).toEqual([{ name: 'translate', on: 'server', documentation: undefined }])
    })

    it('answers an empty list when there is no statement at all', () => {
        expect(declaredOperations(null)).toEqual([])
    })

    it('declares the capture type with create, read, and search', () => {
        const response = metadata.rest?.[0].resource?.find(
            (resource) => resource.type === 'QuestionnaireResponse',
        )
        expect(response?.interaction?.map((interaction) => interaction.code)).toEqual([
            'create',
            'read',
            'search-type',
        ])
    })
})

describe('canonicalId', () => {
    it('takes the last segment of a canonical URL', () => {
        expect(canonicalId('http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt')).toBe('BfMAe6Itzgt')
    })

    it('answers null for nothing to read', () => {
        expect(canonicalId(undefined)).toBeNull()
        expect(canonicalId('')).toBeNull()
    })
})

describe('unescapeMarkup', () => {
    it('reverses the emit-time escaping of the three markup entities', () => {
        expect(unescapeMarkup('Age (&lt;5 - 49) &amp; over')).toBe('Age (<5 - 49) & over')
        expect(unescapeMarkup('Age (&lt;5 &gt;5) &amp; sex')).toBe('Age (<5 >5) & sex')
    })

    it('leaves text without entities untouched and survives a real ampersand', () => {
        expect(unescapeMarkup('Malaria cases')).toBe('Malaria cases')
        expect(unescapeMarkup('A &amp;amp; B')).toBe('A &amp; B')
    })
})
