import { useMemo, useState } from 'react'
import { ChevronsUpDown, Loader2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    Command,
    CommandEmpty,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { useValueSetOptions, type ValueSetOption } from '@/hooks/use-valueset-options'
import { EMPTY_SLOT, type QuestionnaireNode, type AnswerSlot } from '@/lib/questionnaire'

/**
 * How many options a question offers before it is searched rather than scrolled.
 *
 * A DHIS2 option set of a dozen ARV regimens is a list a person reads; an ICD-10 binding is 14,240
 * concepts, and a select over one mounts every row before it opens. The threshold is where reading
 * the whole list stops being how anybody finds anything, and it is deliberately generous - a list
 * that fits on a screen and a half keeps the plain control, which is the one a field device handles
 * best.
 */
const SEARCH_ABOVE = 50

/**
 * How many rows the search draws before it asks for a narrower one.
 *
 * The same cap the organisation-unit picker draws under, and for the same reason: the count of what
 * is not shown is on screen, and one more character reaches any of it. It is a rendering limit and
 * never a filter on what may be chosen.
 */
const MAX_ROWS = 100

/**
 * The control for a coded question - the one kind of answer that is not typed but picked.
 *
 * TWO CONTROLS, ONE THRESHOLD. A DHIS2 option set routinely runs to dozens of options, and a select
 * costs one line whatever the count is, which is what keeps a 200-question aggregate form
 * scrollable. But a real terminology binding is not dozens: ICD-10 is 14,240 concepts, a select over
 * one mounts 14,240 rows and takes a visible pause to open, and the only way to reach a code is the
 * type-ahead the browser happens to give. So a question offering more than `SEARCH_ABOVE` options is
 * picked from a searched list instead - the same shape, the same cap, and the same "N more match"
 * footer as the organisation-unit picker, because finding one row in thousands is one problem and
 * this app should solve it once.
 *
 * WHY THE OPTION VALUE IS THE CODE. Radix's Select carries a string, and the string that
 * identifies an option is its concept code - the same code the capture validator resolves
 * against the served CodeSystem. The full Coding (system, code, display) is what goes on the
 * wire, so the code is looked back up in the option list on selection rather than reconstructed.
 *
 * WHAT A SEARCH MATCHES. The display and the code alike: a person reaching for "N76.2" has the code
 * in hand, and a person reaching for "acute vaginitis" has the words. Nothing here scores or ranks -
 * the concepts arrive in the order the published CodeSystem states them, and that order is kept.
 *
 * A closed `choice` offers only what its ValueSet admits. An `open-choice` offers the same list
 * plus a free-text field, and R4 spells that second answer as a `valueString` - which is what
 * `slotAnswer` writes when a slot carries text and no coding.
 */
export function ChoiceControl({
    node,
    slot,
    controlId,
    disabled,
    clearable,
    onChange,
}: {
    node: QuestionnaireNode
    slot: AnswerSlot
    controlId: string
    disabled: boolean
    /**
     * Whether this control offers its own clear button.
     *
     * False on a repeating question, where the row's Remove button already takes the answer
     * away - two X buttons side by side on one row is two ways to do one thing, and neither
     * of them says which.
     */
    clearable: boolean
    onChange: (slot: AnswerSlot) => void
}) {
    const inline = inlineOptions(node)
    const expansion = useValueSetOptions(inline.length > 0 ? null : node.answerValueSet)
    const options = inline.length > 0 ? inline : expansion.options
    const selected = slot.coding?.code ?? null
    const chosen = options.find((candidate) => candidate.coding.code === selected) ?? null

    const choose = (option: ValueSetOption) => {
        onChange({ ...EMPTY_SLOT, coding: option.coding })
    }

    return (
        <div className="grid gap-2">
            <div className="flex items-center gap-2">
                {options.length > SEARCH_ABOVE ? (
                    <OptionSearch
                        controlId={controlId}
                        options={options}
                        chosen={chosen}
                        selected={selected}
                        disabled={disabled}
                        required={node.required}
                        onChoose={choose}
                    />
                ) : (
                    <Select
                        value={selected ?? ''}
                        disabled={disabled || expansion.loading || options.length === 0}
                        onValueChange={(code) => {
                            const option = options.find((candidate) => candidate.coding.code === code)
                            if (option !== undefined) choose(option)
                        }}
                    >
                        <SelectTrigger id={controlId} className="w-full max-w-md">
                            <SelectValue placeholder={selectPlaceholder(expansion.loading, options.length)} />
                        </SelectTrigger>
                        <SelectContent>
                            {options.map((option) => (
                                <SelectItem key={option.coding.code ?? option.label} value={option.coding.code ?? ''}>
                                    {option.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                )}
                {expansion.loading && (
                    <Loader2 className="text-muted-foreground size-4 shrink-0 animate-spin" aria-hidden />
                )}
                {clearable && selected !== null && !disabled && (
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Clear ${node.text ?? node.linkId}`}
                        onClick={() => onChange(EMPTY_SLOT)}
                    >
                        <X className="size-4" />
                    </Button>
                )}
            </div>

            {node.type === 'open-choice' && (
                <Input
                    id={`${controlId}-other`}
                    aria-label={`${node.text ?? node.linkId}, other`}
                    placeholder="Or type an answer this list does not have"
                    value={slot.text}
                    disabled={disabled}
                    onChange={(event) => onChange({ ...EMPTY_SLOT, text: event.target.value })}
                />
            )}

            {expansion.error !== null && (
                <p className="text-destructive text-xs">
                    The options for this question could not be read: {expansion.error}
                </p>
            )}
            {expansion.error === null && !expansion.loading && options.length === 0 && (
                <p className="text-muted-foreground text-xs">
                    This question binds terminology this server does not publish, so it offers no options.
                </p>
            )}
        </div>
    )
}

/**
 * A coded answer picked out of a list too long to read, by typing at it.
 *
 * The popover mounts nothing until it is opened and draws `MAX_ROWS` rows at a time, so a binding of
 * fourteen thousand concepts costs what a binding of fifty does. cmdk's own scoring is off for the
 * same reason it is off in the organisation-unit picker: the rule for what answers a query is stated
 * here, in one place, and a code has to match as readily as a display does.
 */
function OptionSearch({
    controlId,
    options,
    chosen,
    selected,
    disabled,
    required,
    onChoose,
}: {
    controlId: string
    options: ValueSetOption[]
    /** The option currently held, when it is one this list still offers. */
    chosen: ValueSetOption | null
    /** The code currently held, which a chosen option is looked up by. */
    selected: string | null
    disabled: boolean
    required: boolean
    onChoose: (option: ValueSetOption) => void
}) {
    const [open, setOpen] = useState(false)
    const [query, setQuery] = useState('')

    const matched = useMemo(() => {
        const needle = query.trim().toLowerCase()
        if (needle === '') return options
        return options.filter((option) => matchesOption(option, needle))
    }, [options, query])
    const shown = matched.slice(0, MAX_ROWS)

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    id={controlId}
                    type="button"
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    aria-required={required}
                    disabled={disabled}
                    className="w-full max-w-md justify-between font-normal"
                >
                    <span className={chosen === null ? 'text-muted-foreground truncate' : 'truncate'}>
                        {chosen?.label ?? (selected ?? 'Not answered')}
                    </span>
                    <ChevronsUpDown className="text-muted-foreground size-4 shrink-0" aria-hidden />
                </Button>
            </PopoverTrigger>
            {/* Matched to the trigger rather than the popover's own narrow default: a concept
                display runs long, and a list whose every row is truncated is one nobody can pick
                from. */}
            <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
                <Command shouldFilter={false}>
                    <CommandInput
                        placeholder="Search by name or code"
                        value={query}
                        onValueChange={setQuery}
                    />
                    <CommandList>
                        <CommandEmpty>No option matches that search.</CommandEmpty>
                        {shown.map((option) => (
                            <CommandItem
                                key={option.coding.code ?? option.label}
                                value={option.coding.code ?? option.label}
                                data-checked={option.coding.code === selected ? 'true' : 'false'}
                                onSelect={() => {
                                    onChoose(option)
                                    setOpen(false)
                                    setQuery('')
                                }}
                            >
                                <span className="truncate">{option.label}</span>
                                {option.coding.code !== undefined && option.coding.code !== option.label && (
                                    <span className="text-muted-foreground shrink-0 font-mono text-[10px]">
                                        {option.coding.code}
                                    </span>
                                )}
                            </CommandItem>
                        ))}
                    </CommandList>
                </Command>
                {matched.length > shown.length && (
                    <p className="text-muted-foreground border-t px-3 py-2 text-xs">
                        {matched.length - shown.length} more match - narrow the search to reach them.
                    </p>
                )}
            </PopoverContent>
        </Popover>
    )
}

/** Whether one option answers a search: its display, or the code a person read off a card. */
function matchesOption(option: ValueSetOption, needle: string): boolean {
    return (
        option.label.toLowerCase().includes(needle) ||
        (option.coding.code?.toLowerCase().includes(needle) ?? false)
    )
}

/** What the trigger says while there is nothing to pick from yet. */
function selectPlaceholder(loading: boolean, optionCount: number): string {
    if (loading) return 'Reading the option set'
    return optionCount === 0 ? 'No options' : 'Not answered'
}

/**
 * The options an item states inline, rather than through a ValueSet.
 *
 * Only the `valueCoding` spelling is offered. R4 also allows `valueString` and `valueInteger`
 * answer options, but a DHIS2 `choice` question always answers on `valueCoding` - see
 * `ANSWER_ELEMENTS_BY_ITEM_TYPE` - so an option in either other spelling could not be submitted
 * as an answer to it, and offering one would be offering something the server refuses.
 */
function inlineOptions(node: QuestionnaireNode): ValueSetOption[] {
    return node.answerOptions.flatMap((option) =>
        option.valueCoding === undefined
            ? []
            : [{ coding: option.valueCoding, label: option.valueCoding.display ?? option.valueCoding.code ?? '' }],
    )
}
