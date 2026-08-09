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

import type { Extension, Location, Questionnaire, ResourceList } from '@/lib/fhir'
import { formIdentifier, unescapeMarkup } from '@/lib/fhir'

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
 * The extension a boundary polygon travels on.
 *
 * This one is absolute rather than suffix-matched, because it is HL7's own and not this IG's -
 * `location-boundary-geojson` is the standard place for a Location's shape, and the DHIS2
 * generator uses it verbatim.
 */
export const BOUNDARY_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/location-boundary-geojson'

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
    /** How many units the registry publishes. */
    total: number
    /** How many of them name a parent this project never published. */
    orphanCount: number
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

/** Everything the registry knows about where its units are, plus what could not be read. */
export interface OrgUnitGeometry {
    boundaries: OrgUnitBoundary[]
    points: OrgUnitPoint[]
    /** Units publishing a boundary attachment this reader could not decode into a polygon. */
    skippedBoundaries: number
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
 */
export function buildOrgUnitTree(locations: Location[]): OrgUnitTree {
    const byId = new Map<string, OrgUnitNode>()
    for (const location of locations) {
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
    }
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

/** Whether one unit answers a filter - on its name, its id, or any identifier value it carries. */
export function matchesUnit(node: OrgUnitNode, lowercaseQuery: string): boolean {
    if (node.name.toLowerCase().includes(lowercaseQuery)) return true
    if (node.id.toLowerCase().includes(lowercaseQuery)) return true
    return (node.location.identifier ?? []).some((identifier) =>
        (identifier.value ?? '').toLowerCase().includes(lowercaseQuery),
    )
}

/** One unit's boundary polygon, decoded, or null when it publishes none this reader can read. */
export function boundaryOf(location: Location): OrgUnitBoundary | null {
    const unitId = location.id
    if (unitId === undefined || unitId === '') return null
    const data = findExtension(location.extension, BOUNDARY_EXTENSION_URL)?.valueAttachment?.data
    if (data === undefined || data === '') return null
    const geometry = decodeBoundaryGeometry(data)
    return geometry === null ? null : { unitId, geometry }
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
 * Decode every boundary and read every point the registry publishes.
 *
 * One pass over the whole set, because the map draws every shape at once and a per-unit decode on
 * selection would re-do the same base64 on every click. A unit whose attachment does not decode
 * into a polygon is counted rather than thrown: `skippedBoundaries` is what the page states, and
 * the other units keep their shapes.
 */
export function readGeometry(locations: Location[]): OrgUnitGeometry {
    const boundaries: OrgUnitBoundary[] = []
    const points: OrgUnitPoint[] = []
    let skippedBoundaries = 0
    for (const location of locations) {
        const attachment = findExtension(location.extension, BOUNDARY_EXTENSION_URL)?.valueAttachment
        if (attachment?.data !== undefined && attachment.data !== '') {
            const boundary = boundaryOf(location)
            if (boundary === null) skippedBoundaries += 1
            else boundaries.push(boundary)
        }
        const point = pointOf(location)
        if (point !== null) points.push(point)
    }
    return { boundaries, points, skippedBoundaries }
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

/**
 * Base64 to a boundary geometry, or null for anything this cannot read.
 *
 * The payload is a GeoJSON Feature, so the geometry is one level in - but a hand-written registry
 * could put a bare geometry there, and reading both costs one branch. Everything else - invalid
 * base64, valid base64 that is not JSON, JSON that is not a Feature, a geometry type with no
 * polygons in it - answers null, which the caller counts.
 */
function decodeBoundaryGeometry(data: string): BoundaryGeometry | null {
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
