/**
 * Shelving served forms by the DHIS2 capture model they came from.
 *
 * A flat list of Questionnaires mixes four different things: a data set is a periodic report for
 * an organisation unit, an event program records single events with no person involved, a tracker
 * program is one surface whose registration form enrols a person and whose stage forms record that
 * person's visits, and a person-only form registers a person in the instance without enrolling
 * them in anything. The fold here is the one grouping algorithm for that split - the Forms page
 * renders it as sections and the organisation-units rail renders it as shelves, and both read the
 * same catalogue so the two listings can never disagree about what a form is.
 *
 * Everything here is pure, like the rest of lib/: the kind comes off `formTypeOf` (the
 * `D2FormType` extension) and the program join off `programOf` (the `{base}/id/program`
 * identifier), both of which are the wire facts the guide publishes.
 */

import { formIdentifier, formsByTitle, formTitle, formTypeOf, programOf, type Questionnaire } from '@/lib/fhir'

/**
 * What the shelf of `tracked-entity` forms is called, and what it says these forms do.
 *
 * NOT "PEOPLE". DHIS2 tracks whatever a project tracks, and a `tracked-entity` form is generated
 * from a tracked entity type - which is a Person on one instance and a Focus area or a Malaria
 * Entity on the next, all three of them on the same instance in the ordinary case. A shelf headed
 * People listing two things that register nobody names half of what is under it. DHIS2's own word
 * for the family is the one that is true of all of them.
 *
 * The strings live here rather than in the screens because two screens shelve this same set - the
 * Forms page as a section, the organisation-units rail as a shelf - and a name kept in one of them
 * is a name the other can disagree with.
 */
export const TRACKED_ENTITY_FORM_SHELF = 'Tracked entity registration'

/** What that shelf says the forms on it do, at one organisation unit. */
export const TRACKED_ENTITY_FORM_SHELF_NOTE =
    'Registers a tracked entity here without enrolling it in a program.'

/** One program's published capture surface: registration and stages together, or its one event form. */
export interface ProgramGroup {
    /** The DHIS2 program uid, or the form's own id when it names no program. */
    key: string
    /** The program's name: its registration form's title, else its event form's, else its first stage's. */
    title: string
    registration: Questionnaire | null
    event: Questionnaire | null
    stages: Questionnaire[]
}

/** Served forms shelved by kind: data sets, programs, people, and the ones declaring no kind at all. */
export interface FormCatalog {
    /** Aggregate forms, in title order. */
    dataSets: Questionnaire[]
    /** Event and tracker programs as groups, in title order; `isEventProgram` tells the two apart. */
    programs: ProgramGroup[]
    /**
     * Registration forms of the `tracked-entity` kind, in title order - see `TRACKED_ENTITY_FORM_SHELF`.
     *
     * A shelf of its own, and honestly so: this form is generated from a DHIS2 tracked entity type
     * rather than from a data set or a program, and it names no program to group under. Folding it
     * into the tracker section would put a form that enrols nobody under a heading that says a
     * subject is enrolled once and then visited; folding it into data sets would say it is a
     * periodic report. It is neither, so it is its own thing.
     */
    people: Questionnaire[]
    /** Forms declaring no `D2FormType` - listed, not hidden, because the server refuses to capture against them. */
    unclassified: Questionnaire[]
}

/**
 * Shelve served forms by DHIS2 kind.
 *
 * A data set and a program are different capture surfaces, and a tracker program is one thing
 * whose registration and stage forms belong together - so the flat list is folded into a
 * catalogue, with the program grouping keyed on the program uid every tracker form carries.
 */
export function catalogueForms(questionnaires: Questionnaire[]): FormCatalog {
    const dataSets: Questionnaire[] = []
    const people: Questionnaire[] = []
    const unclassified: Questionnaire[] = []
    const groups = new Map<string, ProgramGroup>()
    const groupFor = (key: string): ProgramGroup => {
        const existing = groups.get(key)
        if (existing !== undefined) return existing
        const created: ProgramGroup = { key, title: key, registration: null, event: null, stages: [] }
        groups.set(key, created)
        return created
    }

    for (const questionnaire of questionnaires) {
        const kind = formTypeOf(questionnaire)
        if (kind === 'aggregate') dataSets.push(questionnaire)
        else if (kind === 'tracked-entity') people.push(questionnaire)
        else if (kind === null) unclassified.push(questionnaire)
        else {
            const group = groupFor(programOf(questionnaire) ?? formIdentifier(questionnaire))
            if (kind === 'event') group.event = questionnaire
            else if (kind === 'tracker') group.registration = questionnaire
            else group.stages.push(questionnaire)
        }
    }

    const programs = [...groups.values()]
    for (const group of programs) {
        // The program is named by its registration when one is published, by its event form
        // otherwise - the event form IS the program - and by its first stage as the last resort.
        const naming = group.registration ?? group.event ?? group.stages[0]
        if (naming !== undefined) group.title = formTitle(naming)
        group.stages = formsByTitle(group.stages)
    }
    programs.sort((left, right) => left.title.localeCompare(right.title))

    return {
        dataSets: formsByTitle(dataSets),
        programs,
        people: formsByTitle(people),
        unclassified: formsByTitle(unclassified),
    }
}

/**
 * Whether a program group is an event program: its one form, with no tracker surface beside it.
 *
 * The negative is a tracker program - anything with a registration or a stage - and the split is
 * worth a named predicate because two pages make it: the Forms page renders event programs and
 * tracker programs as different sections, and the organisation-units rail renders an event
 * program as a single row where a tracker program gets its grouped block.
 */
export function isEventProgram(group: ProgramGroup): boolean {
    return group.event !== null && group.registration === null && group.stages.length === 0
}
