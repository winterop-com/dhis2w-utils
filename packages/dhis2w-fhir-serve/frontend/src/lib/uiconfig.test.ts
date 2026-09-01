import { describe, expect, it } from 'vitest'

import {
    capturesSubmissions,
    DEFAULT_UI_CONFIG,
    metadataHealthOffered,
    NO_REGISTER_OFFERED,
    PEOPLE_RESOURCE_TYPE,
    REGISTER_TITLE,
    registerChoices,
    registerResourceForSubjectType,
    registerSectionTitle,
    registerSubject,
    registerTitle,
    registerWords,
    servesPeopleOnly,
    subjectOfTypeName,
    trackedEntityRecordOffered,
    trackedEntitySettings,
    type TrackedEntitiesSettings,
    type UiConfig,
} from '@/lib/uiconfig'

/**
 * Which pages this run offers and what they are called, decided in one place.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. Every other setting `/facade/uiconfig` carries changes how a page
 * renders; this one decides whether a page is reachable at all and which subject it is about, and
 * the failures it guards against are a navigation entry that leads somewhere answering a refusal
 * and a screen calling a specimen batch a person. A live server always states the object - a
 * compiled run says `{enabled: false, listing: false, registers: []}` rather than leaving it out -
 * so every absent form here is a server nothing is known about, and the answer for all of them is
 * the same as for a server that stated it offers nothing.
 */

const settings = (tracked_entities: UiConfig['tracked_entities']): UiConfig => ({
    basemaps: [],
    dhis2_base_url: null,
    tracked_entities,
})

const PEOPLE_REGISTER = { resource: 'Patient', types: [{ uid: 'TetPerson01', name: 'Person' }] }
const SPECIMEN_REGISTER = { resource: 'Specimen', types: [{ uid: 'TetSample01', name: 'Specimen batch' }] }

describe('what a run offers about the instance it tracks', () => {
    it('offers the pages when the server says the routes are there', () => {
        expect(
            trackedEntitySettings(settings({ enabled: true, listing: true, registers: [PEOPLE_REGISTER] })),
        ).toEqual({ enabled: true, listing: true, registers: [PEOPLE_REGISTER] })
    })

    it('keeps the search and the listing as two separate offers', () => {
        // A deployment can answer a lookup by identifier value and decline to page through an
        // instance's whole set of tracked entities, which is a heavier thing to publish.
        expect(
            trackedEntitySettings(settings({ enabled: true, listing: false, registers: [PEOPLE_REGISTER] }))
                .listing,
        ).toBe(false)
    })

    it('offers nothing on a compiled run, which states the effective state rather than nothing', () => {
        expect(
            trackedEntitySettings(settings({ enabled: false, listing: false, registers: [] })).enabled,
        ).toBe(false)
    })

    it('offers nothing when the server stated nothing, however that came about', () => {
        // An older facade, a proxy that swallowed the path, or a read that failed and left the
        // defaults in place: three routes to the same state, and none of them is an offer.
        expect(trackedEntitySettings(settings(undefined)).enabled).toBe(false)
        expect(trackedEntitySettings(settings(null)).enabled).toBe(false)
        expect(trackedEntitySettings(DEFAULT_UI_CONFIG).enabled).toBe(false)
    })

    it('offers no listing wherever it offers no routes, because the listing is one of them', () => {
        expect(trackedEntitySettings(settings(null)).listing).toBe(false)
        expect(trackedEntitySettings(DEFAULT_UI_CONFIG).listing).toBe(false)
    })

    it('names no register at all wherever it offers none', () => {
        expect(trackedEntitySettings(settings(null)).registers).toEqual([])
        expect(trackedEntitySettings(DEFAULT_UI_CONFIG).registers).toEqual([])
    })
})

/** A register served as Patient over three types, two of which register nobody - the live shape. */
const MIXED_PATIENT_REGISTER = {
    resource: 'Patient',
    types: [
        { uid: 'nEenWmSyUEp', name: 'Person' },
        { uid: 'We9I19a3vO1', name: 'Focus area' },
        { uid: 'Zy2SEgA61ys', name: 'Malaria Entity' },
    ],
}

describe('who a register speaks about', () => {
    it('is people when every type riding it is a person', () => {
        expect(servesPeopleOnly({ enabled: true, listing: true, registers: [PEOPLE_REGISTER] })).toBe(true)
    })

    it('is not people the moment one type riding it registers something else', () => {
        expect(
            servesPeopleOnly({ enabled: true, listing: true, registers: [PEOPLE_REGISTER, SPECIMEN_REGISTER] }),
        ).toBe(false)
    })

    it('is not people because the resource is Patient, which is a projection rather than a subject', () => {
        // The live shape: a Focus area and a Malaria Entity served as Patient beside the people.
        // Reading person-hood off the resource string put "one person is one tracked entity" over
        // eleven villages.
        expect(servesPeopleOnly({ enabled: true, listing: true, registers: [MIXED_PATIENT_REGISTER] })).toBe(
            false,
        )
    })

    it('is nobody in particular on a run serving no register, which speaks about nothing', () => {
        expect(servesPeopleOnly({ enabled: false, listing: false, registers: [] })).toBe(false)
    })

    it('speaks as one type by the name the instance holds when the register is narrowed to it', () => {
        expect(registerSubject(MIXED_PATIENT_REGISTER, 'We9I19a3vO1')).toEqual({
            kind: 'type',
            name: 'Focus area',
        })
        expect(registerSubject(MIXED_PATIENT_REGISTER, 'nEenWmSyUEp')).toEqual({ kind: 'people' })
    })

    it('speaks as tracked entities over a union it cannot name with one name', () => {
        expect(registerSubject(MIXED_PATIENT_REGISTER, null)).toEqual({ kind: 'tracked-entities' })
    })

    it('speaks as tracked entities over a type the guide published no name for', () => {
        expect(registerSubject({ resource: 'Patient', types: [{ uid: 'TetFridge01', name: null }] }, null)).toEqual(
            { kind: 'tracked-entities' },
        )
    })

    it('narrows to nothing on a type this register is not served over', () => {
        expect(registerSubject(PEOPLE_REGISTER, 'TetSample01')).toEqual({ kind: 'tracked-entities' })
    })
})

describe('the words a register speaks with', () => {
    it('says person and people where the subject is people', () => {
        const words = registerWords({ kind: 'people' })
        expect(words.one).toBe('person')
        expect(words.empty).toBe('This DHIS2 instance holds nobody.')
        expect(words.missing).toBe('This DHIS2 instance holds nobody under that tracked entity UID.')
        expect(words.paging(1, 2)).toBe('Showing 1 of 2 people this DHIS2 instance holds as tracked entities.')
    })

    it('says the name the instance holds where the subject is one type, and never pluralises it', () => {
        const words = registerWords({ kind: 'type', name: 'Focus area' })
        expect(words.one).toBe('Focus area')
        expect(words.empty).toBe('This DHIS2 instance holds no Focus area.')
        expect(words.declined).toContain('a search for one Focus area')
        // The plural falls on DHIS2's own word, because guessing at the morphology of a name that
        // may be in any language is the thing this project does not do.
        expect(words.paging(11, 11)).toBe(
            'Showing 11 of 11 Focus area tracked entities this DHIS2 instance holds.',
        )
    })

    it('says tracked entity where it cannot say anything more specific', () => {
        const words = registerWords({ kind: 'tracked-entities' })
        expect(words.one).toBe('tracked entity')
        expect(words.paging(25, null)).toBe('Showing 25 tracked entities. This DHIS2 instance stated no total.')
    })

    it('words one type by its name whatever a screen holds it as', () => {
        // The detail page resolves one type and words itself from that, so the listing narrowed to
        // Focus area and the record of one Focus area say the same word.
        expect(registerWords(subjectOfTypeName('Focus area')).one).toBe('Focus area')
        expect(registerWords(subjectOfTypeName('Person')).one).toBe('person')
        expect(registerWords(subjectOfTypeName(null)).one).toBe('tracked entity')
    })
})

describe('what the register is called', () => {

    it('titles a section with the names the instance holds, never the FHIR resource type', () => {
        expect(registerSectionTitle(SPECIMEN_REGISTER)).toBe('Specimen batch')
        expect(
            registerSectionTitle({
                resource: 'Group',
                types: [
                    { uid: 'TetHouseh01', name: 'Household' },
                    { uid: 'TetHerd0001', name: 'Herd' },
                ],
            }),
        ).toBe('Household, Herd')
    })

    it('falls back to the uid for a type the guide published no name for', () => {
        expect(registerSectionTitle({ resource: 'Patient', types: [{ uid: 'TetPerson01', name: null }] })).toBe(
            'TetPerson01',
        )
    })
})

/**
 * What the register is called, which is the one name the navigation and the page both read.
 *
 * The rule names the actual subject: DHIS2 holds a name for each type it tracks, and that name is
 * what the people running the server say. It beats "Tracked entities", which is DHIS2's word for the
 * whole family rather than for this one, and it beats "Patients", which is the FHIR resource this
 * project projects a person onto - a projection stated as though it were the subject.
 */
describe('what the register is called on this run', () => {
    it('takes the instance`s own name for the one type it serves', () => {
        expect(registerTitle({ enabled: true, listing: true, registers: [PEOPLE_REGISTER] })).toBe('Person')
        expect(registerTitle({ enabled: true, listing: true, registers: [SPECIMEN_REGISTER] })).toBe(
            'Specimen batch',
        )
    })

    it('uses the name as DHIS2 spells it, in whatever language the instance holds it', () => {
        // Never pluralised and never rewritten: turning "Personne" into anything else means
        // guessing at a string this project did not write.
        expect(
            registerTitle({
                enabled: true,
                listing: true,
                registers: [{ resource: 'Patient', types: [{ uid: 'TetPerson01', name: 'Personne' }] }],
            }),
        ).toBe('Personne')
    })

    it('is the register itself once more than one type rides, whichever resources they ride', () => {
        expect(
            registerTitle({
                enabled: true,
                listing: true,
                registers: [PEOPLE_REGISTER, SPECIMEN_REGISTER],
            }),
        ).toBe(REGISTER_TITLE)
        expect(
            registerTitle({
                enabled: true,
                listing: true,
                registers: [
                    {
                        resource: 'Patient',
                        types: [
                            { uid: 'TetPerson01', name: 'Person' },
                            { uid: 'TetMidwif01', name: 'Midwife' },
                        ],
                    },
                ],
            }),
        ).toBe(REGISTER_TITLE)
    })

    it('is the register for a type the guide published no name for, and for a run serving none', () => {
        expect(
            registerTitle({
                enabled: true,
                listing: true,
                registers: [{ resource: 'Patient', types: [{ uid: 'TetPerson01', name: null }] }],
            }),
        ).toBe(REGISTER_TITLE)
        expect(registerTitle({ enabled: false, listing: false, registers: [] })).toBe(REGISTER_TITLE)
    })
})

describe('whether this server takes what a form was filled in with', () => {
    it('receives when the server says so, and does not when it says not', () => {
        expect(capturesSubmissions({ ...DEFAULT_UI_CONFIG, capture: true })).toBe(true)
        expect(capturesSubmissions({ ...DEFAULT_UI_CONFIG, capture: false })).toBe(false)
    })

    it('reads an unstated setting as receiving, which is the opposite of the register default', () => {
        // The opposite reading, on purpose: a page the register does not offer is a page nobody
        // misses, while withholding Submit because a settings read did not answer would take away
        // the one thing these screens exist to do - over a fact this app does not have.
        expect(capturesSubmissions(DEFAULT_UI_CONFIG)).toBe(true)
        expect(capturesSubmissions({ basemaps: [], dhis2_base_url: null })).toBe(true)
    })
})

/**
 * Which register a form's subject lives in, when the form itself does not say.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. The answer is what the search gate asks the conformance
 * document about, and a wrong answer is invisible on a deployment that serves people: `Patient`
 * happens to be right there. It is wrong everywhere else, and the failure it produces is a search
 * control that never appears on a run that would have answered a search perfectly well.
 */
/** The served set of a run, in the shape `/facade/uiconfig` states it. */
const serving = (...resources: string[]): TrackedEntitiesSettings => ({
    enabled: resources.length > 0,
    listing: true,
    registers: resources.map((resource) => ({ resource, types: [] })),
})

describe('the register a form registers into', () => {
    it('is what the form names, whatever the run happens to serve', () => {
        expect(registerResourceForSubjectType('Specimen', serving('Patient'))).toBe('Specimen')
        expect(registerResourceForSubjectType('Patient', serving('Specimen', 'Device'))).toBe('Patient')
    })

    it('is the one register a run serves, for a form naming no subject', () => {
        expect(registerResourceForSubjectType(undefined, serving('Specimen'))).toBe('Specimen')
        expect(registerResourceForSubjectType(undefined, serving('Device'))).toBe('Device')
    })

    it('is the unnamed-type default where a run serves several, since no first one is a better guess', () => {
        expect(registerResourceForSubjectType(undefined, serving('Specimen', 'Device'))).toBe(
            PEOPLE_RESOURCE_TYPE,
        )
    })

    it('is the unnamed-type default where a run serves no register at all', () => {
        expect(registerResourceForSubjectType(undefined, NO_REGISTER_OFFERED)).toBe(PEOPLE_RESOURCE_TYPE)
    })
})

/** A run stating only what it says about the metadata behind its guide. */
const withHealth = (metadata_health: UiConfig['metadata_health']): UiConfig => ({
    basemaps: [],
    dhis2_base_url: null,
    tracked_entities: null,
    metadata_health,
})

describe('whether this run can report on the metadata behind its guide', () => {
    it('offers the page when the server says it reaches an instance', () => {
        expect(metadataHealthOffered(withHealth({ enabled: true }))).toBe(true)
    })

    it('offers nothing on a compiled run, which states the effective state rather than nothing', () => {
        expect(metadataHealthOffered(withHealth({ enabled: false }))).toBe(false)
    })

    it('reads a server that stated nothing as a server with no instance behind it', () => {
        // A live server always states the object, so silence is a read that failed or something in
        // front of this server swallowing `/facade/uiconfig` - and an entry offered on a guess would lead
        // to a page with nothing on it.
        expect(metadataHealthOffered(withHealth(null))).toBe(false)
        expect(metadataHealthOffered(DEFAULT_UI_CONFIG)).toBe(false)
    })
})

/**
 * Whether one tracked entity's own record is answered, and which registers one can be picked out of.
 *
 * WHY THESE TWO ARE WORTH A TEST OF THEIR OWN. Both decide whether a control exists rather than how
 * it renders, and each guards a failure that has to be prevented ahead of the request: a picker on a
 * run that answers no record is a picker whose every choice ends in a refusal, and a picker over one
 * hard-wired register cannot reach a specimen batch on an instance that tracks several kinds.
 */
describe('whether this run answers one tracked entity’s own record', () => {
    it('answers it where the server serves the register and answers the events', () => {
        expect(
            trackedEntityRecordOffered({
                enabled: true,
                listing: true,
                events: true,
                registers: [PEOPLE_REGISTER],
            }),
        ).toBe(true)
    })

    it('keeps the record and the register as two separate offers', () => {
        // A deployment can answer who somebody is and decline to answer what they have been
        // through, which is what `[serve.tracked_entities] events = false` says.
        expect(
            trackedEntityRecordOffered({
                enabled: true,
                listing: true,
                events: false,
                registers: [PEOPLE_REGISTER],
            }),
        ).toBe(false)
    })

    it('answers none on a run serving no register, since a record is read under a tracked entity', () => {
        expect(
            trackedEntityRecordOffered({ enabled: false, listing: false, events: true, registers: [] }),
        ).toBe(false)
    })

    it('reads a server that stated nothing as a server answering no record', () => {
        expect(
            trackedEntityRecordOffered({ enabled: true, listing: true, registers: [PEOPLE_REGISTER] }),
        ).toBe(false)
        expect(trackedEntityRecordOffered(trackedEntitySettings(DEFAULT_UI_CONFIG))).toBe(false)
        expect(trackedEntityRecordOffered(NO_REGISTER_OFFERED)).toBe(false)
    })
})

describe('the registers a tracked entity is picked out of', () => {
    it('offers the one a person-only run serves, which is nothing to choose between', () => {
        expect(
            registerChoices({ enabled: true, listing: true, events: true, registers: [PEOPLE_REGISTER] }),
        ).toEqual([{ resource: 'Patient', label: 'Person', subject: { kind: 'people' } }])
    })

    it('offers one per served resource where the instance tracks several kinds', () => {
        const choices = registerChoices({
            enabled: true,
            listing: true,
            events: true,
            registers: [PEOPLE_REGISTER, SPECIMEN_REGISTER],
        })

        expect(choices.map((choice) => choice.resource)).toEqual(['Patient', 'Specimen'])
        // Named the way the instance names the types riding each register, never by the FHIR
        // resource the guide projects them onto.
        expect(choices.map((choice) => choice.label)).toEqual(['Person', 'Specimen batch'])
        expect(choices[1].subject).toEqual({ kind: 'type', name: 'Specimen batch' })
    })

    it('names a register over several types by every one of them, and speaks of none of them', () => {
        const choices = registerChoices({
            enabled: true,
            listing: true,
            events: true,
            registers: [
                {
                    resource: 'Patient',
                    types: [
                        { uid: 'TetPerson01', name: 'Person' },
                        { uid: 'TetFocusAr1', name: 'Focus area' },
                    ],
                },
            ],
        })

        expect(choices[0].label).toBe('Person, Focus area')
        // One of the two types is a place, so the control cannot be worded for people without
        // calling a focus area somebody.
        expect(choices[0].subject).toEqual({ kind: 'tracked-entities' })
    })

    it('falls back to the register where the guide published no name for what rides it', () => {
        expect(
            registerChoices({
                enabled: true,
                listing: true,
                events: true,
                registers: [{ resource: 'Patient', types: [] }],
            })[0].label,
        ).toBe(REGISTER_TITLE)
    })

    it('offers none at all where the run serves no register', () => {
        expect(registerChoices(NO_REGISTER_OFFERED)).toEqual([])
        expect(registerChoices(trackedEntitySettings(DEFAULT_UI_CONFIG))).toEqual([])
    })
})
