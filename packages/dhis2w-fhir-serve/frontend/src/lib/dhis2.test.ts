import { describe, expect, it } from 'vitest'

import codeSystemFixture from '@/lib/__fixtures__/codesystem-d2-de-cs.json'
import questionnaireFixture from '@/lib/__fixtures__/questionnaire-TuL8IOPzpHh.json'
import { holdsDataElementConcepts, maintenanceTargetOf, maintenanceUrl } from '@/lib/dhis2'
import type { CodeSystem, Questionnaire } from '@/lib/fhir'

/**
 * The route out of the guide and into the instance it came from.
 *
 * WHY THESE ARE UNIT TESTS AND NOT ONLY BROWSER ONES. The four routes below were checked by hand
 * against a running DHIS2 2.43.1 - each opened the named object's own edit form - and what these
 * hold is that the strings the app builds are still those routes. A browser test can prove a link
 * is rendered and where it points; only the instance can prove the route resolves, and it did.
 */

const INSTANCE = 'https://play.example.org/dhis'

/** One aggregate form as the goldens publish it, so the identifier join is the real wire shape. */
const AGGREGATE = questionnaireFixture as unknown as Questionnaire

describe('a Maintenance app url', () => {
    it('opens each kind of object in the section that owns it', () => {
        expect(maintenanceUrl(INSTANCE, 'organisationUnit', 'Rp268JB6Ne4')).toBe(
            `${INSTANCE}/dhis-web-maintenance/index.html#/edit/organisationUnitSection/organisationUnit/Rp268JB6Ne4`,
        )
        expect(maintenanceUrl(INSTANCE, 'dataSet', 'BfMAe6Itzgt')).toBe(
            `${INSTANCE}/dhis-web-maintenance/index.html#/edit/dataSetSection/dataSet/BfMAe6Itzgt`,
        )
        expect(maintenanceUrl(INSTANCE, 'dataElement', 'DeAncDanger')).toBe(
            `${INSTANCE}/dhis-web-maintenance/index.html#/edit/dataElementSection/dataElement/DeAncDanger`,
        )
        // A program stage is edited inside the program section rather than one of its own.
        expect(maintenanceUrl(INSTANCE, 'programStage', 'A03MvHHogjR')).toBe(
            `${INSTANCE}/dhis-web-maintenance/index.html#/edit/programSection/programStage/A03MvHHogjR`,
        )
    })

    it('joins one slash to the instance however its address was written', () => {
        expect(maintenanceUrl('https://play.example.org/', 'program', 'lxAQ7Zs9VYR')).toBe(
            'https://play.example.org/dhis-web-maintenance/index.html#/edit/programSection/program/lxAQ7Zs9VYR',
        )
    })

    it('is null when the server named no instance, which is what renders as no link at all', () => {
        expect(maintenanceUrl(null, 'dataSet', 'BfMAe6Itzgt')).toBeNull()
        expect(maintenanceUrl('   ', 'dataSet', 'BfMAe6Itzgt')).toBeNull()
    })

    it('is null when there is no uid to open, rather than a link to the section index', () => {
        expect(maintenanceUrl(INSTANCE, 'dataSet', null)).toBeNull()
        expect(maintenanceUrl(INSTANCE, 'dataSet', '')).toBeNull()
    })
})

describe('what DHIS2 object a served form was generated from', () => {
    it('reads an aggregate form as its data set, off the identifier the emitter writes', () => {
        expect(maintenanceTargetOf(AGGREGATE)).toEqual({ object: 'dataSet', uid: 'TuL8IOPzpHh' })
    })

    it('reads an event form and a registration form alike as their program', () => {
        expect(maintenanceTargetOf(form('event', '/id/program', 'EVTsupVis01'))).toEqual({
            object: 'program',
            uid: 'EVTsupVis01',
        })
        expect(maintenanceTargetOf(form('tracker', '/id/program', 'PrAncCare01'))).toEqual({
            object: 'program',
            uid: 'PrAncCare01',
        })
    })

    it('reads a stage form as its stage, not as the program it also names', () => {
        const stage = form('tracker-event', '/id/program-stage', 'PsAncVisit1')
        stage.identifier?.push({ system: 'http://dhis2.org/fhir/id/program', value: 'PrAncCare01' })

        expect(maintenanceTargetOf(stage)).toEqual({ object: 'programStage', uid: 'PsAncVisit1' })
    })

    it('is null for a form declaring no kind - the facade refuses to capture against it either', () => {
        expect(maintenanceTargetOf({ resourceType: 'Questionnaire', id: 'Unclassified', status: 'draft' })).toBeNull()
    })
})

describe('a code system whose concepts are data elements', () => {
    it('is the data dictionary, under whatever prefix the project named itself', () => {
        expect(holdsDataElementConcepts(codeSystemFixture as unknown as CodeSystem)).toBe(true)
        // `NamingConfig.prefix` may be empty, and then the id has no prefix segment at all.
        expect(holdsDataElementConcepts(codeSystem('de-cs'))).toBe(true)
    })

    it('is nothing else the guide publishes, so no other concept row links anywhere', () => {
        for (const id of ['d2-tea-cs', 'd2-coc-cs', 'd2-os-OsSymptom01-cs', 'd2-ou-cs', 'd2-ou-level-cs']) {
            expect(holdsDataElementConcepts(codeSystem(id)), id).toBe(false)
        }
    })
})

/** One form carrying a kind and the identifier that kind is joined on, in the emitter's shape. */
function form(kind: string, systemSuffix: string, uid: string): Questionnaire {
    return {
        resourceType: 'Questionnaire',
        id: uid,
        status: 'draft',
        extension: [
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: kind },
        ],
        identifier: [{ system: `http://dhis2.org/fhir${systemSuffix}`, value: uid }],
    }
}

/** One code system, reduced to the id the rule reads. */
function codeSystem(id: string): CodeSystem {
    return { resourceType: 'CodeSystem', id, status: 'draft' }
}
