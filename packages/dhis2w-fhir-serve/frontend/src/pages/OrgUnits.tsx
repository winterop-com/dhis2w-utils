import { Suspense, lazy, useCallback, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, MapPin, Search } from 'lucide-react'

import { IdentifierBadges } from '@/components/IdentifierBadges'
import { PageHeader, PageState } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import {
    formIdentifier,
    formTitle,
    type Location,
    type Questionnaire,
    type ResourceList,
} from '@/lib/fhir'
import {
    ancestorsOf,
    buildFormAssignments,
    buildOrgUnitTree,
    descendantIdsOf,
    hasGeometry,
    matchingUnitIds,
    readGeometry,
    reportableFormsAt,
    type OrgUnitNode,
    type OrgUnitTree,
} from '@/lib/orgunits'
import { identifierBadges } from '@/lib/terminology'
import { cn } from '@/lib/utils'

/**
 * MapLibre, and everything that draws with it, fetched only when this page opens.
 *
 * This is the frontend's one heavy dependency, and the reason it is heavy is that it ships a whole
 * WebGL rendering engine. A capture client that never opens the hierarchy must not pay for it, so
 * the import is deferred here rather than at the top of the module - which is what puts the engine
 * in its own chunk instead of in the entry bundle.
 */
const OrgUnitMap = lazy(async () => {
    const module = await import('@/components/OrgUnitMap')
    return { default: module.OrgUnitMap }
})

/** The query parameter one selected unit is shareable under. */
const UNIT_PARAM = 'unit'

/** How many children the detail panel names before it defers to the tree. */
const CHILD_PREVIEW = 8

/**
 * The reporting hierarchy: where a capture can happen, and which forms may happen there.
 *
 * THREE READS, ONE PAGE. `GET /Location` is the registry, `GET /Questionnaire` the forms, and
 * `GET /List` the assignment artifacts - and only the first of them is required for this page to be
 * useful. So the tree renders off the registry alone, and the forms section states its own state:
 * a project that published no assignment Lists still gets a tree, a map, and a correct "every form
 * is reportable here".
 *
 * THE SELECTION IS IN THE URL. `#/org-units?unit=DiszpKrYNg8` is a link that opens one facility
 * with its ancestors expanded and the map framed on it, which is what makes a unit something you
 * can send someone rather than a set of directions through a tree.
 *
 * WHAT THIS PAGE IS NOT. It is not an editor and not a picker. DHIS2 owns the hierarchy; this is
 * the view of what the guide published from it - which is the thing that decides whether a capture
 * the facade receives will be accepted, and the thing that is hardest to check by reading JSON.
 */
export function OrgUnits() {
    const registry = useFhirSearch<Location>('Location')
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const assignments = useFhirSearch<ResourceList>('List')
    const [parameters, setParameters] = useSearchParams()
    const [query, setQuery] = useState('')

    const tree = useMemo(() => buildOrgUnitTree(registry.resources), [registry.resources])
    const geometry = useMemo(() => readGeometry(registry.resources), [registry.resources])
    const assignmentIndex = useMemo(
        () => buildFormAssignments(forms.resources, assignments.resources),
        [forms.resources, assignments.resources],
    )
    const formsById = useMemo(() => {
        const found = new Map<string, Questionnaire>()
        for (const questionnaire of forms.resources) found.set(formIdentifier(questionnaire), questionnaire)
        return found
    }, [forms.resources])

    const requested = parameters.get(UNIT_PARAM) ?? ''
    const selected = tree.byId.get(requested) ?? null
    const filtered = useMemo(() => matchingUnitIds(tree, query), [tree, query])

    const select = useCallback(
        (unitId: string) => {
            const next = new URLSearchParams(parameters)
            next.set(UNIT_PARAM, unitId)
            // Replace rather than push: clicking through a tree is browsing one page, and a back
            // button that walks every unit visited is a worse answer than one that leaves.
            setParameters(next, { replace: true })
        },
        [parameters, setParameters],
    )

    const expanded = useMemo(() => {
        const open = new Set<string>(filtered)
        if (selected !== null) for (const ancestor of ancestorsOf(tree, selected.id)) open.add(ancestor.id)
        return open
    }, [filtered, selected, tree])

    return (
        <>
            <PageHeader
                title="Org units"
                description="The organisation units this guide published, as the hierarchy DHIS2 holds them in - what a capture may report for, and which forms it may report there."
            />

            <div className="grid gap-6 lg:grid-cols-[minmax(16rem,22rem)_1fr]">
                <section className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-base font-semibold">The hierarchy</h3>
                        {!registry.loading && registry.error === null && (
                            <span className="text-muted-foreground font-mono text-xs">
                                {tree.total} units
                            </span>
                        )}
                    </div>
                    <div className="relative">
                        <Search
                            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                            aria-hidden
                        />
                        <Input
                            className="pl-9"
                            aria-label="Filter organisation units"
                            placeholder="Filter by name, uid, or code"
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                        />
                    </div>
                    <PageState
                        loading={registry.loading}
                        error={registry.error}
                        empty={tree.total === 0}
                        emptyMessage="This project publishes no organisation units. `[generate.organisation_units]` in fhir.toml is what selects them - a `root` of nothing and a `max_level` of 0 publishes none."
                    >
                        <UnitTree
                            tree={tree}
                            selectedId={selected?.id ?? null}
                            expanded={expanded}
                            filtered={query.trim() === '' ? null : filtered}
                            onSelect={select}
                        />
                        {tree.orphanCount > 0 && (
                            <p className="text-muted-foreground text-xs">
                                {tree.orphanCount} unit{tree.orphanCount === 1 ? '' : 's'} name a parent
                                this project did not publish, so they are shown as roots. That is what a
                                selection with a `root` or a `max_level` looks like from below.
                            </p>
                        )}
                    </PageState>
                </section>

                <section className="min-w-0 space-y-6">
                    {selected === null ? (
                        <NothingSelected total={tree.total} loading={registry.loading} />
                    ) : (
                        <UnitDetail
                            tree={tree}
                            node={selected}
                            formsById={formsById}
                            reportable={reportableFormsAt(assignmentIndex, selected.id)}
                            unresolvedAssignmentFormIds={assignmentIndex.unresolvedAssignmentFormIds}
                            formsLoading={forms.loading || assignments.loading}
                            formsError={forms.error ?? assignments.error}
                            onSelect={select}
                        />
                    )}

                    <MapPanel
                        tree={tree}
                        geometry={geometry}
                        selected={selected}
                        loading={registry.loading}
                        onSelect={select}
                    />
                </section>
            </div>
        </>
    )
}

/** The tree itself: roots, and whatever the caller has opened below them. */
function UnitTree({
    tree,
    selectedId,
    expanded,
    filtered,
    onSelect,
}: {
    tree: OrgUnitTree
    selectedId: string | null
    expanded: Set<string>
    /** The ids a filter is limiting the tree to, or null when nothing is being filtered. */
    filtered: Set<string> | null
    onSelect: (unitId: string) => void
}) {
    // Expansion is the union of what the caller opened by hand and what the URL and the filter
    // imply - so a filter that matches a facility opens the districts above it without the reader
    // clicking three chevrons, and clearing the filter leaves their own expansions intact.
    const [opened, setOpened] = useState<Set<string>>(new Set())
    const toggle = useCallback((unitId: string) => {
        setOpened((previous) => {
            const next = new Set(previous)
            if (next.has(unitId)) next.delete(unitId)
            else next.add(unitId)
            return next
        })
    }, [])

    const roots = filtered === null ? tree.roots : tree.roots.filter((node) => filtered.has(node.id))

    if (roots.length === 0) {
        return (
            <p className="text-muted-foreground rounded-lg border px-4 py-8 text-sm">
                No unit matches that filter.
            </p>
        )
    }

    return (
        <ul className="show-scrollbars max-h-[32rem] overflow-y-auto rounded-lg border p-1">
            {roots.map((node) => (
                <UnitBranch
                    key={node.id}
                    node={node}
                    depth={0}
                    selectedId={selectedId}
                    opened={opened}
                    expanded={expanded}
                    filtered={filtered}
                    onToggle={toggle}
                    onSelect={onSelect}
                />
            ))}
        </ul>
    )
}

/**
 * One unit and, when it is open, its children.
 *
 * The children of a closed node are not rendered at all - which is the whole point of a lazily
 * expanded tree over a registry that runs to four figures. A district with two hundred facilities
 * costs one row until someone asks for it.
 */
function UnitBranch({
    node,
    depth,
    selectedId,
    opened,
    expanded,
    filtered,
    onToggle,
    onSelect,
}: {
    node: OrgUnitNode
    depth: number
    selectedId: string | null
    opened: Set<string>
    expanded: Set<string>
    filtered: Set<string> | null
    onToggle: (unitId: string) => void
    onSelect: (unitId: string) => void
}) {
    const hasChildren = node.children.length > 0
    const open = hasChildren && (opened.has(node.id) || expanded.has(node.id))
    const children = filtered === null ? node.children : node.children.filter((child) => filtered.has(child.id))
    const isSelected = node.id === selectedId

    return (
        <li>
            <div
                className={cn(
                    'flex items-center gap-1 rounded-md',
                    isSelected && 'bg-sidebar-accent text-sidebar-accent-foreground',
                )}
                style={{ paddingLeft: `${String(depth * 0.85)}rem` }}
            >
                {hasChildren ? (
                    <button
                        type="button"
                        aria-label={`${open ? 'Collapse' : 'Expand'} ${node.name}`}
                        aria-expanded={open}
                        onClick={() => onToggle(node.id)}
                        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 flex size-6 shrink-0 items-center justify-center rounded focus-visible:ring-[3px] focus-visible:outline-none"
                    >
                        {open ? (
                            <ChevronDown className="size-3.5" aria-hidden />
                        ) : (
                            <ChevronRight className="size-3.5" aria-hidden />
                        )}
                    </button>
                ) : (
                    <span className="size-6 shrink-0" aria-hidden />
                )}
                {/* The accessible name is the unit's name and nothing else: the level chip and the
                    detached marker are decoration on a row whose detail panel states both in full,
                    and folding them into the name would make every unit's name its level too. */}
                <button
                    type="button"
                    onClick={() => onSelect(node.id)}
                    aria-label={node.name}
                    aria-current={isSelected ? 'true' : undefined}
                    className="hover:bg-accent/40 focus-visible:ring-ring/50 flex min-w-0 flex-1 items-center gap-2 rounded px-1.5 py-1 text-left text-sm focus-visible:ring-[3px] focus-visible:outline-none"
                >
                    <span className="truncate">{node.name}</span>
                    {node.level !== null && (
                        <span className="text-muted-foreground shrink-0 font-mono text-[10px]" aria-hidden>
                            {node.level.code}
                        </span>
                    )}
                    {node.orphaned && (
                        <span
                            className="text-muted-foreground shrink-0 text-[10px]"
                            aria-hidden
                            title={`Its parent, ${node.unresolvedParentId ?? 'unknown'}, is not published here.`}
                        >
                            detached
                        </span>
                    )}
                </button>
            </div>
            {open && children.length > 0 && (
                <ul>
                    {children.map((child) => (
                        <UnitBranch
                            key={child.id}
                            node={child}
                            depth={depth + 1}
                            selectedId={selectedId}
                            opened={opened}
                            expanded={expanded}
                            filtered={filtered}
                            onToggle={onToggle}
                            onSelect={onSelect}
                        />
                    ))}
                </ul>
            )}
        </li>
    )
}

/** One unit, opened: what it is, where it sits, and what may be captured against it. */
function UnitDetail({
    tree,
    node,
    formsById,
    reportable,
    unresolvedAssignmentFormIds,
    formsLoading,
    formsError,
    onSelect,
}: {
    tree: OrgUnitTree
    node: OrgUnitNode
    formsById: Map<string, Questionnaire>
    reportable: { universalFormIds: string[]; restrictedFormIds: string[] }
    unresolvedAssignmentFormIds: string[]
    formsLoading: boolean
    formsError: string | null
    onSelect: (unitId: string) => void
}) {
    const chain = ancestorsOf(tree, node.id)
    const badges = identifierBadges(node.location.identifier)
    const shown = node.children.slice(0, CHILD_PREVIEW)

    return (
        <div className="space-y-6">
            <div className="space-y-3 rounded-lg border p-4">
                <div className="space-y-1">
                    <h3 className="text-lg font-semibold tracking-tight">{node.name}</h3>
                    {node.location.description !== undefined && (
                        <p className="text-muted-foreground text-sm">{node.location.description}</p>
                    )}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                    {node.level === null ? (
                        <Badge variant="outline" className="text-muted-foreground" data-testid="org-unit-level">
                            no level stated
                        </Badge>
                    ) : (
                        <Badge variant="secondary" data-testid="org-unit-level">
                            {node.level.display ?? node.level.code}
                            <span className="ml-1 font-mono text-[10px] opacity-70">{node.level.code}</span>
                        </Badge>
                    )}
                    <span className="text-muted-foreground text-sm">
                        {node.children.length} direct {node.children.length === 1 ? 'child' : 'children'}
                        {node.descendantCount > node.children.length
                            ? `, ${String(node.descendantCount)} below in all`
                            : ''}
                    </span>
                </div>

                <IdentifierBadges badges={badges} />

                {chain.length > 0 && (
                    <nav aria-label="Parent units" className="flex flex-wrap items-center gap-1 text-sm">
                        {chain.map((ancestor) => (
                            <span key={ancestor.id} className="flex items-center gap-1">
                                <button
                                    type="button"
                                    onClick={() => onSelect(ancestor.id)}
                                    className="text-primary hover:underline"
                                >
                                    {ancestor.name}
                                </button>
                                <span className="text-muted-foreground" aria-hidden>
                                    /
                                </span>
                            </span>
                        ))}
                        <span className="text-muted-foreground">{node.name}</span>
                    </nav>
                )}

                {node.orphaned && (
                    <p className="text-muted-foreground text-sm">
                        Its parent is{' '}
                        <span className="font-mono text-xs">
                            Location/{node.unresolvedParentId ?? 'unknown'}
                        </span>
                        , which this project does not publish - so it sits at the top of the served tree
                        rather than at the top of DHIS2's.
                    </p>
                )}

                {shown.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2">
                        {shown.map((child) => (
                            <Button
                                key={child.id}
                                variant="outline"
                                size="sm"
                                onClick={() => onSelect(child.id)}
                            >
                                {child.name}
                            </Button>
                        ))}
                        {node.children.length > shown.length && (
                            <span className="text-muted-foreground text-xs">
                                and {node.children.length - shown.length} more in the tree
                            </span>
                        )}
                    </div>
                )}
            </div>

            <ReportableForms
                formsById={formsById}
                reportable={reportable}
                unresolvedAssignmentFormIds={unresolvedAssignmentFormIds}
                loading={formsLoading}
                error={formsError}
            />
        </div>
    )
}

/**
 * Which forms may be captured against this unit.
 *
 * THE WORDING IS DHIS2'S. A form carrying no assignment artifact is **assigned everywhere**, and
 * one whose List names this unit is **assigned to this unit** - the two phrases a DHIS2 administrator
 * already uses for the same fact. Nothing here calls a form "unrestricted" or "universal": those
 * describe the artifact rather than the assignment, and the reader of this page is asking about the
 * assignment.
 *
 * THE ASYMMETRY IS THE POINT. Most forms are assigned everywhere, so listing them one by one at
 * every unit would bury the one or two that are not. The everywhere group collapses to a single
 * line with its count; the ones assigned to this unit by name are listed and linked, because those
 * are where "may this unit report this form" has an answer worth reading.
 */
function ReportableForms({
    formsById,
    reportable,
    unresolvedAssignmentFormIds,
    loading,
    error,
}: {
    formsById: Map<string, Questionnaire>
    reportable: { universalFormIds: string[]; restrictedFormIds: string[] }
    unresolvedAssignmentFormIds: string[]
    loading: boolean
    error: string | null
}) {
    const [showEverywhere, setShowEverywhere] = useState(false)
    const everywhere = reportable.universalFormIds.length
    const here = reportable.restrictedFormIds

    return (
        <section className="space-y-3">
            <div className="space-y-0.5">
                <h3 className="text-base font-semibold">Forms reportable here</h3>
                <p className="text-muted-foreground text-sm">
                    DHIS2 assigns each data set and program to organisation units. A form whose
                    assignment is narrower than the published registry names its units in a List; a
                    form carrying none is assigned everywhere.
                </p>
            </div>
            <PageState
                loading={loading}
                error={error}
                empty={everywhere === 0 && here.length === 0}
                emptyMessage="Nothing is assigned here, and nothing is assigned everywhere either - which means this project publishes no forms at all."
            >
                <Card>
                    <CardContent className="space-y-4 py-4">
                        {here.length > 0 && (
                            <div className="space-y-2">
                                <p className="text-sm font-medium">
                                    Assigned to this unit
                                    <span className="text-muted-foreground ml-2 font-mono text-xs">
                                        {here.length}
                                    </span>
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    {here.map((formId) => (
                                        <FormLink key={formId} formId={formId} formsById={formsById} />
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="space-y-2">
                            <button
                                type="button"
                                onClick={() => setShowEverywhere((open) => !open)}
                                aria-expanded={showEverywhere}
                                className="hover:text-foreground text-muted-foreground flex items-center gap-1.5 text-sm"
                            >
                                {showEverywhere ? (
                                    <ChevronDown className="size-3.5" aria-hidden />
                                ) : (
                                    <ChevronRight className="size-3.5" aria-hidden />
                                )}
                                {/* Two readings of the same set, because the sentence a unit with no
                                    named assignment wants is "all of them" and the sentence a unit
                                    with one wants is "and these others as well". */}
                                {here.length === 0
                                    ? `All ${String(everywhere)} published ${everywhere === 1 ? 'form is' : 'forms are'} assigned everywhere`
                                    : `${String(everywhere)} more assigned everywhere`}
                            </button>
                            {showEverywhere && (
                                <div className="flex flex-wrap gap-2">
                                    {reportable.universalFormIds.map((formId) => (
                                        <FormLink key={formId} formId={formId} formsById={formsById} />
                                    ))}
                                </div>
                            )}
                        </div>

                        {unresolvedAssignmentFormIds.length > 0 && (
                            <p className="text-muted-foreground text-xs">
                                {unresolvedAssignmentFormIds.length} form
                                {unresolvedAssignmentFormIds.length === 1 ? '' : 's'} name an assignment
                                List this server does not publish, and are read as assigned everywhere -
                                which is how the facade grades them too.
                            </p>
                        )}
                    </CardContent>
                </Card>
            </PageState>
        </section>
    )
}

/** One form, linked to the form itself - which is what a reader wants next from this page. */
function FormLink({ formId, formsById }: { formId: string; formsById: Map<string, Questionnaire> }) {
    const questionnaire = formsById.get(formId)
    return (
        <Button asChild variant="outline" size="sm">
            <Link to={`/forms/${formId}`}>
                {questionnaire === undefined ? formId : formTitle(questionnaire)}
            </Link>
        </Button>
    )
}

/**
 * The map, and every reason it might not be one.
 *
 * A registry with no coordinates at all gets no panel - an empty grey rectangle says nothing that
 * one sentence does not say better. A selected unit that has no geometry of its own keeps the map,
 * framed on the nearest ancestor that does, with a note: "we do not know where this is" is a fact
 * about the registry, and hiding the map would make it look like a rendering failure.
 */
function MapPanel({
    tree,
    geometry,
    selected,
    loading,
    onSelect,
}: {
    tree: OrgUnitTree
    geometry: ReturnType<typeof readGeometry>
    selected: OrgUnitNode | null
    loading: boolean
    onSelect: (unitId: string) => void
}) {
    const descendantUnitIds = useMemo(
        () => new Set(selected === null ? [] : descendantIdsOf(selected)),
        [selected],
    )
    const located = useMemo(() => {
        const found = new Set<string>()
        for (const boundary of geometry.boundaries) found.add(boundary.unitId)
        for (const point of geometry.points) found.add(point.unitId)
        return found
    }, [geometry])

    const focus = useMemo((): { unitIds: string[]; framedOn: OrgUnitNode | null } => {
        if (selected === null) return { unitIds: [], framedOn: null }
        const own = [selected.id, ...descendantUnitIds].filter((unitId) => located.has(unitId))
        if (own.length > 0) return { unitIds: own, framedOn: selected }
        // Nothing in this branch has coordinates. The nearest ancestor that does is the honest
        // frame - it is where this unit is, to the resolution the registry actually holds.
        const ancestor = ancestorsOf(tree, selected.id)
            .toReversed()
            .find((node) => located.has(node.id))
        if (ancestor === undefined) return { unitIds: [], framedOn: null }
        return { unitIds: [ancestor.id], framedOn: ancestor }
    }, [selected, descendantUnitIds, located, tree])

    if (loading) return null
    if (!hasGeometry(geometry)) {
        return (
            <section className="space-y-3">
                <h3 className="text-base font-semibold">On the map</h3>
                <Card>
                    <CardContent className="text-muted-foreground py-6 text-sm">
                        This registry holds no coordinates - DHIS2 has neither a point nor a boundary for
                        any of the published units, so there is nothing to draw.
                    </CardContent>
                </Card>
            </section>
        )
    }

    const selectedIsLocated = selected !== null && located.has(selected.id)

    return (
        <section className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-base font-semibold">On the map</h3>
                <span className="text-muted-foreground text-xs">
                    {geometry.boundaries.length} boundaries, {geometry.points.length} points - drawn from
                    this server alone, with no basemap
                </span>
            </div>
            <Suspense
                fallback={
                    <div className="bg-card text-muted-foreground flex h-[22rem] items-center justify-center rounded-lg border text-sm">
                        Loading the map renderer
                    </div>
                }
            >
                <OrgUnitMap
                    boundaries={geometry.boundaries}
                    points={geometry.points}
                    selectedUnitId={selected?.id ?? null}
                    descendantUnitIds={descendantUnitIds}
                    focusUnitIds={focus.unitIds}
                    onSelect={onSelect}
                />
            </Suspense>
            {selected !== null && !selectedIsLocated && (
                <p data-testid="org-unit-map-note" className="text-muted-foreground text-xs">
                    {focus.framedOn === null
                        ? `DHIS2 holds no geometry for ${selected.name}, and none for any unit above it, so the map shows the whole registry instead.`
                        : `DHIS2 holds no geometry for ${selected.name}, so the map is framed on ${focus.framedOn.name} - the nearest unit above it that has some.`}
                </p>
            )}
            {geometry.skippedBoundaries > 0 && (
                <p className="text-muted-foreground text-xs">
                    {geometry.skippedBoundaries} published{' '}
                    {geometry.skippedBoundaries === 1 ? 'boundary' : 'boundaries'} could not be decoded
                    into a polygon and {geometry.skippedBoundaries === 1 ? 'is' : 'are'} not drawn.
                </p>
            )}
        </section>
    )
}

/** What the right-hand side says before a unit is picked. */
function NothingSelected({ total, loading }: { total: number; loading: boolean }) {
    if (loading || total === 0) return null
    return (
        <Card>
            <CardContent className="text-muted-foreground flex items-center gap-3 py-6 text-sm">
                <MapPin className="size-4 shrink-0" aria-hidden />
                Pick a unit in the tree, or click a shape on the map. The one you pick goes into the
                address, so a unit is a link you can send.
            </CardContent>
        </Card>
    )
}
