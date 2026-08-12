import { describe, expect, it } from 'vitest'

import attributeCodeSystemFixture from '@/lib/__fixtures__/codesystem-d2-aoc-idcDPkDtepR-cs.json'
import generateAggregateFixture from '@/lib/__fixtures__/generate-BfMAe6Itzgt.json'
import generateTrackerEventFixture from '@/lib/__fixtures__/generate-ZzYYXq4fJie.json'
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
    bundleLink,
    bundleResources,
    canonicalId,
    conceptDisplay,
    declaredOperations,
    declaresPatientSearch,
    enrolledAtOf,
    FORM_TYPE_LABELS,
    FORM_TYPES,
    formIdentifier,
    formSlice,
    formTitle,
    formTypeOf,
    formsByTitle,
    identifierSystemBaseOf,
    incidentAtOf,
    operationNames,
    programOf,
    questionCount,
    registersAPerson,
    servedIgLabel,
    trackedEntityOf,
    trackedEntityTypeOf,
    trackerEnrollmentOf,
    trackerEnrollmentExtensionUrl,
    type Bundle,
    type CapabilityStatement,
    type CodeSystem,
    type Questionnaire,
    type QuestionnaireResponse,
    type ValueSet } from '@/lib/fhir'

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
const aggregateSkeleton = generateAggregateFixture as unknown as QuestionnaireResponse
const trackerEventSkeleton = generateTrackerEventFixture as unknown as QuestionnaireResponse

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
        // Each operation is declared on the resource entry whose URL answers it:
        // `/Questionnaire/{id}/$generate` and `/ConceptMap/$translate`. The ConceptMap
        // entry is only there because this fixture's store holds maps, so a store
        // without them declares neither the type nor the operation.
        const translate = operations.find((operation) => operation.name === 'translate')
        expect(translate?.on).toBe('ConceptMap')
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

/**
 * Whether this server can be asked who a person is, read off the conformance document.
 *
 * THIS IS THE ONE PROBE, AND THE FIXTURE IS THE COMPILED CASE. `metadata.json` is a real
 * `/metadata` from a compiled run, and a compiled run declares no `Patient` at all - the resource
 * is answered from a DHIS2 instance and there is none behind a compiled guide. So the fixture is
 * the negative, and the positive is built here in the shape `dhis2w_fhir_serve.capability` emits
 * under `--live`.
 *
 * BOTH HALVES ARE REQUIRED ON PURPOSE. A statement naming `Patient` with a read interaction alone
 * would be a server that resolves a person by uid and cannot look one up, and a search box offered
 * against it would be a search box that always fails.
 */
describe('whether patient search is published', () => {
    /** The Patient entry a live process over a project publishing a registration form declares. */
    const livePatient = {
        type: 'Patient',
        interaction: [{ code: 'read' }, { code: 'search-type' }],
        searchParam: [{ name: 'identifier', type: 'token' }],
    }

    /** One statement carrying whatever Patient entry a case is about, beside the compiled ones. */
    const withPatient = (entry: Record<string, unknown> | null): CapabilityStatement => ({
        ...metadata,
        rest: [
            {
                ...metadata.rest![0],
                resource: [
                    ...(metadata.rest?.[0].resource ?? []),
                    ...(entry === null ? [] : [entry as unknown as (typeof livePatient)]),
                ],
            },
        ],
    })

    it('is not published by a compiled run, which declares no Patient at all', () => {
        expect(metadata.rest?.[0].resource?.some((resource) => resource.type === 'Patient')).toBe(false)
        expect(declaresPatientSearch(metadata)).toBe(false)
    })

    it('is published when the statement declares Patient with a search on identifier', () => {
        expect(declaresPatientSearch(withPatient(livePatient))).toBe(true)
    })

    it('is not published by a Patient entry that can only be read by uid', () => {
        expect(
            declaresPatientSearch(withPatient({ type: 'Patient', interaction: [{ code: 'read' }] })),
        ).toBe(false)
    })

    it('is not published by a search on some parameter other than identifier', () => {
        expect(
            declaresPatientSearch(
                withPatient({
                    type: 'Patient',
                    interaction: [{ code: 'search-type' }],
                    searchParam: [{ name: 'name', type: 'string' }],
                }),
            ),
        ).toBe(false)
    })

    it('is not published by a server that answered nothing at all', () => {
        expect(declaresPatientSearch(null)).toBe(false)
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

    it('orders on the string it renders, which is the one the wire carries', () => {
        const forms: Questionnaire[] = [
            { resourceType: 'Questionnaire', status: 'active', id: 'b', title: 'Bravo' },
            { resourceType: 'Questionnaire', status: 'active', id: 'a', title: 'Age <5' },
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
    it('names each declared operation once, in declaration order', () => {
        expect(operationNames(metadata)).toEqual(['generate', 'translate'])
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

describe('served text', () => {
    it('is shown exactly as the server sends it, entities and all', () => {
        // The server carries the DHIS2 text byte for byte, so a name that really holds `&lt;`
        // holds it here too - the UI decodes nothing, because nothing was encoded.
        const named = {
            resourceType: 'Questionnaire',
            status: 'draft',
            title: 'Age (<5 - 49) & over',
        } as const satisfies Questionnaire
        expect(formTitle(named)).toBe('Age (<5 - 49) & over')
        expect(formTitle({ ...named, title: 'A &amp; B' })).toBe('A &amp; B')
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
        expect(attributeOptionComboLabel('Weight < 5kg')).toBe('Reporting for Weight < 5kg')
    })

    it('resolves a concept display through the served CodeSystem', () => {
        expect(conceptDisplay(attributeCodeSystem, 'pO5CEqK6c1s')).toBe('Improve access to clean water')
        expect(conceptDisplay(attributeCodeSystem, 'NotAConcept')).toBeNull()
        expect(conceptDisplay(null, 'pO5CEqK6c1s')).toBeNull()
        expect(conceptDisplay(attributeCodeSystem, undefined)).toBeNull()
    })
})

/**
 * The five DHIS2 objects a capture form can have come from, as this UI names them.
 *
 * `tracker` is the registration form - one Questionnaire per tracker program, asking the tracked
 * entity attributes - and it is one character away from `tracker-event`, the program stage. The
 * two are different forms of different shapes producing different DHIS2 payloads, so the pair
 * being spelled apart is worth an assertion of its own: a label lookup that fell through would
 * render a registration form as a bare code in every listing that shows the kind.
 *
 * `tracked-entity` is the third one-person kind and the one no program is behind: it registers a
 * person and enrols them in nothing. Admitting it is what lets a served person-only form be
 * shelved, opened, filled, and submitted rather than being listed as a form declaring no kind.
 */
describe('the form-kind vocabulary', () => {
    it('carries every code of the D2FormType terminology, both registration kinds included', () => {
        expect([...FORM_TYPES]).toEqual(['aggregate', 'event', 'tracker', 'tracker-event', 'tracked-entity'])
    })

    it('names each kind, and never leaves one to render as its code', () => {
        expect(FORM_TYPE_LABELS.tracker).toBe('Tracker registration')
        expect(FORM_TYPE_LABELS['tracker-event']).toBe('Tracker program stage')
        expect(FORM_TYPE_LABELS['tracked-entity']).toBe('Person registration')
        for (const kind of FORM_TYPES) expect(FORM_TYPE_LABELS[kind], kind).not.toBe('')
    })

    it('reads the person-only kind off a form that declares it, and grades who registers a person', () => {
        expect(
            formTypeOf({
                resourceType: 'Questionnaire',
                status: 'active',
                extension: [
                    {
                        url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type',
                        valueCode: 'tracked-entity',
                    },
                ],
            }),
        ).toBe('tracked-entity')
        expect(registersAPerson('tracked-entity')).toBe(true)
        expect(registersAPerson('tracker')).toBe(true)
        // A stage form is about a person, but it names one rather than registering one.
        expect(registersAPerson('tracker-event')).toBe(false)
        expect(registersAPerson('aggregate')).toBe(false)
        expect(registersAPerson(null)).toBe(false)
    })

    it('reads the registration kind off a form that declares it', () => {
        expect(
            formTypeOf({
                resourceType: 'Questionnaire',
                status: 'active',
                extension: [
                    {
                        url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type',
                        valueCode: 'tracker',
                    },
                ],
            }),
        ).toBe('tracker')
    })
})

/**
 * The tracker facts a response carries in its envelope rather than in an answer.
 *
 * WHERE THE REGISTRATION DOCUMENT COMES FROM. Two of the three fixtures here are harvested
 * `$generate` output, and they are what prove the readers against the wire - a tracker event's
 * enrollment and tracked entity are read off a real one, and an aggregate response is what proves
 * a `Location` subject is not mistaken for a person. The registration envelope is written from the
 * published profile instead (`D2TrackerRegistrationResponse` in dhis2w_fhir's
 * foundation/templates/d2-responses.fsh.jinja), because the dates are the half of the contract no
 * harvested fixture carries yet. The e2e capture walkthrough is what pins the same reading against
 * a real server.
 */
describe('the tracker context on a response envelope', () => {
    /** A registration response as the profile requires it: minted identities, both dates. */
    const registration: QuestionnaireResponse = {
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
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type',
                valueCode: 'tracker',
            },
        ],
    }

    it('reads both enrollment dates a registration files', () => {
        expect(enrolledAtOf(registration)).toBe('2026-07-21T04:00:00Z')
        expect(incidentAtOf(registration)).toBe('2026-07-14T04:00:00Z')
    })

    it('reads the identities a registration mints for itself', () => {
        expect(trackedEntityOf(registration)).toBe('wJt3Qy1PxLd')
        expect(trackerEnrollmentOf(registration)).toBe('Qm4bTnPzKdE')
    })

    it('reads the same two identities off a real tracker-event skeleton', () => {
        // The stage response quotes an enrollment rather than minting one, and the extension is
        // spelled identically - which is what lets one reader serve both tracker kinds.
        expect(trackedEntityOf(trackerEventSkeleton)).toBe('zPde0IgxLd6')
        expect(trackerEnrollmentOf(trackerEventSkeleton)).toBe('GncfBAepfJB')
    })

    it('states no enrollment date for a stage response, because the profile carries none', () => {
        expect(enrolledAtOf(trackerEventSkeleton)).toBeNull()
        expect(incidentAtOf(trackerEventSkeleton)).toBeNull()
    })

    it('never reads a Location subject as a person', () => {
        // An aggregate response's subject is the organisation unit it reports from, identified by
        // reference and not by a tracked-entity identifier at all.
        expect(trackedEntityOf(aggregateSkeleton)).toBeNull()
        expect(trackerEnrollmentOf(aggregateSkeleton)).toBeNull()
        expect(enrolledAtOf(aggregateSkeleton)).toBeNull()
    })

    it('refuses a subject identifier from a system that is not the tracked-entity one', () => {
        expect(
            trackedEntityOf({
                resourceType: 'QuestionnaireResponse',
                status: 'completed',
                subject: {
                    type: 'Patient',
                    identifier: { system: 'http://example.org/id/person', value: 'wJt3Qy1PxLd' },
                },
            }),
        ).toBeNull()
    })

    it('states the absence of every fact rather than guessing one', () => {
        const bare: QuestionnaireResponse = { resourceType: 'QuestionnaireResponse', status: 'completed' }
        expect(enrolledAtOf(bare)).toBeNull()
        expect(incidentAtOf(bare)).toBeNull()
        expect(trackerEnrollmentOf(bare)).toBeNull()
        expect(trackedEntityOf(bare)).toBeNull()
    })

    it('tells the incident date from the enrollment date, which share a url stem', () => {
        // `endsWith` is exact at the end, so `...d2-enrolled-at` cannot answer for
        // `...d2-incident-at` - the same rule the attribute-option-combo pair relies on.
        const enrolledOnly: QuestionnaireResponse = {
            resourceType: 'QuestionnaireResponse',
            status: 'completed',
            extension: [
                {
                    url: 'http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at',
                    valueDateTime: '2026-07-21T04:00:00Z',
                },
            ],
        }
        expect(incidentAtOf(enrolledOnly)).toBeNull()
        expect(enrolledAtOf(enrolledOnly)).toBe('2026-07-21T04:00:00Z')
    })
})

describe('the program a form belongs to', () => {
    it('reads the program uid off a real stage form, where it is a grouping identifier', () => {
        expect(programOf(servedForm('PsAncVisit1'))).toBe('PrAncCare01')
    })

    it('reads it off an event form too, where the form is the program', () => {
        // Which is exactly why the value alone cannot say "tracker": callers joining tracker
        // surfaces pair this with `formTypeOf`.
        expect(programOf(servedForm('EVTsupVis01'))).toBe('EVTsupVis01')
        expect(formTypeOf(servedForm('EVTsupVis01'))).toBe('event')
    })

    it('does not read `/id/program-stage` as the program, because the suffix match is exact', () => {
        const stageOnly: Questionnaire = {
            resourceType: 'Questionnaire',
            status: 'active',
            identifier: [{ system: 'http://dhis2.org/fhir/id/program-stage', value: 'PsAncVisit1' }],
        }
        expect(programOf(stageOnly)).toBeNull()
    })

    it('states the absence for a form naming no program at all', () => {
        expect(programOf(servedForm('BfMAe6Itzgt'))).toBeNull()
    })
})

describe('the derived tracker spellings the no-envelope rewrite falls back on', () => {
    it('derives the identifier-system base off the form’s own program identifier', () => {
        expect(identifierSystemBaseOf(servedForm('PsAncVisit1'))).toBe('http://dhis2.org/fhir')
    })

    it('derives the enrollment extension url off the form-type declaration’s canonical', () => {
        expect(trackerEnrollmentExtensionUrl(servedForm('PsAncVisit1'))).toBe(
            'http://localhost:8080/fhir/StructureDefinition/d2-tracker-enrollment',
        )
    })

    it('answers null for a form that states neither, rather than guessing a spelling', () => {
        const bare: Questionnaire = { resourceType: 'Questionnaire', status: 'active' }
        expect(identifierSystemBaseOf(bare)).toBeNull()
        expect(trackerEnrollmentExtensionUrl(bare)).toBeNull()
    })
})

/**
 * Where a paged search says its neighbours are.
 *
 * The one read in this app whose answer arrives in pieces, so the links are how the pieces are
 * joined. `next` absent is the server stating there is no page after this one - a fact rather than
 * an omission - which is why the reader answers null instead of guessing at an offset.
 */
describe('the links a searchset states', () => {
    const paged: Bundle<Questionnaire> = {
        resourceType: 'Bundle',
        type: 'searchset',
        link: [
            { relation: 'self', url: '/Patient?_count=25' },
            { relation: 'next', url: '/Patient?_count=25&page=ON' },
        ],
    }

    it('finds a relation by name rather than by where it sits in the list', () => {
        expect(bundleLink(paged, 'next')).toBe('/Patient?_count=25&page=ON')
        expect(bundleLink(paged, 'self')).toBe('/Patient?_count=25')
    })

    it('answers null for a relation the Bundle did not state, and for no Bundle at all', () => {
        expect(bundleLink(paged, 'previous')).toBeNull()
        expect(bundleLink(questionnaireBundle, 'next')).toBeNull()
        expect(bundleLink(undefined, 'next')).toBeNull()
    })
})

/**
 * The tracked entity type a person-only form was generated from.
 *
 * The one place the guide publishes a name for a type: a served Patient states the type uid as a
 * tag and carries no display for it, so this identifier is the join that turns `TetPerson01` into
 * whatever the instance calls that type. The suffix comparison is exact at the end, which is what
 * keeps `/id/tracked-entity` - a different system, on a different element - out of the answer.
 */
describe('a person-only form’s tracked entity type', () => {
    it('reads the uid the form was generated from', () => {
        const personForm: Questionnaire = {
            resourceType: 'Questionnaire',
            id: 'TetPerson01',
            status: 'draft',
            identifier: [
                { system: 'http://dhis2.org/fhir/id/tracked-entity-type', value: 'TetPerson01' },
                { system: 'http://dhis2.org/fhir/id/tracked-entity-type-code', value: 'TET_PERSON' },
            ],
        }
        expect(trackedEntityTypeOf(personForm)).toBe('TetPerson01')
    })

    it('reads nothing off a form that names a program instead', () => {
        expect(trackedEntityTypeOf(servedForm('PsAncVisit1'))).toBeNull()
        expect(trackedEntityTypeOf({ resourceType: 'Questionnaire', status: 'draft' })).toBeNull()
    })
})
