import type { Dispatch } from 'react'
import { Plus, X } from 'lucide-react'

import { ChoiceControl } from '@/components/ChoiceControl'
import { OrgUnitPicker } from '@/components/OrgUnitPicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { orgUnitReference, referencedUnitId } from '@/lib/orgunits'
import {
    dateTimeInputValue,
    EMPTY_SLOT,
    type AnswerAction,
    type AnswerSlot,
    type QuestionnaireNode,
} from '@/lib/questionnaire'

/**
 * One question's control, dispatched on the R4 item type.
 *
 * WHY THE CONTROL HOLDS A LITERAL. Every scalar control here is a plain controlled input over
 * `slot.text` - the string the browser gave, kept verbatim. Nothing parses on keystroke, which
 * is what lets a decimal field pass through "-", "1." and "" without the value being rewritten
 * under the cursor. `lib/questionnaire.ts` converts to `value[x]` once, at submit.
 *
 * WHY NO DATE PICKER. `date`, `dateTime` and `time` use the browser's own controls. A picker
 * component would be the first thing in this app that owns a calendar, and native inputs
 * already give keyboard entry, locale formatting and mobile keypads for free. The gap they
 * leave is that a `datetime-local` yields no timezone and a `time` yields no seconds, and R4
 * demands both - closed by the normalisers in lib/questionnaire.ts, not here.
 *
 * WHY A REFERENCE QUESTION IS A UNIT PICKER. `reference` is what the emitter writes for a DHIS2
 * `ORGANISATION_UNIT` data element and nothing else, so the only resource one can name is a
 * published Location - and the set it may name is the form's own assignment, which is what
 * `OrgUnitPicker` offers. It is the one control here that needs the server, and the one whose
 * answer is a `value[x]` the reducer holds settled rather than a literal.
 *
 * WHY SOME QUESTIONS STILL HAVE NO CONTROL. `attachment` needs a file and `quantity` has no DHIS2
 * wire spelling at all. Rather than fake either, the question is shown, named, and stated as
 * unfillable here.
 */
export function AnswerControl({
    node,
    slots,
    dispatch,
}: {
    node: QuestionnaireNode
    slots: readonly AnswerSlot[]
    dispatch: Dispatch<AnswerAction>
}) {
    if (!node.fillable) {
        return (
            <p className="text-muted-foreground border-border rounded-lg border border-dashed px-2.5 py-2 text-xs">
                A <code className="font-mono">{node.type}</code> question is not filled in this UI. Post it with a
                client that can carry one.
            </p>
        )
    }

    if (!node.repeats) {
        return (
            <SlotControl
                node={node}
                slot={slots[0] ?? EMPTY_SLOT}
                controlId={node.linkId}
                onChange={(slot) => dispatch({ kind: 'set', linkId: node.linkId, index: 0, slot })}
            />
        )
    }

    // A repeating question starts with no rows at all rather than one empty one: an empty row
    // is indistinguishable from an unanswered question on screen, and this way the Add button
    // is the only way a row appears, which makes the count on screen the count submitted.
    return (
        <div className="grid gap-2">
            {slots.map((slot, index) => (
                // The row position is the only identity a repeat row has - an answer slot
                // carries no id, and two rows of the same option set can hold the same value.
                // Every control below is fully controlled from the reducer, so a reused DOM node
                // after a removal still renders the right value; only caret position is lost.
                // oxlint-disable-next-line react/no-array-index-key
                <div key={`${node.linkId}-${index}`} className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                        <SlotControl
                            node={node}
                            slot={slot}
                            controlId={index === 0 ? node.linkId : `${node.linkId}-${index}`}
                            onChange={(next) =>
                                dispatch({ kind: 'set', linkId: node.linkId, index, slot: next })
                            }
                        />
                    </div>
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove answer ${index + 1} of ${node.text ?? node.linkId}`}
                        disabled={node.readOnly}
                        onClick={() => dispatch({ kind: 'remove-repeat', linkId: node.linkId, index })}
                    >
                        <X className="size-4" />
                    </Button>
                </div>
            ))}
            <div>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={node.readOnly}
                    onClick={() => dispatch({ kind: 'add-repeat', linkId: node.linkId })}
                >
                    <Plus className="size-4" />
                    Add answer
                </Button>
            </div>
        </div>
    )
}

/** One row of one question: the control its item type asks for. */
function SlotControl({
    node,
    slot,
    controlId,
    onChange,
}: {
    node: QuestionnaireNode
    slot: AnswerSlot
    controlId: string
    onChange: (slot: AnswerSlot) => void
}) {
    const disabled = node.readOnly
    const write = (text: string) => onChange({ ...EMPTY_SLOT, text })

    switch (node.type) {
        case 'boolean':
            return (
                <div className="flex items-center gap-2">
                    <Switch
                        id={controlId}
                        checked={slot.text === 'true'}
                        disabled={disabled}
                        aria-required={node.required}
                        onCheckedChange={(checked) => write(checked ? 'true' : 'false')}
                    />
                    <span className="text-muted-foreground text-xs">{booleanLabel(slot.text)}</span>
                    {slot.text !== '' && !disabled && (
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-muted-foreground h-6"
                            onClick={() => write('')}
                        >
                            Unanswer
                        </Button>
                    )}
                </div>
            )
        case 'integer':
        case 'decimal':
            return (
                <Input
                    id={controlId}
                    type="number"
                    inputMode={node.type === 'integer' ? 'numeric' : 'decimal'}
                    step={node.type === 'integer' ? 1 : 'any'}
                    min={node.minimum ?? undefined}
                    max={node.maximum ?? undefined}
                    className="max-w-xs"
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        case 'text':
            return (
                <Textarea
                    id={controlId}
                    rows={3}
                    maxLength={node.maxLength ?? undefined}
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        case 'url':
            return (
                <Input
                    id={controlId}
                    type="url"
                    inputMode="url"
                    placeholder="https://"
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        case 'date':
            return (
                <Input
                    id={controlId}
                    type="date"
                    className="max-w-xs"
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        case 'dateTime':
            return (
                <Input
                    id={controlId}
                    type="datetime-local"
                    step={1}
                    className="max-w-xs"
                    value={dateTimeInputValue(slot.text)}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        case 'time':
            return (
                <Input
                    id={controlId}
                    type="time"
                    step={1}
                    className="max-w-xs"
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        case 'choice':
        case 'open-choice':
            return (
                <ChoiceControl
                    node={node}
                    slot={slot}
                    controlId={controlId}
                    disabled={disabled}
                    clearable={!node.repeats}
                    onChange={onChange}
                />
            )
        case 'reference':
            return (
                <OrgUnitPicker
                    controlId={controlId}
                    selectedUnitId={referencedUnitId(slot.reference)}
                    disabled={disabled}
                    required={node.required}
                    clearable={!node.repeats}
                    className="max-w-md"
                    placeholder="No organisation unit chosen"
                    onChange={(choice) =>
                        onChange({
                            ...EMPTY_SLOT,
                            reference: choice === null ? null : orgUnitReference(choice),
                        })
                    }
                />
            )
        default:
            return (
                <Input
                    id={controlId}
                    type="text"
                    maxLength={node.maxLength ?? undefined}
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
    }
}

/** What a boolean switch says it currently means, including the state of not having been touched. */
function booleanLabel(text: string): string {
    if (text === 'true') return 'Yes'
    if (text === 'false') return 'No'
    return 'Not answered'
}
