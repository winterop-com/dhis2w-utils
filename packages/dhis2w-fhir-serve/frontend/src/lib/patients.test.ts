import { describe, expect, it } from 'vitest'

import registrationFixture from '@/lib/__fixtures__/questionnaire-PrAncCare01.json'
import { formatInstant } from '@/lib/spool'
import type { Bundle, CodeSystem, Patient, Questionnaire } from '@/lib/fhir'
import {
    enrollmentStatusLabel,
    enrollmentsInProgram,
    holdsTrackedEntityAttributeConcepts,
    isCompletedEnrollment,
    narrowedRegisterAttribute,
    narrowedRegisterType,
    parseRegisterAttributeToken,
    registerAttributeToken,
    registerAttributeValue,
    registerTableColumns,
    registerTypeChoices,
    REGISTER_ATTRIBUTE_COLUMNS,
    REGISTER_ATTRIBUTE_PARAMETER,
    REGISTER_ATTRIBUTE_SEARCH_PARAMETER,
    REGISTER_TYPE_PARAMETER,
    subjectExistsExtensionUrl,
    marksAnExistingSubject,
    MINIMUM_PATIENT_SEARCH_LENGTH,
    NOTHING_SYNCED,
    pageTokenOf,
    patientIdentifierValue,
    patientLeadValue,
    patientPage,
    patientProjection,
    patientSearchQuery,
    projectionAsOfLine,
    PATIENT_SEARCH_DEBOUNCE_MS,
    trackedEntityAttributeLabel,
    trackedEntityAttributeNames,
    trackedEntityAttributesInList,
    trackedEntityTypeLabel,
    trackedEntityTypeNames,
    type PatientEnrollment,
    type PatientProjection,
} from '@/lib/patients'
import type { Register } from '@/lib/uiconfig'

/**
 * Reading a person the DHIS2 instance holds, and the two decisions a capture screen makes from it.
 *
 * The Patient below is the shape `dhis2w_fhir_serve.register.projection` really emits, under the
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
            // A display carries the DHIS2 text byte for byte, markup characters included.
            { code: 'TeaHousehld', display: 'Household size < 10' },
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

    it('names an attribute by what the dictionary published, verbatim', () => {
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

/**
 * The two facts a register listing reads out of the published attribute dictionary.
 *
 * WHICH VALUE NAMES SOMEBODY, and whether there is one at all. `patientLeadValue` has always
 * answered the first by falling back to the tracked entity uid; `patientIdentifierValue` is the half
 * before the fallback, and it exists because a screen sometimes has to act on the fallback rather
 * than only render it - a page headed by a uid must not badge that same uid underneath.
 *
 * WHICH VALUES BELONG IN A LIST. DHIS2 lets an administrator mark the attributes that let a clerk
 * recognise somebody, and that marking is a fact about the instance's workflow rather than a guess a
 * browser can make. An instance marking none states no preference, which is a different thing from
 * marking none as wanted.
 */
describe('what a register listing reads out of the dictionary', () => {
    const dictionary: CodeSystem = {
        resourceType: 'CodeSystem',
        status: 'active',
        id: 'd2-tea-cs',
        url: 'http://localhost:8080/fhir/CodeSystem/d2-tea-cs',
        concept: [
            {
                code: 'TeaBirthDat',
                display: 'Date of birth',
                property: [{ code: 'display-in-list', valueBoolean: true }],
            },
            {
                code: 'TeaHousehld',
                display: 'Household size',
                property: [{ code: 'display-in-list', valueBoolean: false }],
            },
            { code: 'TeaConsent1', display: 'Consent given' },
        ],
    }

    it('collects the attributes DHIS2 puts in a listing, and nothing it declined or left unsaid', () => {
        const flagged = trackedEntityAttributesInList([dictionary])
        expect(flagged.has('TeaBirthDat')).toBe(true)
        expect(flagged.has('TeaHousehld')).toBe(false)
        expect(flagged.has('TeaConsent1')).toBe(false)
    })

    it('reads no preference out of a vocabulary that is not the attribute dictionary', () => {
        const options: CodeSystem = {
            resourceType: 'CodeSystem',
            status: 'active',
            id: 'd2-os-OsSex000001-cs',
            concept: [{ code: 'OpFemale001', property: [{ code: 'display-in-list', valueBoolean: true }] }],
        }
        expect(trackedEntityAttributesInList([options]).size).toBe(0)
    })

    it('separates the value that names somebody from the uid that stands in when there is none', () => {
        const named = patientProjection(person)
        expect(patientIdentifierValue(named)).toBe(patientLeadValue(named))

        const unnamed = { ...named, identifiers: [] }
        expect(patientIdentifierValue(unnamed)).toBeNull()
        // The renderer's answer is still the uid; what changed is that a caller can now tell that
        // the uid is a fallback rather than a value this instance holds.
        expect(patientLeadValue(unnamed)).toBe(unnamed.trackedEntityUid)
    })
})

/** The OperationOutcome a projection-served searchset carries beside its matches. */
const outcome = (diagnostics: string) => ({
    resourceType: 'OperationOutcome' as const,
    issue: [{ severity: 'information' as const, code: 'informational', diagnostics }],
})

describe('how old a register answer says it is', () => {
    it('says nothing at all when the answer came from the DHIS2 instance itself', () => {
        expect(projectionAsOfLine(null, null)).toBeNull()
    })

    it('states the instant off the header, in the wall clock every other instant is read in', () => {
        const stated = projectionAsOfLine('2026-08-21T16:46:57', null)
        expect(stated).toContain('Answered from the synced copy of this DHIS2 instance, as of ')
        expect(stated).toContain(formatInstant('2026-08-21T16:46:57'))
    })

    it('states the instant once, not twice, when the outcome says it too', () => {
        const stated = projectionAsOfLine(
            '2026-08-21T16:46:57',
            outcome("served from this project's materialized projection, as of 2026-08-21T16:46:57"),
        )
        expect(stated).not.toContain('materialized projection')
        expect(stated?.match(/2026/g) ?? []).toHaveLength(1)
    })

    it('falls back to the server’s own sentence for a copy nothing has filled yet', () => {
        const nothing = "this project's materialized projection holds nothing yet: no sync has read the instance."
        expect(projectionAsOfLine(NOTHING_SYNCED, outcome(nothing))).toBe(nothing)
    })

    it('falls back to the same sentence when the header never arrived but the outcome did', () => {
        const said = 'served from a synced copy of the DHIS2 instance.'
        expect(projectionAsOfLine(null, outcome(said))).toBe(said)
    })

    it('says nothing for an outcome carrying no diagnostics to say', () => {
        expect(
            projectionAsOfLine(NOTHING_SYNCED, {
                resourceType: 'OperationOutcome',
                issue: [{ severity: 'information', code: 'informational' }],
            }),
        ).toBeNull()
    })
})

/**
 * Narrowing one register to one of the tracked entity types it is served over.
 *
 * THE CHOICES ARE THE SERVER'S OWN DECLARATION. `/facade/uiconfig` states the types riding each register
 * and the name the published map holds for each; `/metadata` documents the same set under the `_tag`
 * parameter that narrows to one of them. Nothing here reads a row to find out what a register serves,
 * because a page holding no fridges today would then offer no way to ask for one.
 */
describe('the tracked entity types one register offers', () => {
    const cold: Register = {
        resource: 'Device',
        types: [
            { uid: 'TetFridge01', name: 'Fridge' },
            { uid: 'TetVehicle1', name: 'Cold chain vehicle' },
        ],
    }

    it('offers one choice per declared type, named as the instance names it', () => {
        expect(registerTypeChoices(cold)).toEqual([
            { uid: 'TetFridge01', name: { text: 'Fridge', isMachineSpelling: false } },
            { uid: 'TetVehicle1', name: { text: 'Cold chain vehicle', isMachineSpelling: false } },
        ])
    })

    it('falls back to the uid for a type this guide published no name for, and spells it as one', () => {
        const unnamed: Register = { resource: 'Device', types: [{ uid: 'TetFridge01', name: null }] }
        expect(registerTypeChoices(unnamed)).toEqual([
            { uid: 'TetFridge01', name: { text: 'TetFridge01', isMachineSpelling: true } },
        ])
    })

    it('offers nothing to choose between on a register serving one type', () => {
        expect(registerTypeChoices({ resource: 'Patient', types: [{ uid: 'TetPerson01', name: 'Person' }] })).toHaveLength(1)
    })

    it('carries the chosen type in the address under its own parameter', () => {
        expect(REGISTER_TYPE_PARAMETER).toBe('type')
    })
})

describe('which type a register is narrowed to', () => {
    const cold: Register = {
        resource: 'Device',
        types: [
            { uid: 'TetFridge01', name: 'Fridge' },
            { uid: 'TetVehicle1', name: 'Cold chain vehicle' },
        ],
    }

    it('is the type the address names, when this register serves it', () => {
        expect(narrowedRegisterType(cold, 'TetVehicle1')).toBe('TetVehicle1')
    })

    it('is nothing when the address names none', () => {
        expect(narrowedRegisterType(cold, null)).toBeNull()
        expect(narrowedRegisterType(cold, '')).toBeNull()
    })

    it('is nothing when the address names a type this register is not served over', () => {
        // A page serving several registers carries one narrowing, and a `_tag` naming a type this
        // resource does not serve would empty it - which reads as "this instance holds none of
        // these" rather than as an address about the register next door.
        expect(narrowedRegisterType(cold, 'TetPerson01')).toBeNull()
    })
})

/**
 * The attribute value filter, from the address to the wire and back.
 *
 * ONE PAIR, SPELLED ONE WAY. `?attribute=<uid>|<value>` in the browser and
 * `d2-attribute=<uid>|<value>` on the request are the same two halves in the same spelling, so a
 * filtered register is a link that can be sent and the request it produces is the one the server
 * documented. What is tested here is the round trip: what a control writes into the address is what
 * comes back out of it, values with a pipe in them included.
 */
describe('the attribute value a register is filtered by', () => {
    const cold: Register = {
        resource: 'Device',
        types: [{ uid: 'TetFridge01', name: 'Fridge' }],
        filter_attributes: [
            { uid: 'TeaModel0001', name: 'Model', value_type: 'TEXT', value_set: null },
            { uid: 'TeaCapacity1', name: 'Capacity in litres', value_type: 'NUMBER', value_set: null },
        ],
    }

    it('rides the address under its own parameter, and the wire under the one the server documents', () => {
        expect(REGISTER_ATTRIBUTE_PARAMETER).toBe('attribute')
        expect(REGISTER_ATTRIBUTE_SEARCH_PARAMETER).toBe('d2-attribute')
    })

    it('writes and reads back the pair it was given', () => {
        const filter = { attributeUid: 'TeaModel0001', value: 'MK-4' }
        const token = registerAttributeToken(filter)
        expect(token).toBe('TeaModel0001|MK-4')
        expect(narrowedRegisterAttribute(cold, token)).toEqual(filter)
    })

    it('keeps a pipe inside a value, because a DHIS2 value may hold one', () => {
        const filter = { attributeUid: 'TeaModel0001', value: 'MK-4|B' }
        expect(narrowedRegisterAttribute(cold, registerAttributeToken(filter))).toEqual(filter)
    })

    it('is nothing while an attribute is chosen and no value is stated', () => {
        // A control somebody has half-filled, which is a different state from a filter matching the
        // empty string - and the request must not go out for it.
        expect(parseRegisterAttributeToken('TeaModel0001|')).toBeNull()
        expect(parseRegisterAttributeToken('TeaModel0001')).toBeNull()
        expect(parseRegisterAttributeToken(null)).toBeNull()
    })

    it('is nothing when the address names an attribute this register does not filter by', () => {
        // The same rule the type narrowing follows: a filter the server does not answer over would
        // empty the page, and an empty page reads as an instance holding nobody.
        expect(narrowedRegisterAttribute(cold, 'TeaNationId|19850312-4471')).toBeNull()
    })

    it('is nothing on a register declaring no filter attributes at all', () => {
        expect(
            narrowedRegisterAttribute({ resource: 'Device', types: [] }, 'TeaModel0001|MK-4'),
        ).toBeNull()
    })
})

/**
 * What the register table draws for one page of rows.
 *
 * ONE COLUMN PER ATTRIBUTE, derived from what the rows hold rather than from a declaration: DHIS2
 * requires no attribute of an entity, so a column set taken from a type's whole attribute list would
 * be columns of dashes.
 */
/** One row of a register page, as `patientProjection` hands one over. */
const row = (
    trackedEntityUid: string,
    attributeValues: { attributeUid: string; attributeCode?: string | null; value: string }[],
    identifiers: { attributeUid: string; value: string }[] = [],
): PatientProjection => ({
    trackedEntityUid,
    trackedEntityTypeUid: 'TetPerson01',
    identifiers,
    attributeValues: attributeValues.map((value) => ({
        attributeUid: value.attributeUid,
        attributeCode: value.attributeCode ?? null,
        value: value.value,
    })),
})

describe('the columns one page of register rows earns', () => {
    const names = new Map([
        ['TeaBirthDat', 'Date of birth'],
        ['TeaHousehld', 'Household size'],
        ['TeaSex00001', 'Sex'],
    ])

    it('gives every attribute the rows hold a column of its own, named once', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [
                    { attributeUid: 'TeaBirthDat', attributeCode: 'TEA_BIRTH_DATE', value: '1985-03-12' },
                ]),
                row('TeiPerson002', [{ attributeUid: 'TeaHousehld', value: '6' }]),
            ],
            names,
            new Set(),
        )
        expect(columns.attributes.map((column) => column.attributeUid)).toEqual(['TeaBirthDat', 'TeaHousehld'])
        expect(columns.attributes.map((column) => column.name.text)).toEqual(['Date of birth', 'Household size'])
        expect(columns.hidden).toBe(0)
    })

    it('leads with the attributes DHIS2 marks as belonging in a listing', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [
                    { attributeUid: 'TeaHousehld', value: '4' },
                    { attributeUid: 'TeaBirthDat', value: '1985-03-12' },
                    { attributeUid: 'TeaSex00001', value: 'OpFemale001' },
                ]),
            ],
            names,
            new Set(['TeaBirthDat', 'TeaSex00001']),
        )
        expect(columns.attributes.map((column) => column.attributeUid)).toEqual([
            'TeaBirthDat',
            'TeaSex00001',
            'TeaHousehld',
        ])
    })

    it('takes the order from the published dictionary, not from the order the rows carried', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [
                    { attributeUid: 'TeaHousehld', value: '4' },
                    { attributeUid: 'TeaBirthDat', value: '1985-03-12' },
                ]),
            ],
            names,
            new Set(),
        )
        expect(columns.attributes.map((column) => column.attributeUid)).toEqual(['TeaBirthDat', 'TeaHousehld'])
    })

    it('gives every page of a walk the same columns in the same order', () => {
        // WHY THIS IS THE CLAIM. The columns are derived from the rows on the page, and no two
        // pages of a real instance hold their attributes in the same order - so an order taken off
        // first appearance reshuffles the header on every press of Next, and a reader compares a
        // value under a header that has moved. Both pages below hold the same three attributes,
        // written in different orders, and one row on the second holds them all.
        const header = (rows: ReturnType<typeof row>[]): string[] =>
            registerTableColumns(rows, names, new Set(['TeaBirthDat'])).attributes.map(
                (column) => column.attributeUid,
            )
        const first = header([
            row('TeiPerson001', [
                { attributeUid: 'TeaSex00001', value: 'OpFemale001' },
                { attributeUid: 'TeaBirthDat', value: '1985-03-12' },
                { attributeUid: 'TeaHousehld', value: '4' },
            ]),
        ])
        const second = header([
            row('TeiPerson002', [
                { attributeUid: 'TeaHousehld', value: '6' },
                { attributeUid: 'TeaSex00001', value: 'OpMale00001' },
            ]),
            row('TeiPerson003', [{ attributeUid: 'TeaBirthDat', value: '1991-07-04' }]),
        ])
        expect(first).toEqual(['TeaBirthDat', 'TeaHousehld', 'TeaSex00001'])
        expect(second).toEqual(first)
    })

    it('sorts an attribute the guide published nothing for after every one it did, by uid', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [
                    { attributeUid: 'TeaZebra0001', value: 'z' },
                    { attributeUid: 'TeaAlpha0001', value: 'a' },
                    { attributeUid: 'TeaSex00001', value: 'OpFemale001' },
                ]),
            ],
            names,
            new Set(),
        )
        expect(columns.attributes.map((column) => column.attributeUid)).toEqual([
            'TeaSex00001',
            'TeaAlpha0001',
            'TeaZebra0001',
        ])
    })

    it('stops at the cap and says how many attributes it is not showing', () => {
        const many = Array.from({ length: 8 }, (_, index) => ({
            attributeUid: `TeaValue000${String(index)}`,
            value: String(index),
        }))
        const columns = registerTableColumns([row('TeiPerson001', many)], names, new Set())
        expect(columns.attributes).toHaveLength(REGISTER_ATTRIBUTE_COLUMNS)
        expect(columns.hidden).toBe(8 - REGISTER_ATTRIBUTE_COLUMNS)
    })

    it('cuts the ones DHIS2 states no preference for first, whatever order they arrived in', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [
                    { attributeUid: 'TeaHousehld', value: '4' },
                    { attributeUid: 'TeaBirthDat', value: '1985-03-12' },
                ]),
            ],
            names,
            new Set(['TeaBirthDat']),
            1,
        )
        expect(columns.attributes.map((column) => column.attributeUid)).toEqual(['TeaBirthDat'])
        expect(columns.hidden).toBe(1)
    })

    it('names a column the guide published nothing for by the DHIS2 code, and spells it as one', () => {
        const columns = registerTableColumns(
            [row('TeiPerson001', [{ attributeUid: 'TeaLabRef01', attributeCode: 'TEA_LAB_REF', value: 'LAB-1' }])],
            names,
            new Set(),
        )
        expect(columns.attributes[0].name).toEqual({ text: 'TEA_LAB_REF', isMachineSpelling: true })
    })

    it('takes the code off a later row when the first row carried none', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [{ attributeUid: 'TeaLabRef01', value: 'LAB-1' }]),
                row('TeiPerson002', [
                    { attributeUid: 'TeaLabRef01', attributeCode: 'TEA_LAB_REF', value: 'LAB-2' },
                ]),
            ],
            names,
            new Set(),
        )
        expect(columns.attributes[0].name.text).toBe('TEA_LAB_REF')
    })

    it('draws the identifier column when a row on the page carries an identifier value', () => {
        const columns = registerTableColumns(
            [
                row('TeiPerson001', [], [{ attributeUid: 'TeaNationId', value: '19850312-4471' }]),
                row('TeiPerson002', []),
            ],
            names,
            new Set(),
        )
        expect(columns.identifiers).toBe(true)
    })

    it('omits it entirely when no row does', () => {
        // The instance whose type declares no unique attribute: a leading column of dashes on every
        // row states nothing about the records and reads as a defect in the page.
        const columns = registerTableColumns([row('TeiPerson001', []), row('TeiPerson002', [])], names, new Set())
        expect(columns.identifiers).toBe(false)
    })

    it('omits it on an empty page too, and asks for no columns at all', () => {
        expect(registerTableColumns([], names, new Set())).toEqual({ identifiers: false, attributes: [], hidden: 0 })
    })

    it('reads one row’s value of one column, and says nothing where the instance holds none', () => {
        const entity = row('TeiPerson001', [{ attributeUid: 'TeaBirthDat', value: '1985-03-12' }])
        expect(registerAttributeValue(entity, 'TeaBirthDat')).toBe('1985-03-12')
        expect(registerAttributeValue(entity, 'TeaHousehld')).toBeNull()
    })
})
