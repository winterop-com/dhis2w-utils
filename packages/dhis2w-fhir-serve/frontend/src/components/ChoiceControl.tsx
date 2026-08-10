import { Loader2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
 * The control for a coded question - the one kind of answer that is not typed but picked.
 *
 * WHY A SELECT AND NOT A RADIO GROUP. DHIS2 option sets routinely run to dozens of options (an
 * ARV regimen list, a diagnosis list), and a radio group renders all of them at once. A select
 * costs one line whatever the option count is, which is what keeps a 200-question aggregate
 * form scrollable.
 *
 * WHY THE OPTION VALUE IS THE CODE. Radix's Select carries a string, and the string that
 * identifies an option is its concept code - the same code the capture validator resolves
 * against the served CodeSystem. The full Coding (system, code, display) is what goes on the
 * wire, so the code is looked back up in the option list on selection rather than reconstructed.
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

    return (
        <div className="grid gap-2">
            <div className="flex items-center gap-2">
                <Select
                    value={selected ?? ''}
                    disabled={disabled || expansion.loading || options.length === 0}
                    onValueChange={(code) => {
                        const option = options.find((candidate) => candidate.coding.code === code)
                        if (option !== undefined) onChange({ ...EMPTY_SLOT, coding: option.coding })
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
