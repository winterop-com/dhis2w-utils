import { describe, expect, it } from 'vitest'

import registrationFixture from '@/lib/__fixtures__/questionnaire-PrAncCare01.json'
import type { Bundle, CodeSystem, Patient, Questionnaire } from '@/lib/fhir'
import {
    enrollmentStatusLabel,
    enrollmentsInProgram,
    holdsTrackedEntityAttributeConcepts,
    isCompletedEnrollment,
    subjectExistsExtensionUrl,
    marksAnExistingSubject,
    MINIMUM_PATIENT_SEARCH_LENGTH,
    pageTokenOf,
    patientLeadValue,
    patientPage,
    patientProjection,
    patientSearchQuery,
    PATIENT_SEARCH_DEBOUNCE_MS,
    trackedEntityAttributeLabel,
    trackedEntityAttributeNames,
    trackedEntityTypeLabel,
    trackedEntityTypeNames,
    type PatientEnrollment,
} from '@/lib/patients'

/**
 * Reading a person the DHIS2 instance holds, and the two decisions a capture screen makes from it.
 *
 * The Patient below is the shape `dhis2w_fhir_serve.patients.projection` really emits, under the
 * fixture project's own canonical and identifier base: the tracked entity uid as `id` and as the
 * first identifier, one identifier per unique attribute value under
 * `{base}/tracked-entity-attribute/{uid}`, the tracked entity type as a `meta.tag`, and every
 * other attribute value on a `D2TrackedEntityAttributeValue` extension carrying `attributeId`,
 * `attributeCode` where the instance set one, and `value`.
 */

const IDENTIFIER_BASE = 'http://dhis2.org/fhir'
const CANONICAL = 'http://localhost:8080/fhir'

const registration = registrationFixture as unknown as Questionnaire

const person: Patient = {
    resourceType: 'Patient',
    id: 'TeiPerson001',
    meta: {
        tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetPerson01' }],
    },
    identifier: [
        { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: 'TeiPerson001' },
        { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaNationId`, value: '19850312-4471' },
    ],
    extension: [
        {
            url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
            extension: [
                { url: 'attributeId', valueString: 'TeaBirthDat' },
                { url: 'attributeCode', valueString: 'TEA_BIRTH_DATE' },
                { url: 'value', valueString: '1985-03-12' },
            ],
        },
        {
            // The uncoded case: DHIS2 requires no code on a tracked entity attribute, and the
            // projection writes no `attributeCode` sub-extension for one that has none.
            url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
            extension: [
                { url: 'attributeId', valueString: 'TeaHousehld' },
                { url: 'value', valueString: '4' },
            ],
        },
    ],
}

describe('reading one served Patient', () => {
    const projection = patientProjection(person)

    it('takes the tracked entity uid off the resource id', () => {
        expect(projection.trackedEntityUid).toBe('TeiPerson001')
    })

    it('takes the tracked entity type off the meta tag, where a classification belongs', () => {
        expect(projection.trackedEntityTypeUid).toBe('TetPerson01')
    })

    it('keeps only the unique attribute values as identifiers, each naming its attribute', () => {
        // The tracked-entity identifier is dropped: it is the same string as `trackedEntityUid`,
        // and a row listing it twice would state one fact in two places.
        expect(projection.identifiers).toEqual([{ attributeUid: 'TeaNationId', value: '19850312-4471' }])
    })

    it('reads every describing attribute value, code and all, and never invents a missing code', () => {
        expect(projection.attributeValues).toEqual([
            { attributeUid: 'TeaBirthDat', attributeCode: 'TEA_BIRTH_DATE', value: '1985-03-12' },
            { attributeUid: 'TeaHousehld', attributeCode: null, value: '4' },
        ])
    })

    it('leads a result row with the value that names the person', () => {
        expect(patientLeadValue(projection)).toBe('19850312-4471')
    })

    it('leads with the tracked entity uid when the person holds no unique value at all', () => {
        // A real answer rather than an empty cell: the uid was the search key that found them.
        const anonymous = patientProjection({ ...person, identifier: undefined, extension: undefined })
        expect(anonymous.identifiers).toEqual([])
        expect(patientLeadValue(anonymous)).toBe('TeiPerson001')
    })

    it('falls back to the tracked-entity identifier when the resource carries no id', () => {
        expect(patientProjection({ ...person, id: undefined }).trackedEntityUid).toBe('TeiPerson001')
    })

    it('skips an attribute value extension missing either half of what makes it one', () => {
        const partial = patientProjection({
            ...person,
            extension: [
                { url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`, extension: [] },
                {
                    url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
                    extension: [{ url: 'attributeId', valueString: 'TeaBirthDat' }],
                },
            ],
        })
        expect(partial.attributeValues).toEqual([])
    })
})

/**
 * When a typed identifier becomes a request.
 *
 * The rule is here rather than in the hook so it can be checked without a timer, and it is two
 * decisions: below `MINIMUM_PATIENT_SEARCH_LENGTH` nothing is asked at all, and what is asked is
 * trimmed - a trailing space in a scanned identifier is a keystroke, not part of the value.
 */
describe('the patient search query', () => {
    it('asks nothing until there is something worth asking', () => {
        expect(patientSearchQuery('')).toBeNull()
        expect(patientSearchQuery('   ')).toBeNull()
        expect(patientSearchQuery('1')).toBeNull()
        expect(MINIMUM_PATIENT_SEARCH_LENGTH).toBe(2)
    })

    it('sends the value trimmed, and nothing else about it', () => {
        expect(patientSearchQuery('  19850312-4471 ')).toBe('19850312-4471')
        expect(patientSearchQuery('AB')).toBe('AB')
    })

    it('waits for the typing to stop, because each call is a DHIS2 round trip', () => {
        expect(PATIENT_SEARCH_DEBOUNCE_MS).toBeGreaterThan(0)
    })
})

/** One enrollment of the person under test, as the listing states it. */
const enrollment = (uid: string, program: string, status: string): PatientEnrollment => ({
    enrollment_uid: uid,
    program_uid: program,
    program_name: program === 'PrAncCare01' ? 'Antenatal care' : null,
    status,
    active: status === 'ACTIVE',
    enrolled_at: '2026-02-01T00:00:00Z',
    organisation_unit_uid: 'DiszpKrYNg8',
    organisation_unit_name: 'Ngelehun CHC',
})

/**
 * Which of a person's enrollments a stage form may answer for.
 *
 * DHIS2 refuses an event filed against an enrollment in another program, so a picker offering the
 * person's other enrollments would be offering submissions that cannot import. The listing is
 * entity-scoped by design, so this narrowing is the whole of the rule.
 */
describe('a person’s enrollments', () => {
    const held = [
        enrollment('EnrAnc00001', 'PrAncCare01', 'ACTIVE'),
        enrollment('EnrAnc00002', 'PrAncCare01', 'COMPLETED'),
        enrollment('EnrChild001', 'IpHINAT79UW', 'ACTIVE'),
    ]

    it('offers this program’s enrollments and no others', () => {
        expect(enrollmentsInProgram(held, 'PrAncCare01').map((row) => row.enrollment_uid)).toEqual([
            'EnrAnc00001',
            'EnrAnc00002',
        ])
    })

    it('offers nothing for a form that names no program', () => {
        expect(enrollmentsInProgram(held, null)).toEqual([])
        expect(enrollmentsInProgram(held, '')).toEqual([])
    })

    it('spells each status once, in words', () => {
        expect(enrollmentStatusLabel('ACTIVE')).toBe('Active')
        expect(enrollmentStatusLabel('COMPLETED')).toBe('Completed')
        expect(enrollmentStatusLabel('CANCELLED')).toBe('Cancelled')
        // A status this UI has never heard of is shown as it arrived rather than translated.
        expect(enrollmentStatusLabel('SOMETHING_ELSE')).toBe('SOMETHING_ELSE')
    })

    it('grades the completed one, which is the one DHIS2 takes events into without complaint', () => {
        expect(held.filter(isCompletedEnrollment).map((row) => row.enrollment_uid)).toEqual(['EnrAnc00002'])
    })
})

/**
 * The marker a submission about an existing person carries, and where its url comes from.
 *
 * The vocabulary belongs to the conversion wave; what this UI owns is that the url is derived from
 * the form's own canonical rather than hard-coded, so a facade serving a guide compiled under a
 * different canonical than it answers on still writes a marker that guide can read.
 */
describe('the subject-exists marker', () => {
    it('derives its url from the form’s own form-type extension', () => {
        expect(subjectExistsExtensionUrl(registration)).toBe(`${CANONICAL}/StructureDefinition/d2-subject-exists`)
    })

    it('derives nothing from a form declaring no kind, which is one this server refuses anyway', () => {
        expect(subjectExistsExtensionUrl({ resourceType: 'Questionnaire', status: 'draft' })).toBeNull()
    })

    it('reads the marker back off a built response, by the tail rather than the canonical', () => {
        expect(marksAnExistingSubject(undefined)).toBe(false)
        expect(marksAnExistingSubject([{ url: `${CANONICAL}/StructureDefinition/d2-organisation-unit` }])).toBe(false)
        expect(
            marksAnExistingSubject([
                { url: 'http://elsewhere.example/StructureDefinition/d2-subject-exists', valueBoolean: true },
            ]),
        ).toBe(true)
    })
})

/**
 * One page of the listing, read off the Bundle's own links.
 *
 * THE TOKENS ARE NEVER CONSTRUCTED, only echoed - which is why this is tested at all. `page` is
 * opaque: the server mints it, the server reads it, and a UI that derived the next one would be
 * deciding how the DHIS2 instance is paged. What is under test is that a token comes back byte for
 * byte, that a missing link reads as "there is no page that way" rather than as an error, and that
 * a stated total is told apart from an absent one.
 */
describe('one page of everyone the instance holds', () => {
    const bundle = (links: { relation: string; url: string }[], total?: number): Bundle<Patient> => ({
        resourceType: 'Bundle',
        type: 'searchset',
        total,
        link: links,
        entry: [{ resource: person, search: { mode: 'match' } }],
    })

    it('reads the people, the tokens either side, and the total the server stated', () => {
        const page = patientPage(
            bundle(
                [
                    { relation: 'self', url: '/Patient?_count=25&page=NOW' },
                    { relation: 'previous', url: '/Patient?_count=25&page=BACK' },
                    { relation: 'next', url: '/Patient?_count=25&page=ON' },
                ],
                412,
            ),
        )
        expect(page.people.map((row) => row.trackedEntityUid)).toEqual(['TeiPerson001'])
        expect(page.previous).toBe('BACK')
        expect(page.next).toBe('ON')
        expect(page.total).toBe(412)
    })

    it('reads a link the server wrote absolute exactly as one it wrote relative', () => {
        const page = patientPage(
            bundle([{ relation: 'next', url: 'https://facade.example/Patient?page=ON&_count=25' }]),
        )
        expect(page.next).toBe('ON')
    })

    it('echoes the token verbatim, however the server spelled it', () => {
        // A token is whatever this server minted - a cursor, an encoded offset, a signed blob - and
        // it survives the round trip unparsed, punctuation and all.
        expect(pageTokenOf('/Patient?page=eyJvIjoyNX0%3D%2F%2B&_count=25')).toBe('eyJvIjoyNX0=/+')
    })

    it('reads a missing link as no page that way rather than as a failure', () => {
        const page = patientPage(bundle([{ relation: 'self', url: '/Patient?_count=25' }]))
        expect(page.previous).toBeNull()
        expect(page.next).toBeNull()
    })

    it('tells a total the server did not state apart from a total of zero', () => {
        expect(patientPage(bundle([])).total).toBeNull()
        expect(patientPage(bundle([], 0)).total).toBe(0)
    })

    it('reads no token out of a link that carries none', () => {
        expect(pageTokenOf(null)).toBeNull()
        expect(pageTokenOf('/Patient')).toBeNull()
        expect(pageTokenOf('/Patient?_count=25')).toBeNull()
        expect(pageTokenOf('/Patient?page=')).toBeNull()
    })
})

/**
 * What a uid is called, joined through what this project published rather than through the instance.
 *
 * A served Patient carries uids and no display for any of them, because the projection refuses to
 * invent one. The names do exist, in the guide: `D2TEA_CS` names every attribute the selected forms
 * ask, and a person-only form is titled with the name of the tracked entity type it was generated
 * from. So these are the two joins, and what an unpublished object falls back to is the other half
 * of the rule - a spelling DHIS2 sent, never one this screen made up.
 */
describe('naming what a person is described in terms of', () => {
    const attributeDictionary: CodeSystem = {
        resourceType: 'CodeSystem',
        id: 'd2-tea-cs',
        status: 'draft',
        concept: [
            { code: 'TeaNationId', display: 'National identifier' },
            { code: 'TeaBirthDat', display: 'Date of birth' },
            // Escaped at emit time, like every published display, and unescaped for the screen.
            { code: 'TeaHousehld', display: 'Household size &lt; 10' },
        ],
    }
    const personForm: Questionnaire = {
        resourceType: 'Questionnaire',
        id: 'TetPerson01',
        title: 'Person',
        status: 'draft',
        extension: [{ url: `${CANONICAL}/StructureDefinition/d2-form-type`, valueCode: 'tracked-entity' }],
        identifier: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, value: 'TetPerson01' }],
    }

    it('finds the attribute dictionary by the id rule rather than by a hard-coded name', () => {
        expect(holdsTrackedEntityAttributeConcepts(attributeDictionary)).toBe(true)
        // A project with no prefix publishes the bare id; every other vocabulary answers false.
        expect(holdsTrackedEntityAttributeConcepts({ ...attributeDictionary, id: 'tea-cs' })).toBe(true)
        for (const id of ['d2-de-cs', 'd2-coc-cs', 'd2-tea-vs', 'd2-ou-cs']) {
            expect(holdsTrackedEntityAttributeConcepts({ ...attributeDictionary, id }), id).toBe(false)
        }
    })

    it('names an attribute by what the dictionary published, unescaped', () => {
        const names = trackedEntityAttributeNames([
            {
                resourceType: 'CodeSystem',
                id: 'd2-de-cs',
                status: 'draft',
                concept: [{ code: 'TeaNationId', display: 'A data element of the same code' }],
            },
            attributeDictionary,
        ])
        expect(trackedEntityAttributeLabel(names, 'TeaNationId')).toEqual({
            text: 'National identifier',
            isMachineSpelling: false,
        })
        expect(trackedEntityAttributeLabel(names, 'TeaHousehld').text).toBe('Household size < 10')
    })

    it('falls back to the DHIS2 code, then to the uid, for an attribute this project never published', () => {
        const names = trackedEntityAttributeNames([attributeDictionary])
        expect(trackedEntityAttributeLabel(names, 'TeaUnknown1', 'TEA_UNKNOWN')).toEqual({
            text: 'TEA_UNKNOWN',
            isMachineSpelling: true,
        })
        expect(trackedEntityAttributeLabel(names, 'TeaUnknown1')).toEqual({
            text: 'TeaUnknown1',
            isMachineSpelling: true,
        })
        expect(trackedEntityAttributeLabel(names, 'TeaUnknown1', '')).toEqual({
            text: 'TeaUnknown1',
            isMachineSpelling: true,
        })
    })

    it('names a tracked entity type by the person-only form generated from it', () => {
        // The tracker registration form beside it carries the very same tracked-entity-type
        // identifier - it is the type it enrols people as - and is titled with its program's name.
        // Joining on the identifier alone would call every person here "Antenatal care".
        const names = trackedEntityTypeNames([registration, personForm])
        expect([...names.entries()]).toEqual([['TetPerson01', 'Person']])
        expect(trackedEntityTypeLabel(names, 'TetPerson01')).toEqual({ text: 'Person', isMachineSpelling: false })
    })

    it('keeps the uid for a type this project publishes no form for, and states nothing for none', () => {
        const names = trackedEntityTypeNames([personForm])
        expect(trackedEntityTypeLabel(names, 'TetOther001')).toEqual({
            text: 'TetOther001',
            isMachineSpelling: true,
        })
        expect(trackedEntityTypeLabel(names, null)).toBeNull()
        expect(trackedEntityTypeLabel(names, '')).toBeNull()
    })
})
