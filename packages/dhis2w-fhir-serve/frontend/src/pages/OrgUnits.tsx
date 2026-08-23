import { Suspense, lazy, useCallback, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, MapPin, PanelRightClose, PanelRightOpen, Search } from 'lucide-react'
import { usePanelRef } from 'react-resizable-panels'

import { IdentifierBadges } from '@/components/IdentifierBadges'
import { MaintenanceLink } from '@/components/MaintenanceLink'
import { PageHeader, PageState } from '@/components/PageState'
import { LifecycleBadge } from '@/components/ReceiptBadges'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { useSpool, type SpoolState } from '@/hooks/use-spool'
import { useUiConfig } from '@/hooks/use-ui-config'
import { catalogueForms, isEventProgram, type ProgramGroup } from '@/lib/catalogue'
import { maintenanceTargetOf } from '@/lib/dhis2'
import { formIdentifier, formTitle, type Location, type Questionnaire, type ResourceList } from '@/lib/fhir'
import {
    ancestorsOf,
    buildFormAssignments,
    buildOrgUnitTree,
    descendantIdsOf,
    hasGeometry,
    levelLabel,
    matchingUnitIds,
    readGeometry,
    reportableFormsAt,
    unitExtent,
    type OrgUnitNode,
    type OrgUnitTree,
    type ReportableForms,
} from '@/lib/orgunits'
import {
    formatInstant,
    LIFECYCLE_LABELS,
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    type SpoolResponseSummary,
} from '@/lib/spool'
import { identifierBadges } from '@/lib/terminology'
import type { BasemapLayer } from '@/lib/uiconfig'
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

/** How many receipts the Captured here section names before it defers to the responses page. */
const RECENT_RECEIPTS = 5

/**
 * The width at which the page runs three panes: tree, map canvas, inspector rail.
 *
 * Below it, three panes would crush each other - even at their minimum sizes the tree and the rail
 * leave no map worth reading - so the page falls back to two columns with the selection's sections
 * behind tabs instead.
 */
const THREE_PANE_QUERY = '(min-width: 1100px)'

/**
 * The pane divider, invisible until pointed at.
 *
 * The bar is transparent at rest so the layout reads as three panes, not five columns; hovering,
 * dragging, or keyboard focus paints it. The `w-1.5` strip is also the pointer target - wide
 * enough to hit, narrow enough that the panes still sit close.
 */
const PANE_HANDLE =
    'mx-1 w-1.5 rounded-full bg-transparent transition-colors hover:bg-border active:bg-border focus-visible:bg-border'

/** The width the inspector rail keeps when collapsed: room for the expand control, nothing else. */
const RAIL_COLLAPSED_SIZE = '2.5rem'

/** Whether the viewport is wide enough for the three-pane layout, tracked live. */
function useThreePane(): boolean {
    const [wide, setWide] = useState(() => window.matchMedia(THREE_PANE_QUERY).matches)
    useEffect(() => {
        const media = window.matchMedia(THREE_PANE_QUERY)
        const onChange = () => setWide(media.matches)
        media.addEventListener('change', onChange)
        return () => media.removeEventListener('change', onChange)
    }, [])
    return wide
}

/**
 * The reporting hierarchy: where a capture can happen, and which forms may happen there.
 *
 * THREE READS AND THE SPOOL, ONE PAGE. `GET /Location` is the registry, `GET /Questionnaire` the
 * forms, `GET /List` the assignment artifacts, and `GET /spool` the receipts - and only the first
 * of them is required for this page to be useful. The tree and the map render off the registry
 * alone; every other section states its own absence.
 *
 * THE SELECTION IS IN THE URL. `#/organisation-units?unit=DiszpKrYNg8` is a link that opens one
 * facility with its ancestors expanded and the map framed on it, which is what makes an
 * organisation unit something you can send someone rather than a set of directions through a tree.
 *
 * THE SHAPE IS A GIS TOOL'S. Wide viewports run three resizable panes: the tree, the map as the
 * always-visible centre canvas, and a collapsible inspector rail carrying everything else about
 * the selection - identity, the forms shelved by kind, the captures this server received, the
 * children below it. Below `THREE_PANE_QUERY` the page falls back to two columns with the
 * selection's sections behind tabs (Map the default).
 *
 * WHAT THIS PAGE IS NOT. It is not an editor and not a picker. DHIS2 owns the hierarchy; this is
 * the view of what the guide published from it - which is the thing that decides whether a capture
 * the facade receives will be accepted, and the thing that is hardest to check by reading JSON.
 */
export function OrgUnits() {
    const registry = useFhirSearch<Location>('Location')
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const assignments = useFhirSearch<ResourceList>('List')
    const spool = useSpool()
    const settings = useUiConfig()
    const [parameters, setParameters] = useSearchParams()
    const [query, setQuery] = useState('')
    const threePane = useThreePane()
    // The rail choice lives for this mount of the page and nowhere else - deliberately plain
    // state, not storage: an inspector someone shut is not a standing preference the way the
    // app sidebar's width is. It starts open only when the mount already has a selection - a
    // `?unit=` deep link arrives selected and deserves the open rail; a plain visit starts with
    // the tree and the map, and the rail opens when something is picked.
    const [railOpen, setRailOpen] = useState(() => (parameters.get(UNIT_PARAM) ?? '') !== '')
    // The rail pane's collapse is owned by the panel so that the chevron and dragging the handle
    // shut agree; `railOpen` mirrors it (via onResize below) and survives breakpoint crossings.
    const railPanel = usePanelRef()

    // The panel mounts expanded (its defaultSize) and is collapsed before first paint when the
    // mirror says closed - which is also what re-collapses it when the viewport crosses back over
    // the three-pane breakpoint. Collapsing an already-collapsed panel is a no-op, so the mirror
    // updating from onResize never loops this.
    useLayoutEffect(() => {
        if (threePane && !railOpen) railPanel.current?.collapse()
    }, [threePane, railOpen, railPanel])

    const toggleRail = useCallback(() => {
        const panel = railPanel.current
        if (panel === null) return
        if (panel.isCollapsed()) panel.expand()
        else panel.collapse()
    }, [railPanel])

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
    // Arriving with no unit named selects the hierarchy's root by default - the page then opens
    // framing the country with the tree anchored, not an empty prompt. The default is a view,
    // not a user act: it neither writes ?unit= nor opens the inspector rail (railOpen keys on
    // the parameter alone), so the first click a person makes still behaves like a first click.
    const selected = tree.byId.get(requested) ?? (requested === '' ? (tree.roots[0] ?? null) : null)
    const filtered = useMemo(() => matchingUnitIds(tree, query), [tree, query])
    const catalog = useMemo(
        () =>
            selected === null ? null : catalogueUnitForms(reportableFormsAt(assignmentIndex, selected.id), formsById),
        [selected, assignmentIndex, formsById],
    )

    const select = useCallback(
        (unitId: string) => {
            const next = new URLSearchParams(parameters)
            next.set(UNIT_PARAM, unitId)
            // Replace rather than push: clicking through a tree is browsing one page, and a back
            // button that walks every unit visited is a worse answer than one that leaves.
            setParameters(next, { replace: true })
            // A selection is a question about an organisation unit, so the inspector opens to
            // answer it even when it was collapsed - collapsing is a view choice, not a standing
            // instruction. The state covers the narrow layout; the panel call covers the pane.
            setRailOpen(true)
            railPanel.current?.expand()
        },
        [parameters, setParameters, railPanel],
    )

    const expanded = useMemo(() => {
        const open = new Set<string>(filtered)
        // The selected unit's own row opens too, not just its ancestors: selecting something means
        // wanting what is under it - which is also what puts the districts on screen when the page
        // opens on its default root selection.
        if (selected !== null) {
            open.add(selected.id)
            for (const ancestor of ancestorsOf(tree, selected.id)) open.add(ancestor.id)
        }
        return open
    }, [filtered, selected, tree])

    // The tree pane, shared by both layouts: a pane of the three-pane run, a column of the
    // narrow grid.
    const hierarchyPane = (
        <section className="flex h-full min-h-0 flex-1 flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold">Hierarchy</h3>
                {!registry.loading && registry.error === null && (
                    <span className="text-muted-foreground text-xs">
                        {tree.total.toLocaleString('en')} organisation unit{tree.total === 1 ? '' : 's'}
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
                emptyMessage={
                    <>
                        This project publishes no organisation units.{' '}
                        <code className="font-mono">[generate.organisation_units]</code> in{' '}
                        <code className="font-mono">fhir.toml</code> is what selects them - a{' '}
                        <code className="font-mono">root</code> of nothing and a{' '}
                        <code className="font-mono">max_level</code> of 0 publishes none.
                    </>
                }
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
                        {tree.orphanCount} organisation unit{tree.orphanCount === 1 ? '' : 's'} name a
                        parent this project did not publish, so they are shown as roots. That is what a
                        selection with a <code className="font-mono">root</code> or a{' '}
                        <code className="font-mono">max_level</code> looks like from below.
                    </p>
                )}
            </PageState>
        </section>
    )

    return (
        // The one page in this app that claims the viewport rather than growing to its content:
        // the map is worth more the bigger it is, and a fixed-height box with dead space under it
        // on a tall screen is the shape this replaced.
        <div className="flex min-h-0 flex-1 flex-col">
            <PageHeader
                title="Organisation units"
                description="The organisation units this implementation guide publishes, as the hierarchy the DHIS2 instance holds them in - what a capture may report for, and which forms it may report there."
            />

            {threePane ? (
                // Three resizable panes. The sizes are per-mount state, same posture as the rail
                // choice - deliberately not persisted: a width dragged for one reading session is
                // not a standing preference. The `min-h` floor is what keeps a short viewport
                // scrolling `main` instead of crushing the panes - a panel group clips its
                // content, so without the floor nothing would ever overflow.
                <ResizablePanelGroup className="min-h-[30rem] flex-1">
                    <ResizablePanel
                        id="hierarchy"
                        defaultSize="22%"
                        minSize="15%"
                        maxSize="40%"
                        className="flex min-h-0 flex-col"
                    >
                        {hierarchyPane}
                    </ResizablePanel>
                    <ResizableHandle className={PANE_HANDLE} />
                    {/* The centre canvas. At this width the map is never behind anything:
                        collapsing the rail hands it the rail's width too. */}
                    <ResizablePanel id="map" minSize="30%" className="flex min-h-0 min-w-0 flex-col">
                        <section className="flex h-full min-w-0 flex-col">
                            <MapPanel
                                tree={tree}
                                geometry={geometry}
                                selected={selected}
                                loading={registry.loading}
                                onSelect={select}
                                basemaps={settings.config.basemaps}
                                settingsLoading={settings.loading}
                            />
                        </section>
                    </ResizablePanel>
                    <ResizableHandle className={PANE_HANDLE} />
                    {/* `collapsible` is what makes the chevron and dragging the handle shut agree:
                        both land the pane on RAIL_COLLAPSED_SIZE, and onResize keeps the mirror
                        state true to whichever control moved it. */}
                    <ResizablePanel
                        id="rail"
                        collapsible
                        collapsedSize={RAIL_COLLAPSED_SIZE}
                        defaultSize="24%"
                        minSize="18%"
                        maxSize="40%"
                        panelRef={railPanel}
                        onResize={() => {
                            const panel = railPanel.current
                            if (panel !== null) setRailOpen(!panel.isCollapsed())
                        }}
                        className="flex min-h-0 flex-col"
                    >
                        <InspectorRail open={railOpen} onToggle={toggleRail}>
                            {selected === null || catalog === null ? (
                                <NothingSelected total={tree.total} loading={registry.loading} />
                            ) : (
                                <>
                                    <UnitHeader
                                        tree={tree}
                                        node={selected}
                                        onSelect={select}
                                        dhis2BaseUrl={settings.config.dhis2_base_url}
                                    />
                                    <FormCatalogSections
                                        catalog={catalog}
                                        published={formsById.size}
                                        unresolvedAssignmentFormIds={assignmentIndex.unresolvedAssignmentFormIds}
                                        loading={forms.loading || assignments.loading}
                                        error={forms.error ?? assignments.error}
                                        dhis2BaseUrl={settings.config.dhis2_base_url}
                                    />
                                    <CapturedHere node={selected} formsById={formsById} spool={spool} />
                                    <UnitChildren key={selected.id} node={selected} onSelect={select} />
                                </>
                            )}
                        </InspectorRail>
                    </ResizablePanel>
                </ResizablePanelGroup>
            ) : (
                // The narrow fallback: two columns, and the selection's sections behind tabs.
                // `flex-1` without `min-h-0`: the row takes the leftover height when there is any -
                // which is what the map grows into - and floors at its own content when there is
                // not, so a short viewport scrolls `main` instead of crushing the panels.
                <div className="grid flex-1 gap-6 lg:grid-cols-[minmax(16rem,22rem)_1fr]">
                    {hierarchyPane}
                    <section className="flex min-w-0 flex-col gap-6">
                        {selected === null || catalog === null ? (
                            <>
                                <NothingSelected total={tree.total} loading={registry.loading} />
                                <MapPanel
                                    tree={tree}
                                    geometry={geometry}
                                    selected={null}
                                    loading={registry.loading}
                                    onSelect={select}
                                    basemaps={settings.config.basemaps}
                                    settingsLoading={settings.loading}
                                />
                            </>
                        ) : (
                            <>
                                <UnitHeader
                                    tree={tree}
                                    node={selected}
                                    onSelect={select}
                                    dhis2BaseUrl={settings.config.dhis2_base_url}
                                />
                                <UnitTabs
                                    tree={tree}
                                    node={selected}
                                    geometry={geometry}
                                    catalog={catalog}
                                    published={formsById.size}
                                    unresolvedAssignmentFormIds={assignmentIndex.unresolvedAssignmentFormIds}
                                    formsLoading={forms.loading || assignments.loading}
                                    formsError={forms.error ?? assignments.error}
                                    registryLoading={registry.loading}
                                    basemaps={settings.config.basemaps}
                                    settingsLoading={settings.loading}
                                    formsById={formsById}
                                    spool={spool}
                                    onSelect={select}
                                    dhis2BaseUrl={settings.config.dhis2_base_url}
                                />
                            </>
                        )}
                    </section>
                </div>
            )}
        </div>
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
    // A hand toggle is an OVERRIDE over what the URL and the filter imply, not a union member:
    // the chevron opens a closed branch and closes an open one, whichever authority opened it -
    // so the default-expanded root remains the reader's to fold up. A filter that matches a
    // facility still opens the districts above it without three chevron clicks, and clearing
    // the filter leaves the reader's own toggles intact.
    const [overrides, setOverrides] = useState<Map<string, boolean>>(new Map())
    const toggle = useCallback((unitId: string, isOpen: boolean) => {
        setOverrides((previous) => new Map(previous).set(unitId, !isOpen))
    }, [])

    // A new selection must be visible whatever was folded up before it: any closed-override on
    // the selected unit or its ancestors is stale the moment the selection lands, so it is
    // dropped rather than left to hide the row the page is about.
    useEffect(() => {
        if (selectedId === null) return
        setOverrides((previous) => {
            const chain = [selectedId, ...ancestorsOf(tree, selectedId).map((ancestor) => ancestor.id)]
            const stale = chain.filter((unitId) => previous.get(unitId) === false)
            if (stale.length === 0) return previous
            const next = new Map(previous)
            for (const unitId of stale) next.delete(unitId)
            return next
        })
    }, [selectedId, tree])

    const roots = filtered === null ? tree.roots : tree.roots.filter((node) => filtered.has(node.id))

    if (roots.length === 0) {
        return (
            <p className="text-muted-foreground rounded-lg border px-4 py-8 text-sm">
                No organisation unit matches that filter.
            </p>
        )
    }

    return (
        // `min-h-0` is what lets this shrink below its content so the overflow is the list's own
        // scrollbar rather than the page's.
        <ul className="show-scrollbars min-h-0 flex-1 overflow-y-auto rounded-lg border p-1">
            {roots.map((node) => (
                <UnitBranch
                    key={node.id}
                    node={node}
                    depth={0}
                    selectedId={selectedId}
                    overrides={overrides}
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
    overrides,
    expanded,
    filtered,
    onToggle,
    onSelect,
}: {
    node: OrgUnitNode
    depth: number
    selectedId: string | null
    /** Hand toggles, winning over `expanded`: true holds a branch open, false holds it closed. */
    overrides: Map<string, boolean>
    expanded: Set<string>
    filtered: Set<string> | null
    onToggle: (unitId: string, isOpen: boolean) => void
    onSelect: (unitId: string) => void
}) {
    const hasChildren = node.children.length > 0
    const open = hasChildren && (overrides.get(node.id) ?? expanded.has(node.id))
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
                        onClick={() => onToggle(node.id, open)}
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
                    detached marker are decoration on a row whose inspector states both in full,
                    and folding them into the name would make every unit's name its level too. */}
                <button
                    type="button"
                    onClick={() => onSelect(node.id)}
                    aria-label={node.name}
                    aria-current={isSelected ? 'true' : undefined}
                    className="hover:bg-accent/40 focus-visible:ring-ring/50 flex min-w-0 flex-1 items-center gap-2 rounded px-1.5 py-1 text-left text-sm focus-visible:ring-[3px] focus-visible:outline-none"
                >
                    {/* A tree row stays one line, so the name may truncate - the title carries
                        the full name for exactly that case. */}
                    <span className="truncate" title={node.name}>
                        {node.name}
                    </span>
                    {/* The level is spelled the way the panel beside it spells the level, because
                        it is the same fact: `levelLabel` is where that rule lives. */}
                    {node.level !== null && (
                        <span className="text-muted-foreground shrink-0 text-[10px]" aria-hidden>
                            {levelLabel(node.level)}
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
                            overrides={overrides}
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

/**
 * The right rail: everything about the selected organisation unit that is not the map.
 *
 * STACKED SECTIONS, NOT TABS, deliberately: at rail widths, tab triggers would cost a row to say
 * what four short headings already say, while hiding most of the content behind clicks. A rail
 * this narrow reads best as one scroll with quiet headings. NO HEADING OF ITS OWN: the rail opens
 * with the selected organisation unit's name and level, and that compact header is the heading -
 * a generic label above it would state nothing the header does not. The collapse toggle mirrors
 * the main sidebar's.
 */
function InspectorRail({
    open,
    onToggle,
    children,
}: {
    open: boolean
    onToggle: () => void
    children: ReactNode
}) {
    if (!open) {
        return (
            <aside aria-label="Organisation unit details" className="flex h-full flex-col items-center">
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={onToggle}
                            aria-label="Expand the details panel"
                            className="text-muted-foreground hover:text-foreground"
                        >
                            <PanelRightOpen className="size-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="left">Expand the details panel</TooltipContent>
                </Tooltip>
            </aside>
        )
    }

    return (
        <aside aria-label="Organisation unit details" className="flex h-full min-h-0 flex-col gap-1">
            <div className="-mb-1 flex items-center justify-end">
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={onToggle}
                            aria-label="Collapse the details panel"
                            className="text-muted-foreground hover:text-foreground"
                        >
                            <PanelRightClose className="size-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="left">Collapse the details panel</TooltipContent>
                </Tooltip>
            </div>
            {/* The rail scrolls on its own; the map beside it never does. */}
            <div className="show-scrollbars min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">{children}</div>
        </aside>
    )
}

/**
 * The identity strip: what this unit is and where it sits.
 *
 * Name, one line of description, the level, the identifiers, and the clickable parent chain - the
 * "where am I" a reader needs whatever they came for. Everything else lives in a section or a tab.
 */
function UnitHeader({
    tree,
    node,
    onSelect,
    dhis2BaseUrl,
}: {
    tree: OrgUnitTree
    node: OrgUnitNode
    onSelect: (unitId: string) => void
    /** The DHIS2 instance this guide was generated from, or null when the server named none. */
    dhis2BaseUrl: string | null
}) {
    const chain = ancestorsOf(tree, node.id)
    const badges = identifierBadges(node.location.identifier)

    return (
        <div className="space-y-2 rounded-lg border p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h3 className="text-lg font-semibold tracking-tight">{node.name}</h3>
                {/* The way out to the instance, beside the name it belongs to. Absent entirely
                    when the server named no instance, which is the compiled-guide posture. */}
                <MaintenanceLink
                    baseUrl={dhis2BaseUrl}
                    object="organisationUnit"
                    uid={node.id}
                    subject={node.name}
                    className="self-center"
                />
                {node.level === null ? (
                    <Badge variant="outline" className="text-muted-foreground" data-testid="org-unit-level">
                        no level stated
                    </Badge>
                ) : (
                    // One spelling of one fact, and `levelLabel` is the one place it is decided.
                    // The machine casing (`level-1`) is the concept code and stays where codes go:
                    // the identifier badges below, never beside its own translation.
                    <Badge variant="secondary" data-testid="org-unit-level">
                        {levelLabel(node.level)}
                    </Badge>
                )}
            </div>
            {node.location.description !== undefined && (
                <p className="text-muted-foreground text-sm">{node.location.description}</p>
            )}
            <IdentifierBadges badges={badges} />
            {node.orphaned && (
                <p className="text-muted-foreground text-sm">
                    Its parent is{' '}
                    <span className="font-mono text-xs">
                        Location/{node.unresolvedParentId ?? 'unknown'}
                    </span>
                    , which this project does not publish - so it sits at the top of the served tree
                    rather than where the DHIS2 instance holds it.
                </p>
            )}
            {chain.length > 0 && (
                <nav aria-label="Parent organisation units" className="flex flex-wrap items-center gap-1 text-sm">
                    {chain.map((ancestor) => (
                        <span key={ancestor.id} className="flex items-center gap-1">
                            <button
                                type="button"
                                onClick={() => onSelect(ancestor.id)}
                                className="interactive-link"
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
        </div>
    )
}

/** Which of the three narrow-layout views of one unit is open. */
type UnitTab = 'map' | 'forms' | 'details'

/**
 * The narrow fallback: the selection's sections behind tabs, under the identity strip.
 *
 * THE TAB IS VIEW STATE, NOT ADDRESS. `?unit=` in the URL is the selection and stays shareable;
 * which tab is open is deliberately not a query parameter, and every selection change opens on
 * Map. The rule is the derivation below - a stored choice counts only for the unit it was made
 * on - rather than an effect, so a new selection never renders the old unit's tab first.
 */
function UnitTabs({
    tree,
    node,
    geometry,
    catalog,
    published,
    unresolvedAssignmentFormIds,
    formsLoading,
    formsError,
    registryLoading,
    basemaps,
    settingsLoading,
    formsById,
    spool,
    onSelect,
    dhis2BaseUrl,
}: {
    tree: OrgUnitTree
    node: OrgUnitNode
    geometry: ReturnType<typeof readGeometry>
    catalog: UnitFormCatalog
    published: number
    unresolvedAssignmentFormIds: string[]
    formsLoading: boolean
    formsError: string | null
    registryLoading: boolean
    basemaps: BasemapLayer[]
    settingsLoading: boolean
    formsById: Map<string, Questionnaire>
    spool: SpoolState
    onSelect: (unitId: string) => void
    dhis2BaseUrl: string | null
}) {
    const [choice, setChoice] = useState<{ unitId: string; tab: UnitTab }>({ unitId: node.id, tab: 'map' })
    const tab = choice.unitId === node.id ? choice.tab : 'map'

    return (
        <Tabs
            value={tab}
            onValueChange={(value) => setChoice({ unitId: node.id, tab: value as UnitTab })}
            className="flex-1 gap-3"
        >
            <TabsList>
                <TabsTrigger value="map">Map</TabsTrigger>
                <TabsTrigger value="forms">Forms</TabsTrigger>
                <TabsTrigger value="details">Details</TabsTrigger>
            </TabsList>
            {/* `forceMount` + hidden rather than unmount: a tab flip must not tear down the WebGL
                engine and rebuild the whole scene on the way back. Hidden, the container is
                zero-sized; the ResizeObserver inside OrgUnitMap picks the size back up the moment
                the tab returns. */}
            <TabsContent value="map" forceMount className="flex flex-col data-[state=inactive]:hidden">
                <MapPanel
                    tree={tree}
                    geometry={geometry}
                    selected={node}
                    loading={registryLoading}
                    onSelect={onSelect}
                    basemaps={basemaps}
                    settingsLoading={settingsLoading}
                />
            </TabsContent>
            <TabsContent value="forms">
                <FormCatalogSections
                    catalog={catalog}
                    published={published}
                    unresolvedAssignmentFormIds={unresolvedAssignmentFormIds}
                    loading={formsLoading}
                    error={formsError}
                    dhis2BaseUrl={dhis2BaseUrl}
                />
            </TabsContent>
            <TabsContent value="details" className="space-y-4">
                <UnitChildren key={node.id} node={node} onSelect={onSelect} />
                <CapturedHere node={node} formsById={formsById} spool={spool} />
            </TabsContent>
        </Tabs>
    )
}

/** A stable empty set: the mini tree implies no expansions - only its own chevrons open rows. */
const NO_IMPLIED_EXPANSIONS = new Set<string>()

/**
 * The subtree below the selected organisation unit, in the same row idiom as the hierarchy pane.
 *
 * Direct children render collapsed; a chevron opens a branch on demand, so a district with two
 * hundred facilities costs its own rows only when asked - the same lazy rendering as the main
 * tree. Selecting a row re-roots this view to that organisation unit, exactly like a tree click.
 *
 * Mount it keyed on the selected unit's id, so one subtree's expansions never leak into the next
 * selection's.
 */
function UnitChildren({ node, onSelect }: { node: OrgUnitNode; onSelect: (unitId: string) => void }) {
    // The same override map the main tree keeps - with no implied expansions here, an absent
    // entry simply means closed.
    const [overrides, setOverrides] = useState<Map<string, boolean>>(new Map())
    const toggle = useCallback((unitId: string, isOpen: boolean) => {
        setOverrides((previous) => new Map(previous).set(unitId, !isOpen))
    }, [])

    const direct = node.children.length
    return (
        <section className="space-y-2" data-testid="org-unit-children">
            {/* The space is load-bearing: without it the heading and the count beside it are read
                off as the one word "Children4 direct". */}
            <h4 className="text-sm font-semibold">
                Children{' '}
                {direct > 0 && (
                    <span className="text-muted-foreground ml-2 text-xs font-normal">
                        {direct.toLocaleString('en')} direct
                        {node.descendantCount > direct
                            ? `, ${node.descendantCount.toLocaleString('en')} below`
                            : ''}
                    </span>
                )}
            </h4>
            {direct === 0 ? (
                <p className="text-muted-foreground text-sm">
                    This organisation unit has no children - it is a leaf of the published hierarchy.
                </p>
            ) : (
                <ul className="rounded-lg border p-1">
                    {node.children.map((child) => (
                        <UnitBranch
                            key={child.id}
                            node={child}
                            depth={0}
                            selectedId={null}
                            overrides={overrides}
                            expanded={NO_IMPLIED_EXPANSIONS}
                            filtered={null}
                            onToggle={toggle}
                            onSelect={onSelect}
                        />
                    ))}
                </ul>
            )}
        </section>
    )
}

/** The forms reportable at one unit, shelved the way DHIS2 shelves them. */
interface UnitFormCatalog {
    dataSets: Questionnaire[]
    programs: ProgramGroup[]
    /**
     * Person-only registration forms reportable here.
     *
     * A shelf of its own for the reason the Forms page gives, and one that lands harder in this
     * rail: DHIS2 hangs an assignment on a data set and on a program, never on a tracked entity
     * type, so a person-only form is assigned everywhere by construction and appears at every unit.
     * Folded into Programs it would be a row under a heading naming something it does not belong to.
     */
    people: Questionnaire[]
    /** Reportable forms declaring no kind, or ids the store no longer serves - listed, not hidden. */
    other: { formId: string; questionnaire: Questionnaire | null }[]
    /** The form ids an assignment List names this unit on; every other entry is assigned everywhere. */
    assignedHere: Set<string>
}

/**
 * Shelve the reportable forms by DHIS2 kind, through the one grouping algorithm in lib/catalogue.
 *
 * What this adds over `catalogueForms` is the resolution step the rail needs: the reportable list
 * is form ids, and an id the store no longer serves still has to be listed rather than hidden -
 * so unresolved ids join the kindless forms in `other`, keyed by the id the assignment names.
 */
function catalogueUnitForms(reportable: ReportableForms, formsById: Map<string, Questionnaire>): UnitFormCatalog {
    const served: Questionnaire[] = []
    const missingFormIds: string[] = []
    for (const formId of [...reportable.restrictedFormIds, ...reportable.universalFormIds]) {
        const questionnaire = formsById.get(formId)
        if (questionnaire === undefined) missingFormIds.push(formId)
        else served.push(questionnaire)
    }

    const catalog = catalogueForms(served)
    const other: { formId: string; questionnaire: Questionnaire | null }[] = [
        ...catalog.unclassified.map((questionnaire) => ({
            formId: formIdentifier(questionnaire),
            questionnaire: questionnaire as Questionnaire | null,
        })),
        ...missingFormIds.map((formId) => ({ formId, questionnaire: null })),
    ]

    return {
        dataSets: catalog.dataSets,
        programs: catalog.programs,
        people: catalog.people,
        other: other.toSorted((left, right) => left.formId.localeCompare(right.formId)),
        assignedHere: new Set(reportable.restrictedFormIds),
    }
}

/**
 * The reportable forms as rail sections: Data sets, Programs, People, and whatever fits none.
 *
 * THE WORDING IS DHIS2'S. A form whose assignment List names this unit carries the badge; a form
 * carrying no artifact is assigned everywhere, so it appears plainly - which keeps the one or two
 * forms with a real assignment answer from drowning among the ones that are everywhere by default.
 */
function FormCatalogSections({
    catalog,
    published,
    unresolvedAssignmentFormIds,
    loading,
    error,
    dhis2BaseUrl,
}: {
    catalog: UnitFormCatalog
    published: number
    unresolvedAssignmentFormIds: string[]
    loading: boolean
    error: string | null
    dhis2BaseUrl: string | null
}) {
    const empty =
        catalog.dataSets.length === 0 &&
        catalog.programs.length === 0 &&
        catalog.people.length === 0 &&
        catalog.other.length === 0

    return (
        // The testid scopes assertions to the shelves: a receipt in Captured here legitimately
        // carries the same form title as a shelf row, and the two must be tellable apart.
        <div data-testid="org-unit-forms">
            <PageState
                loading={loading}
                error={error}
                empty={empty}
                // Two different absences: a project with no forms at all, and a unit that every
                // published assignment happens to leave out. Only the first may say "no forms".
                emptyMessage={
                    published > 0
                        ? `None of the ${String(published)} published ${published === 1 ? 'form' : 'forms'} is assigned to this organisation unit.`
                        : 'Nothing is assigned here, and nothing is assigned everywhere either - which means this project publishes no forms at all.'
                }
            >
                <div className="space-y-4">
                    {catalog.dataSets.length > 0 && (
                        <section className="space-y-2">
                            {/* Two facts, said as two: the count is its own element for the mono
                                face it is set in, and a name read off the elements alone would run
                                the shelf and its count together into "Data sets26". */}
                            <h4
                                className="text-sm font-semibold"
                                aria-label={`Data sets, ${String(catalog.dataSets.length)}`}
                            >
                                Data sets
                                <span className="text-muted-foreground ml-2 font-mono text-xs">
                                    {catalog.dataSets.length}
                                </span>
                            </h4>
                            <ul className="space-y-1">
                                {catalog.dataSets.map((questionnaire) => (
                                    <FormRow
                                        key={formIdentifier(questionnaire)}
                                        formId={formIdentifier(questionnaire)}
                                        questionnaire={questionnaire}
                                        assignedHere={catalog.assignedHere.has(formIdentifier(questionnaire))}
                                        dhis2BaseUrl={dhis2BaseUrl}
                                    />
                                ))}
                            </ul>
                        </section>
                    )}

                    {catalog.programs.length > 0 && (
                        <section className="space-y-2">
                            <h4
                                className="text-sm font-semibold"
                                aria-label={`Programs, ${String(catalog.programs.length)}`}
                            >
                                Programs
                                <span className="text-muted-foreground ml-2 font-mono text-xs">
                                    {catalog.programs.length}
                                </span>
                            </h4>
                            <ul className="space-y-2">
                                {catalog.programs.map((group) => (
                                    <ProgramRows
                                        key={group.key}
                                        group={group}
                                        assignedHere={catalog.assignedHere}
                                        dhis2BaseUrl={dhis2BaseUrl}
                                    />
                                ))}
                            </ul>
                        </section>
                    )}

                    {catalog.people.length > 0 && (
                        <section className="space-y-2">
                            <h4
                                className="text-sm font-semibold"
                                aria-label={`People, ${String(catalog.people.length)}`}
                            >
                                People
                                <span className="text-muted-foreground ml-2 font-mono text-xs">
                                    {catalog.people.length}
                                </span>
                            </h4>
                            <p className="text-muted-foreground text-xs">
                                Registers a person here without enrolling them in a program.
                            </p>
                            <ul className="space-y-1">
                                {catalog.people.map((questionnaire) => (
                                    <FormRow
                                        key={formIdentifier(questionnaire)}
                                        formId={formIdentifier(questionnaire)}
                                        questionnaire={questionnaire}
                                        assignedHere={catalog.assignedHere.has(formIdentifier(questionnaire))}
                                        dhis2BaseUrl={dhis2BaseUrl}
                                    />
                                ))}
                            </ul>
                        </section>
                    )}

                    {catalog.other.length > 0 && (
                        <section className="space-y-2">
                            <h4
                                className="text-sm font-semibold"
                                aria-label={`Other forms, ${String(catalog.other.length)}`}
                            >
                                Other forms
                                <span className="text-muted-foreground ml-2 font-mono text-xs">
                                    {catalog.other.length}
                                </span>
                            </h4>
                            <ul className="space-y-1">
                                {catalog.other.map((entry) => (
                                    <FormRow
                                        key={entry.formId}
                                        formId={entry.formId}
                                        questionnaire={entry.questionnaire}
                                        assignedHere={catalog.assignedHere.has(entry.formId)}
                                        dhis2BaseUrl={dhis2BaseUrl}
                                    />
                                ))}
                            </ul>
                        </section>
                    )}

                    {unresolvedAssignmentFormIds.length > 0 && (
                        <p className="text-muted-foreground text-xs">
                            {unresolvedAssignmentFormIds.length} form
                            {unresolvedAssignmentFormIds.length === 1 ? '' : 's'} name an assignment
                            List this server does not publish, and are read as assigned everywhere -
                            which is how the facade grades them too.
                        </p>
                    )}
                </div>
            </PageState>
        </div>
    )
}

/** One program's rows: an event program is its one form; a tracker program groups its stages. */
function ProgramRows({
    group,
    assignedHere,
    dhis2BaseUrl,
}: {
    group: ProgramGroup
    assignedHere: Set<string>
    dhis2BaseUrl: string | null
}) {
    if (isEventProgram(group) && group.event !== null) {
        const formId = formIdentifier(group.event)
        return (
            <FormRow
                formId={formId}
                questionnaire={group.event}
                note="event"
                assignedHere={assignedHere.has(formId)}
                dhis2BaseUrl={dhis2BaseUrl}
            />
        )
    }

    return (
        <li className="space-y-1">
            <ul className="space-y-1">
                {group.event !== null && (
                    <FormRow
                        formId={formIdentifier(group.event)}
                        questionnaire={group.event}
                        note="event"
                        assignedHere={assignedHere.has(formIdentifier(group.event))}
                        dhis2BaseUrl={dhis2BaseUrl}
                    />
                )}
                {group.registration !== null ? (
                    <FormRow
                        formId={formIdentifier(group.registration)}
                        questionnaire={group.registration}
                        note="registration"
                        assignedHere={assignedHere.has(formIdentifier(group.registration))}
                        dhis2BaseUrl={dhis2BaseUrl}
                    />
                ) : (
                    group.event === null && <li className="text-sm font-medium">{group.title}</li>
                )}
            </ul>
            {group.stages.length > 0 && (
                <ul className="space-y-1 border-l pl-3">
                    {group.stages.map((stage) => (
                        <FormRow
                            key={formIdentifier(stage)}
                            formId={formIdentifier(stage)}
                            questionnaire={stage}
                            note="stage"
                            assignedHere={assignedHere.has(formIdentifier(stage))}
                            dhis2BaseUrl={dhis2BaseUrl}
                        />
                    ))}
                </ul>
            )}
        </li>
    )
}

/** One form as a rail row: its title linked to the form, and how its assignment reaches this unit. */
function FormRow({
    formId,
    questionnaire,
    assignedHere,
    note,
    dhis2BaseUrl,
}: {
    formId: string
    /** Null when the assignment names a form the store no longer serves - linked by bare id. */
    questionnaire: Questionnaire | null
    /** True when an assignment List names this unit; everything else is assigned everywhere. */
    assignedHere: boolean
    /** A muted role note beside the title - 'registration', 'stage', 'event'. */
    note?: string
    dhis2BaseUrl: string | null
}) {
    // A form the store no longer serves has no declared kind to read, so it carries no link out:
    // the row knows an id and nothing about which kind of DHIS2 object wears it.
    const target = questionnaire === null ? null : maintenanceTargetOf(questionnaire)
    return (
        // The row WRAPS rather than truncates or squeezes: `flex-wrap` lets the note and badge
        // drop to their own line when the rail is narrow, and the title keeps `flex-1` with a
        // floor so flex pressure can never collapse it to a zero-width - the invisible-link twin
        // of the ellipsis bug this row already fixed once.
        <li className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
            <Link to={`/forms/${formId}`} className="interactive-link min-w-[8ch] flex-1 break-words">
                {questionnaire === null ? formId : formTitle(questionnaire)}
            </Link>
            {target !== null && (
                <MaintenanceLink
                    baseUrl={dhis2BaseUrl}
                    object={target.object}
                    uid={target.uid}
                    subject={questionnaire === null ? formId : formTitle(questionnaire)}
                    className="self-center"
                />
            )}
            {/* The space before the note is the whole reason it is written out: the title and the
                note are two facts, and adjacent elements with nothing between them are read as one
                word - "Child Programmeregistration". */}
            {note !== undefined && <span className="text-muted-foreground shrink-0 text-xs">{` ${note}`}</span>}
            {assignedHere && (
                <Badge variant="outline" className="text-muted-foreground shrink-0 text-[10px]">
                    assigned to this organisation unit
                </Badge>
            )}
        </li>
    )
}

/**
 * The receipts this server holds for captures at this unit - the events half of the inspector.
 *
 * THE JOIN IS THE LISTING'S OWN FIELD. Every spool receipt states the DHIS2 organisation unit its
 * capture happened at, so this is a filter over data the page's `GET /spool` already carries - no
 * per-receipt fetch. The subtree count rides the same filter over the tree fold.
 *
 * THE SCOPE IS STATED, NOT IMPLIED. These are captures THIS SERVER received. What DHIS2 itself
 * already holds at the unit is the output leg's question, and pretending to answer it from a spool
 * would be lying with a number.
 */
function CapturedHere({
    node,
    formsById,
    spool,
}: {
    node: OrgUnitNode
    formsById: Map<string, Questionnaire>
    spool: SpoolState
}) {
    const descendants = useMemo(() => new Set(descendantIdsOf(node)), [node])
    const here = useMemo(
        () => spool.listing.responses.filter((summary) => summary.organisation_unit === node.id),
        [spool.listing, node.id],
    )
    const belowCount = useMemo(
        () =>
            spool.listing.responses.filter(
                (summary) =>
                    summary.organisation_unit !== null &&
                    summary.organisation_unit !== undefined &&
                    descendants.has(summary.organisation_unit),
            ).length,
        [spool.listing, descendants],
    )
    const counts = RESPONSE_LIFECYCLES.map((lifecycle) => ({
        lifecycle,
        count: here.filter((summary) => summary.lifecycle === lifecycle).length,
    })).filter((entry) => entry.count > 0)
    // The listing is newest first, so the head of the filtered list is the most recent capture.
    const recent = here.slice(0, RECENT_RECEIPTS)

    return (
        <section className="space-y-2" data-testid="org-unit-captured">
            <h4
                className="text-sm font-semibold"
                aria-label={here.length > 0 ? `Captured here, ${String(here.length)}` : undefined}
            >
                Captured here
                {here.length > 0 && (
                    <span className="text-muted-foreground ml-2 font-mono text-xs">{here.length}</span>
                )}
            </h4>
            <PageState
                loading={spool.loading}
                error={spool.error}
                empty={here.length === 0}
                emptyMessage="No received capture names this organisation unit."
            >
                <div className="space-y-2">
                    <div className="flex flex-wrap gap-1.5">
                        {counts.map((entry) => (
                            <Badge
                                key={entry.lifecycle}
                                variant="outline"
                                className={LIFECYCLE_TINTS[entry.lifecycle].badge}
                            >
                                {entry.count} {LIFECYCLE_LABELS[entry.lifecycle].toLowerCase()}
                            </Badge>
                        ))}
                    </div>
                    <ul className="space-y-1.5">
                        {/* Two lines per receipt, not one truncated one: the form's label wraps
                            in full, and the when-and-state line sits muted under it. An ellipsis
                            at rail width cut every long form name to the same prefix. */}
                        {recent.map((summary) => (
                            <li key={summary.response_id}>
                                <Link
                                    to={`/responses/${summary.response_id}`}
                                    className="hover:bg-accent/40 -mx-1 flex min-w-0 flex-col gap-0.5 rounded px-1 py-1 text-sm"
                                >
                                    <span className="min-w-0 break-words">
                                        {receiptFormLabel(summary, formsById)}
                                    </span>
                                    <span className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                                        {formatInstant(summary.received_at)}
                                        <LifecycleBadge summary={summary} showWarnings={false} />
                                    </span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                    <Link to="/responses" className="interactive-link text-sm">
                        All responses
                    </Link>
                </div>
            </PageState>
            {belowCount > 0 && (
                <p className="text-muted-foreground text-xs">
                    {belowCount} more below this organisation unit.
                </p>
            )}
            <p className="text-muted-foreground text-xs">
                Captures this server received. What the DHIS2 instance holds at this organisation
                unit is not read here.
            </p>
        </section>
    )
}

/** The form a receipt answered, named by its served title while the store still serves it. */
function receiptFormLabel(summary: SpoolResponseSummary, formsById: Map<string, Questionnaire>): string {
    const formId = summary.questionnaire_id ?? null
    if (formId === null) return summary.form_kind
    const questionnaire = formsById.get(formId)
    return questionnaire === undefined ? formId : formTitle(questionnaire)
}

/**
 * The stable empty focus, for the states with no selected extent - no selection, or a `?unit=`
 * naming a unit this registry does not hold. One frozen array, because the map re-frames (and
 * closes its popup) whenever the focus prop changes identity - a fresh `[]` minted per render
 * would re-frame on every keystroke in the filter box.
 */
const NO_FOCUS_UNIT_IDS: readonly string[] = Object.freeze([])

/**
 * The map, and every reason it might not be one.
 *
 * A registry with no coordinates at all gets no panel - an empty grey rectangle says nothing that
 * one sentence does not say better. A selected unit that has no geometry of its own keeps the map,
 * framed on the most honest extent the registry holds for it, with a note saying what is shown.
 */
function MapPanel({
    tree,
    geometry,
    selected,
    loading,
    onSelect,
    basemaps,
    settingsLoading,
}: {
    tree: OrgUnitTree
    geometry: ReturnType<typeof readGeometry>
    selected: OrgUnitNode | null
    loading: boolean
    onSelect: (unitId: string) => void
    basemaps: BasemapLayer[]
    /** True until `GET /uiconfig` has answered - the map is built once, against settled settings. */
    settingsLoading: boolean
}) {
    const descendantUnitIds = useMemo(
        () => new Set(selected === null ? [] : descendantIdsOf(selected)),
        [selected],
    )
    // FIT PRIORITY lives in `unitExtent`, stated once: own geometry -> union bbox of the subtree's
    // boundaries and points -> nearest located ancestor -> registry extent. Memoised per
    // selection; the map is handed the ids so a selection change stays one setData and one fit.
    const extent = useMemo(
        () => (selected === null ? null : unitExtent(tree, selected.id, geometry)),
        [tree, selected, geometry],
    )

    if (loading) return null
    if (!hasGeometry(geometry)) {
        return (
            <section className="flex flex-col gap-3">
                <h3 className="text-base font-semibold">Map</h3>
                <Card>
                    <CardContent className="text-muted-foreground py-6 text-sm">
                        This registry holds no coordinates - this DHIS2 instance stores neither a point
                        nor a boundary for any of the published organisation units, so there is nothing
                        to draw.
                    </CardContent>
                </Card>
            </section>
        )
    }

    return (
        // `flex-1` here and `min-h-0` all the way up is what makes the map take the height the
        // panels above it did not use, at every viewport, with a floor so it never collapses
        // to a sliver on a short one.
        <section className="flex flex-1 flex-col gap-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-base font-semibold">Map</h3>
                {/* The caption states the OFFER, which is the deployment's own posture and does
                    not change while the page is open. Which of the offered layers is drawn right
                    now is the reader's, and the map's layer control is where that is said. */}
                <span className="text-muted-foreground text-xs">
                    {shapeCount(geometry)}
                    {basemaps.length === 0 ? ' - no basemap offered, so the map draws from this server alone' : ''}
                </span>
            </div>
            <Suspense
                fallback={
                    <div className="bg-card text-muted-foreground flex min-h-[20rem] flex-1 items-center justify-center rounded-lg border text-sm">
                        Loading the map
                    </div>
                }
            >
                {settingsLoading ? (
                    <div className="bg-card min-h-[20rem] flex-1 rounded-lg border" />
                ) : (
                    <OrgUnitMap
                        boundaries={geometry.boundaries}
                        points={geometry.points}
                        // The folded registry: where the click popup reads a unit's name,
                        // level, and parent from.
                        tree={tree}
                        basemaps={basemaps}
                        selectedUnitId={selected?.id ?? null}
                        descendantUnitIds={descendantUnitIds}
                        focusUnitIds={extent?.unitIds ?? NO_FOCUS_UNIT_IDS}
                        onSelect={onSelect}
                    />
                )}
            </Suspense>
            {selected !== null && extent !== null && extent.coverage !== 'own' && (
                <p data-testid="org-unit-map-note" className="text-muted-foreground text-xs">
                    {extent.coverage === 'descendants' &&
                        `This DHIS2 instance stores no boundary for ${selected.name}, so the map frames the organisation units below it.`}
                    {extent.coverage === 'ancestor' &&
                        `This DHIS2 instance stores no boundary for ${selected.name}, so the map frames ${
                            tree.byId.get(extent.framedOnUnitId ?? '')?.name ?? extent.framedOnUnitId
                        } - the nearest organisation unit above it that has one.`}
                    {extent.coverage === 'registry' &&
                        `This DHIS2 instance stores no boundary for ${selected.name}, and none for any organisation unit above or below it, so the map shows the whole registry instead.`}
                </p>
            )}
            {geometry.unreadableGeometries > 0 && (
                <p data-testid="org-unit-map-unreadable" className="text-muted-foreground text-xs">
                    {geometry.unreadableGeometries} published{' '}
                    {geometry.unreadableGeometries === 1 ? 'geometry' : 'geometries'} could not be read
                    and {geometry.unreadableGeometries === 1 ? 'is' : 'are'} not drawn.
                </p>
            )}
        </section>
    )
}

/**
 * How much the map is drawing, in the two nouns the reader can see on it.
 *
 * Counted after the merge, so a facility whose geometry attachment holds a Point is a point here
 * and not a boundary that failed - which is what the counts said before the decoder learned that
 * DHIS2 keeps polygons and pins in one field.
 */
function shapeCount(geometry: ReturnType<typeof readGeometry>): string {
    const boundaries = `${String(geometry.boundaries.length)} ${geometry.boundaries.length === 1 ? 'boundary' : 'boundaries'}`
    const points = `${String(geometry.points.length)} ${geometry.points.length === 1 ? 'point' : 'points'}`
    return `${boundaries}, ${points}`
}

/** What the inspector says before a unit is picked. */
function NothingSelected({ total, loading }: { total: number; loading: boolean }) {
    if (loading || total === 0) return null
    return (
        <Card>
            <CardContent className="text-muted-foreground flex items-center gap-3 py-6 text-sm">
                <MapPin className="size-4 shrink-0" aria-hidden />
                Pick an organisation unit in the tree, or click a shape on the map. The one you pick
                goes into the address, so an organisation unit is a link you can send.
            </CardContent>
        </Card>
    )
}
