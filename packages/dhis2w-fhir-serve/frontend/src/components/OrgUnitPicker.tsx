import { createContext, use, useMemo, useState, type ReactNode } from 'react'
import { ChevronsUpDown, Loader2 } from 'lucide-react'

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
import { matchesUnit, type OrgUnitChoice } from '@/lib/orgunits'
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
 * WHY A SEARCH BOX AND NOT A TREE. The org-units page renders the hierarchy as a tree because
 * browsing it is the point there. Picking is a different task: a person filling a form knows which
 * facility they are at and wants to type three letters of its name, not click down four levels. So
 * the list is flat, ordered the way the tree walks - every unit under the one it belongs to, with
 * the parent's name beside it - and searched by name, uid, or DHIS2 code through the same
 * `matchesUnit` rule the tree filter uses.
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

    const matched = useMemo(() => {
        const needle = query.trim().toLowerCase()
        if (needle === '') return scope.choices
        return scope.choices.filter((choice) => matchesUnit(choice, needle))
    }, [scope.choices, query])

    const selected = selectedUnitId === null ? null : (scope.byId.get(selectedUnitId) ?? null)
    const shown = matched.slice(0, MAX_ROWS)

    const choose = (choice: OrgUnitChoice | null) => {
        onChange(choice)
        setOpen(false)
        setQuery('')
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
                        `matchesUnit`, the same one the org-units tree filters by, so a uid and a
                        DHIS2 code find a unit here exactly as they do there. */}
                    <Command shouldFilter={false}>
                        <CommandInput
                            placeholder="Search by name, uid, or code"
                            value={query}
                            onValueChange={setQuery}
                        />
                        <CommandList>
                            <CommandEmpty>No unit matches that search.</CommandEmpty>
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
                    </Command>
                    {matched.length > shown.length && (
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
                ? `This form's organisation-unit assignment names no unit this project publishes, so there is nothing to report from - the registry holds ${String(scope.registryTotal)}. DHIS2 refuses a capture outside the assignment with E1029.`
                : 'This project publishes no organisation units, so there is nothing to report from. `[generate.organisation_units]` in fhir.toml is what selects them.'}
        </p>
    )
}
