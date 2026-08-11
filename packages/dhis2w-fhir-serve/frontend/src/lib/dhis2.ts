/**
 * Links from a published identity back to the DHIS2 object it was generated from.
 *
 * WHAT THIS SOLVES. Every identity on these pages is a DHIS2 uid: a Location is an organisation
 * unit, a Questionnaire is a data set, a program, or one of its stages, a concept of the data
 * dictionary is a data element. Reading one here answers "what did the guide publish", and the very
 * next question is "what does the instance hold", which until now meant copying eleven characters
 * into a search box. The address of the instance comes from `/uiconfig` - the profile this serve
 * run resolved - so the links exist exactly when the server knows which instance to point at, and
 * not at all when it does not.
 *
 * WHY THE MAINTENANCE APP. It is the one screen in DHIS2 that opens a single metadata object by uid
 * on a stable, bookmarkable route, and it has carried the same route on every major this toolchain
 * supports (v41, v42, v43). On 2.43 the app itself is served through the global shell - the path
 * below redirects to `/apps/maintenance` carrying its own fragment along - and shows a banner
 * pointing at the newer Metadata Management app, which has no by-uid route of its own to link to.
 *
 * THE ROUTE, VERIFIED AGAINST A RUNNING 2.43.1 INSTANCE, is
 * `{base}/dhis-web-maintenance/index.html#/edit/{section}/{type}/{uid}` - each of the four pairs
 * below opened the named object's own edit form.
 *
 * Pure, like the rest of lib/: a base url, a kind, and a uid in; a string or null out. Null is what
 * every caller renders as "no link", which is the state a server with no resolved profile puts the
 * whole app in.
 */

import { formTypeOf, dataSetOf, programOf, programStageOf, type CodeSystem, type Questionnaire } from '@/lib/fhir'

/** The Maintenance app's entry point, under a DHIS2 instance's base url. */
export const MAINTENANCE_APP_PATH = '/dhis-web-maintenance/index.html'

/** The kinds of DHIS2 object this UI holds a uid for and can open in Maintenance. */
export type MaintenanceObject = 'organisationUnit' | 'dataSet' | 'program' | 'programStage' | 'dataElement'

/**
 * Which Maintenance section owns each kind.
 *
 * A program stage is edited inside the program section rather than one of its own, which is the one
 * pair that does not read off the type's own name.
 */
const MAINTENANCE_SECTIONS: Record<MaintenanceObject, string> = {
    organisationUnit: 'organisationUnitSection',
    dataSet: 'dataSetSection',
    program: 'programSection',
    programStage: 'programSection',
    dataElement: 'dataElementSection',
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
 * One object's page in a DHIS2 instance's Maintenance app, or null when there is nothing to open.
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
    return `${root}${MAINTENANCE_APP_PATH}#/edit/${MAINTENANCE_SECTIONS[object]}/${object}/${uid.trim()}`
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
