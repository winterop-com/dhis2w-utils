import { useEffect, useState } from 'react'

import { readResource, searchResources } from '@/lib/api'
import { bundleResources, type Location, type Questionnaire, type ResourceList } from '@/lib/fhir'
import {
    admittedUnitIds,
    assignmentListIdOf,
    buildOrgUnitTree,
    orgUnitBrowseTree,
    orgUnitChoices,
    type OrgUnitBrowseNode,
    type OrgUnitChoice,
} from '@/lib/orgunits'

/**
 * The organisation units one form may be captured against.
 *
 * WHY THIS IS A SCOPE AND NOT A LIST. `GET /Location` is the whole published registry, and a form
 * that names an assignment List is capturable at a subset of it - a rule the facade enforces
 * (`_assignment_issues` in `dhis2w_fhir_serve.capture.validate`, `E1029` on the dial) rather than
 * one this UI invented. Intersecting here is what makes the picker unable to offer what the server
 * would refuse, which is a better shape than offering everything and rendering a warning after the
 * fact. A form declaring no assignment, and a form naming a List this server does not publish, both
 * scope to the whole registry - the second because that is exactly how the facade grades it.
 *
 * WHY THE READS ARE CACHED AT MODULE LEVEL. One capture screen can want this three ways at once:
 * the reporting-unit picker above the form, and one picker per `ORGANISATION_UNIT` question in it.
 * A per-component fetch would read a Bundle of 1,300 Locations once per control. The store behind
 * the server is immutable for the life of the process - it is loaded at startup and never written -
 * so a cache with no invalidation is the honest choice here for the same reason it is in
 * hooks/use-valueset-options.ts, and it is why this app still has no query library.
 */

/** What a picker offers for one form, and the two states a read can leave it in. */
export interface OrgUnitScope {
    /** Every unit the form may report from, in the order the hierarchy renders them. */
    choices: OrgUnitChoice[]
    /** The same set by id, so a stored reference can be shown as the unit it names. */
    byId: ReadonlyMap<string, OrgUnitChoice>
    /**
     * The same offer as a hierarchy: the registry folded, with every branch it admits nothing in
     * pruned away and the units it does not admit kept as disabled context. Folded once here beside
     * the flat offer, because both are derived from the same tree and the same assignment.
     */
    browseRoots: OrgUnitBrowseNode[]
    /** True when the form publishes an assignment List - so this is narrower than the registry. */
    restricted: boolean
    /** How many units the registry publishes, so an empty offer can say what it is empty of. */
    registryTotal: number
    loading: boolean
    /** The refusal the server stated, already reduced to its OperationOutcome diagnostics. */
    error: string | null
}

/** A scope nothing has been read into yet - what a picker renders before the first byte lands. */
export const EMPTY_ORG_UNIT_SCOPE: OrgUnitScope = {
    choices: [],
    byId: new Map(),
    browseRoots: [],
    restricted: false,
    registryTotal: 0,
    loading: false,
    error: null,
}

/** The registry, folded once and kept: the served store never changes under a running process. */
let registry: Promise<Location[]> | null = null

/** Every assignment List this session has read, keyed by the id the form names it under. */
const assignments = new Map<string, Promise<ResourceList | null>>()

/**
 * The units one form may be captured against, read once per session however many controls ask.
 *
 * The dependency is the form's assignment rather than the form: `readResource` hands back a fresh
 * Questionnaire object on every read and the assignment List id is the only thing about it this
 * scope depends on, so keying on the id is what stops the tree being re-folded on every render of
 * a page that re-read its form.
 */
export function useFormOrgUnitScope(questionnaire: Questionnaire | null): OrgUnitScope {
    return useScope(questionnaire === null ? null : assignmentListIdOf(questionnaire), questionnaire !== null)
}

/**
 * Every published unit, with no form narrowing it.
 *
 * What a *receipt* wants. A stored answer names `Location/<stem>` and may carry no display at all,
 * and the unit it names is a fact about the registry rather than about whichever form's assignment
 * was in force when it was captured - so narrowing here would leave a perfectly nameable unit
 * rendered as a uid. Same cached read as the form scope: opening a receipt after filling a form
 * costs nothing.
 */
export function useOrgUnitRegistry(): OrgUnitScope {
    return useScope(null, true)
}

/** What one read answered, stamped with the assignment it was read for. */
interface AnsweredScope {
    assignmentListId: string | null
    scope: OrgUnitScope
}

/** The read both hooks are: one assignment (or none), against the cached registry. */
function useScope(assignmentListId: string | null, opened: boolean): OrgUnitScope {
    const [answered, setAnswered] = useState<AnsweredScope | null>(null)

    useEffect(() => {
        if (!opened) return
        let cancelled = false
        readScope(assignmentListId)
            .then((read) => {
                if (cancelled) return
                setAnswered({ assignmentListId, scope: read })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setAnswered({
                    assignmentListId,
                    scope: {
                        ...EMPTY_ORG_UNIT_SCOPE,
                        error: failure instanceof Error ? failure.message : String(failure),
                    },
                })
            })
        return () => {
            cancelled = true
        }
    }, [assignmentListId, opened])

    if (!opened) return EMPTY_ORG_UNIT_SCOPE
    if (answered === null) return SCOPE_IN_FLIGHT
    if (answered.assignmentListId !== assignmentListId) return { ...answered.scope, loading: true, error: null }
    return answered.scope
}

/** A read that has been started and has not landed - what a picker renders while it waits. */
const SCOPE_IN_FLIGHT: OrgUnitScope = { ...EMPTY_ORG_UNIT_SCOPE, loading: true }

/** Read the registry and the form's assignment, and fold them into what a picker offers. */
async function readScope(assignmentListId: string | null): Promise<OrgUnitScope> {
    const [locations, list] = await Promise.all([
        readRegistry(),
        assignmentListId === null ? Promise.resolve(null) : readAssignment(assignmentListId),
    ])
    const tree = buildOrgUnitTree(locations)
    const admitted = admittedUnitIds(list)
    const choices = orgUnitChoices(tree, admitted)
    return {
        choices,
        byId: new Map(choices.map((choice) => [choice.id, choice])),
        browseRoots: orgUnitBrowseTree(tree, admitted),
        restricted: list !== null,
        registryTotal: tree.total,
        loading: false,
        error: null,
    }
}

/** Every published Location, read once. */
async function readRegistry(): Promise<Location[]> {
    registry ??= searchResources<Location>('Location')
        .then((bundle) => bundleResources(bundle))
        .catch((failure: unknown) => {
            // A failed read is not cached: the server may have been starting up, and a capture
            // screen opened a moment later should get a registry rather than the same refusal.
            registry = null
            throw failure instanceof Error ? failure : new Error(String(failure))
        })
    return registry
}

/**
 * One assignment List, or null when this server does not publish it.
 *
 * A 404 here is not a failure to report. The facade reads an unresolvable assignment as no
 * assignment at all, so a picker that refused to open would be stricter than the server it fills
 * forms for - and would hide a registry the capture would have been accepted against.
 */
async function readAssignment(listId: string): Promise<ResourceList | null> {
    const known = assignments.get(listId)
    if (known !== undefined) return known
    const started = readResource<ResourceList>('List', listId).catch(() => null)
    assignments.set(listId, started)
    return started
}
