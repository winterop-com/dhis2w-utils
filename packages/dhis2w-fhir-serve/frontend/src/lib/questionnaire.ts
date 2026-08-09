/**
 * A Questionnaire, read as something a person can fill in.
 *
 * WHAT THIS MODULE IS. `d2w fhir serve` publishes forms and accepts answers to them, and
 * nothing in this repo family has ever rendered one. This module is the half of that renderer
 * that has no DOM in it: it flattens the item tree into an ordered spec, holds every answer in
 * one reducer, decides which questions the form is currently asking, and assembles the
 * QuestionnaireResponse that goes back over the wire. The components in components/ do nothing
 * but choose a control per node and dispatch into the reducer here - which is what keeps the
 * interesting behaviour under `vitest run` in a Node environment, with no jsdom in the project.
 *
 * WHY linkId IS THE ANSWER KEY. R4 requires `Questionnaire.item.linkId` to be unique across the
 * whole questionnaire, not merely within its parent, and the capture validator on the Python
 * side keys its question index by exactly that (`dhis2w_fhir.conversion.context._walk` builds
 * `questions: dict[link_id, QuestionSpec]`, and `validate.py` refuses a link id answered twice).
 * The aggregate emitter leans on this: a disaggregated cell's link id is `{dataElement}.{coc}`,
 * globally unique by construction. So the answer state is a flat map keyed by link id, and the
 * item *tree* is reconstructed at build time from the spec rather than carried around in state.
 * Each node still records its ancestor chain, which is what the group rendering and the
 * enableWhen cascade read.
 *
 * WHY SLOTS HOLD LITERALS, NOT value[x]. A `value[x]` is a settled fact; "", "-" and "1." are
 * all states a numeric field passes through on the way to one, and a reducer holding
 * `valueDecimal: NaN` mid-keystroke is a reducer that fights its own controls. So a slot holds
 * the literal the control shows plus the concept a coded control picked, and the conversion to
 * `value[x]` happens once, in `buildQuestionnaireResponse`, against the answer element the
 * question's item type pins. The temporal normalisers below are part of that conversion: an
 * `<input type="time">` yields `20:00`, and R4 `time` requires seconds, so what the browser
 * gives is not what the server accepts and the gap is closed here rather than in a component.
 *
 * WHERE THE ENVELOPE COMES FROM. See `buildQuestionnaireResponse`.
 */

import {
    type Coding,
    type Questionnaire,
    type QuestionnaireAnswerOption,
    type QuestionnaireEnableBehavior,
    type QuestionnaireEnableWhen,
    type QuestionnaireEnableWhenOperator,
    type QuestionnaireInitial,
    type QuestionnaireItem,
    type QuestionnaireItemType,
    type QuestionnaireResponse,
    type QuestionnaireResponseAnswer,
    type QuestionnaireResponseItem,
} from '@/lib/fhir'

/** The standard R4 extensions a numeric question carries its inclusive bounds on. */
export const MINIMUM_VALUE_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/minValue'
export const MAXIMUM_VALUE_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/maxValue'

/**
 * The `value[x]` element each answerable item type answers on.
 *
 * This table is the UI's half of a contract, not a convention: it is
 * `ANSWER_ELEMENTS_BY_ITEM_TYPE` in `dhis2w_fhir.conversion.context` transcribed, and the
 * capture validator refuses any answer that carries a different element than the one the
 * question's item type names ("`X` answers as `decimal`, so it carries `valueDecimal`, not
 * `valueString`"). `group` and `display` are absent because they carry no answer, and
 * `quantity` is absent because DHIS2 has no wire spelling for it - a served form asking one
 * could not be converted, so this UI renders it as unfillable rather than inventing a value.
 */
export const ANSWER_ELEMENTS_BY_ITEM_TYPE: Partial<Record<QuestionnaireItemType, AnswerElement>> = {
    boolean: 'valueBoolean',
    decimal: 'valueDecimal',
    integer: 'valueInteger',
    date: 'valueDate',
    dateTime: 'valueDateTime',
    time: 'valueTime',
    string: 'valueString',
    text: 'valueString',
    url: 'valueUri',
    attachment: 'valueAttachment',
    choice: 'valueCoding',
    'open-choice': 'valueCoding',
    reference: 'valueReference',
}

/** One `value[x]` element name a question can answer on - every element of an R4 answer but its nesting. */
export type AnswerElement = Exclude<keyof QuestionnaireResponseAnswer, 'item'>

/**
 * The elements this UI can actually fill.
 *
 * `valueAttachment` needs a file, `valueReference` needs a resource picker over organisation
 * units; neither is something a test-data capture screen should fake. Questions answering on
 * them are rendered as read-only notices, and `buildQuestionnaireResponse` writes no answer
 * for them - which is a submission missing an answer, not a submission carrying a wrong one.
 */
export const FILLABLE_ANSWER_ELEMENTS: ReadonlySet<AnswerElement> = new Set<AnswerElement>([
    'valueBoolean',
    'valueDecimal',
    'valueInteger',
    'valueDate',
    'valueDateTime',
    'valueTime',
    'valueString',
    'valueUri',
    'valueCoding',
])

/** One flattened item: everything a control needs to render itself and write its answer back. */
export interface QuestionnaireNode {
    linkId: string
    /** Ancestor link ids, outermost first. Empty for a root item. */
    ancestorLinkIds: string[]
    /** The group this item sits in, or null at the root. */
    parentLinkId: string | null
    /** How deep the item sits; 0 at the root. */
    depth: number
    type: QuestionnaireItemType
    /** The question as the form asks it, or null when the item states no text. */
    text: string | null
    required: boolean
    repeats: boolean
    readOnly: boolean
    maxLength: number | null
    /** The inclusive bounds the `minValue` / `maxValue` extensions state, or null for none. */
    minimum: number | null
    maximum: number | null
    /** The `value[x]` the answer lands on, or null for a group, a display, or a `quantity`. */
    answerElement: AnswerElement | null
    /** Whether this UI has a control that can produce that element. */
    fillable: boolean
    answerOptions: QuestionnaireAnswerOption[]
    /** The canonical of the ValueSet the options come from, for a question that binds one. */
    answerValueSet: string | null
    enableWhen: QuestionnaireEnableWhen[]
    enableBehavior: QuestionnaireEnableBehavior
    initial: QuestionnaireInitial[]
    /**
     * The DHIS2 coding the item carries.
     *
     * This is the domain identity - a data element UID, or a category option combo UID on a
     * disaggregated cell - and it is what the people who run these servers think in, so it is
     * shown beside every label rather than hidden behind a tooltip.
     */
    code: Coding | null
    /** Direct children, in document order. */
    childLinkIds: string[]
}

/** One Questionnaire flattened: every item in document order, plus the lookups a renderer needs. */
export interface QuestionnaireSpec {
    /** Depth-first pre-order, which is the order a form is read and filled in. */
    nodes: QuestionnaireNode[]
    byLinkId: ReadonlyMap<string, QuestionnaireNode>
    /** The link ids of the top-level items, in document order. */
    rootLinkIds: string[]
    /** Every node that carries an answer of its own - not a group, not a display. */
    questionLinkIds: string[]
}

/** One answer slot as the form holds it mid-edit: the literal a control shows, and the concept it picked. */
export interface AnswerSlot {
    /**
     * What every text-shaped control holds verbatim - strings, numbers mid-typing, dates,
     * times, urls - and what a boolean holds as `'true'` or `'false'`.
     */
    text: string
    /** The concept a coded control picked, or null for every other control and for none picked. */
    coding: Coding | null
}

/** Every answer of one form, keyed by link id; a question with no entry is unanswered. */
export type AnswerState = Readonly<Record<string, readonly AnswerSlot[]>>

/** A slot holding nothing, which is what a fresh repeat row and a cleared control both are. */
export const EMPTY_SLOT: AnswerSlot = { text: '', coding: null }

/** Everything that can happen to the answers of one form. */
export type AnswerAction =
    | { kind: 'set'; linkId: string; index: number; slot: AnswerSlot }
    | { kind: 'clear'; linkId: string }
    | { kind: 'add-repeat'; linkId: string }
    | { kind: 'remove-repeat'; linkId: string; index: number }
    | { kind: 'replace'; answers: AnswerState }

/** Flatten one Questionnaire's item tree into the ordered spec every other function here reads. */
export function flattenQuestionnaire(questionnaire: Questionnaire): QuestionnaireSpec {
    const nodes: QuestionnaireNode[] = []
    const rootLinkIds = collectItems(questionnaire.item ?? [], [], nodes)
    const byLinkId = new Map(nodes.map((node) => [node.linkId, node]))
    const questionLinkIds = nodes
        .filter((node) => node.type !== 'group' && node.type !== 'display')
        .map((node) => node.linkId)
    return { nodes, byLinkId, rootLinkIds, questionLinkIds }
}

/** The answers a freshly opened form starts with: whatever its items declare as `initial`. */
export function initialAnswers(spec: QuestionnaireSpec): AnswerState {
    const answers: Record<string, readonly AnswerSlot[]> = {}
    for (const node of spec.nodes) {
        const slots = node.initial.flatMap((initial) => {
            const slot = slotFromInitial(initial)
            return slot === null ? [] : [slot]
        })
        if (slots.length > 0) answers[node.linkId] = slots
    }
    return answers
}

/** The one reducer every control writes through. */
export function answersReducer(state: AnswerState, action: AnswerAction): AnswerState {
    switch (action.kind) {
        case 'replace':
            return action.answers
        case 'clear': {
            if (!(action.linkId in state)) return state
            const next = { ...state }
            delete next[action.linkId]
            return next
        }
        case 'set': {
            const slots = [...(state[action.linkId] ?? [])]
            // A control can write to a slot that does not exist yet - the single slot of a
            // question nobody has touched. Padding rather than refusing keeps every control
            // free of "create the row first" ceremony.
            while (slots.length <= action.index) slots.push(EMPTY_SLOT)
            slots[action.index] = action.slot
            return { ...state, [action.linkId]: slots }
        }
        case 'add-repeat':
            return { ...state, [action.linkId]: [...(state[action.linkId] ?? []), EMPTY_SLOT] }
        case 'remove-repeat': {
            const slots = (state[action.linkId] ?? []).filter((_, index) => index !== action.index)
            if (slots.length === 0) {
                const next = { ...state }
                delete next[action.linkId]
                return next
            }
            return { ...state, [action.linkId]: slots }
        }
    }
}

/**
 * Every link id the form is currently asking, given what has been answered so far.
 *
 * Computed over the whole spec in one pre-order pass rather than per item on demand, because a
 * group's `enableWhen` disables everything under it: a child's answer is decided by its own
 * conditions *and* by every ancestor's, and pre-order means each ancestor's verdict is already
 * in the set by the time its children are reached. A disabled item keeps its answers in state -
 * re-enabling it must not lose what was typed - but `buildQuestionnaireResponse` writes none of
 * them, which is what R4 means by an item the form did not ask.
 */
export function enabledLinkIds(spec: QuestionnaireSpec, answers: AnswerState): ReadonlySet<string> {
    const enabled = new Set<string>()
    for (const node of spec.nodes) {
        const parentEnabled = node.parentLinkId === null || enabled.has(node.parentLinkId)
        if (parentEnabled && conditionsHold(spec, node, answers)) enabled.add(node.linkId)
    }
    return enabled
}

/** Whether one item is asked, ancestors included. */
export function isEnabled(spec: QuestionnaireSpec, linkId: string, answers: AnswerState): boolean {
    return enabledLinkIds(spec, answers).has(linkId)
}

/**
 * Assemble the QuestionnaireResponse to POST.
 *
 * THE ENVELOPE COMES FROM `$generate`. A capture-valid response is not only its answers: it is
 * a `meta.profile` naming the form kind's response profile, a D2Period for an aggregate form, a
 * Location subject, an `authored` instant for an event, a tracked entity identifier and an
 * enrollment extension for a tracker event - the context `dhis2w_fhir_serve.capture.validate`
 * checks in its phases before it ever looks at an answer. Deriving that client-side would mean
 * reimplementing DHIS2 period arithmetic and the organisation-unit hierarchy in TypeScript, and
 * getting it subtly wrong. So this UI does not derive it. It asks the server for a skeleton -
 * one `GET /Questionnaire/{id}/$generate`, whose output the Python suite pins as postable to
 * this very server (`test_a_generated_response_posts_back_201`) - keeps that skeleton's
 * envelope, and replaces its answers with the user's. The user edits the answers; the server
 * owns the context.
 *
 * The seed identifier is deliberately *not* carried over: it says which draw produced these
 * answers, and once a person has edited them it would be a false claim about the submission.
 * With no envelope at all the response is still assembled, and the server's refusal naming the
 * missing context is a better error than a button that refuses to submit.
 */
export function buildQuestionnaireResponse(
    spec: QuestionnaireSpec,
    answers: AnswerState,
    questionnaire: Questionnaire,
    envelope: QuestionnaireResponse | null,
): QuestionnaireResponse {
    const enabled = enabledLinkIds(spec, answers)
    const item = spec.rootLinkIds.flatMap((linkId) => {
        const built = buildItem(spec, linkId, answers, enabled)
        return built === null ? [] : [built]
    })
    const questionnaireUrl = questionnaire.url ?? envelope?.questionnaire
    return {
        resourceType: 'QuestionnaireResponse',
        ...(envelope?.meta ? { meta: envelope.meta } : {}),
        ...(questionnaireUrl ? { questionnaire: questionnaireUrl } : {}),
        status: 'completed',
        ...(envelope?.extension ? { extension: envelope.extension } : {}),
        ...(envelope?.subject ? { subject: envelope.subject } : {}),
        ...(envelope?.authored ? { authored: envelope.authored } : {}),
        ...(item.length > 0 ? { item } : {}),
    }
}

/**
 * Read a QuestionnaireResponse back into answer state.
 *
 * This is what "fill with test data" is made of: `$generate` answers with a whole response, and
 * rather than posting it blind the UI pours its answers into the reducer so a person can look
 * at them, change one, and submit that. It is also the inverse `buildQuestionnaireResponse` is
 * tested against - refilling a generated response and rebuilding it must reproduce its item
 * tree exactly.
 *
 * Answers to link ids the form does not ask are dropped rather than kept: they could not be
 * rendered, so keeping them would mean submitting something invisible.
 */
export function answersFromResponse(spec: QuestionnaireSpec, response: QuestionnaireResponse): AnswerState {
    const answers: Record<string, readonly AnswerSlot[]> = {}
    const walk = (items: QuestionnaireResponseItem[]): void => {
        for (const item of items) {
            const node = spec.byLinkId.get(item.linkId)
            if (node !== undefined && item.answer !== undefined) {
                const slots = item.answer.flatMap((answer) => {
                    const slot = slotFromAnswer(answer)
                    return slot === null ? [] : [slot]
                })
                if (slots.length > 0) answers[item.linkId] = slots
            }
            walk(item.item ?? [])
        }
    }
    walk(response.item ?? [])
    return answers
}

/**
 * One slot as the `value[x]` the question answers on, or null when the slot holds nothing.
 *
 * Exported because it is the whole of the "is this question answered" question: a control that
 * wants to know whether a required question has been filled asks this, rather than
 * re-implementing "an empty string is not an answer but `false` is".
 */
export function slotAnswer(node: QuestionnaireNode, slot: AnswerSlot): QuestionnaireResponseAnswer | null {
    switch (node.answerElement) {
        case 'valueBoolean':
            if (slot.text === 'true') return { valueBoolean: true }
            if (slot.text === 'false') return { valueBoolean: false }
            return null
        case 'valueDecimal': {
            const parsed = Number(slot.text)
            return slot.text.trim() === '' || Number.isNaN(parsed) ? null : { valueDecimal: parsed }
        }
        case 'valueInteger': {
            const parsed = Number(slot.text)
            if (slot.text.trim() === '' || !Number.isInteger(parsed)) return null
            return { valueInteger: parsed }
        }
        case 'valueDate':
            return slot.text.trim() === '' ? null : { valueDate: slot.text }
        case 'valueDateTime': {
            const normalised = normaliseDateTime(slot.text)
            return normalised === null ? null : { valueDateTime: normalised }
        }
        case 'valueTime': {
            const normalised = normaliseTime(slot.text)
            return normalised === null ? null : { valueTime: normalised }
        }
        case 'valueString':
            return slot.text.trim() === '' ? null : { valueString: slot.text }
        case 'valueUri':
            return slot.text.trim() === '' ? null : { valueUri: slot.text }
        case 'valueCoding':
            if (slot.coding !== null) return { valueCoding: slot.coding }
            // R4 lets an `open-choice` answer be a plain string, which is exactly what the
            // free-text half of that control produces. A closed `choice` has no such spelling.
            if (node.type === 'open-choice' && slot.text.trim() !== '') return { valueString: slot.text }
            return null
        default:
            return null
    }
}

/** Whether one question has at least one answer that would be written. */
export function isAnswered(node: QuestionnaireNode, answers: AnswerState): boolean {
    return (answers[node.linkId] ?? []).some((slot) => slotAnswer(node, slot) !== null)
}

/** Every enabled, required question the form is still waiting on. */
export function unansweredRequiredLinkIds(spec: QuestionnaireSpec, answers: AnswerState): string[] {
    const enabled = enabledLinkIds(spec, answers)
    return spec.nodes
        .filter((node) => node.required && node.fillable && enabled.has(node.linkId) && !isAnswered(node, answers))
        .map((node) => node.linkId)
}

/**
 * An R4 `dateTime` from what `<input type="datetime-local">` produces, or null for nothing.
 *
 * The browser yields `2026-07-11T02:00` (seconds only when the step asks for them) and R4
 * requires seconds *and* a timezone whenever a time is present, which the capture validator
 * enforces through `is_fhir_date_time`. The wall time is read as UTC rather than as the
 * browser's zone: a DHIS2 capture instant is the one the form states, and silently shifting it
 * by whatever zone the operator's laptop is in would make the same keystrokes mean different
 * data in different offices. A value that already states a zone is left exactly as it is.
 */
export function normaliseDateTime(text: string): string | null {
    const trimmed = text.trim()
    if (trimmed === '') return null
    if (/(Z|[+-]\d{2}:\d{2})$/.test(trimmed)) return trimmed
    if (!trimmed.includes('T')) return trimmed
    return /T\d{2}:\d{2}$/.test(trimmed) ? `${trimmed}:00Z` : `${trimmed}Z`
}

/**
 * An R4 `time` from what `<input type="time">` produces, or null for nothing.
 *
 * R4 `time` has mandatory seconds (`FHIR_TIME_PATTERN` in `dhis2w_fhir.r4.primitives`) and the
 * browser omits them unless the input's step asks for them, so `20:00` becomes `20:00:00`.
 */
export function normaliseTime(text: string): string | null {
    const trimmed = text.trim()
    if (trimmed === '') return null
    return /^\d{2}:\d{2}$/.test(trimmed) ? `${trimmed}:00` : trimmed
}

/** What `<input type="datetime-local">` will accept back from a stored R4 dateTime. */
export function dateTimeInputValue(text: string): string {
    return text.replace(/(Z|[+-]\d{2}:\d{2})$/, '')
}

/** Read one Questionnaire item and its subtree, returning the link ids of the items read at this level. */
function collectItems(
    items: QuestionnaireItem[],
    ancestorLinkIds: string[],
    nodes: QuestionnaireNode[],
): string[] {
    const linkIds: string[] = []
    for (const item of items) {
        const node = readItem(item, ancestorLinkIds)
        nodes.push(node)
        linkIds.push(node.linkId)
        node.childLinkIds = collectItems(item.item ?? [], [...ancestorLinkIds, item.linkId], nodes)
    }
    return linkIds
}

/** One item, read into the node a control renders from. */
function readItem(item: QuestionnaireItem, ancestorLinkIds: string[]): QuestionnaireNode {
    const answerElement = ANSWER_ELEMENTS_BY_ITEM_TYPE[item.type] ?? null
    return {
        linkId: item.linkId,
        ancestorLinkIds,
        parentLinkId: ancestorLinkIds.at(-1) ?? null,
        depth: ancestorLinkIds.length,
        type: item.type,
        text: item.text ?? null,
        required: item.required === true,
        repeats: item.repeats === true,
        readOnly: item.readOnly === true,
        maxLength: item.maxLength ?? null,
        minimum: numericExtension(item, MINIMUM_VALUE_EXTENSION_URL),
        maximum: numericExtension(item, MAXIMUM_VALUE_EXTENSION_URL),
        answerElement,
        fillable: answerElement !== null && FILLABLE_ANSWER_ELEMENTS.has(answerElement),
        answerOptions: item.answerOption ?? [],
        answerValueSet: item.answerValueSet ?? null,
        enableWhen: item.enableWhen ?? [],
        // R4 makes `enableBehavior` mandatory once there is more than one condition, and `all`
        // is the reading that asks fewer questions - the safe direction for a capture form.
        enableBehavior: item.enableBehavior ?? 'all',
        initial: item.initial ?? [],
        code: item.code?.[0] ?? null,
        childLinkIds: [],
    }
}

/** The number one bounds extension states, on whichever numeric `value[x]` it was written with. */
function numericExtension(item: QuestionnaireItem, url: string): number | null {
    const extension = item.extension?.find((candidate) => candidate.url === url)
    if (extension === undefined) return null
    return extension.valueInteger ?? extension.valueDecimal ?? null
}

/** Whether one item's own conditions hold - ancestors are the caller's business. */
function conditionsHold(spec: QuestionnaireSpec, node: QuestionnaireNode, answers: AnswerState): boolean {
    if (node.enableWhen.length === 0) return true
    const holds = (condition: QuestionnaireEnableWhen) => conditionHolds(spec, condition, answers)
    return node.enableBehavior === 'any' ? node.enableWhen.some(holds) : node.enableWhen.every(holds)
}

/**
 * Whether one condition holds against the answers to the question it names.
 *
 * R4: a condition with a comparison operator holds when *any* answer to the named question
 * satisfies it, and a condition naming a question the form does not have never holds - which
 * hides the dependent item rather than showing it unconditionally, the conservative reading.
 */
function conditionHolds(spec: QuestionnaireSpec, condition: QuestionnaireEnableWhen, answers: AnswerState): boolean {
    const target = spec.byLinkId.get(condition.question)
    if (target === undefined) return false
    const values = (answers[condition.question] ?? []).flatMap((slot) => {
        const value = comparableSlot(target, slot)
        return value === null ? [] : [value]
    })
    if (condition.operator === 'exists') {
        // `exists` states its sense on `answerBoolean`; R4 requires it, and an absent one is
        // read as "must exist", which is what a form author writing `exists` alone means.
        return (values.length > 0) === (condition.answerBoolean !== false)
    }
    const expected = comparableCondition(condition)
    if (expected === null) return false
    return values.some((value) => comparesAs(value, expected, condition.operator))
}

/** One answer or condition operand, reduced to something two of them can be compared as. */
type ComparableValue =
    | { kind: 'number'; number: number }
    | { kind: 'text'; text: string }
    | { kind: 'boolean'; boolean: boolean }
    | { kind: 'coding'; coding: Coding }

/** What a slot compares as, read through the answer element the question it answers pins. */
function comparableSlot(node: QuestionnaireNode, slot: AnswerSlot): ComparableValue | null {
    const answer = slotAnswer(node, slot)
    if (answer === null) return null
    if (answer.valueBoolean !== undefined) return { kind: 'boolean', boolean: answer.valueBoolean }
    if (answer.valueDecimal !== undefined) return { kind: 'number', number: answer.valueDecimal }
    if (answer.valueInteger !== undefined) return { kind: 'number', number: answer.valueInteger }
    if (answer.valueCoding !== undefined) return { kind: 'coding', coding: answer.valueCoding }
    const text = answer.valueDate ?? answer.valueDateTime ?? answer.valueTime ?? answer.valueString ?? answer.valueUri
    return text === undefined ? null : { kind: 'text', text }
}

/** What a condition compares against, read off whichever `answer[x]` it states. */
function comparableCondition(condition: QuestionnaireEnableWhen): ComparableValue | null {
    if (condition.answerBoolean !== undefined) return { kind: 'boolean', boolean: condition.answerBoolean }
    if (condition.answerDecimal !== undefined) return { kind: 'number', number: condition.answerDecimal }
    if (condition.answerInteger !== undefined) return { kind: 'number', number: condition.answerInteger }
    if (condition.answerCoding !== undefined) return { kind: 'coding', coding: condition.answerCoding }
    const text =
        condition.answerDate ?? condition.answerDateTime ?? condition.answerTime ?? condition.answerString
    return text === undefined ? null : { kind: 'text', text }
}

/**
 * One comparison, on the two kinds of thing R4 lets be compared.
 *
 * Codings and booleans admit equality and nothing else - "greater than a concept" has no
 * meaning - and comparing values of different kinds is false rather than coerced, because a
 * form comparing a string against an integer is a form with a bug in it, and answering `true`
 * to it would show a question the author never meant to ask. Dates, dateTimes and times are
 * compared as text, which is exactly right for the ISO-8601 forms R4 pins them to.
 */
function comparesAs(
    left: ComparableValue,
    right: ComparableValue,
    operator: QuestionnaireEnableWhenOperator,
): boolean {
    if (left.kind !== right.kind) return false
    if (left.kind === 'coding' && right.kind === 'coding') {
        const same =
            left.coding.code === right.coding.code &&
            (left.coding.system === undefined ||
                right.coding.system === undefined ||
                left.coding.system === right.coding.system)
        if (operator === '=') return same
        if (operator === '!=') return !same
        return false
    }
    if (left.kind === 'boolean' && right.kind === 'boolean') {
        if (operator === '=') return left.boolean === right.boolean
        if (operator === '!=') return left.boolean !== right.boolean
        return false
    }
    if (left.kind === 'number' && right.kind === 'number') {
        return ordersAs(left.number, right.number, operator)
    }
    if (left.kind === 'text' && right.kind === 'text') {
        return ordersAs(left.text, right.text, operator)
    }
    return false
}

/** The six comparisons, over the two primitive kinds that admit an ordering. */
function ordersAs<T extends number | string>(
    left: T,
    right: T,
    operator: QuestionnaireEnableWhenOperator,
): boolean {
    switch (operator) {
        case '=':
            return left === right
        case '!=':
            return left !== right
        case '>':
            return left > right
        case '<':
            return left < right
        case '>=':
            return left >= right
        case '<=':
            return left <= right
        default:
            return false
    }
}

/** One response item for a node and its subtree, or null when nothing under it was answered. */
function buildItem(
    spec: QuestionnaireSpec,
    linkId: string,
    answers: AnswerState,
    enabled: ReadonlySet<string>,
): QuestionnaireResponseItem | null {
    const node = spec.byLinkId.get(linkId)
    if (node === undefined || !enabled.has(linkId)) return null
    // A `display` item is prose the form shows; it is not something the response answers, and
    // the capture validator would refuse an answer written under one.
    if (node.type === 'display') return null
    const children = node.childLinkIds.flatMap((childLinkId) => {
        const built = buildItem(spec, childLinkId, answers, enabled)
        return built === null ? [] : [built]
    })
    if (node.type === 'group') {
        return children.length > 0 ? { linkId, item: children } : null
    }
    const answer = (answers[linkId] ?? []).flatMap((slot) => {
        const built = slotAnswer(node, slot)
        return built === null ? [] : [built]
    })
    if (answer.length === 0 && children.length === 0) return null
    return {
        linkId,
        ...(answer.length > 0 ? { answer } : {}),
        ...(children.length > 0 ? { item: children } : {}),
    }
}

/**
 * One slot from a `value[x]` already settled - an answer off the wire, or a declared initial.
 *
 * Dispatching on which element is present rather than on the question's type is deliberate: an
 * `open-choice` answers as `valueCoding` or `valueString` depending on what was picked, so the
 * question's own answer element cannot decide this one.
 */
function slotFromAnswer(answer: QuestionnaireResponseAnswer): AnswerSlot | null {
    if (answer.valueCoding !== undefined) return { text: '', coding: answer.valueCoding }
    if (answer.valueBoolean !== undefined) return { text: String(answer.valueBoolean), coding: null }
    if (answer.valueDecimal !== undefined) return { text: String(answer.valueDecimal), coding: null }
    if (answer.valueInteger !== undefined) return { text: String(answer.valueInteger), coding: null }
    const text = answer.valueDate ?? answer.valueDateTime ?? answer.valueTime ?? answer.valueString ?? answer.valueUri
    if (text !== undefined) return { text, coding: null }
    // valueAttachment and valueReference have no control here, so there is nothing to fill.
    return null
}

/** One slot from an item's declared initial value, which is a `value[x]` in the same spelling. */
function slotFromInitial(initial: QuestionnaireInitial): AnswerSlot | null {
    return slotFromAnswer(initial)
}
