import { describe, expect, it } from 'vitest'

import registrationFixture from '@/lib/__fixtures__/questionnaire-PrAncCare01.json'
import scopedFixture from '@/lib/__fixtures__/questionnaire-PrScoped001.json'
import temporalFixture from '@/lib/__fixtures__/questionnaire-PrTemporal1.json'
import attributeComboFormFixture from '@/lib/__fixtures__/questionnaire-TuL8IOPzpHh.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import { catalogueForms, isEventProgram } from '@/lib/catalogue'
import { bundleResources, formTitle, type Bundle, type Questionnaire } from '@/lib/fhir'

/**
 * The one grouping algorithm, checked against the forms the fixture project really serves.
 *
 * The served set below is the e2e fixture project's whole catalogue - the harvested bundle plus
 * the four individually harvested forms - which deliberately carries both tracker shapes: a
 * program with a published registration and a stage (`PrAncCare01`), and a program whose stage is
 * published alone (`IpHINAT79UW`). A grouping that keyed on anything but the program identifier,
 * or that guessed a registration where none is served, fails here before it misleads a page.
 */

const questionnaireBundle = questionnaireBundleFixture as unknown as Bundle<Questionnaire>
const registration = registrationFixture as unknown as Questionnaire
const scoped = scopedFixture as unknown as Questionnaire
const temporal = temporalFixture as unknown as Questionnaire
const attributeComboForm = attributeComboFormFixture as unknown as Questionnaire

/** Every form the fixture project serves, in an arbitrary order the fold must not depend on. */
const served: Questionnaire[] = [
    ...bundleResources(questionnaireBundle),
    scoped,
    temporal,
    attributeComboForm,
    registration,
]

describe('catalogueForms over the fixture project', () => {
    const catalog = catalogueForms(served)

    it('shelves the aggregate forms as data sets, in title order', () => {
        expect(catalog.dataSets.map(formTitle)).toEqual(['Child Health', 'EPI Stock'])
    })

    it('groups every program once, in title order', () => {
        expect(catalog.programs.map((group) => group.title)).toEqual([
            'Antenatal care',
            'Child Programme - Baby Postnatal',
            'Outbreak response',
            'Supervision visit',
            'Temporal capture',
        ])
    })

    it('tells the event programs from the tracker ones', () => {
        const kinds = Object.fromEntries(catalog.programs.map((group) => [group.title, isEventProgram(group)]))
        expect(kinds).toEqual({
            'Antenatal care': false,
            'Child Programme - Baby Postnatal': false,
            'Outbreak response': true,
            'Supervision visit': true,
            'Temporal capture': true,
        })
    })

    it('joins a registration and its stage on the program uid they both carry', () => {
        const ancCare = catalog.programs.find((group) => group.key === 'PrAncCare01')
        expect(ancCare?.registration?.id).toBe('PrAncCare01')
        expect(ancCare?.stages.map((stage) => stage.id)).toEqual(['PsAncVisit1'])
        expect(ancCare?.event).toBeNull()
        // Named by the registration, not by the stage that sorts first.
        expect(ancCare?.title).toBe('Antenatal care')
    })

    it('keeps a stage whose registration is not served, stating the absence as null', () => {
        const childProgramme = catalog.programs.find((group) => group.key === 'IpHINAT79UW')
        expect(childProgramme?.registration).toBeNull()
        expect(childProgramme?.stages.map((stage) => stage.id)).toEqual(['ZzYYXq4fJie'])
        // With no registration and no event form, the first stage names the program.
        expect(childProgramme?.title).toBe('Child Programme - Baby Postnatal')
    })

    it('keys an event program on its own program identifier, which is the form itself', () => {
        const supervision = catalog.programs.find((group) => group.title === 'Supervision visit')
        expect(supervision?.key).toBe('EVTsupVis01')
        expect(supervision?.event?.id).toBe('EVTsupVis01')
    })

    it('serves no unclassified form in this project', () => {
        expect(catalog.unclassified).toEqual([])
    })
})

/** A questionnaire built by hand, since the fixture project publishes only well-formed ones. */
const form = (overrides: Partial<Questionnaire>): Questionnaire => ({
    resourceType: 'Questionnaire',
    status: 'active',
    ...overrides,
})

/** The one canonical-rooted extension the fold reads the kind from. */
const kind = (code: string) => ({
    url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type',
    valueCode: code,
})

describe('catalogueForms edge shapes', () => {
    it('shelves a form declaring no kind as unclassified rather than guessing one', () => {
        const catalog = catalogueForms([form({ id: 'NoKind00001', title: 'Kindless' })])
        expect(catalog.unclassified.map(formTitle)).toEqual(['Kindless'])
        expect(catalog.dataSets).toEqual([])
        expect(catalog.programs).toEqual([])
    })

    it('sorts the stages of one program by title, whatever order they arrive in', () => {
        const stage = (id: string, title: string) =>
            form({
                id,
                title,
                extension: [kind('tracker-event')],
                identifier: [{ system: 'http://dhis2.org/fhir/id/program', value: 'PrProgram01' }],
            })
        const catalog = catalogueForms([stage('PsSecond001', 'Second visit'), stage('PsFirst0001', 'First visit')])
        const group = catalog.programs[0]
        expect(catalog.programs).toHaveLength(1)
        expect(group?.stages.map(formTitle)).toEqual(['First visit', 'Second visit'])
        expect(group !== undefined && isEventProgram(group)).toBe(false)
    })

    it('groups a stage naming no program under its own form id, so it is never dropped', () => {
        const catalog = catalogueForms([
            form({ id: 'PsOrphan001', title: 'Orphan stage', extension: [kind('tracker-event')] }),
        ])
        expect(catalog.programs.map((group) => group.key)).toEqual(['PsOrphan001'])
        expect(catalog.programs[0]?.title).toBe('Orphan stage')
    })

    it('answers an empty catalogue for a project publishing nothing', () => {
        expect(catalogueForms([])).toEqual({ dataSets: [], programs: [], unclassified: [] })
    })
})
