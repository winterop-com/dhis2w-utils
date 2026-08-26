import { describe, expect, it } from 'vitest'

import codeSystemFixture from '@/lib/__fixtures__/codesystem-d2-de-cs.json'
import questionnaireFixture from '@/lib/__fixtures__/questionnaire-TuL8IOPzpHh.json'
import { captureEnrollmentUrl, holdsDataElementConcepts, maintenanceTargetOf, maintenanceUrl } from '@/lib/dhis2'
import type { CodeSystem, Questionnaire } from '@/lib/fhir'
import type { PatientEnrollment } from '@/lib/patients'

/**
 * The route out of the guide and into the instance it came from.
 *
 * WHY THESE ARE UNIT TESTS AND NOT ONLY BROWSER ONES. The five routes below were driven against a
 * running DHIS2 2.43.2 on 2026-08-26 - each opened the named object's own edit form, headed
 * "Edit: <the object's name>" - and what these hold is that the strings the app builds are still
 * those routes. A browser test can prove a link is rendered and where it points; only the instance
 * can prove the route resolves, and it did:
 *
 * - `#/dataElements/fbfJHSPpUQD` opened "Edit: ANC 1st visit"
 * - `#/dataSets/BfMAe6Itzgt` opened "Edit: Child Health"
 * - `#/programs/IpHINAT79UW` opened "Edit: Child Programme"
 * - `#/programStages/A03MvHHogjR` opened "Edit: Birth"
 * - `#/organisationUnits/Rp268JB6Ne4` opened "Edit: Adonkia CHP"
 */

const INSTANCE = 'https://play.example.org/dhis'

/** One aggregate form as the goldens publish it, so the identifier join is the real wire shape. */
const AGGREGATE = questionnaireFixture as unknown as Questionnaire

describe('a Metadata Management app url', () => {
    const APP = `${INSTANCE}/dhis-web-metadata-management/index.html`

    it('opens each kind of object in the collection that owns it', () => {
        expect(maintenanceUrl(INSTANCE, 'organisationUnit', 'Rp268JB6Ne4')).toBe(
            `${APP}#/organisationUnits/Rp268JB6Ne4`,
        )
        expect(maintenanceUrl(INSTANCE, 'dataSet', 'BfMAe6Itzgt')).toBe(`${APP}#/dataSets/BfMAe6Itzgt`)
        expect(maintenanceUrl(INSTANCE, 'dataElement', 'DeAncDanger')).toBe(`${APP}#/dataElements/DeAncDanger`)
        // A program stage is edited on a route of its own rather than inside the program.
        expect(maintenanceUrl(INSTANCE, 'programStage', 'A03MvHHogjR')).toBe(
            `${APP}#/programStages/A03MvHHogjR`,
        )
        expect(maintenanceUrl(INSTANCE, 'program', 'IpHINAT79UW')).toBe(`${APP}#/programs/IpHINAT79UW`)
    })

    it('sends the shortest address that resolves, leaving the app to name the section it opens on', () => {
        // A data set settles on `?section=setup` and a program on `?section=programDetails` once the
        // app has read the object; neither belongs in a link, because neither is needed to get there.
        expect(maintenanceUrl(INSTANCE, 'dataSet', 'BfMAe6Itzgt')).not.toContain('section=')
        expect(maintenanceUrl(INSTANCE, 'program', 'IpHINAT79UW')).not.toContain('section=')
    })

    it('joins one slash to the instance however its address was written', () => {
        expect(maintenanceUrl('https://play.example.org/', 'program', 'lxAQ7Zs9VYR')).toBe(
            'https://play.example.org/dhis-web-metadata-management/index.html#/programs/lxAQ7Zs9VYR',
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

/**
 * The route out of the guide and into one person in the instance.
 *
 * VERIFIED THE SAME WAY THE MAINTENANCE ROUTES WERE: against a running DHIS2 2.43.1, by opening the
 * built address in a browser. `teiId` with `programId` and `enrollmentId` rendered that person's
 * enrollment dashboard; the same address without `orgUnitId` rendered it too, with the organisation
 * unit unselected and the event actions disabled, which is why the unit is sent whenever the
 * instance stated one. `teiId` alone resolved the person and then stopped on a program chooser -
 * a screen this project does not link to, because a link's own words name a record.
 */
describe('a Capture app url', () => {
    const enrollment: PatientEnrollment = {
        enrollment_uid: 'Ez7mSJ7lmp2',
        program_uid: 'IpHINAT79UW',
        program_name: 'Child programme',
        status: 'ACTIVE',
        active: true,
        enrolled_at: '2026-02-01T00:00:00Z',
        organisation_unit_uid: 'WZ8PTx8qQlE',
        organisation_unit_name: 'Saama MCHP',
    }

    it('opens the person on the enrollment the row states, at the unit it was filed under', () => {
        expect(captureEnrollmentUrl(INSTANCE, 'q7X7Vqagb4P', enrollment)).toBe(
            `${INSTANCE}/dhis-web-capture/index.html#/enrollment` +
                '?teiId=q7X7Vqagb4P&programId=IpHINAT79UW&orgUnitId=WZ8PTx8qQlE&enrollmentId=Ez7mSJ7lmp2',
        )
    })

    it('still opens the dashboard for an enrollment the instance named no unit for', () => {
        expect(captureEnrollmentUrl(INSTANCE, 'q7X7Vqagb4P', { ...enrollment, organisation_unit_uid: null })).toBe(
            `${INSTANCE}/dhis-web-capture/index.html#/enrollment` +
                '?teiId=q7X7Vqagb4P&programId=IpHINAT79UW&enrollmentId=Ez7mSJ7lmp2',
        )
    })

    it('joins one slash to the instance however its address was written', () => {
        expect(captureEnrollmentUrl('https://play.example.org/dhis/', 'q7X7Vqagb4P', enrollment)).toContain(
            'https://play.example.org/dhis/dhis-web-capture/index.html#/enrollment?',
        )
    })

    it('links nowhere when there is nowhere honest to point', () => {
        // No instance is the ordinary state of a run that resolved no profile; no program is an
        // address Capture answers with a chooser rather than with this person's record.
        expect(captureEnrollmentUrl(null, 'q7X7Vqagb4P', enrollment)).toBeNull()
        expect(captureEnrollmentUrl('  ', 'q7X7Vqagb4P', enrollment)).toBeNull()
        expect(captureEnrollmentUrl(INSTANCE, '', enrollment)).toBeNull()
        expect(captureEnrollmentUrl(INSTANCE, 'q7X7Vqagb4P', { ...enrollment, program_uid: '' })).toBeNull()
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
