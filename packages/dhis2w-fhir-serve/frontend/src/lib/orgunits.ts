/**
 * The reporting hierarchy, read off the registry: the tree, the levels, the geometry, the assignments.
 *
 * WHAT THE REGISTRY ACTUALLY IS. `GET /Location` answers with every organisation unit the project
 * published, flat, in one Bundle. Four separate facts are folded out of that flat set here, and
 * each of them is a rule that looks obvious until the wire disagrees:
 *
 *   1. THE TREE is `partOf` and nothing else. A unit whose `partOf` names a Location this project
 *      never published is not an error and must not vanish - a project generated with a `root` and
 *      a `max_level` publishes a slice of DHIS2's hierarchy, so the slice's own top units name
 *      parents that were left out by design. Those become roots, flagged, and the page says so.
 *   2. THE LEVEL is a coding on the `D2OrganisationUnitLevel` extension, not a count of `partOf`
 *      hops. Counting hops would be wrong for exactly the units in (1), whose depth in the served
 *      tree is smaller than their depth in DHIS2.
 *   3. THE BOUNDARY is a whole GeoJSON Feature, base64-encoded, inside an `Attachment`, on the
 *      official HL7 `location-boundary-geojson` extension - because R4's Location has no element
 *      for a polygon. It decodes to a Feature (not a bare geometry), the geometry is Polygon or
 *      MultiPolygon, and a payload that decodes to neither is skipped with a count rather than
 *      thrown: one malformed unit out of a thousand must not blank a map of the other nine
 *      hundred and ninety-nine.
 *   4. THE ASSIGNMENT is an absence for most forms. A Questionnaire carrying no
 *      `D2OrganisationUnitAssignment` extension is assigned everywhere - reportable at every
 *      published unit, which is how the facade itself reads it - so the join never materialises a
 *      form-times-unit pair for that case. It keeps those forms as one list and adds per-unit
 *      entries only for the forms an artifact restricts. (`universalFormIds` is the name in code;
 *      the page says "assigned everywhere", which is the phrase DHIS2 itself uses.)
 *
 * Everything here is pure. The network stays behind the choke point in lib/api.ts, which is what
 * lets all four rules be tested against harvested documents with no server running.
 */

import type {
    Extension,
    FormType,
    Location,
    Questionnaire,
    QuestionnaireResponse,
    Reference,
    ResourceList,
} from '@/lib/fhir'
import { FORM_TYPE_EXTENSION_SUFFIX, formIdentifier, unescapeMarkup } from '@/lib/fhir'

/**
 * The extension a Location states its DHIS2 hierarchy level on.
 *
 * Matched on the suffix like every other canonical-derived url this UI meets: the full url is
 * `{canonical}/StructureDefinition/d2-organisation-unit-level` and the canonical is whatever that
 * project's fhir.toml declares.
 */
export const ORG_UNIT_LEVEL_EXTENSION_SUFFIX = '/StructureDefinition/d2-organisation-unit-level'

/** The extension a Questionnaire names its assignment List on, matched on the same kind of suffix. */
export const ORG_UNIT_ASSIGNMENT_EXTENSION_SUFFIX = '/StructureDefinition/d2-organisation-unit-assignment'

/**
 * The extension a tracker response states the unit it reports from on.
 *
 * One character shy of two of its neighbours, and `endsWith` is what tells the three apart: a url
 * ending in `-level` or `-assignment` does not end in this. The response side of the contract
 * rather than the form side - an aggregate or event response names its unit as `subject`, and a
 * tracker one names it here because its subject is the tracked entity.
 */
export const ORG_UNIT_EXTENSION_SUFFIX = '/StructureDefinition/d2-organisation-unit'

/**
 * The extension a boundary polygon travels on.
 *
 * This one is absolute rather than suffix-matched, because it is HL7's own and not this IG's -
 * `location-boundary-geojson` is the standard place for a Location's shape, and the DHIS2
 * generator uses it verbatim.
 */
export const BOUNDARY_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/location-boundary-geojson'

/**
 * The identifier system tail every published Location carries its DHIS2 organisation-unit uid on.
 *
 * The full system is `{identifier_system_base}/id/org-unit`, and the base is per-project - so this
 * is matched on the tail like every other derived url here. `/id/org-unit-code` is a different
 * system and does not match, because a suffix comparison against this string is exact at the end.
 */
export const ORG_UNIT_IDENTIFIER_SYSTEM_SUFFIX = '/id/org-unit'

/** The prefix an assignment List entry names a unit with. */
export const LOCATION_REFERENCE_PREFIX = 'Location/'

/** The prefix a Questionnaire's assignment extension names its List with. */
export const LIST_REFERENCE_PREFIX = 'List/'

/** Which level of the DHIS2 hierarchy a unit sits at, as the published coding states it. */
export interface OrgUnitLevel {
    /** The concept code, `level-<n>`. */
    code: string
    /** How the level CodeSystem displays it, or null when the coding carries no display. */
    display: string | null
    /** The level CodeSystem the coding is drawn from, or null when it names none. */
    system: string | null
    /** The number in `level-<n>`, or null when the code is not shaped that way. */
    depth: number | null
}

/** One unit in the folded hierarchy, with its children already sorted and its subtree already counted. */
export interface OrgUnitNode {
    id: string
    /** The unit's name as page text, unescaped, falling back to its id. */
    name: string
    location: Location
    level: OrgUnitLevel | null
    /** The parent this node hangs off in the served tree - null for a root. */
    parentId: string | null
    children: OrgUnitNode[]
    /**
     * True when `partOf` named a Location this project does not publish.
     *
     * The node is a root either way; the flag is what lets the page say the hierarchy above it was
     * left out of the selection rather than implying the unit is a top-level one.
     */
    orphaned: boolean
    /**
     * The parent `partOf` named that this tree could not hang the unit under.
     *
     * Either a Location the project never published, or - vanishingly rarely - one that would have
     * made the hierarchy a cycle. Null when the unit states no parent at all.
     */
    unresolvedParentId: string | null
    /** How many units sit below this one, at any depth. */
    descendantCount: number
}

/** The whole registry, folded once: the roots to render from, and an index to reach any unit by id. */
export interface OrgUnitTree {
    roots: OrgUnitNode[]
    byId: Map<string, OrgUnitNode>
    /** How many organisation units the registry publishes, counting each one once. */
    total: number
    /** How many of them name a parent this project never published. */
    orphanCount: number
    /**
     * How many published Locations were a second copy of a unit already in the tree.
     *
     * Not an error and not rendered: it is the documentation exemplar the IG publishes beside the
     * registry profiles. Kept as a number so the fold can be tested for having done the dropping.
     */
    duplicateCount: number
}

/** A polygonal shape, in the two GeoJSON geometry types DHIS2 stores a boundary as. */
export type BoundaryGeometry =
    | { type: 'Polygon'; coordinates: number[][][] }
    | { type: 'MultiPolygon'; coordinates: number[][][][] }

/** One unit's boundary, kept with the id of the unit it belongs to so a map can select by click. */
export interface OrgUnitBoundary {
    unitId: string
    geometry: BoundaryGeometry
}

/** One unit's point, in GeoJSON's own longitude-then-latitude order. */
export interface OrgUnitPoint {
    unitId: string
    longitude: number
    latitude: number
}

/**
 * What one Location's geometry attachment turned out to hold.
 *
 * Three outcomes rather than two, because the extension is not a polygon slot. It is DHIS2's
 * `geometry` field, verbatim, and DHIS2 keeps a district's catchment polygon and a health post's
 * pin in that same field - so the attachment holds a Polygon for some units and a Point for many
 * more of them. Reading it as "polygon or failure" is what made a registry of 766 located units
 * report 601 failures: those were the facilities.
 */
export interface AttachmentGeometry {
    /** The polygonal shape, when the attachment held one. */
    boundary: OrgUnitBoundary | null
    /** The pins, when it held a Point or a MultiPoint instead. */
    points: OrgUnitPoint[]
    /** True when the attachment is there but holds nothing this map draws - the only real failure. */
    unreadable: boolean
}

/** Everything the registry knows about where its units are, plus what genuinely could not be read. */
export interface OrgUnitGeometry {
    boundaries: OrgUnitBoundary[]
    points: OrgUnitPoint[]
    /**
     * Attachments holding nothing drawable: not JSON, not GeoJSON, or a geometry type this map has
     * no mark for (a LineString, a GeometryCollection). A Point is not one of these - it is a point.
     */
    unreadableGeometries: number
}

/**
 * Which forms may be captured where, without materialising a pair per unit.
 *
 * The assigned-everywhere list is the common case and is one array however many units the project
 * publishes; `formIdsByUnitId` holds only the additions an assignment artifact makes.
 */
export interface FormAssignmentIndex {
    /** Forms no assignment artifact restricts - assigned everywhere, so reportable at every unit. */
    universalFormIds: string[]
    /** Unit id -> the ids of the restricted forms whose assignment admits it. */
    formIdsByUnitId: Map<string, string[]>
    /** Every form an assignment artifact restricts, in the order the forms were read. */
    restrictedFormIds: string[]
    /**
     * Forms naming an assignment List this server does not publish.
     *
     * Read as assigned everywhere, because that is how the facade grades them: an unresolvable reference
     * is the project's incomplete build rather than a restriction, and
     * `dhis2w_fhir_serve.capture.index._assignment` says so in the same words. Kept as a list so
     * the page can name them instead of quietly widening their scope.
     */
    unresolvedAssignmentFormIds: string[]
}

/** What a given unit may report: the forms assigned everywhere, and the ones assigned to it by name. */
export interface ReportableForms {
    universalFormIds: string[]
    restrictedFormIds: string[]
}

/**
 * Fold a flat set of Locations into the tree the browser renders.
 *
 * Children are sorted by the name that is rendered, so the order a reader sees is the order the
 * comparison made. Roots are sorted the same way, with the orphans last: a unit whose parent was
 * left out of the selection is a root by accident rather than by design, and putting it under the
 * real roots keeps the top of the tree readable.
 *
 * The set is deduplicated before anything is folded - see `dedupeByOrgUnitIdentifier` for why one
 * organisation unit can arrive as two Locations.
 */
export function buildOrgUnitTree(locations: Location[]): OrgUnitTree {
    const { kept, dropped } = dedupeByOrgUnitIdentifier(locations)
    const byId = new Map<string, OrgUnitNode>()
    for (const location of kept) {
        const id = location.id
        if (id === undefined || id === '') continue
        byId.set(id, {
            id,
            name: orgUnitName(location),
            location,
            level: levelOf(location),
            parentId: null,
            children: [],
            orphaned: false,
            unresolvedParentId: null,
            descendantCount: 0,
        })
    }

    const roots: OrgUnitNode[] = []
    for (const node of byId.values()) {
        const declared = parentIdOf(node.location)
        if (declared === null) {
            roots.push(node)
            continue
        }
        const parent = byId.get(declared)
        if (parent === undefined || parent === node) {
            // The parent was not published, or the unit names itself. Either way there is no edge
            // to draw, and dropping the unit would hide a real published place.
            node.orphaned = true
            node.unresolvedParentId = declared
            roots.push(node)
            continue
        }
        node.parentId = declared
        parent.children.push(node)
    }

    // A registry with a `partOf` cycle would otherwise loop here forever. Cycles are not something
    // DHIS2 can produce, but the store this reads is whatever a project published, and a browser
    // that hangs is a worse answer than one that renders the cycle as an unreachable branch.
    breakCycles(roots, byId)

    for (const node of byId.values()) node.children.sort(compareByName)
    roots.sort((left, right) => {
        if (left.orphaned !== right.orphaned) return left.orphaned ? 1 : -1
        return compareByName(left, right)
    })
    for (const root of roots) countDescendants(root)

    return {
        roots,
        byId,
        total: byId.size,
        orphanCount: roots.filter((node) => node.orphaned).length,
        duplicateCount: dropped.length,
    }
}

/**
 * One Location per organisation unit, when the store publishes more than one.
 *
 * WHY THIS IS NEEDED. A generated IG publishes the registry as pre-built JSON, and beside it a
 * curated `Usage: #example` pair so the `D2Location` and `D2Organization` profiles have a worked
 * example the publisher can validate against - `registry-examples.fsh`, built from the selection's
 * own root unit. The exemplar therefore carries that unit's real DHIS2 uid on the real
 * `{base}/id/org-unit` system, under a different resource id (`d2-location-example`) and with no
 * `partOf`. The facade serves everything the project published, so a tree folded from `partOf`
 * alone sees two Sierra Leones: the real root, and a second one that hangs off nothing.
 *
 * WHY IT IS NOT AN ID BLACKLIST. `d2-location-example` is what today's emitter happens to name it,
 * derived from a profile id that the naming tokens can change. What is invariant is the claim the
 * two documents make: the same organisation unit, stated as the same identifier value on the same
 * system. So the grouping key is that value, and the system is recognised by its tail rather than
 * by a hard-coded base, because the base is `[generate] identifier_system_base` and differs per
 * project.
 *
 * WHICH ONE SURVIVES. The one that participates in the hierarchy, in this order:
 *
 *   1. A Location some other Location's `partOf` points at. Whatever else it is, the rest of the
 *      registry hangs off it, and dropping it would detach every one of them.
 *   2. Failing that, a Location that names a parent itself - it has a place in the tree, and the
 *      exemplar by construction does not.
 *   3. Failing both - a degenerate registry of one unit plus its exemplar, where neither document
 *      participates in anything - the lowest resource id, sorted. That tiebreak is arbitrary and
 *      admitted to be: what it buys is determinism, so the same store always folds the same way
 *      rather than following whatever order the Bundle happened to arrive in.
 *
 * A Location carrying no org-unit identifier at all is never grouped and never dropped: it claims
 * to be no particular unit, so nothing else can be a duplicate of it.
 *
 * ORGANIZATIONS WOULD NEED THE SAME RULE. The exemplar comes as a pair, and
 * `Organization/d2-organization-example` carries the same uid on the same system. Nothing in this
 * UI folds Organizations today; whatever does should call this, not reimplement it.
 */
export function dedupeByOrgUnitIdentifier(locations: Location[]): {
    kept: Location[]
    dropped: Location[]
} {
    const referenced = new Set<string>()
    for (const location of locations) {
        const parent = parentIdOf(location)
        if (parent !== null && parent !== location.id) referenced.add(parent)
    }

    const claims = new Map<string, Location[]>()
    for (const location of locations) {
        const value = orgUnitIdentifierValue(location)
        if (value === null) continue
        const group = claims.get(value)
        if (group === undefined) claims.set(value, [location])
        else group.push(location)
    }

    const dropped = new Set<Location>()
    for (const group of claims.values()) {
        if (group.length < 2) continue
        const winner =
            group.find((candidate) => candidate.id !== undefined && referenced.has(candidate.id)) ??
            group.find((candidate) => parentIdOf(candidate) !== null) ??
            group.toSorted((left, right) => (left.id ?? '').localeCompare(right.id ?? ''))[0]
        for (const candidate of group) if (candidate !== winner) dropped.add(candidate)
    }

    return {
        kept: locations.filter((location) => !dropped.has(location)),
        dropped: [...dropped],
    }
}

/** The DHIS2 organisation-unit uid a Location claims to be, or null when it claims none. */
export function orgUnitIdentifierValue(location: Location): string | null {
    const identifier = (location.identifier ?? []).find((candidate) =>
        (candidate.system ?? '').endsWith(ORG_UNIT_IDENTIFIER_SYSTEM_SUFFIX),
    )
    const value = identifier?.value
    return value === undefined || value === '' ? null : value
}

/** The level a Location declares, or null when it declares none. */
export function levelOf(location: Location): OrgUnitLevel | null {
    const extension = findExtension(location.extension, ORG_UNIT_LEVEL_EXTENSION_SUFFIX)
    const coding = extension?.valueCoding
    if (coding?.code === undefined || coding.code === '') return null
    const digits = /^level-(\d+)$/.exec(coding.code)
    return {
        code: coding.code,
        display: coding.display ?? null,
        system: coding.system ?? null,
        depth: digits === null ? null : Number(digits[1]),
    }
}

/** What a unit is called, as page text - unescaped, and falling back to the id it is served under. */
export function orgUnitName(location: Location): string {
    const raw = location.name
    if (raw === undefined || raw === '') return location.id ?? ''
    return unescapeMarkup(raw)
}

/** The unit its `partOf` names, or null when it states none - which is what makes a unit a root. */
export function parentIdOf(location: Location): string | null {
    const reference = location.partOf?.reference
    if (reference === undefined || !reference.startsWith(LOCATION_REFERENCE_PREFIX)) return null
    const id = reference.slice(LOCATION_REFERENCE_PREFIX.length)
    return id === '' ? null : id
}

/**
 * Every unit above one, nearest ancestor last, so a breadcrumb reads root-first left to right.
 *
 * Stops at a node already seen, which is the same cycle guard `buildOrgUnitTree` applies - this
 * function is also called on ids the caller got from a URL, so it cannot assume a folded tree.
 */
export function ancestorsOf(tree: OrgUnitTree, unitId: string): OrgUnitNode[] {
    const chain: OrgUnitNode[] = []
    const seen = new Set<string>([unitId])
    let current = tree.byId.get(unitId)?.parentId ?? null
    while (current !== null && !seen.has(current)) {
        const node = tree.byId.get(current)
        if (node === undefined) break
        chain.unshift(node)
        seen.add(current)
        current = node.parentId
    }
    return chain
}

/** Every unit below one, at any depth, in the order the tree renders them. */
export function descendantIdsOf(node: OrgUnitNode): string[] {
    const found: string[] = []
    const walk = (current: OrgUnitNode) => {
        for (const child of current.children) {
            found.push(child.id)
            walk(child)
        }
    }
    walk(node)
    return found
}

/**
 * The ids a filter should leave visible: every match, plus every ancestor of a match.
 *
 * A tree filter that showed only the matching nodes would show them detached from the hierarchy
 * that gives them meaning, so the ancestors come along - and because they are in the set, the tree
 * knows to expand them without the caller tracking expansion state per keystroke.
 */
export function matchingUnitIds(tree: OrgUnitTree, query: string): Set<string> {
    const needle = query.trim().toLowerCase()
    const visible = new Set<string>()
    if (needle === '') return visible
    for (const node of tree.byId.values()) {
        if (!matchesUnit(node, needle)) continue
        visible.add(node.id)
        for (const ancestor of ancestorsOf(tree, node.id)) visible.add(ancestor.id)
    }
    return visible
}

/**
 * Whether one unit answers a filter - on its name, its id, or any identifier value it carries.
 *
 * Typed on the three fields it reads rather than on a whole `OrgUnitNode`, so the picker's rows
 * are matched by this one function instead of by a second reading of the same rule. The identifier
 * sweep is what makes a DHIS2 code (`OU_NGELEHUN`) a thing a person can type.
 */
export function matchesUnit(node: Pick<OrgUnitNode, 'id' | 'name' | 'location'>, lowercaseQuery: string): boolean {
    if (node.name.toLowerCase().includes(lowercaseQuery)) return true
    if (node.id.toLowerCase().includes(lowercaseQuery)) return true
    return (node.location.identifier ?? []).some((identifier) =>
        (identifier.value ?? '').toLowerCase().includes(lowercaseQuery),
    )
}

/** One unit as a picker offers it: what it is called, where it sits, and what it writes. */
export interface OrgUnitChoice {
    id: string
    /** The unit's name as page text, unescaped - the same string the tree renders. */
    name: string
    location: Location
    level: OrgUnitLevel | null
    /** The parent's name, as muted context on the row - null for a root of the served tree. */
    parentName: string | null
}

/**
 * The units a picker may offer, in the order the tree renders them.
 *
 * PRE-ORDER, NOT ALPHABETICAL. A flat alphabetical list of 1,300 units puts a district between two
 * facilities of a different district, which is the one ordering a person reading DHIS2's hierarchy
 * cannot navigate. Walking the folded tree keeps every unit under the one it belongs to, and the
 * parent's name on each row is what makes that readable once the search has broken the list up.
 *
 * `admitted` is the form's assignment: a set of unit ids when the form publishes one, and null when
 * it publishes none - which means the whole registry, exactly as the facade grades it. An empty set
 * is not the same as null and offers nothing, because that is what the server would accept.
 */
export function orgUnitChoices(tree: OrgUnitTree, admitted: ReadonlySet<string> | null): OrgUnitChoice[] {
    const choices: OrgUnitChoice[] = []
    const walk = (node: OrgUnitNode, parentName: string | null): void => {
        if (admitted === null || admitted.has(node.id)) {
            choices.push({ id: node.id, name: node.name, location: node.location, level: node.level, parentName })
        }
        for (const child of node.children) walk(child, node.name)
    }
    for (const root of tree.roots) walk(root, null)
    return choices
}

/** One row of a picker's browsable hierarchy: what it is, whether it may be picked, what is under it. */
export interface OrgUnitBrowseNode {
    id: string
    /** The unit's name as page text - the same string the tree and the flat offer render. */
    name: string
    level: OrgUnitLevel | null
    /**
     * True when the form's assignment admits this unit, so the row is a choice rather than context.
     *
     * False rows are kept and shown disabled, never hidden: a district that is not itself assigned
     * is the thing that tells two facilities of the same name apart.
     */
    admitted: boolean
    /** The children that survived pruning - a branch admitting nothing anywhere is not here at all. */
    children: OrgUnitBrowseNode[]
}

/** One visible row of a browsable hierarchy, as the keyboard walks it: the node, and where it sits. */
export interface OrgUnitBrowseRow {
    node: OrgUnitBrowseNode
    /** How many units sit above it in the rendered tree, so a root is 0. */
    depth: number
    /** The row above it that owns it, so ArrowLeft on a closed node has somewhere to go. */
    parentId: string | null
    /** Which of its parent's children it is, counting from one - `aria-posinset` verbatim. */
    positionInParent: number
    /** How many children that parent has - `aria-setsize` verbatim. */
    siblingCount: number
}

/**
 * The hierarchy a picker browses: the whole tree, minus every branch the form admits nothing in.
 *
 * TWO RULES, AND THEY ARE DIFFERENT RULES. A unit outside the assignment is **disabled**, not
 * hidden, because an assignment List names exact units and can therefore admit a facility whose
 * district it does not - `PrScoped001` admits Bo and Ngelehun CHC, and Ngelehun's own district
 * Badjia is not admitted. Dropping Badjia would leave the facility hanging off nothing, and the
 * parent chain is precisely what disambiguates the repeated facility names a national registry is
 * full of. But a branch with no admitted unit anywhere below it is **pruned**, because it is
 * offering nothing and a tree that renders 1,300 unpickable rows is a tree nobody browses.
 *
 * One post-order pass, so admitted-descendant presence is just `children.length` after the
 * children have been pruned - no second walk and no memo table. `admitted === null` is the form
 * that declares no assignment: every unit is admitted, so nothing prunes and nothing disables.
 */
export function orgUnitBrowseTree(tree: OrgUnitTree, admitted: ReadonlySet<string> | null): OrgUnitBrowseNode[] {
    const keep = (node: OrgUnitNode): OrgUnitBrowseNode | null => {
        const children = node.children.flatMap((child) => {
            const kept = keep(child)
            return kept === null ? [] : [kept]
        })
        const isAdmitted = admitted === null || admitted.has(node.id)
        if (!isAdmitted && children.length === 0) return null
        return { id: node.id, name: node.name, level: node.level, admitted: isAdmitted, children }
    }
    return tree.roots.flatMap((root) => {
        const kept = keep(root)
        return kept === null ? [] : [kept]
    })
}

/**
 * The ids above one unit in a browsable hierarchy, root first, or null when the tree has no such unit.
 *
 * Null and the empty array are different answers and both happen: a unit pruned out of the tree is
 * null, and a unit that is itself a root has no ancestors at all.
 */
export function browseAncestorIds(roots: OrgUnitBrowseNode[], unitId: string): string[] | null {
    const walk = (node: OrgUnitBrowseNode, chain: string[]): string[] | null => {
        if (node.id === unitId) return chain
        for (const child of node.children) {
            const found = walk(child, [...chain, node.id])
            if (found !== null) return found
        }
        return null
    }
    for (const root of roots) {
        const found = walk(root, [])
        if (found !== null) return found
    }
    return null
}

/**
 * What a browsable hierarchy opens with: the selection in view, or the roots one level down.
 *
 * A picker holding a unit should open showing it, not showing a collapsed root the reader has to
 * click four times to get back to where they already are - so the selection's ancestors are open.
 * With nothing held, and for a selection that is itself a root, the answer is the roots' own
 * children: one level is enough to show the shape without mounting a national hierarchy.
 */
export function expandedForSelection(roots: OrgUnitBrowseNode[], selectedUnitId: string | null): Set<string> {
    const chain = selectedUnitId === null ? null : browseAncestorIds(roots, selectedUnitId)
    if (chain !== null && chain.length > 0) return new Set(chain)
    return new Set(roots.map((root) => root.id))
}

/**
 * The rows a browsable hierarchy is currently drawing, in the order they appear on screen.
 *
 * The keyboard's model of the tree. ArrowDown is the next entry of this array whatever depth it is
 * at, which is what makes arrowing off the last facility of one district land on the next district
 * rather than stopping - and a closed node contributes exactly one row, which is the same rule that
 * keeps the tree cheap to render. It is also the DOM's model of it: the rows render flat with
 * `aria-level`, `aria-posinset`, and `aria-setsize`, which is the shape ARIA defines for a tree
 * whose branches are not nested elements.
 */
export function visibleBrowseRows(
    roots: OrgUnitBrowseNode[],
    expanded: ReadonlySet<string>,
): OrgUnitBrowseRow[] {
    const rows: OrgUnitBrowseRow[] = []
    const walk = (
        node: OrgUnitBrowseNode,
        depth: number,
        parentId: string | null,
        positionInParent: number,
        siblingCount: number,
    ): void => {
        rows.push({ node, depth, parentId, positionInParent, siblingCount })
        if (node.children.length === 0 || !expanded.has(node.id)) return
        node.children.forEach((child, index) => {
            walk(child, depth + 1, node.id, index + 1, node.children.length)
        })
    }
    roots.forEach((root, index) => {
        walk(root, 0, null, index + 1, roots.length)
    })
    return rows
}

/**
 * The reference a chosen unit is written as.
 *
 * `Location/<stem>` is the whole of what the capture contract checks - `_is_location_reference` in
 * `dhis2w_fhir_serve.capture.validate` reads the shape, and the forwarder reads the stem back as
 * the DHIS2 organisation-unit uid. The display rides along only when the registry states a name:
 * `orgUnitName` falls back to the id, and a reference whose display repeats its own reference says
 * nothing and would read as a name on every receipt that showed it.
 */
export function orgUnitReference(choice: OrgUnitChoice): Reference {
    const stated = choice.location.name
    return {
        reference: `${LOCATION_REFERENCE_PREFIX}${choice.id}`,
        ...(stated === undefined || stated === '' ? {} : { display: choice.name }),
    }
}

/** The unit id a `Location/<stem>` reference names, or null when it names something else. */
export function referencedUnitId(reference: Reference | null | undefined): string | null {
    const stated = reference?.reference
    if (stated === undefined || !stated.startsWith(LOCATION_REFERENCE_PREFIX)) return null
    const id = stated.slice(LOCATION_REFERENCE_PREFIX.length)
    return id === '' ? null : id
}

/**
 * The unit ids one form's assignment admits, or null for "every unit the registry publishes".
 *
 * The same three-way reading `buildFormAssignments` applies across all forms, for the one form a
 * capture screen is filling. Null is the answer for two different absences and deliberately so: a
 * form that declares no assignment extension is assigned everywhere, and a form naming a List this
 * server does not publish is read as assigned everywhere too - which is how
 * `dhis2w_fhir_serve.capture.index._assignment` grades it, so a picker that narrowed there would
 * offer less than the server accepts. A published List is exactly its entries, empty included.
 */
export function admittedUnitIds(list: ResourceList | null): ReadonlySet<string> | null {
    return list === null ? null : new Set(assignedUnitIds(list))
}

/**
 * The organisation unit a response reports from, wherever its form kind carries it.
 *
 * TWO PLACES, ONE FACT. An aggregate or event response names its unit as `subject`, because that
 * is what the submission is about. A tracker response's subject is the tracked entity - a person,
 * not a place - so the unit rides the `d2-organisation-unit` extension instead, and
 * `dhis2w_fhir_serve.capture.validate._tracker_context_issues` requires exactly one of them.
 * Reading both here is what lets one picker serve all four kinds.
 */
export function reportingUnitOf(response: QuestionnaireResponse, formKind: FormType | null): Reference | null {
    if (!carriesUnitOnExtension(formKind)) return response.subject ?? null
    const extension = findExtension(response.extension, ORG_UNIT_EXTENSION_SUFFIX)
    return extension?.valueReference ?? null
}

/** Whether a form kind states its unit on the extension rather than on `subject`. */
export function carriesUnitOnExtension(formKind: FormType | null): boolean {
    return formKind === 'tracker' || formKind === 'tracker-event'
}

/**
 * The url a response states its organisation unit under, derived from the form that declared its kind.
 *
 * Every extension of this IG hangs off one canonical, and a served capture form always carries the
 * form-type extension - it is what `formTypeOf` reads - so its url is the canonical this project
 * publishes under, whatever `fhir.toml` set it to. Deriving rather than hard-coding is the same
 * rule `attributeOptionComboExtensionUrl` follows, and for the same reason: a facade can serve a
 * guide compiled under a different canonical than it answers on.
 */
export function organisationUnitExtensionUrl(questionnaire: Questionnaire): string | null {
    const declared = questionnaire.extension?.find((candidate) =>
        candidate.url.endsWith(FORM_TYPE_EXTENSION_SUFFIX),
    )
    if (declared === undefined) return null
    const canonical = declared.url.slice(0, declared.url.length - FORM_TYPE_EXTENSION_SUFFIX.length)
    return `${canonical}${ORG_UNIT_EXTENSION_SUFFIX}`
}

/**
 * Read one unit's geometry attachment, or null when it publishes none.
 *
 * The extension is DHIS2's `geometry` field carried verbatim, so what comes out of it is whatever
 * DHIS2 stores for that unit: a catchment polygon for a district, a pin for a health post. Both
 * are drawn; a geometry type with no mark on this map (a LineString, a GeometryCollection) and a
 * payload that is not GeoJSON at all are the two cases that count as unreadable.
 */
export function attachmentGeometryOf(location: Location): AttachmentGeometry | null {
    const unitId = location.id
    if (unitId === undefined || unitId === '') return null
    const data = findExtension(location.extension, BOUNDARY_EXTENSION_URL)?.valueAttachment?.data
    if (data === undefined || data === '') return null
    const geometry = decodeGeometry(data)
    if (geometry === null) return { boundary: null, points: [], unreadable: true }
    if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') {
        return { boundary: { unitId, geometry }, points: [], unreadable: false }
    }
    const positions = geometry.type === 'Point' ? [geometry.coordinates] : geometry.coordinates
    const points = positions.flatMap((position) => {
        const [longitude, latitude] = position
        if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return []
        return [{ unitId, longitude, latitude }]
    })
    // A Point whose coordinates are not numbers is as unreadable as a payload that is not JSON.
    return { boundary: null, points, unreadable: points.length === 0 }
}

/** One unit's boundary polygon, decoded, or null when its attachment holds something else. */
export function boundaryOf(location: Location): OrgUnitBoundary | null {
    return attachmentGeometryOf(location)?.boundary ?? null
}

/** One unit's point, or null when DHIS2 holds no coordinates for it. */
export function pointOf(location: Location): OrgUnitPoint | null {
    const unitId = location.id
    const position = location.position
    if (unitId === undefined || unitId === '' || position === undefined) return null
    if (!Number.isFinite(position.longitude) || !Number.isFinite(position.latitude)) return null
    return { unitId, longitude: position.longitude, latitude: position.latitude }
}

/** Whether the registry holds any geometry at all - which is what decides the map panel exists. */
export function hasGeometry(geometry: OrgUnitGeometry): boolean {
    return geometry.boundaries.length > 0 || geometry.points.length > 0
}

/**
 * Read every shape the registry publishes, in one pass.
 *
 * One pass over the whole set, because the map draws everything at once and a per-unit decode on
 * selection would re-do the same base64 on every click. Nothing throws: an attachment holding
 * something this map has no mark for is counted in `unreadableGeometries` and the other units keep
 * their shapes.
 *
 * TWO DEDUPE RULES, ONE PER PAIR OF SOURCES. A unit can state where it is more than once, and each
 * pair resolves to one mark:
 *
 *   - `position` WINS OVER THE ATTACHMENT'S POINT. Both are renderings of one DHIS2 field on a
 *     generated registry, so they agree; when they do not, the R4 element wins - `position` is the
 *     standard place a Location says where it is, it is what every other FHIR client reads, and a
 *     map that drew the extension instead would disagree with all of them over the same document.
 *     The attachment's points are used only for a unit that states no `position`.
 *   - THE BOUNDARY WINS OVER `position`. DHIS2 keeps one geometry per unit, but its exporter also
 *     fills `coordinates` with the polygon's centroid, which a generated registry renders as
 *     `position` beside the boundary attachment. Drawing both puts a facility-sized dot in the
 *     middle of every district's own polygon - so a unit whose attachment holds a polygon is a
 *     boundary and nothing else, mirroring the rule above: one unit, one mark.
 */
export function readGeometry(locations: Location[]): OrgUnitGeometry {
    const boundaries: OrgUnitBoundary[] = []
    const points: OrgUnitPoint[] = []
    let unreadableGeometries = 0
    for (const location of locations) {
        const attachment = attachmentGeometryOf(location)
        if (attachment !== null) {
            if (attachment.unreadable) unreadableGeometries += 1
            if (attachment.boundary !== null) {
                boundaries.push(attachment.boundary)
                continue
            }
        }
        const position = pointOf(location)
        if (position !== null) points.push(position)
        else if (attachment !== null) points.push(...attachment.points)
    }
    return { boundaries, points, unreadableGeometries }
}

/** The bounding box `[west, south, east, north]` of a set of shapes, or null when they hold no coordinates. */
export function boundsOf(boundaries: OrgUnitBoundary[], points: OrgUnitPoint[]): [number, number, number, number] | null {
    let west = Infinity
    let south = Infinity
    let east = -Infinity
    let north = -Infinity
    const extend = (longitude: number, latitude: number) => {
        if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return
        west = Math.min(west, longitude)
        east = Math.max(east, longitude)
        south = Math.min(south, latitude)
        north = Math.max(north, latitude)
    }
    for (const boundary of boundaries) {
        const rings =
            boundary.geometry.type === 'Polygon'
                ? boundary.geometry.coordinates
                : boundary.geometry.coordinates.flat()
        for (const ring of rings) for (const position of ring) extend(position[0], position[1])
    }
    for (const point of points) extend(point.longitude, point.latitude)
    return west === Infinity ? null : [west, south, east, north]
}

/** What a unit's extent actually covers, so a caption can say what is being shown. */
export type ExtentCoverage = 'own' | 'descendants' | 'ancestor' | 'registry' | 'none'

/** Where one unit is, to the resolution the registry holds - a rectangle, and what it is a rectangle of. */
export interface UnitExtent {
    /** `[west, south, east, north]`, or null when nothing anywhere carries coordinates. */
    bounds: [number, number, number, number] | null
    coverage: ExtentCoverage
    /** The located unit ids whose shapes compose the bounds - what a map fits, empty for `registry`. */
    unitIds: string[]
    /** The ancestor the bounds belong to, when the coverage is `ancestor`. */
    framedOnUnitId: string | null
}

/**
 * The extent one unit should be framed on.
 *
 * FIT PRIORITY, STATED ONCE: the unit's own geometry; else the union bounding box of its subtree's
 * boundaries and points - a level-1 unit with no polygon of its own is where its districts are,
 * not where its country's ancestor is; else the nearest located ancestor; else the whole
 * registry's extent. Exported as a pure function because a unit's extent is an answer other
 * consumers want too (climate services read org-unit extents), not just this map's framing.
 */
export function unitExtent(tree: OrgUnitTree, unitId: string, geometry: OrgUnitGeometry): UnitExtent {
    const located = new Set<string>()
    for (const boundary of geometry.boundaries) located.add(boundary.unitId)
    for (const point of geometry.points) located.add(point.unitId)
    const boundsAmong = (unitIds: string[]): [number, number, number, number] | null => {
        const wanted = new Set(unitIds)
        return boundsOf(
            geometry.boundaries.filter((boundary) => wanted.has(boundary.unitId)),
            geometry.points.filter((point) => wanted.has(point.unitId)),
        )
    }

    if (located.has(unitId)) {
        return { bounds: boundsAmong([unitId]), coverage: 'own', unitIds: [unitId], framedOnUnitId: null }
    }
    const node = tree.byId.get(unitId)
    const below = node === undefined ? [] : descendantIdsOf(node).filter((id) => located.has(id))
    if (below.length > 0) {
        return { bounds: boundsAmong(below), coverage: 'descendants', unitIds: below, framedOnUnitId: null }
    }
    const ancestor = ancestorsOf(tree, unitId)
        .toReversed()
        .find((candidate) => located.has(candidate.id))
    if (ancestor !== undefined) {
        return {
            bounds: boundsAmong([ancestor.id]),
            coverage: 'ancestor',
            unitIds: [ancestor.id],
            framedOnUnitId: ancestor.id,
        }
    }
    const registry = boundsOf(geometry.boundaries, geometry.points)
    if (registry === null) return { bounds: null, coverage: 'none', unitIds: [], framedOnUnitId: null }
    return { bounds: registry, coverage: 'registry', unitIds: [], framedOnUnitId: null }
}

/**
 * Join the served forms to the served assignment Lists.
 *
 * The absence of an artifact is the common case and means "assigned everywhere", so it is
 * represented as one list of form ids rather than as an entry per unit - a project with 1300 units
 * and 40 such forms would otherwise build 52,000 pairs to say nothing.
 */
export function buildFormAssignments(
    questionnaires: Questionnaire[],
    lists: ResourceList[],
): FormAssignmentIndex {
    const unitIdsByListId = new Map<string, string[]>()
    for (const list of lists) {
        const listId = list.id
        if (listId === undefined || listId === '') continue
        unitIdsByListId.set(listId, assignedUnitIds(list))
    }

    const universalFormIds: string[] = []
    const restrictedFormIds: string[] = []
    const unresolvedAssignmentFormIds: string[] = []
    const formIdsByUnitId = new Map<string, string[]>()

    for (const questionnaire of questionnaires) {
        const formId = formIdentifier(questionnaire)
        if (formId === '') continue
        const listId = assignmentListIdOf(questionnaire)
        if (listId === null) {
            universalFormIds.push(formId)
            continue
        }
        const unitIds = unitIdsByListId.get(listId)
        if (unitIds === undefined) {
            unresolvedAssignmentFormIds.push(formId)
            universalFormIds.push(formId)
            continue
        }
        restrictedFormIds.push(formId)
        for (const unitId of unitIds) {
            const forms = formIdsByUnitId.get(unitId)
            if (forms === undefined) formIdsByUnitId.set(unitId, [formId])
            else forms.push(formId)
        }
    }

    return { universalFormIds, formIdsByUnitId, restrictedFormIds, unresolvedAssignmentFormIds }
}

/** What one unit may report - the forms assigned everywhere, and the ones assigned to it by name. */
export function reportableFormsAt(index: FormAssignmentIndex, unitId: string): ReportableForms {
    return {
        universalFormIds: index.universalFormIds,
        restrictedFormIds: index.formIdsByUnitId.get(unitId) ?? [],
    }
}

/** The List a Questionnaire names its assignment on, or null when it names none. */
export function assignmentListIdOf(questionnaire: Questionnaire): string | null {
    const extension = findExtension(questionnaire.extension, ORG_UNIT_ASSIGNMENT_EXTENSION_SUFFIX)
    const reference = extension?.valueReference?.reference
    if (reference === undefined || !reference.startsWith(LIST_REFERENCE_PREFIX)) return null
    const id = reference.slice(LIST_REFERENCE_PREFIX.length)
    return id === '' ? null : id
}

/** The unit ids an assignment List admits, dropping entries that name something other than a Location. */
export function assignedUnitIds(list: ResourceList): string[] {
    return (list.entry ?? []).flatMap((entry) => {
        const reference = entry.item.reference
        if (reference === undefined || !reference.startsWith(LOCATION_REFERENCE_PREFIX)) return []
        const id = reference.slice(LOCATION_REFERENCE_PREFIX.length)
        return id === '' ? [] : [id]
    })
}

/** One extension by url, matched exactly for HL7's own and on the suffix for this IG's. */
function findExtension(extensions: Extension[] | undefined, url: string): Extension | undefined {
    return extensions?.find((candidate) => candidate.url === url || candidate.url.endsWith(url))
}

/** Every geometry type this map has a mark for - two areal, two punctual. */
type DrawableGeometry =
    | BoundaryGeometry
    | { type: 'Point'; coordinates: number[] }
    | { type: 'MultiPoint'; coordinates: number[][] }

/**
 * Base64 to a geometry this map can draw, or null for anything it cannot.
 *
 * The payload is a GeoJSON Feature, so the geometry is one level in - but a hand-written registry
 * could put a bare geometry there, and reading both costs one branch.
 *
 * FOUR TYPES ARE DRAWABLE, not two. The extension's name says boundary and R4 documents it as one,
 * but what DHIS2 puts in it is its own `geometry` field, and DHIS2 keeps a district's polygon and a
 * facility's pin in that single field. So a Point here is a point, not a failure - reading only the
 * polygonal types is what made a registry whose facilities outnumber its districts four to one
 * report most of itself as broken. Null is kept for what it should always have meant: invalid
 * base64, valid base64 that is not JSON, a Feature with no geometry, or a type this map has no mark
 * for - a LineString, a GeometryCollection.
 */
function decodeGeometry(data: string): DrawableGeometry | null {
    let parsed: unknown
    try {
        parsed = JSON.parse(decodeBase64(data))
    } catch {
        return null
    }
    if (typeof parsed !== 'object' || parsed === null) return null
    const document = parsed as { type?: unknown; geometry?: unknown; coordinates?: unknown }
    const candidate =
        document.type === 'Feature' && typeof document.geometry === 'object' && document.geometry !== null
            ? (document.geometry as { type?: unknown; coordinates?: unknown })
            : document
    if (!Array.isArray(candidate.coordinates)) return null
    if (candidate.type === 'Polygon') return { type: 'Polygon', coordinates: candidate.coordinates as number[][][] }
    if (candidate.type === 'MultiPolygon') {
        return { type: 'MultiPolygon', coordinates: candidate.coordinates as number[][][][] }
    }
    if (candidate.type === 'Point') return { type: 'Point', coordinates: candidate.coordinates as number[] }
    if (candidate.type === 'MultiPoint') {
        return { type: 'MultiPoint', coordinates: candidate.coordinates as number[][] }
    }
    return null
}

/**
 * Base64 to a UTF-8 string.
 *
 * `atob` answers bytes as a latin-1 string, so a boundary whose Feature carries a non-ASCII place
 * name would arrive mojibaked without the re-decode. Names in `properties` are not read by this UI,
 * but a decoder that corrupts them is a trap for the next caller.
 */
function decodeBase64(data: string): string {
    const binary = atob(data)
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0))
    return new TextDecoder().decode(bytes)
}

/** Order two nodes the way the tree renders them - by the name a reader sees. */
function compareByName(left: OrgUnitNode, right: OrgUnitNode): number {
    return left.name.localeCompare(right.name)
}

/** Fill in `descendantCount` for a subtree, bottom up. */
function countDescendants(node: OrgUnitNode): number {
    let total = 0
    for (const child of node.children) total += 1 + countDescendants(child)
    node.descendantCount = total
    return total
}

/**
 * Detach any unit that is not reachable from a root, and re-root it.
 *
 * `partOf` describing a cycle would leave a set of nodes pointing at each other with no root above
 * them, which every recursive walk here would follow forever. Re-rooting the first unvisited member
 * of each such group leaves the branch renderable and visibly odd, which is the honest rendering of
 * a registry that says A is inside B is inside A.
 */
function breakCycles(roots: OrgUnitNode[], byId: Map<string, OrgUnitNode>): void {
    const reachable = new Set<string>()
    const visit = (node: OrgUnitNode) => {
        if (reachable.has(node.id)) return
        reachable.add(node.id)
        for (const child of node.children) visit(child)
    }
    for (const root of roots) visit(root)
    if (reachable.size === byId.size) return
    for (const node of byId.values()) {
        if (reachable.has(node.id)) continue
        const parent = node.parentId === null ? undefined : byId.get(node.parentId)
        if (parent !== undefined) parent.children = parent.children.filter((child) => child !== node)
        node.orphaned = true
        node.unresolvedParentId = node.parentId
        node.parentId = null
        roots.push(node)
        visit(node)
    }
}
