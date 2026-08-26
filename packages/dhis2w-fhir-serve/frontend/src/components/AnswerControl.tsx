import type { Dispatch } from 'react'
import { Plus, X } from 'lucide-react'

import { ChoiceControl } from '@/components/ChoiceControl'
import { OrgUnitPicker } from '@/components/OrgUnitPicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { orgUnitReference, referencedUnitId } from '@/lib/orgunits'
import { cn } from '@/lib/utils'
import {
    dateTimeInputValue,
    EMPTY_SLOT,
    numericInputShape,
    TRUE_ONLY_VALUE_TYPE,
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
 * under the cursor. `lib/questionnaire.ts` converts to `value[x]` once, at submit - and states
 * what it could not convert, which is why a numeric question is a text box: `type="number"` drops
 * the characters it cannot parse, so "1.2.3" would become "1.23" with nothing said about it.
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
 * WHY A BOOLEAN QUESTION HAS TWO SHAPES. R4 spells the DHIS2 value types `BOOLEAN` and `TRUE_ONLY`
 * as one `#boolean` item type, and the question's own concept is what tells them apart - the
 * `value-type` property of the served data dictionary, on `node.valueType`. A `BOOLEAN` takes Yes,
 * No, or no answer; a `TRUE_ONLY` takes a tick or no answer, because DHIS2 stores no false value
 * for one and a No offered here would be discarded on the way in.
 *
 * WHY SOME QUESTIONS STILL HAVE NO CONTROL. `attachment` needs a file and `quantity` has no DHIS2
 * wire spelling at all. Rather than fake either, the question is shown, named, and stated as
 * unfillable here.
 */
export function AnswerControl({
    node,
    slots,
    locked = false,
    controlClassName,
    dispatch,
}: {
    node: QuestionnaireNode
    slots: readonly AnswerSlot[]
    /**
     * True when the submission will not carry this answer whatever is typed.
     *
     * A fact about the submission rather than about the question - `node.readOnly` is the form's
     * own statement and this is the page's - and it disables the same controls for the same
     * reason: a control that accepts input nothing will send is a control that lies.
     */
    locked?: boolean
    /**
     * What the caller has to say about how wide this control is, over what its type asks for.
     *
     * The only caller with anything to say is the disaggregation table, whose cells are tighter
     * than a control standing on its own: a count read in a grid is read against the counts above
     * and below it. Everywhere else the answer's own shape decides, which is the default.
     */
    controlClassName?: string
    dispatch: Dispatch<AnswerAction>
}) {
    if (!node.fillable) {
        return (
            <p className="text-muted-foreground border-border rounded-lg border border-dashed px-2.5 py-2 text-xs">
                {/* Plural, so one sentence serves both types that reach here: an `attachment`
                    question and a `quantity` one take different articles and the same statement. */}
                This UI does not fill <code className="font-mono">{node.type}</code> questions. Post one with a
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
                disabled={node.readOnly || locked}
                className={controlClassName}
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
                            disabled={node.readOnly || locked}
                            className={controlClassName}
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
                        disabled={node.readOnly || locked}
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
                    disabled={node.readOnly || locked}
                    onClick={() => dispatch({ kind: 'add-repeat', linkId: node.linkId })}
                >
                    <Plus className="size-4" />
                    Add answer
                </Button>
            </div>
        </div>
    )
}

/**
 * One row of one question: the control its item type asks for, at the width that answer takes.
 *
 * A CONTROL IS AS WIDE AS WHAT GOES IN IT. A weekly case count is three digits and a box three
 * hundred pixels wide says a sentence would be welcome; a date is ten characters however wide the
 * screen is; a line of free text is read in one glance up to about sixty characters and no further.
 * So each control states its own width and the form's columns flow around them, rather than every
 * answer being poured into one column the width of the page. The narrative box is the deliberate
 * exception and keeps the full width: `text` is what DHIS2's `LONG_TEXT` emits, the answer is
 * paragraphs, and a paragraph is the one answer a wide box helps.
 */
function SlotControl({
    node,
    slot,
    controlId,
    disabled,
    className,
    onChange,
}: {
    node: QuestionnaireNode
    slot: AnswerSlot
    controlId: string
    /** Whether this row accepts input at all - the form's own `readOnly`, or the page's lock. */
    disabled: boolean
    /** The caller's width, where a caller has one - a table cell's. Null everywhere else. */
    className?: string
    onChange: (slot: AnswerSlot) => void
}) {
    const write = (text: string) => onChange({ ...EMPTY_SLOT, text })

    switch (node.type) {
        case 'boolean':
            // TWO STATES, NOT THREE, FOR A TRUE_ONLY QUESTION. R4 spells `BOOLEAN` and `TRUE_ONLY`
            // as one `#boolean` item type, and the DHIS2 value types behind them differ on exactly
            // one point: a TRUE_ONLY data element stores `true` or nothing, and the forwarder drops
            // a `false` on the way to DHIS2. So the control for one is a tick that is either on or
            // unanswered, and offers no No it would have to discard.
            if (node.valueType === TRUE_ONLY_VALUE_TYPE) {
                return (
                    <div className="flex items-center gap-2">
                        <Switch
                            id={controlId}
                            checked={slot.text === 'true'}
                            disabled={disabled}
                            aria-required={node.required}
                            onCheckedChange={(checked) => write(checked ? 'true' : '')}
                        />
                        <span className="text-muted-foreground text-xs">
                            {slot.text === 'true' ? 'Yes' : 'Not answered'}
                        </span>
                    </div>
                )
            }
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
        case 'decimal': {
            // A text box with a numeric keypad, never `type="number"`: see `numericInputShape`. The
            // bounds are not on the element either - the browser only enforces them on a number
            // box, and grading them here would be a second opinion beside `answerBreaches`, which
            // states the fact for every value this form does not accept.
            //
            // AND AS WIDE AS A COUNT. A number is a handful of characters, so the box is a handful
            // of characters wide - which is what makes a page of counts read as counts rather than
            // as a column of empty sentences.
            const shape = numericInputShape(node.type)
            return (
                <Input
                    id={controlId}
                    type={shape.type}
                    inputMode={shape.inputMode}
                    className={cn('w-28 max-w-full text-right tabular-nums', className)}
                    value={slot.text}
                    disabled={disabled}
                    aria-required={node.required}
                    onChange={(event) => write(event.target.value)}
                />
            )
        }
        case 'text':
            return (
                <Textarea
                    id={controlId}
                    rows={3}
                    maxLength={node.maxLength ?? undefined}
                    className={className}
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
                    className={cn('max-w-[60ch]', className)}
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
                    // The browser's own calendar greys out what the form does not accept, which is
                    // the earliest a bounded day can be caught. Submit refuses one typed in anyway.
                    min={node.minimumDate ?? undefined}
                    max={node.maximumDate ?? undefined}
                    className={cn('w-44 max-w-full', className)}
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
                    className={cn('w-60 max-w-full', className)}
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
                    className={cn('w-36 max-w-full', className)}
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
                    className={cn('max-w-md', className)}
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
                    // Sixty characters is the line a reader takes in at a glance, which is as much
                    // of a name, a code or an address as a box needs to show at once.
                    className={cn('max-w-[60ch]', className)}
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
