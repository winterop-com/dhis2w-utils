import { describe, expect, it } from 'vitest'

import attributeCodeSystemFixture from '@/lib/__fixtures__/codesystem-d2-aoc-idcDPkDtepR-cs.json'
import metadataFixture from '@/lib/__fixtures__/metadata.json'
import attributeComboFormFixture from '@/lib/__fixtures__/questionnaire-TuL8IOPzpHh.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import attributeComboResponseFixture from '@/lib/__fixtures__/response-TuL8IOPzpHh.json'
import attributeValueSetFixture from '@/lib/__fixtures__/valueset-d2-aoc-idcDPkDtepR-vs.json'
import {
    attributeOptionComboExtensionUrl,
    attributeOptionComboLabel,
    attributeOptionCombosOf,
    attributeOptionComboOf,
    bundleResources,
    canonicalId,
    conceptDisplay,
    declaredOperations,
    formIdentifier,
    formSlice,
    formTitle,
    formTypeOf,
    formsByTitle,
    operationNames,
    questionCount,
    servedIgLabel,
    type Bundle,
    type CapabilityStatement,
    type CodeSystem,
    type Questionnaire,
    type QuestionnaireResponse,
    type ValueSet, unescapeMarkup } from '@/lib/fhir'

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
const attributeComboForm = attributeComboFormFixture as unknown as Questionnaire
const attributeComboResponse = attributeComboResponseFixture as unknown as QuestionnaireResponse
const attributeValueSet = attributeValueSetFixture as unknown as ValueSet
const attributeCodeSystem = attributeCodeSystemFixture as unknown as CodeSystem

/** One form of the served bundle by its DHIS2 uid, failing loudly rather than testing undefined. */
function servedForm(id: string): Questionnaire {
    const found = bundleResources(questionnaireBundle).find((questionnaire) => questionnaire.id === id)
    if (found === undefined) throw new Error(`the fixture bundle serves no Questionnaire ${id}`)
    return found
}

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

describe('naming a served form', () => {
    it('reads the harvested bundle in title order, whatever order the server sent it in', () => {
        const ordered = formsByTitle(bundleResources(questionnaireBundle))
        expect(ordered.map(formTitle)).toEqual([
            'ANC follow-up - ANC visit',
            'Child Health',
            'Child Programme - Baby Postnatal',
            'Supervision visit',
        ])
    })

    it('orders on the string it renders, not the escaped one the wire carries', () => {
        // `&lt;` sorts under the ampersand while `<` sorts where a reader expects it, so a
        // comparison taken before the unescape puts the row somewhere the eye cannot follow.
        const forms: Questionnaire[] = [
            { resourceType: 'Questionnaire', status: 'active', id: 'b', title: 'Bravo' },
            { resourceType: 'Questionnaire', status: 'active', id: 'a', title: 'Age &lt;5' },
        ]
        expect(formsByTitle(forms).map(formTitle)).toEqual(['Age <5', 'Bravo'])
    })

    it('falls back from title to name to the id it is served under', () => {
        expect(
            formTitle({ resourceType: 'Questionnaire', status: 'active', name: 'ChildHealth' }),
        ).toBe('ChildHealth')
        expect(
            formTitle({
                resourceType: 'Questionnaire',
                status: 'active',
                url: 'http://example.org/fhir/Questionnaire/BfMAe6Itzgt',
            }),
        ).toBe('BfMAe6Itzgt')
    })

    it('ids a form by its own id, then by the canonical last segment', () => {
        expect(formIdentifier({ resourceType: 'Questionnaire', status: 'active', id: 'abc' })).toBe('abc')
        expect(
            formIdentifier({
                resourceType: 'Questionnaire',
                status: 'active',
                url: 'http://example.org/fhir/Questionnaire/xyz',
            }),
        ).toBe('xyz')
        expect(formIdentifier({ resourceType: 'Questionnaire', status: 'active' })).toBe('')
    })
})

describe('formSlice', () => {
    const forms = bundleResources(questionnaireBundle)

    it('takes the first of the title order and says how many it left behind', () => {
        const slice = formSlice(forms, 2)
        expect(slice.shown.map(formTitle)).toEqual(['ANC follow-up - ANC visit', 'Child Health'])
        expect(slice.total).toBe(4)
        expect(slice.hidden).toBe(2)
    })

    it('hides nothing when the limit is wider than the set', () => {
        const slice = formSlice(forms, 8)
        expect(slice.shown).toHaveLength(4)
        expect(slice.hidden).toBe(0)
    })

    it('answers an empty slice for a project that publishes no forms', () => {
        expect(formSlice([], 8)).toEqual({ shown: [], total: 0, hidden: 0 })
    })
})

describe('operationNames', () => {
    it('names each declared operation once, rest-level first', () => {
        expect(operationNames(metadata)).toEqual(['translate', 'generate'])
    })

    it('drops the duplicate when one operation is declared on several resources', () => {
        expect(
            operationNames({
                ...metadata,
                rest: [
                    {
                        mode: 'server',
                        resource: [
                            { type: 'CodeSystem', operation: [{ name: 'translate' }] },
                            { type: 'ConceptMap', operation: [{ name: 'translate' }] },
                        ],
                    },
                ],
            }),
        ).toEqual(['translate'])
    })

    it('answers an empty list for a store that declares none', () => {
        expect(operationNames(null)).toEqual([])
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

/**
 * The attribute-option-combo contract, read off the artifacts the wave that added it emits.
 *
 * `Questionnaire-TuL8IOPzpHh` is the golden aggregate form whose DHIS2 data set rides a
 * non-default category combo, and the ValueSet and CodeSystem beside it are the vocabulary it
 * names. All three are the emitter's own bytes, so the suffix matching below is checked against
 * the urls the guide really publishes rather than against a spelling invented here.
 */
describe('the attribute option combo a form reports for', () => {
    it('reads the ValueSet a non-default-combo form declares', () => {
        expect(attributeOptionCombosOf(attributeComboForm)).toBe(attributeValueSet.url)
    })

    it('answers null for a form on the default combo, which is every other served form', () => {
        expect(attributeOptionCombosOf(servedForm('BfMAe6Itzgt'))).toBeNull()
    })

    it('derives the response-side url from the form-side one, off the same canonical', () => {
        expect(attributeOptionComboExtensionUrl(attributeComboForm)).toBe(
            'http://localhost:8080/fhir/StructureDefinition/d2-attribute-option-combo',
        )
        expect(attributeOptionComboExtensionUrl(servedForm('BfMAe6Itzgt'))).toBeNull()
    })

    it('tells the plural extension from the singular one, which differ by a character', () => {
        // The form declares the vocabulary and answers no combo of its own; reading it as one
        // would put a canonical where a Coding belongs.
        expect(
            attributeOptionComboOf({
                resourceType: 'QuestionnaireResponse',
                status: 'completed',
                extension: attributeComboForm.extension,
            }),
        ).toBeNull()
    })

    it('reads the coding a stored response reports under', () => {
        const coding = attributeOptionComboOf(attributeComboResponse)
        expect(coding?.system).toBe(attributeCodeSystem.url)
        expect(coding?.code).toBe('BqblOcSwGey')
    })

    it('names the choice by the vocabulary title, and by the artifact when there is none', () => {
        expect(attributeOptionComboLabel(attributeValueSet.title)).toBe('Reporting for Project')
        expect(attributeOptionComboLabel(attributeCodeSystem.title)).toBe('Reporting for Project')
        expect(attributeOptionComboLabel(null)).toBe('Attribute option combo')
        expect(attributeOptionComboLabel('   ')).toBe('Attribute option combo')
        expect(attributeOptionComboLabel('Weight &lt; 5kg')).toBe('Reporting for Weight < 5kg')
    })

    it('resolves a concept display through the served CodeSystem', () => {
        expect(conceptDisplay(attributeCodeSystem, 'pO5CEqK6c1s')).toBe('Improve access to clean water')
        expect(conceptDisplay(attributeCodeSystem, 'NotAConcept')).toBeNull()
        expect(conceptDisplay(null, 'pO5CEqK6c1s')).toBeNull()
        expect(conceptDisplay(attributeCodeSystem, undefined)).toBeNull()
    })
})
