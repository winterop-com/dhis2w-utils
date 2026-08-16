import { describe, expect, it } from 'vitest'

import {
    capturesSubmissions,
    DEFAULT_UI_CONFIG,
    REGISTER_TITLE,
    registerSectionTitle,
    registerTitle,
    servesPeopleOnly,
    trackedEntitySettings,
    type UiConfig,
} from '@/lib/uiconfig'

/**
 * Which pages this run offers and what they are called, decided in one place.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. Every other setting `/uiconfig` carries changes how a page
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

describe('what the register is called', () => {
    it('is people alone when every served resource is Patient', () => {
        expect(servesPeopleOnly({ enabled: true, listing: true, registers: [PEOPLE_REGISTER] })).toBe(true)
    })

    it('is not people alone the moment one served resource is something else', () => {
        expect(
            servesPeopleOnly({ enabled: true, listing: true, registers: [PEOPLE_REGISTER, SPECIMEN_REGISTER] }),
        ).toBe(false)
    })

    it('counts a run serving no register as people alone, since it names no page either way', () => {
        expect(servesPeopleOnly({ enabled: false, listing: false, registers: [] })).toBe(true)
    })

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
        // Never pluralised and never rewritten: turning "Person (Play)" into anything else means
        // guessing at a string this project did not write.
        expect(
            registerTitle({
                enabled: true,
                listing: true,
                registers: [{ resource: 'Patient', types: [{ uid: 'TetPerson01', name: 'Person (Play)' }] }],
            }),
        ).toBe('Person (Play)')
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
