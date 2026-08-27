/**
 * Links from a published identity back to the DHIS2 object it was generated from.
 *
 * WHAT THIS SOLVES. Every identity on these pages is a DHIS2 uid: a Location is an organisation
 * unit, a Questionnaire is a data set, a program, or one of its stages, a concept of the data
 * dictionary is a data element. Reading one here answers "what did the guide publish", and the very
 * next question is "what does the instance hold", which until now meant copying eleven characters
 * into a search box. The address of the instance comes from `/facade/uiconfig` - the profile this serve
 * run resolved - so the links exist exactly when the server knows which instance to point at, and
 * not at all when it does not.
 *
 * WHY THE METADATA MANAGEMENT APP. It is the one screen in DHIS2 that opens a single metadata object
 * by uid on a stable, bookmarkable route, and it is the app the platform now ships for the job: the
 * older Maintenance app it replaces is no longer listed in `/api/apps` on 2.43 at all, and the
 * screens still reachable there banner themselves as no longer maintained.
 *
 * THE ROUTE, VERIFIED AGAINST A RUNNING 2.43.2 INSTANCE ON 2026-08-26, is
 * `{base}/dhis-web-metadata-management/index.html#/{collection}/{uid}` - the collection is the
 * plural the app's own menu uses, and each of the five below opened the named object's own edit
 * form. The path redirects into the global shell as `/apps/metadata-management` carrying its own
 * fragment along, and the app then appends whichever section it opens on - a data set arrives at
 * `?section=setup`, a program at `?section=programDetails`, a program stage at `?section=stageSetup`
 * - so the address sent is the shortest one that resolves, not the one the app settles on.
 *
 * WHY A PERSON GOES SOMEWHERE ELSE. A tracked entity is not metadata - the metadata screens have no
 * page for one - so a person opens in the Capture app instead, on the enrollment dashboard that app
 * is built around. That is the one other link this module makes, and `captureEnrollmentUrl` argues
 * its own shape.
 *
 * Pure, like the rest of lib/: a base url, a kind, and a uid in; a string or null out. Null is what
 * every caller renders as "no link", which is the state a server with no resolved profile puts the
 * whole app in.
 */

import { formTypeOf, dataSetOf, programOf, programStageOf, type CodeSystem, type Questionnaire } from '@/lib/fhir'
import type { PatientEnrollment } from '@/lib/patients'

/** The Metadata Management app's entry point, under a DHIS2 instance's base url. */
export const METADATA_MANAGEMENT_APP_PATH = '/dhis-web-metadata-management/index.html'

/**
 * The Capture app's entry point, under a DHIS2 instance's base url.
 *
 * The bundled-app path rather than `/apps/capture`, and deliberately: on 2.43 this redirects into
 * the global shell carrying its own fragment along, which the shell then forwards into the app - so
 * one spelling works across the majors this toolchain supports, as the metadata path does too.
 */
export const CAPTURE_APP_PATH = '/dhis-web-capture/index.html'

/** The kinds of DHIS2 object this UI holds a uid for and can open in Metadata Management. */
export type MaintenanceObject = 'organisationUnit' | 'dataSet' | 'program' | 'programStage' | 'dataElement'

/**
 * Which collection of the Metadata Management app owns each kind.
 *
 * Every one is the plural of the type's own name, including a program stage: the app edits a stage
 * on a route of its own rather than inside the program that holds it.
 */
const METADATA_MANAGEMENT_COLLECTIONS: Record<MaintenanceObject, string> = {
    organisationUnit: 'organisationUnits',
    dataSet: 'dataSets',
    program: 'programs',
    programStage: 'programStages',
    dataElement: 'dataElements',
}

/** How each kind is named in the words of a link, so an accessible name says what it opens. */
export const MAINTENANCE_OBJECT_LABELS: Record<MaintenanceObject, string> = {
    organisationUnit: 'organisation unit',
    dataSet: 'data set',
    program: 'program',
    programStage: 'program stage',
    dataElement: 'data element',
}

/**
 * The suffix of the FHIR id under which the emitter publishes its data-element dictionary.
 *
 * `NamingConfig.data_element_code_system_id` joins the project's own prefix with `de` and `cs`, so
 * a project keeping the default prefix publishes `d2-de-cs` and one with no prefix publishes
 * `de-cs`. Matching the suffix is what makes the concept rows of that one CodeSystem - and of no
 * other - readable as data element uids, whatever the project named itself.
 */
export const DATA_ELEMENT_CODE_SYSTEM_ID_SUFFIX = 'de-cs'

/**
 * One object's page in a DHIS2 instance's Metadata Management app, or null when nothing to open.
 *
 * Null on a missing base url is the ordinary case rather than an error: a server that resolved no
 * profile states so, and every caller renders no link at all instead of a link that goes nowhere.
 */
export function maintenanceUrl(
    baseUrl: string | null,
    object: MaintenanceObject,
    uid: string | null,
): string | null {
    if (baseUrl === null || baseUrl.trim() === '') return null
    if (uid === null || uid.trim() === '') return null
    const root = baseUrl.trim().replace(/\/+$/, '')
    return `${root}${METADATA_MANAGEMENT_APP_PATH}#/${METADATA_MANAGEMENT_COLLECTIONS[object]}/${uid.trim()}`
}

/**
 * One person's enrollment dashboard in a DHIS2 instance's Capture app, or null when there is none.
 *
 * WHY THIS IS SCOPED TO AN ENROLLMENT RATHER THAN TO THE PERSON. A tracked entity uid on its own is
 * a valid Capture address and Capture does resolve the person from it - and then stops on "Choose a
 * program", because the dashboard it renders is a dashboard of one enrollment. So a link with no
 * program on it opens a chooser rather than a record, and this project does not publish one: every
 * link it offers opens the thing its own words name. The enrollment listing carries all three
 * parameters, so a link per enrollment is what there is to give.
 *
 * VERIFIED AGAINST A RUNNING 2.43.1 INSTANCE. `#/enrollment?teiId=&programId=&orgUnitId=&enrollmentId=`
 * rendered the person's dashboard with the organisation unit selected and the event actions live.
 * The organisation unit is not part of what Capture requires to render, but a dashboard opened
 * without one has its create and schedule actions disabled - so it is sent whenever the instance
 * stated it, and a link that omits it is still a working dashboard.
 */
export function captureEnrollmentUrl(
    baseUrl: string | null,
    trackedEntityUid: string,
    enrollment: PatientEnrollment,
): string | null {
    if (baseUrl === null || baseUrl.trim() === '') return null
    if (trackedEntityUid.trim() === '' || enrollment.program_uid.trim() === '') return null
    const root = baseUrl.trim().replace(/\/+$/, '')
    const parameters = new URLSearchParams({
        teiId: trackedEntityUid.trim(),
        programId: enrollment.program_uid.trim(),
    })
    if (enrollment.organisation_unit_uid !== null && enrollment.organisation_unit_uid !== '') {
        parameters.set('orgUnitId', enrollment.organisation_unit_uid)
    }
    parameters.set('enrollmentId', enrollment.enrollment_uid)
    return `${root}${CAPTURE_APP_PATH}#/enrollment?${parameters.toString()}`
}

/** The DHIS2 object one served form was generated from, or null when it names none. */
export function maintenanceTargetOf(
    questionnaire: Questionnaire,
): { object: MaintenanceObject; uid: string } | null {
    const kind = formTypeOf(questionnaire)
    if (kind === 'aggregate') {
        const uid = dataSetOf(questionnaire)
        return uid === null ? null : { object: 'dataSet', uid }
    }
    if (kind === 'tracker-event') {
        const uid = programStageOf(questionnaire)
        return uid === null ? null : { object: 'programStage', uid }
    }
    if (kind === 'event' || kind === 'tracker') {
        const uid = programOf(questionnaire)
        return uid === null ? null : { object: 'program', uid }
    }
    return null
}

/**
 * Whether a served CodeSystem's concept codes are DHIS2 data element uids.
 *
 * The one vocabulary in a generated guide whose codes are data elements is the data dictionary,
 * and the guide names it by rule rather than by declaration - so this is that rule, read back. A
 * vocabulary of option uids, category option combos, or tracked entity attributes answers false,
 * and its concept rows link nowhere, which is the honest outcome: those objects are edited on
 * screens this UI holds no route for.
 */
export function holdsDataElementConcepts(codeSystem: CodeSystem): boolean {
    const id = codeSystem.id ?? ''
    return id === DATA_ELEMENT_CODE_SYSTEM_ID_SUFFIX || id.endsWith(`-${DATA_ELEMENT_CODE_SYSTEM_ID_SUFFIX}`)
}
