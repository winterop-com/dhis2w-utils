import {
    createContext,
    use,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
    type KeyboardEvent,
    type ReactNode,
    type RefObject,
} from 'react'
import { Check, ChevronDown, ChevronRight, ChevronsUpDown, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    Command,
    CommandEmpty,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { EMPTY_ORG_UNIT_SCOPE, type OrgUnitScope } from '@/hooks/use-org-unit-scope'
import {
    expandedForSelection,
    matchesUnit,
    visibleBrowseRows,
    type OrgUnitBrowseNode,
    type OrgUnitChoice,
} from '@/lib/orgunits'
import { cn } from '@/lib/utils'

/**
 * How many rows the list draws before it asks for a narrower search.
 *
 * A published registry runs to four figures, and a popover that mounted 1,300 rows would take a
 * visible beat to open every time - for a list nobody scrolls to the bottom of. The cap is a
 * rendering limit and never a filter on what may be chosen: the count of what it is not showing is
 * on screen, and one more character of search reaches any of it.
 */
const MAX_ROWS = 100

/** The two ways this control finds a unit: by typing at it, or by walking the hierarchy. */
type PickerMode = 'search' | 'browse'

/**
 * The organisation units the form on screen may be captured against.
 *
 * WHY A CONTEXT. Two very different controls want the same answer: the reporting-unit picker above
 * the form, and one picker per `ORGANISATION_UNIT` question inside it. The second sits at the
 * bottom of a recursion that renders whatever the form's item tree says, and threading a registry
 * through `QuestionnaireForm` and every level of `QuestionnaireItemView` would put an
 * organisation-unit concern into code whose whole job is not to know what a question is about. So
 * the page that knows which form is open provides the scope once, and the pickers read it wherever
 * they land.
 */
const OrgUnitScopeContext = createContext<OrgUnitScope>(EMPTY_ORG_UNIT_SCOPE)

/** Publish one form's organisation-unit scope to every picker rendered under it. */
export function OrgUnitScopeProvider({ scope, children }: { scope: OrgUnitScope; children: ReactNode }) {
    return <OrgUnitScopeContext value={scope}>{children}</OrgUnitScopeContext>
}

/** The scope the enclosing form published, or an empty one outside a capture screen. */
export function useOrgUnitScope(): OrgUnitScope {
    return use(OrgUnitScopeContext)
}

/**
 * One organisation unit, picked from what the form is assigned to.
 *
 * THE OFFER IS THE SERVER'S ANSWER, NOT THE REGISTRY. What this lists is the published registry
 * intersected with the form's own assignment List, which is precisely the set
 * `dhis2w_fhir_serve.capture.validate` grades a submission's unit against - `E1029` on the
 * strictness dial for anything outside it. Offering exactly that means the control cannot produce a
 * submission the server refuses on this ground, which is a better arrangement than a free choice
 * corrected by a warning after the round trip.
 *
 * SEARCH IS PRIMARY, BROWSE IS BESIDE IT. A person filling a form usually knows which facility they
 * are at and wants to type three letters of its name, so the search box is what the popover opens
 * on and nothing about it changed. But a flat result list drops the parent chain, and a national
 * registry has four "Ngelehun CHC"s in four districts - so **Browse** switches the result area to
 * the hierarchy itself, lazily expanded exactly as the organisation-units page expands it, which is the one
 * shape that tells those four apart. Both are searched and rendered by the same rules: `matchesUnit`
 * for what answers a query, and the folded tree for what sits under what.
 *
 * THE MODE RULE, STATED ONCE. The toggle is the only thing that sets the mode; a non-empty query
 * forces Search whatever the mode says. So typing while browsing shows results (typing is
 * searching - there is no dead input), clearing the query returns to Browse if that is what the
 * toggle last chose, and pressing Browse clears the query because otherwise the query would
 * immediately override it.
 */
export function OrgUnitPicker({
    controlId,
    selectedUnitId,
    onChange,
    disabled = false,
    required = false,
    clearable = false,
    className,
    placeholder = 'Not chosen',
}: {
    controlId: string
    /** The unit currently held, by id - which is what a stored `Location/<stem>` reduces to. */
    selectedUnitId: string | null
    onChange: (choice: OrgUnitChoice | null) => void
    disabled?: boolean
    required?: boolean
    /** Whether the list offers a way back to no answer at all. */
    clearable?: boolean
    className?: string
    placeholder?: string
}) {
    const scope = useOrgUnitScope()
    const [open, setOpen] = useState(false)
    const [query, setQuery] = useState('')
    const [mode, setMode] = useState<PickerMode>('search')
    const searchRef = useRef<HTMLInputElement>(null)
    const treeRef = useRef<HTMLDivElement>(null)

    const matched = useMemo(() => {
        const needle = query.trim().toLowerCase()
        if (needle === '') return scope.choices
        return scope.choices.filter((choice) => matchesUnit(choice, needle))
    }, [scope.choices, query])

    const selected = selectedUnitId === null ? null : (scope.byId.get(selectedUnitId) ?? null)
    const shown = matched.slice(0, MAX_ROWS)
    const browsing = mode === 'browse' && query.trim() === ''

    const choose = (choice: OrgUnitChoice | null) => {
        onChange(choice)
        setOpen(false)
        setQuery('')
    }

    const chooseById = (unitId: string) => {
        const choice = scope.byId.get(unitId)
        if (choice !== undefined) choose(choice)
    }

    /** Hand the keyboard to the tree, from the search box the popover opens focused on. */
    const enterTree = () => {
        treeRef.current?.querySelector<HTMLElement>('[role="treeitem"][tabindex="0"]')?.focus()
    }

    /** A character typed at the tree is a search: the query starts over with it, in the search box. */
    const searchFor = (character: string) => {
        setMode('search')
        setQuery(character)
        searchRef.current?.focus()
    }

    if (!scope.loading && scope.error === null && scope.choices.length === 0) {
        return <NothingOffered scope={scope} />
    }

    return (
        <div className={cn('grid gap-1', className)}>
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        id={controlId}
                        type="button"
                        variant="outline"
                        role="combobox"
                        aria-expanded={open}
                        aria-required={required}
                        disabled={disabled || scope.loading}
                        className="w-full justify-between font-normal"
                    >
                        <span className="flex min-w-0 items-center gap-2">
                            {scope.loading && (
                                <Loader2 className="text-muted-foreground size-4 shrink-0 animate-spin" aria-hidden />
                            )}
                            <span className={cn('truncate', selected === null && 'text-muted-foreground')}>
                                {selected === null ? triggerPlaceholder(scope, placeholder) : selected.name}
                            </span>
                            {selected?.level !== null && selected !== null && (
                                <span className="text-muted-foreground shrink-0 font-mono text-[10px]">
                                    {selected.level?.code}
                                </span>
                            )}
                        </span>
                        <ChevronsUpDown className="text-muted-foreground size-4 shrink-0" aria-hidden />
                    </Button>
                </PopoverTrigger>
                {/* Matched to the trigger rather than the popover's own 18rem: a facility name plus
                    its district does not fit in a fixed narrow box, and a list whose every row is
                    truncated is a list you cannot pick from. */}
                <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
                    {/* cmdk's own scoring is off: the rule for what answers a search is
                        `matchesUnit`, the same one the organisation-units tree filters by, so a uid and a
                        DHIS2 code find a unit here exactly as they do there. */}
                    <Command shouldFilter={false}>
                        <CommandInput
                            ref={searchRef}
                            placeholder="Search by name, uid, or code"
                            value={query}
                            onValueChange={setQuery}
                            onKeyDown={(event) => {
                                if (!browsing) return
                                if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
                                // cmdk's root would move its own selection through a list that is
                                // not rendered right now, so the event stops here.
                                event.preventDefault()
                                event.stopPropagation()
                                enterTree()
                            }}
                        />
                        <ModeToggle
                            mode={browsing ? 'browse' : 'search'}
                            onChange={(next) => {
                                setMode(next)
                                // A query left standing would force Search straight back on.
                                if (next === 'browse') setQuery('')
                            }}
                        />
                        {browsing ? (
                            <OrgUnitBrowser
                                containerRef={treeRef}
                                roots={scope.browseRoots}
                                selectedUnitId={selectedUnitId}
                                onChoose={chooseById}
                                onTypeAhead={searchFor}
                                onLeaveTop={() => searchRef.current?.focus()}
                            />
                        ) : (
                            <CommandList>
                                <CommandEmpty>No organisation unit matches that search.</CommandEmpty>
                                {shown.map((choice) => (
                                    <CommandItem
                                        key={choice.id}
                                        value={choice.id}
                                        data-checked={choice.id === selectedUnitId ? 'true' : 'false'}
                                        onSelect={() => choose(choice)}
                                    >
                                        <span className="truncate">{choice.name}</span>
                                        {choice.level !== null && (
                                            <span className="text-muted-foreground shrink-0 font-mono text-[10px]">
                                                {choice.level.code}
                                            </span>
                                        )}
                                        {choice.parentName !== null && (
                                            <span className="text-muted-foreground truncate text-xs">
                                                in {choice.parentName}
                                            </span>
                                        )}
                                    </CommandItem>
                                ))}
                                {/* Last, and only while nothing is being searched for. cmdk selects the
                                    first row, so unanswering has to be somewhere a person typing three
                                    letters and pressing Enter cannot land on by accident. */}
                                {clearable && selected !== null && query.trim() === '' && (
                                    <CommandItem value="clear-this-answer" onSelect={() => choose(null)}>
                                        <span className="text-muted-foreground">Clear this answer</span>
                                    </CommandItem>
                                )}
                            </CommandList>
                        )}
                    </Command>
                    {/* Browse has no cmdk row to hang unanswering off, so the way back to no answer
                        at all is a footer under the tree - out of the arrow keys' path, which is the
                        same reason the search mode keeps it last. */}
                    {browsing && clearable && selected !== null && (
                        <button
                            type="button"
                            onClick={() => choose(null)}
                            className="text-muted-foreground hover:text-foreground w-full border-t px-3 py-2 text-left text-xs"
                        >
                            Clear this answer
                        </button>
                    )}
                    {!browsing && matched.length > shown.length && (
                        <p className="text-muted-foreground border-t px-3 py-2 text-xs">
                            {matched.length - shown.length} more match - narrow the search to reach them.
                        </p>
                    )}
                </PopoverContent>
            </Popover>

            {scope.error !== null && (
                <p className="text-destructive text-xs">
                    The organisation units this form may be captured against could not be read:{' '}
                    {scope.error}
                </p>
            )}
        </div>
    )
}

/**
 * The two ways to find a unit, as two words under the search box.
 *
 * Deliberately the least chrome that still reads as a choice: two ghost buttons with the active one
 * filled, rather than a segmented control or a pair of icons. The search box above it is what this
 * control is, and a toggle that competed with it for attention would be arguing the opposite.
 */
function ModeToggle({ mode, onChange }: { mode: PickerMode; onChange: (mode: PickerMode) => void }) {
    return (
        <div role="group" aria-label="How to find an organisation unit" className="flex items-center gap-1.5 px-3 pt-2.5 pb-1.5">
            {(['search', 'browse'] as const).map((candidate) => (
                <button
                    key={candidate}
                    type="button"
                    aria-pressed={mode === candidate}
                    onClick={() => onChange(candidate)}
                    className={cn(
                        'focus-visible:ring-ring/50 rounded px-2 py-0.5 text-xs focus-visible:ring-[3px] focus-visible:outline-none',
                        mode === candidate
                            ? 'bg-muted text-foreground'
                            : 'text-muted-foreground hover:text-foreground',
                    )}
                >
                    {candidate === 'search' ? 'Search' : 'Browse'}
                </button>
            ))}
        </div>
    )
}

/**
 * The hierarchy, in the popover, walkable by keyboard.
 *
 * WHY IT IS NOT A `CommandList`. cmdk owns one focus model: the input keeps DOM focus and the rows
 * are a selection it moves with the arrow keys. A tree needs ArrowLeft and ArrowRight to mean
 * collapse and expand, and needs its rows focusable so a screen reader announces the level and the
 * expanded state - neither of which cmdk's list can express. So this is a plain `role="tree"` with
 * a roving tabindex, rendered as a sibling of the search box inside the same `Command`, and every
 * key it handles is stopped here rather than left to bubble into cmdk's root handler. The
 * compromise that buys consistency: the tree takes focus when Browse opens, and any printable
 * character typed at it goes straight back to the search box as a fresh query - so typing is
 * searching in both modes, which is the one habit a person carries between them.
 *
 * WHY THE ROWS ARE FLAT. `visibleBrowseRows` is the same array the keyboard walks and the DOM
 * renders, so ArrowDown and the next element are the same thing by construction. The nesting is
 * stated as `aria-level` / `aria-posinset` / `aria-setsize`, which is ARIA's own shape for a tree
 * whose branches are not nested elements.
 */
function OrgUnitBrowser({
    containerRef,
    roots,
    selectedUnitId,
    onChoose,
    onTypeAhead,
    onLeaveTop,
}: {
    containerRef: RefObject<HTMLDivElement | null>
    roots: OrgUnitBrowseNode[]
    selectedUnitId: string | null
    onChoose: (unitId: string) => void
    onTypeAhead: (character: string) => void
    /** ArrowUp off the first row goes back where the popover opened - the search box. */
    onLeaveTop: () => void
}) {
    const opening = useMemo(() => expandedForSelection(roots, selectedUnitId), [roots, selectedUnitId])
    const [expanded, setExpanded] = useState(opening)
    const [openedFrom, setOpenedFrom] = useState(opening)
    if (openedFrom !== opening) {
        // The scope finished reading, or the selection changed under an open popover. Either way the
        // hand-made expansions were about a different tree, so the opening state starts over.
        setOpenedFrom(opening)
        setExpanded(opening)
    }

    const rows = useMemo(() => visibleBrowseRows(roots, expanded), [roots, expanded])
    const [activeUnitId, setActiveUnitId] = useState<string | null>(null)
    const active = activeRowId(rows, activeUnitId, selectedUnitId)

    const focusRow = useCallback(
        (unitId: string) => {
            setActiveUnitId(unitId)
            containerRef.current?.querySelector<HTMLElement>(`[data-unit-id="${unitId}"]`)?.focus()
        },
        [containerRef],
    )

    // Browse mode is a tree you operate, so it opens with the keyboard already in it. Typing is
    // still searching: the typeahead below hands the character and the focus back to the search box.
    useEffect(() => {
        containerRef.current?.querySelector<HTMLElement>('[role="treeitem"][tabindex="0"]')?.focus()
    }, [containerRef])

    const toggle = useCallback((unitId: string, open: boolean) => {
        setExpanded((previous) => {
            const next = new Set(previous)
            if (open) next.add(unitId)
            else next.delete(unitId)
            return next
        })
    }, [])

    /** The selected row, scrolled to as it mounts - a picker must open showing what it holds. */
    const showSelected = useCallback((element: HTMLDivElement | null) => {
        element?.scrollIntoView({ block: 'nearest' })
    }, [])

    const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
        if (event.altKey || event.ctrlKey || event.metaKey) return
        const index = rows.findIndex((row) => row.node.id === active)
        if (index === -1) return
        const row = rows[index]
        const open = expanded.has(row.node.id) && row.node.children.length > 0

        const handled = (): boolean => {
            switch (event.key) {
                case 'ArrowDown':
                    if (index + 1 < rows.length) focusRow(rows[index + 1].node.id)
                    return true
                case 'ArrowUp':
                    if (index === 0) onLeaveTop()
                    else focusRow(rows[index - 1].node.id)
                    return true
                case 'ArrowRight':
                    if (row.node.children.length === 0) return true
                    if (open) focusRow(row.node.children[0].id)
                    else toggle(row.node.id, true)
                    return true
                case 'ArrowLeft':
                    if (open) toggle(row.node.id, false)
                    else if (row.parentId !== null) focusRow(row.parentId)
                    return true
                case 'Home':
                    focusRow(rows[0].node.id)
                    return true
                case 'End':
                    focusRow(rows[rows.length - 1].node.id)
                    return true
                case 'Enter':
                case ' ':
                    if (row.node.admitted) onChoose(row.node.id)
                    return true
                default:
                    if (event.key.length !== 1) return false
                    onTypeAhead(event.key)
                    return true
            }
        }

        if (!handled()) return
        // Nothing the tree understands reaches cmdk's root, which would otherwise be moving a
        // selection through a list this mode does not render.
        event.preventDefault()
        event.stopPropagation()
    }

    if (rows.length === 0) {
        return (
            <p className="text-muted-foreground px-3 py-6 text-center text-sm">
                There is no hierarchy to browse.
            </p>
        )
    }

    return (
        <div
            ref={containerRef}
            role="tree"
            aria-label="Organisation unit hierarchy"
            onKeyDown={onKeyDown}
            className="show-scrollbars max-h-72 overflow-y-auto px-2 py-1.5"
        >
            {rows.map((row) => {
                const node = row.node
                const isOpen = expanded.has(node.id) && node.children.length > 0
                const isSelected = node.id === selectedUnitId
                return (
                    <div
                        key={node.id}
                        ref={isSelected ? showSelected : undefined}
                        role="treeitem"
                        data-unit-id={node.id}
                        // Named by the unit and nothing else: the level chip is decoration, and the
                        // chevron beside it is a control with a name of its own that would otherwise
                        // be read as part of this row's.
                        aria-label={node.name}
                        aria-level={row.depth + 1}
                        aria-posinset={row.positionInParent}
                        aria-setsize={row.siblingCount}
                        aria-selected={isSelected}
                        aria-expanded={node.children.length > 0 ? isOpen : undefined}
                        aria-disabled={node.admitted ? undefined : true}
                        tabIndex={node.id === active ? 0 : -1}
                        onClick={() => {
                            if (node.admitted) onChoose(node.id)
                        }}
                        onFocus={() => setActiveUnitId(node.id)}
                        className={cn(
                            'focus-visible:ring-ring/50 flex items-center gap-1 rounded-sm py-1 pr-2 text-sm focus-visible:ring-[3px] focus-visible:outline-none',
                            node.admitted
                                ? 'hover:bg-muted cursor-default'
                                : 'text-muted-foreground cursor-not-allowed',
                            isSelected && 'bg-muted text-foreground',
                        )}
                        style={{ paddingLeft: `${String(row.depth * 0.85 + 0.25)}rem` }}
                    >
                        {node.children.length > 0 ? (
                            <button
                                type="button"
                                tabIndex={-1}
                                aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${node.name}`}
                                onClick={(event) => {
                                    // A chevron opens a branch; it never picks the unit beside it.
                                    event.stopPropagation()
                                    toggle(node.id, !isOpen)
                                }}
                                className="text-muted-foreground hover:text-foreground flex size-5 shrink-0 items-center justify-center rounded"
                            >
                                {isOpen ? (
                                    <ChevronDown className="size-3.5" aria-hidden />
                                ) : (
                                    <ChevronRight className="size-3.5" aria-hidden />
                                )}
                            </button>
                        ) : (
                            <span className="size-5 shrink-0" aria-hidden />
                        )}
                        <span className="truncate">{node.name}</span>
                        {node.level !== null && (
                            <span className="text-muted-foreground shrink-0 font-mono text-[10px]" aria-hidden>
                                {node.level.code}
                            </span>
                        )}
                        {isSelected && <Check className="ml-auto size-4 shrink-0" aria-hidden />}
                    </div>
                )
            })}
        </div>
    )
}

/**
 * Which row the arrow keys are standing on.
 *
 * A roving tabindex needs exactly one row to be tabbable, and the row it was on can have been
 * collapsed out from under it - so the answer falls back through what the tree is actually showing:
 * the row last focused, else the unit this picker holds, else the first row.
 */
function activeRowId(
    rows: ReturnType<typeof visibleBrowseRows>,
    activeUnitId: string | null,
    selectedUnitId: string | null,
): string | null {
    const showing = (unitId: string | null) =>
        unitId !== null && rows.some((row) => row.node.id === unitId)
    if (showing(activeUnitId)) return activeUnitId
    if (showing(selectedUnitId)) return selectedUnitId
    return rows[0]?.node.id ?? null
}

/** What the trigger says while there is nothing chosen. */
function triggerPlaceholder(scope: OrgUnitScope, placeholder: string): string {
    return scope.loading ? 'Reading the organisation units' : placeholder
}

/**
 * The two ways a form can have nowhere to report from, said rather than shown as an empty list.
 *
 * Both are facts about what the project published, and both mean the server would refuse whatever
 * this control produced - so a disabled empty combobox would be the one rendering that tells the
 * reader nothing about why.
 */
function NothingOffered({ scope }: { scope: OrgUnitScope }) {
    return (
        <p className="text-muted-foreground border-border rounded-lg border border-dashed px-2.5 py-2 text-xs">
            {scope.restricted && scope.registryTotal > 0
                ? `This form's organisation-unit assignment names no organisation unit this project publishes, so there is nothing to report from - the registry holds ${String(scope.registryTotal)}. A capture outside the form's assigned organisation units is refused when it reaches DHIS2.`
                : 'This project publishes no organisation units, so there is nothing to report from. `[generate.organisation_units]` in fhir.toml is what selects them.'}
        </p>
    )
}
