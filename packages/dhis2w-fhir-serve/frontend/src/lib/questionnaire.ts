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
 * the literal the control shows, plus the concept a coded control picked and the resource a
 * reference control picked - the two kinds of answer that arrive settled - and the conversion to
 * `value[x]` happens once, in `buildQuestionnaireResponse`, against the answer element the
 * question's item type pins. The temporal normalisers below are part of that conversion: an
 * `<input type="time">` yields `20:00`, and R4 `time` requires seconds, so what the browser
 * gives is not what the server accepts and the gap is closed here rather than in a component.
 *
 * WHERE THE ENVELOPE COMES FROM. See `buildQuestionnaireResponse`.
 */

import {
    attributeOptionComboExtensionUrl,
    attributeOptionComboOf,
    ATTRIBUTE_OPTION_COMBO_EXTENSION_SUFFIX,
    ENROLLED_AT_EXTENSION_SUFFIX,
    formTypeOf,
    identifierSystemBaseOf,
    INCIDENT_AT_EXTENSION_SUFFIX,
    registersAPerson,
    TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX,
    TRACKER_ENROLLMENT_EXTENSION_SUFFIX,
    TRACKER_ENROLLMENT_IDENTIFIER_SYSTEM_SUFFIX,
    trackerEnrollmentExtensionUrl,
    type CodeSystem,
    type Coding,
    type Extension,
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
    type Reference,
} from '@/lib/fhir'
import {
    carriesUnitOnExtension,
    ORG_UNIT_EXTENSION_SUFFIX,
    organisationUnitExtensionUrl,
    orgUnitReference,
    reportingUnitOf,
    type OrgUnitChoice,
} from '@/lib/orgunits'
import { isEntityLevelExtension, subjectExistsExtensionUrl, SUBJECT_EXISTS_EXTENSION_SUFFIX } from '@/lib/patients'
import { conceptPropertyValue } from '@/lib/terminology'

/** The standard R4 extensions a numeric question carries its inclusive bounds on. */
export const MINIMUM_VALUE_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/minValue'
export const MAXIMUM_VALUE_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/maxValue'

/** The extension a registration form declares whether its program collects an incident date on. */
export const COLLECTS_INCIDENT_DATE_EXTENSION_SUFFIX = '/StructureDefinition/d2-collects-incident-date'

/**
 * The extension an aggregate response states the period it reports for on.
 *
 * Complex rather than valued: the three sub-extensions below are what it carries, and the capture
 * validator grades them against each other. Matched on the suffix like every other canonical-rooted
 * url this UI meets - the canonical is whatever that project's fhir.toml declares.
 */
export const PERIOD_EXTENSION_SUFFIX = '/StructureDefinition/d2-period'

/** The sub-extension carrying the DHIS2 ISO period identifier - the period that is captured. */
export const PERIOD_ISO_SUB_EXTENSION = 'iso'

/** The sub-extension carrying the DHIS2 period type the ISO identifier reads as. */
export const PERIOD_TYPE_SUB_EXTENSION = 'type'

/** The sub-extension carrying the date range the ISO identifier resolves to. */
export const PERIOD_RANGE_SUB_EXTENSION = 'period'

/** The concept property a served data dictionary states a question's DHIS2 value type on. */
export const VALUE_TYPE_CONCEPT_PROPERTY = 'value-type'

/** The DHIS2 value type that stores `true` or no value at all - never `false`. */
export const TRUE_ONLY_VALUE_TYPE = 'TRUE_ONLY'

/** No value type known for any concept, which is what a form opens on before its dictionary lands. */
export const NO_VALUE_TYPES: ReadonlyMap<string, string> = new Map()

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
 * `valueAttachment` is the one left out: it needs a file, and a capture screen that invented one
 * would be inventing content rather than context. A question answering on it is rendered as a
 * read-only notice, and `buildQuestionnaireResponse` writes no answer for it - which is a
 * submission missing an answer, not a submission carrying a wrong one.
 *
 * `valueReference` is in, and it is the only element here whose control needs the server: a DHIS2
 * `ORGANISATION_UNIT` data element answers as a reference to a published Location, so the picker
 * offers the registry narrowed to the form's own assignment. See components/OrgUnitPicker.tsx.
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
    'valueReference',
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
    /**
     * The DHIS2 value type the served data dictionary gives this question's concept, or null.
     *
     * R4 spells `BOOLEAN` and `TRUE_ONLY` as one `#boolean` item type, so the form itself cannot
     * tell the two apart. The fact lives on the concept the item's `code` names, as the
     * `value-type` property of the support CodeSystem the guide publishes beside the form -
     * `D2DE_CS` for a data element, `D2TEA_CS` for a tracked entity attribute.
     *
     * Null means the dictionary says nothing here, which is also what a form opened before its
     * CodeSystem was read holds. It is read as "the form does not say" rather than as any
     * particular type, so a boolean question keeps the three states a `BOOLEAN` has.
     */
    valueType: string | null
    /**
     * Which DHIS2 level this question's answer is written at, or null when the form states none.
     *
     * True is the tracked entity - the person themselves - and false is the enrollment. Null is
     * every question of every other kind, and also a registration form compiled before the guide
     * published `D2EntityLevel`: absence is not "enrollment level", it is "this form does not say",
     * and a screen that read it as false would unlock questions it has no grounds to unlock.
     */
    entityLevel: boolean | null
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

/**
 * One answer slot as the form holds it mid-edit: the literal a control shows, and what it picked.
 *
 * THREE FIELDS, NOT ONE STRING. A picked concept and a picked resource are settled values with no
 * half-typed states, so neither travels through `text`: a `Coding` has a system and a display
 * beside its code, a `Reference` has a display beside its `Location/<stem>`, and squeezing either
 * into the string a keyboard writes would mean parsing it back out at submit time and losing
 * whatever the wire carried. Exactly one of the three is meaningful per question, and which one is
 * decided by the item type's answer element rather than by inspecting the slot.
 */
export interface AnswerSlot {
    /**
     * What every text-shaped control holds verbatim - strings, numbers mid-typing, dates,
     * times, urls - and what a boolean holds as `'true'` or `'false'`.
     */
    text: string
    /** The concept a coded control picked, or null for every other control and for none picked. */
    coding: Coding | null
    /** The resource a reference control picked, or null for every other control and for none picked. */
    reference: Reference | null
}

/** Every answer of one form, keyed by link id; a question with no entry is unanswered. */
export type AnswerState = Readonly<Record<string, readonly AnswerSlot[]>>

/** A slot holding nothing, which is what a fresh repeat row and a cleared control both are. */
export const EMPTY_SLOT: AnswerSlot = { text: '', coding: null, reference: null }

/** Everything that can happen to the answers of one form. */
export type AnswerAction =
    | { kind: 'set'; linkId: string; index: number; slot: AnswerSlot }
    | { kind: 'clear'; linkId: string }
    | { kind: 'add-repeat'; linkId: string }
    | { kind: 'remove-repeat'; linkId: string; index: number }
    | { kind: 'replace'; answers: AnswerState }

/**
 * Flatten one Questionnaire's item tree into the ordered spec every other function here reads.
 *
 * `valueTypes` is the served data dictionary, keyed by the concept each question's `code` names -
 * see `valueTypesByConcept`. It is optional because the form is on screen before its CodeSystem
 * has been read, and because every reader but the boolean control works without it: a spec
 * flattened with no dictionary states no value type, which is what an unread dictionary is.
 */
export function flattenQuestionnaire(
    questionnaire: Questionnaire,
    valueTypes: ReadonlyMap<string, string> = NO_VALUE_TYPES,
): QuestionnaireSpec {
    const nodes: QuestionnaireNode[] = []
    const rootLinkIds = collectItems(questionnaire.item ?? [], [], nodes, valueTypes)
    const byLinkId = new Map(nodes.map((node) => [node.linkId, node]))
    const questionLinkIds = nodes
        .filter((node) => node.type !== 'group' && node.type !== 'display')
        .map((node) => node.linkId)
    return { nodes, byLinkId, rootLinkIds, questionLinkIds }
}

/**
 * The DHIS2 value types a set of served CodeSystems states, keyed by the concept each belongs to.
 *
 * WHY THE KEY IS SYSTEM AND CODE. A question's `code` names both, and two dictionaries can hold the
 * same code for different objects - a data element and a tracked entity attribute are separate DHIS2
 * uid spaces. Keying by the pair is what makes this one map safe to build over every dictionary a
 * form draws from, rather than one map per system with a lookup order to get wrong.
 *
 * A concept carrying no `value-type` property contributes nothing, which is the honest reading: the
 * property is optional, and a guide compiled before it was published states none at all.
 */
export function valueTypesByConcept(codeSystems: CodeSystem[]): ReadonlyMap<string, string> {
    const valueTypes = new Map<string, string>()
    for (const codeSystem of codeSystems) {
        for (const concept of codeSystem.concept ?? []) {
            const valueType = conceptPropertyValue(concept, VALUE_TYPE_CONCEPT_PROPERTY)
            if (valueType === null) continue
            valueTypes.set(conceptKey(codeSystem.url, concept.code), valueType)
        }
    }
    return valueTypes
}

/**
 * The ids of the CodeSystems one form's questions are coded in, in first-seen order.
 *
 * This server ids every resource by the last segment of its canonical, so a question coded in
 * `.../CodeSystem/d2-de-cs` is a dictionary read at `/CodeSystem/d2-de-cs` - which is what lets a
 * capture screen read the two or three dictionaries its own form uses rather than the whole
 * terminology. A coding into anything else names no served CodeSystem and is left out.
 */
export function questionCodeSystemIds(spec: QuestionnaireSpec): string[] {
    const ids: string[] = []
    for (const node of spec.nodes) {
        const id = codeSystemId(node.code?.system)
        if (id !== null && !ids.includes(id)) ids.push(id)
    }
    return ids
}

/** The id a served CodeSystem is read under, off a coding's system, or null when it names none. */
function codeSystemId(system: string | undefined): string | null {
    if (system === undefined) return null
    const segments = system.split('/').filter((segment) => segment !== '')
    const id = segments.at(-1)
    return segments.at(-2) === 'CodeSystem' && id !== undefined ? id : null
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
 *
 * TWO PIECES OF CONTEXT ARE THE USER'S, and both are *written over* the envelope rather than taken
 * from it - on exactly the philosophy the answers follow. The attribute option combo is the third
 * key of a DHIS2 data value, beside the organisation unit and the period, and unlike those two it
 * is derivable from nothing: which project a month of stock figures is reported under is a fact
 * only the person filling the form has. The organisation unit is derivable - `$generate` draws one
 * the form admits - but it is a choice, not a fact about the form: a district officer covering four
 * facilities reports the same form from a different one each morning, and a screen that made them
 * accept whichever unit the draw happened to pick would be a screen for one facility.
 *
 * A null in either leaves the envelope exactly as it came. For the combo that is the whole of the
 * default-combo case - a form declaring no vocabulary has nothing to pick and nothing to write. For
 * the unit it is the case where `$generate` was refused: there is no envelope to correct, and the
 * server's refusal naming the missing context is a better answer than a guess at it.
 *
 * THE THIRD PIECE IS THE ENROLLMENT A STAGE SUBMISSION ANSWERS AGAINST, and it is the one piece
 * the envelope gets *wrong* rather than merely proposes: `$generate` mints synthetic tracked
 * entity and enrollment uids that name nothing in any DHIS2, so a stage submission carrying them
 * is refused at forward time. When a real pair is chosen - one a registration capture on this very
 * server minted - it is written over the envelope in place, on both spots the profile reads: the
 * `subject.identifier` value and the enrollment extension's identifier value, each keeping the
 * envelope's own system and url spellings. Null keeps the synthetic draw, stated on the page
 * rather than hidden; and the rewrite runs only for the tracker-event kind, because no other
 * kind's response names an enrollment.
 *
 * THE FOURTH IS WHO A REGISTRATION IS ABOUT, and it changes the item tree rather than only the
 * envelope. `$generate` mints a tracked-entity uid because the ordinary registration creates a
 * person; a registration answering for a person this DHIS2 instance already holds names that
 * person's real uid instead, carries the `D2SubjectExists` marker so the forwarder writes onto
 * that person rather than creating one, and writes no entity-level answer at all - the instance
 * holds those values, and `d2w fhir forward` refuses a submission that states its subject exists
 * and carries one anyway. The rewrite runs only for the two kinds that register a person, because
 * no other kind's subject is one.
 *
 * THE FIFTH IS THE DATE THE SUBMISSION IS ABOUT, and it is the one the person filling the form knows
 * better than any draw can. An event is recorded on a day - the forwarder reads `TrackerEvent.occurredAt`
 * off `authored` - a registration files an enrollment that begins on a day, and an aggregate
 * submission reports for one DHIS2 period. `$generate` draws all three so the draft is postable, and
 * a capture of last Tuesday's visit is a capture of last Tuesday: the drafted value is the default
 * and an edit rides the envelope in the slot the draft put it in. Each of these rewrites replaces
 * what the envelope states and writes nothing where it states nothing, so a context of a kind the
 * response does not carry is a no-op rather than an invention - an aggregate envelope holds no
 * enrollment date to replace, and an event envelope holds no period.
 */
export function buildQuestionnaireResponse(
    spec: QuestionnaireSpec,
    answers: AnswerState,
    questionnaire: Questionnaire,
    envelope: QuestionnaireResponse | null,
    context: CaptureContext,
): QuestionnaireResponse {
    const formKind = formTypeOf(questionnaire)
    const existingSubject = registersAPerson(formKind) ? context.existingSubject : null
    const enabled = enabledLinkIds(spec, answers)
    const answerable = existingSubject === null ? enabled : withoutEntityLevel(spec, enabled)
    const item = spec.rootLinkIds.flatMap((linkId) => {
        const built = buildItem(spec, linkId, answers, answerable)
        return built === null ? [] : [built]
    })
    const questionnaireUrl = questionnaire.url ?? envelope?.questionnaire
    const withCombo = extensionsWithAttributeOptionCombo(questionnaire, envelope, context.attributeOptionCombo)
    const onExtension = carriesUnitOnExtension(formKind)
    const withUnit = onExtension
        ? extensionsWithReportingUnit(questionnaire, withCombo, context.reportingUnit)
        : withCombo
    const chosenEnrollment = formKind === 'tracker-event' ? context.enrollment : null
    const withEnrollment =
        chosenEnrollment === null ? withUnit : extensionsWithEnrollment(questionnaire, withUnit, chosenEnrollment)
    const withDates = extensionsWithIncidentAt(
        extensionsWithEnrolledAt(withEnrollment, context.enrolledAt),
        context.incidentAt,
    )
    const withPeriod = extensionsWithReportingPeriod(withDates, context.reportingPeriodIso)
    const extension =
        existingSubject === null ? withPeriod : extensionsWithSubjectExists(questionnaire, withPeriod)
    const statedSubject = onExtension ? envelope?.subject : (context.reportingUnit ?? envelope?.subject)
    const namedEntity = chosenEnrollment?.trackedEntity ?? existingSubject?.trackedEntity ?? null
    const subject =
        namedEntity === null ? statedSubject : subjectWithTrackedEntity(questionnaire, statedSubject, namedEntity)
    // The visit date of an event, on the one element that carries it: the forwarder reads
    // `TrackerEvent.occurredAt` off `authored`, so editing when the visit happened is editing this.
    const authored = context.authored ?? envelope?.authored
    return {
        resourceType: 'QuestionnaireResponse',
        ...(envelope?.meta ? { meta: envelope.meta } : {}),
        ...(questionnaireUrl ? { questionnaire: questionnaireUrl } : {}),
        status: 'completed',
        ...(extension.length > 0 ? { extension } : {}),
        ...(subject ? { subject } : {}),
        ...(authored ? { authored } : {}),
        ...(item.length > 0 ? { item } : {}),
    }
}

/** The capture context this screen owns, as against the envelope `$generate` drew around it. */
export interface CaptureContext {
    /** The attribute option combo the whole submission is filed under, or null when none is chosen. */
    attributeOptionCombo: Coding | null
    /** The organisation unit the submission reports from, or null to keep whatever the envelope drew. */
    reportingUnit: Reference | null
    /** The enrollment a stage submission answers against, or null to keep the synthetic draw. */
    enrollment: EnrollmentChoice | null
    /**
     * When an event was recorded, as an R4 `dateTime`, or null to keep the instant the draft authored.
     *
     * The visit date of an event or a stage submission: DHIS2 has no element of its own for it here,
     * because the forwarder derives `TrackerEvent.occurredAt` from `QuestionnaireResponse.authored`.
     */
    authored: string | null
    /** When the enrollment a registration files begins, or null to keep the date the draft drew. */
    enrolledAt: string | null
    /** When the incident that enrollment follows occurred, or null to keep the date the draft drew. */
    incidentAt: string | null
    /** The DHIS2 ISO period an aggregate submission reports for, or null to keep the drafted one. */
    reportingPeriodIso: string | null
    /**
     * The person this DHIS2 instance already holds that a registration is about, or null for a new one.
     *
     * Null is the ordinary registration: the envelope's minted tracked-entity uid stands, every
     * question is asked, and the submission creates a person. A value replaces that uid with a real
     * one, marks the submission so the conversion layer knows the person is not being created, and
     * takes the entity-level answers out of the item tree.
     */
    existingSubject: ExistingSubject | null
}

/**
 * A person the instance already holds, as a submission names them.
 *
 * One uid, because that is all the rewrite writes: everything else a search result carries - the
 * identifier values, the attribute values, the enrollments - belongs to the picker rather than to
 * the wire.
 */
export interface ExistingSubject {
    /** The DHIS2 tracked-entity uid of the person this submission is about. */
    trackedEntity: string
}

/**
 * The identifier pair one registration capture minted, as a stage submission names it.
 *
 * Two uids and nothing else, because that is all the rewrite writes: the display facts an offer
 * carries beside them (the date, the lifecycle) belong to the picker, not to the wire.
 */
export interface EnrollmentChoice {
    /** The DHIS2 tracked-entity uid the submission is about. */
    trackedEntity: string
    /** The DHIS2 enrollment uid the submission answers against. */
    enrollment: string
}

/** Nothing chosen, which is what a form holds before its skeleton lands. */
export const NO_CAPTURE_CONTEXT: CaptureContext = {
    attributeOptionCombo: null,
    reportingUnit: null,
    enrollment: null,
    authored: null,
    enrolledAt: null,
    incidentAt: null,
    reportingPeriodIso: null,
    existingSubject: null,
}

/**
 * The picker's selection when a form is first opened: whatever is chosen, else what the server drew.
 *
 * `$generate` answers with a whole capture-valid context, combo included, and adopting it is what
 * makes the common case one click - the form opens already reporting for something plausible, and
 * changing it is a choice rather than a chore. The current selection wins because the skeleton is
 * read *after* the form is on screen: a person who picked while it was still in flight must not
 * have their choice replaced by a draw that started before they made it.
 */
export function openedAttributeOptionCombo(
    current: Coding | null,
    envelope: QuestionnaireResponse | null,
): Coding | null {
    return current ?? (envelope === null ? null : attributeOptionComboOf(envelope))
}

/**
 * The picker's selection after "fill with test data": what the fresh draw states, else what is chosen.
 *
 * The other order, and for the same reason the answers are replaced wholesale - a refill is the
 * server proposing a whole submission, so its combo lands in the picker too. A draw that states no
 * combo leaves the selection alone rather than clearing it: an emptied picker would take a required
 * choice away from a person who had already made one.
 */
export function refilledAttributeOptionCombo(
    current: Coding | null,
    envelope: QuestionnaireResponse | null,
): Coding | null {
    return (envelope === null ? null : attributeOptionComboOf(envelope)) ?? current
}

/** What a form opens reporting from, and whether a kept organisation unit is why it is not that one. */
export interface OpenedReportingUnit {
    /** The organisation unit the picker holds, or null when there is nothing to hold yet. */
    unit: Reference | null
    /**
     * True when this browser tab keeps an organisation unit and this form's assignment excludes it.
     *
     * The form then reports from the unit the draft drew, and the picker states the mismatch: a kept
     * unit that quietly changes between two forms is the one outcome worse than keeping none.
     */
    keptUnitNotAdmitted: boolean
}

/**
 * The reporting unit when a form is first opened: whatever is chosen, then what this tab keeps,
 * then what the server drew.
 *
 * A CHOICE ALREADY MADE ALWAYS WINS, on the rule the combo follows: the skeleton is read after the
 * form is on screen, so a person who picked while it was in flight keeps their choice.
 *
 * THE KEPT UNIT COMES BEFORE THE DRAW because it is the one a person actually reports from. A
 * supervisor filling six forms for one facility answers this control once, and every form after that
 * opens on the same unit rather than on whichever unit the draw happened to land on. It is kept for
 * the browser tab and no longer - see the store in pages/FormFill.tsx.
 *
 * THE ASSIGNMENT HAS THE LAST WORD. `$generate` picks a unit the form's assignment admits
 * (`_capture_location_id` in `dhis2w_fhir_serve.synthesize`), and a kept unit carries no such
 * promise - a form assigned to two facilities is refused at DHIS2 for any unit outside them. So a
 * kept unit the offer does not hold is not adopted, the draw stands, and the mismatch is stated
 * rather than left for the person to notice.
 *
 * `admitted` is the offer a picker would show, or null while it is still being read - null adopts
 * nothing and reports no mismatch, because a unit cannot be graded against an offer nobody has yet.
 */
export function openedReportingUnit(
    current: Reference | null,
    envelope: QuestionnaireResponse | null,
    questionnaire: Questionnaire | null,
    keptUnitId: string | null = null,
    admitted: ReadonlyMap<string, OrgUnitChoice> | null = null,
): OpenedReportingUnit {
    if (current !== null) return { unit: current, keptUnitNotAdmitted: false }
    const drawn =
        envelope === null || questionnaire === null ? null : reportingUnitOf(envelope, formTypeOf(questionnaire))
    if (keptUnitId === null || admitted === null) return { unit: drawn, keptUnitNotAdmitted: false }
    const kept = admitted.get(keptUnitId)
    if (kept === undefined) return { unit: drawn, keptUnitNotAdmitted: true }
    return { unit: orgUnitReference(kept), keptUnitNotAdmitted: false }
}

/**
 * The reporting unit after "fill with test data": what the fresh draw states, else what is chosen.
 *
 * The other order, because a refill is the server proposing a whole submission - envelope included
 * - and a draw that states no unit leaves the selection alone rather than emptying a control the
 * person had already answered.
 */
export function refilledReportingUnit(
    current: Reference | null,
    envelope: QuestionnaireResponse | null,
    questionnaire: Questionnaire | null,
): Reference | null {
    if (envelope === null || questionnaire === null) return current
    return reportingUnitOf(envelope, formTypeOf(questionnaire)) ?? current
}

/**
 * Every question whose answer is written onto the person rather than onto their enrollment.
 *
 * `D2EntityLevel` true is the whole of it - the level the form itself states - and a question that
 * states nothing is not in the set, because absence means the form does not say rather than that
 * the answer rides the enrollment.
 */
export function entityLevelLinkIds(spec: QuestionnaireSpec): ReadonlySet<string> {
    return new Set(spec.nodes.filter((node) => node.entityLevel === true).map((node) => node.linkId))
}

/**
 * The answers with every entity-level one dropped.
 *
 * WHY THEY ARE DROPPED RATHER THAN HIDDEN. A submission about a person this DHIS2 instance already
 * holds carries no entity-level answers at all: the instance has that person's record, and the
 * forwarder refuses a submission that states its subject exists and carries one anyway. Hiding the
 * questions while keeping what was typed would leave a value in state that Submit would then have
 * to remember not to send - so what is unanswerable is unanswered, and the screen and the wire
 * agree without a second rule between them.
 *
 * The identity of the state object is preserved when nothing changes, so choosing a person the
 * instance already holds on a blank form does not rerender every control for no reason.
 */
export function clearedEntityLevelAnswers(spec: QuestionnaireSpec, answers: AnswerState): AnswerState {
    const entityLevel = entityLevelLinkIds(spec)
    const held = Object.keys(answers).filter((linkId) => entityLevel.has(linkId))
    if (held.length === 0) return answers
    const next = { ...answers }
    for (const linkId of held) delete next[linkId]
    return next
}

/**
 * The enrollment after "fill with test data": exactly what was chosen, never the fresh draw.
 *
 * The opposite rule from the combo and the unit, and deliberately so. For those two the refill's
 * draw wins because the server's proposal is a plausible value of the same kind the person would
 * pick. Here it is not: a fresh `$generate` mints a fresh *synthetic* pair, and adopting it would
 * replace a real enrollment the person chose with uids that name nothing - turning a submission
 * that would land into one DHIS2 refuses, silently, on the press of a button about answers. So
 * the answers refill and the identity stands.
 *
 * Generic so the page's richer offer shape (the choice plus its display facts) passes through
 * with its type intact - the rule is about identity, not about which fields ride along.
 */
export function refilledEnrollment<Choice extends EnrollmentChoice>(current: Choice | null): Choice | null {
    return current
}

/** The period an aggregate response reports for: the identifier DHIS2 keys it by, and its type. */
export interface ReportingPeriod {
    /** The DHIS2 ISO period identifier, as `202607` is July 2026. */
    iso: string
    /** The DHIS2 period type the identifier reads as, as `Monthly`, or null when none is stated. */
    periodType: string | null
}

/**
 * The period a response reports for, or null when it states none - which every non-aggregate kind is.
 *
 * The type is read beside the identifier because it is not derivable here: turning `202607` into
 * `Monthly` is DHIS2 period arithmetic, and this UI holds none of it. The draft states both, and
 * what a person edits is the identifier.
 */
export function reportingPeriodOf(response: QuestionnaireResponse | null): ReportingPeriod | null {
    const stated = periodExtension(response?.extension ?? [])
    const iso = subExtension(stated, PERIOD_ISO_SUB_EXTENSION)?.valueString
    if (iso === undefined) return null
    return { iso, periodType: subExtension(stated, PERIOD_TYPE_SUB_EXTENSION)?.valueCode ?? null }
}

/** Whether a registration form's program collects an incident date, as the form itself declares. */
export function collectsIncidentDate(questionnaire: Questionnaire): boolean {
    const declared = questionnaire.extension?.find((candidate) =>
        candidate.url.endsWith(COLLECTS_INCIDENT_DATE_EXTENSION_SUFFIX),
    )
    return declared?.valueBoolean === true
}

/**
 * The extensions with an edited ISO period written into them, for an aggregate response.
 *
 * THE RANGE IS DROPPED RATHER THAN RECOMPUTED, and that is the whole of this function. The capture
 * validator grades all three sub-extensions against each other: the `type` has to be the type the
 * ISO identifier parses as, and the `period` range has to be the range that identifier resolves to.
 * The range is optional - zero of it is valid, and the validator says so in the same breath ("the
 * ISO period is what is captured") - and this UI has no DHIS2 period arithmetic to resolve a new
 * identifier with. So an edited period writes the identifier, keeps the type the draft stated, and
 * carries no range at all rather than a range it cannot stand behind. An identifier of a different
 * type is then refused by the server, naming both types, which is a better answer than a client
 * guess at what the operator meant.
 *
 * The drafted identifier passes the whole extension through untouched, so a submission nobody
 * edited is byte-for-byte the one `$generate` drew.
 */
export function extensionsWithReportingPeriod(carried: Extension[], iso: string | null): Extension[] {
    if (iso === null) return carried
    const stated = periodExtension(carried)
    const drafted = subExtension(stated, PERIOD_ISO_SUB_EXTENSION)
    if (stated === undefined || drafted === undefined || drafted.valueString === iso) return carried
    const written: Extension = {
        ...stated,
        extension: (stated.extension ?? []).flatMap((sub) => {
            if (sub.url === PERIOD_RANGE_SUB_EXTENSION) return []
            return [sub === drafted ? { ...sub, valueString: iso } : sub]
        }),
    }
    return carried.map((candidate) => (candidate === stated ? written : candidate))
}

/** The extensions with an edited enrollment date written into them, for a registration response. */
export function extensionsWithEnrolledAt(carried: Extension[], enrolledAt: string | null): Extension[] {
    return extensionsWithInstant(carried, ENROLLED_AT_EXTENSION_SUFFIX, enrolledAt)
}

/** The extensions with an edited incident date written into them, for a registration response. */
export function extensionsWithIncidentAt(carried: Extension[], incidentAt: string | null): Extension[] {
    return extensionsWithInstant(carried, INCIDENT_AT_EXTENSION_SUFFIX, incidentAt)
}

/**
 * One dated extension replaced in place, or the list unchanged when it carries no such extension.
 *
 * Replace-in-place and nothing else, unlike its neighbours below, which fall back to a url derived
 * from the form. These two dates are drawn by `$generate` as part of what makes a registration
 * postable, and the controls over them exist exactly when the draft states them - so there is never
 * an edit to place under a url nobody wrote, and a guessed one would be a fact nobody can read back.
 */
function extensionsWithInstant(carried: Extension[], suffix: string, instant: string | null): Extension[] {
    if (instant === null) return carried
    const stated = carried.find((candidate) => candidate.url.endsWith(suffix))
    if (stated === undefined || stated.valueDateTime === instant) return carried
    return carried.map((candidate) => (candidate === stated ? { ...candidate, valueDateTime: instant } : candidate))
}

/** The one D2Period extension a list carries, or undefined for the kinds that report for no period. */
function periodExtension(carried: Extension[]): Extension | undefined {
    return carried.find((candidate) => candidate.url.endsWith(PERIOD_EXTENSION_SUFFIX))
}

/** One sub-extension of a complex extension, named by the bare url the IG slices it under. */
function subExtension(extension: Extension | undefined, url: string): Extension | undefined {
    return extension?.extension?.find((candidate) => candidate.url === url)
}

/**
 * The envelope's extensions with the chosen combo written into them.
 *
 * The url is the envelope's own spelling when it already carries the extension, so a project served
 * under one canonical and compiled under another keeps the server's; otherwise it is derived from
 * the form's own declaration. Nothing is written when neither states a url, because an extension
 * under a guessed canonical is a fact nobody can read back.
 */
function extensionsWithAttributeOptionCombo(
    questionnaire: Questionnaire,
    envelope: QuestionnaireResponse | null,
    attributeOptionCombo: Coding | null,
): Extension[] {
    const carried = envelope?.extension ?? []
    if (attributeOptionCombo === null) return [...carried]
    const stated = carried.find((candidate) => candidate.url.endsWith(ATTRIBUTE_OPTION_COMBO_EXTENSION_SUFFIX))
    const url = stated?.url ?? attributeOptionComboExtensionUrl(questionnaire)
    if (url === null) return [...carried]
    const written: Extension = { url, valueCoding: attributeOptionCombo }
    // Replaced where the server wrote it, so a rebuilt response reads as the same document rather
    // than as one with its context shuffled to the end.
    if (stated === undefined) return [...carried, written]
    return carried.map((candidate) => (candidate === stated ? written : candidate))
}

/**
 * The extensions with the chosen organisation unit written into them, for a tracker response.
 *
 * The same replace-in-place discipline the combo follows: the envelope's own url wins when it
 * already states one, the form's canonical is the fallback, and nothing is written under a url
 * neither of them names. `carriesUnitOnExtension` is what decides this runs at all - an aggregate
 * or event response names its unit as `subject` and never reaches here.
 */
function extensionsWithReportingUnit(
    questionnaire: Questionnaire,
    carried: Extension[],
    reportingUnit: Reference | null,
): Extension[] {
    if (reportingUnit === null) return carried
    const stated = carried.find((candidate) => candidate.url.endsWith(ORG_UNIT_EXTENSION_SUFFIX))
    const url = stated?.url ?? organisationUnitExtensionUrl(questionnaire)
    if (url === null) return carried
    const written: Extension = { url, valueReference: reportingUnit }
    if (stated === undefined) return [...carried, written]
    return carried.map((candidate) => (candidate === stated ? written : candidate))
}

/**
 * The extensions with the chosen enrollment written into them, for a stage response.
 *
 * The same replace-in-place discipline the combo and the unit follow: the envelope's own url and
 * identifier system win when it states them, the form's declarations are the fallback for the
 * no-envelope case, and nothing is written under a url neither of them names. The fallback
 * matters more here than for its neighbours: with no envelope the response carries no enrollment
 * at all, and a person who explicitly chose one deserves better than having the choice silently
 * dropped on the floor because `$generate` was refused.
 */
function extensionsWithEnrollment(
    questionnaire: Questionnaire,
    carried: Extension[],
    choice: EnrollmentChoice,
): Extension[] {
    const stated = carried.find((candidate) => candidate.url.endsWith(TRACKER_ENROLLMENT_EXTENSION_SUFFIX))
    const url = stated?.url ?? trackerEnrollmentExtensionUrl(questionnaire)
    if (url === null) return carried
    const base = identifierSystemBaseOf(questionnaire)
    const system =
        stated?.valueIdentifier?.system ??
        (base === null ? undefined : `${base}${TRACKER_ENROLLMENT_IDENTIFIER_SYSTEM_SUFFIX}`)
    const written: Extension = {
        url,
        valueIdentifier: { ...(system === undefined ? {} : { system }), value: choice.enrollment },
    }
    if (stated === undefined) return [...carried, written]
    return carried.map((candidate) => (candidate === stated ? written : candidate))
}

/**
 * The extensions with the `D2SubjectExists` marker written into them, for a registration response.
 *
 * The same replace-in-place discipline the combo, the unit, and the enrollment follow: the
 * envelope's own url wins when it already carries the marker, the form's canonical is the
 * fallback, and nothing is written under a url neither of them names. `$generate` never draws one
 * - every skeleton it produces is about a new person - so in practice this always appends.
 */
function extensionsWithSubjectExists(questionnaire: Questionnaire, carried: Extension[]): Extension[] {
    const stated = carried.find((candidate) => candidate.url.endsWith(SUBJECT_EXISTS_EXTENSION_SUFFIX))
    const url = stated?.url ?? subjectExistsExtensionUrl(questionnaire)
    if (url === null) return carried
    const written: Extension = { url, valueBoolean: true }
    if (stated === undefined) return [...carried, written]
    return carried.map((candidate) => (candidate === stated ? written : candidate))
}

/**
 * The subject with a real tracked entity written into it, for any response about a named person.
 *
 * Two callers, one rewrite: a stage form answering for a chosen enrollment, and a registration
 * answering for a person this instance already holds. Both are the same edit - the envelope's
 * minted uid is a placeholder and the chosen uid is the fact.
 *
 * When the envelope named its synthetic entity the reference is kept whole and only the
 * identifier's value is replaced - same system, same type, same everything else, so the rebuilt
 * response reads as the same document about a different person. With no envelope the subject is
 * built from the form's own statements: the identifier system derived off the form's program
 * identifier, and the type off `subjectType`, which the generator writes on every tracker form.
 * A form stating neither yields no subject at all, and the server's refusal names what is
 * missing better than a guessed system could.
 */
function subjectWithTrackedEntity(
    questionnaire: Questionnaire,
    stated: Reference | undefined,
    trackedEntity: string,
): Reference | undefined {
    const identifier = stated?.identifier
    if (stated !== undefined && identifier?.system?.endsWith(TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX) === true) {
        return { ...stated, identifier: { ...identifier, value: trackedEntity } }
    }
    const base = identifierSystemBaseOf(questionnaire)
    if (base === null) return stated
    return {
        ...(questionnaire.subjectType?.[0] === undefined ? {} : { type: questionnaire.subjectType[0] }),
        identifier: { system: `${base}${TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX}`, value: trackedEntity },
    }
}

/** The enabled set with every entity-level question taken out of it, so no answer is written for one. */
function withoutEntityLevel(spec: QuestionnaireSpec, enabled: ReadonlySet<string>): ReadonlySet<string> {
    const entityLevel = entityLevelLinkIds(spec)
    return new Set([...enabled].filter((linkId) => !entityLevel.has(linkId)))
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
            // A TRUE_ONLY question stores `true` or no value at all, so `false` is not an answer it
            // has: the forwarder drops one, and a submission carrying it would claim something DHIS2
            // never records. The control for one offers no No either - see components/AnswerControl.tsx.
            if (slot.text === 'false' && node.valueType !== TRUE_ONLY_VALUE_TYPE) return { valueBoolean: false }
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
        case 'valueReference':
            // No text spelling to fall back on: a DHIS2 `ORGANISATION_UNIT` answer is a reference
            // to a published Location or it is nothing, and the capture validator reads the shape.
            return slot.reference === null ? null : { valueReference: slot.reference }
        default:
            return null
    }
}

/** Whether one question has at least one answer that would be written. */
export function isAnswered(node: QuestionnaireNode, answers: AnswerState): boolean {
    return (answers[node.linkId] ?? []).some((slot) => slotAnswer(node, slot) !== null)
}

/**
 * Every enabled, required question the form is still waiting on.
 *
 * `exempt` is the set the submission will not carry however the form is filled - today the
 * entity-level questions of a registration answering for a person the instance already holds. A
 * question in it is not "still waiting": nothing anyone types would reach the wire, so counting it
 * would tell a person their form is incomplete and give them no way to complete it.
 */
export function unansweredRequiredLinkIds(
    spec: QuestionnaireSpec,
    answers: AnswerState,
    exempt: ReadonlySet<string> = new Set(),
): string[] {
    const enabled = enabledLinkIds(spec, answers)
    return spec.nodes
        .filter(
            (node) =>
                node.required &&
                node.fillable &&
                enabled.has(node.linkId) &&
                !exempt.has(node.linkId) &&
                !isAnswered(node, answers),
        )
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
    valueTypes: ReadonlyMap<string, string>,
): string[] {
    const linkIds: string[] = []
    for (const item of items) {
        const node = readItem(item, ancestorLinkIds, valueTypes)
        nodes.push(node)
        linkIds.push(node.linkId)
        node.childLinkIds = collectItems(item.item ?? [], [...ancestorLinkIds, item.linkId], nodes, valueTypes)
    }
    return linkIds
}

/** One item, read into the node a control renders from. */
function readItem(
    item: QuestionnaireItem,
    ancestorLinkIds: string[],
    valueTypes: ReadonlyMap<string, string>,
): QuestionnaireNode {
    const answerElement = ANSWER_ELEMENTS_BY_ITEM_TYPE[item.type] ?? null
    const code = item.code?.[0] ?? null
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
        code,
        valueType: code === null ? null : (valueTypes.get(conceptKey(code.system, code.code)) ?? null),
        entityLevel: item.extension?.find(isEntityLevelExtension)?.valueBoolean ?? null,
        childLinkIds: [],
    }
}

/** One concept as the value-type map keys it: the system that defines the code, then the code. */
function conceptKey(system: string | undefined, code: string | undefined): string {
    return `${system ?? ''}|${code ?? ''}`
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
    if (answer.valueCoding !== undefined) return { ...EMPTY_SLOT, coding: answer.valueCoding }
    if (answer.valueReference !== undefined) return { ...EMPTY_SLOT, reference: answer.valueReference }
    if (answer.valueBoolean !== undefined) return { ...EMPTY_SLOT, text: String(answer.valueBoolean) }
    if (answer.valueDecimal !== undefined) return { ...EMPTY_SLOT, text: String(answer.valueDecimal) }
    if (answer.valueInteger !== undefined) return { ...EMPTY_SLOT, text: String(answer.valueInteger) }
    const text = answer.valueDate ?? answer.valueDateTime ?? answer.valueTime ?? answer.valueString ?? answer.valueUri
    if (text !== undefined) return { ...EMPTY_SLOT, text }
    // valueAttachment has no control here, so there is nothing to fill.
    return null
}

/** One slot from an item's declared initial value, which is a `value[x]` in the same spelling. */
function slotFromInitial(initial: QuestionnaireInitial): AnswerSlot | null {
    return slotFromAnswer(initial)
}
