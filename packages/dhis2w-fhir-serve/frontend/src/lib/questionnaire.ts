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
import { conceptPropertyValue, declaredCategoryName } from '@/lib/terminology'

/** The standard R4 extensions a numeric question carries its inclusive bounds on. */
export const MINIMUM_VALUE_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/minValue'
export const MAXIMUM_VALUE_EXTENSION_URL = 'http://hl7.org/fhir/StructureDefinition/maxValue'

/** The extension a registration form declares whether its program collects an incident date on. */
export const COLLECTS_INCIDENT_DATE_EXTENSION_SUFFIX = '/StructureDefinition/d2-collects-incident-date'

/**
 * The extension a form carries its instance's own words for the dates it collects on.
 *
 * DHIS2 lets a programme rename all three - an antenatal programme calls the enrollment date "Date
 * first seen" and the incident date "Date of last menstrual period" - and a capture screen that
 * ignored those words would be asking a different question from the one the clerk was trained on.
 * Complex rather than valued, sliced one sub-extension per date, and each present only when the
 * instance really states a word for that date.
 */
export const DATE_LABELS_EXTENSION_SUFFIX = '/StructureDefinition/d2-date-labels'

/** The three sub-extensions `d2-date-labels` slices, one per date a DHIS2 programme can rename. */
export const ENROLLMENT_DATE_LABEL_SUB_EXTENSION = 'enrollmentDate'
export const INCIDENT_DATE_LABEL_SUB_EXTENSION = 'incidentDate'
export const EVENT_DATE_LABEL_SUB_EXTENSION = 'eventDate'

/** The extension an aggregate form states the DHIS2 period type its data set reports for on. */
export const PERIOD_TYPE_EXTENSION_SUFFIX = '/StructureDefinition/d2-period-type'

/** The extension a stage form states whether one enrollment may answer it more than once on. */
export const REPEATABLE_EXTENSION_SUFFIX = '/StructureDefinition/d2-repeatable'

/** The extension an item carries the description DHIS2 holds for its data element or section on. */
export const DESCRIPTION_EXTENSION_SUFFIX = '/StructureDefinition/d2-description'

/**
 * The extension a form lists the DHIS2 program rules its instance enforces on import under.
 *
 * Repeating, one per rule, and complex: a rule is a uid, a name, a condition, and what DHIS2 does
 * about it, and none of the four is the value of the other three.
 */
export const PROGRAM_RULE_EXTENSION_SUFFIX = '/StructureDefinition/d2-program-rule'

/** The five sub-extensions one `d2-program-rule` repeat slices one rule under. */
export const RULE_SUB_EXTENSION = 'rule'
export const RULE_NAME_SUB_EXTENSION = 'name'
export const RULE_DESCRIPTION_SUB_EXTENSION = 'description'
export const RULE_CONDITION_SUB_EXTENSION = 'condition'
export const RULE_ACTION_SUB_EXTENSION = 'action'

/**
 * One DHIS2 program rule a form declares its instance evaluates when the submission is imported.
 *
 * NOT A RULE THIS APP RUNS. A program rule is a DHIS2 expression over variables an instance holds,
 * and this facade holds no instance - so what a client can do with one is name it: state before the
 * capture that the rule is waiting, and read a rejection that cites its uid back as its name.
 */
export interface ProgramRule {
    /** The DHIS2 uid, which is what a rejection names the rule by. */
    ruleUid: string
    /** What the rule is called in DHIS2 - the sentence a person reads. */
    name: string
    /** What DHIS2 holds as the rule's description, or null when it holds none, which is most rules. */
    description: string | null
    /** The rule's DHIS2 expression, in the machine spelling the instance holds it in. */
    condition: string
    /** The DHIS2 program rule action type, as `SHOWWARNING`, or null when the form states none. */
    action: string | null
}

/**
 * Every program rule one form declares, in the order it lists them.
 *
 * A repeat missing its uid, its name, or its condition is left out rather than shown half read: the
 * three together are what makes a rule nameable in a rejection, and the other two are decoration.
 */
export function programRulesOf(questionnaire: Questionnaire | null): ProgramRule[] {
    const declared = (questionnaire?.extension ?? []).filter((candidate) =>
        candidate.url.endsWith(PROGRAM_RULE_EXTENSION_SUFFIX),
    )
    return declared.flatMap((extension) => {
        const ruleUid = subExtension(extension, RULE_SUB_EXTENSION)?.valueId
        const name = subExtension(extension, RULE_NAME_SUB_EXTENSION)?.valueString
        const condition = subExtension(extension, RULE_CONDITION_SUB_EXTENSION)?.valueString
        if (ruleUid === undefined || name === undefined || condition === undefined) return []
        return [
            {
                ruleUid,
                name,
                description: subExtension(extension, RULE_DESCRIPTION_SUB_EXTENSION)?.valueString ?? null,
                condition,
                action: subExtension(extension, RULE_ACTION_SUB_EXTENSION)?.valueCode ?? null,
            },
        ]
    })
}

/**
 * What a form calls each of the three dates it may collect.
 *
 * ONE SOURCE, TWO SURFACES. The capture screen labels its date controls from this and the receipt
 * page labels its stored facts from the same, so a programme that calls its enrollment date "Date
 * first seen" says that in both places rather than in one. Neither surface reads the extension
 * itself; both read this.
 */
export interface DateLabels {
    /** What the date an enrollment begins is called. */
    enrollmentDate: string
    /** What the date of the incident an enrollment follows is called. */
    incidentDate: string
    /** What the date an event was recorded on is called. */
    eventDate: string
}

/**
 * What each date is called on a form whose instance renamed none of them.
 *
 * These are facts rather than DHIS2 field names: an enrollment begins on a date, an incident
 * occurred on one, and a visit happened on one. A form that states its own word replaces the whole
 * of the label rather than decorating it, because a clerk reading "Date first seen (enrollment
 * date)" is being told the same fact twice in two vocabularies.
 */
export const DEFAULT_DATE_LABELS: DateLabels = {
    enrollmentDate: 'Enrollment date',
    incidentDate: 'Incident date',
    eventDate: 'Visit date',
}

/** What one form calls its dates: the words it states, and this project's own for the rest. */
export function dateLabelsOf(questionnaire: Questionnaire | null): DateLabels {
    const stated = questionnaire?.extension?.find((candidate) =>
        candidate.url.endsWith(DATE_LABELS_EXTENSION_SUFFIX),
    )
    const label = (url: string, fallback: string): string => {
        const declared = subExtension(stated, url)?.valueString?.trim()
        return declared === undefined || declared === '' ? fallback : declared
    }
    return {
        enrollmentDate: label(ENROLLMENT_DATE_LABEL_SUB_EXTENSION, DEFAULT_DATE_LABELS.enrollmentDate),
        incidentDate: label(INCIDENT_DATE_LABEL_SUB_EXTENSION, DEFAULT_DATE_LABELS.incidentDate),
        eventDate: label(EVENT_DATE_LABEL_SUB_EXTENSION, DEFAULT_DATE_LABELS.eventDate),
    }
}

/**
 * The DHIS2 period type an aggregate form reports for, as the form itself declares it.
 *
 * The form is the authority rather than the draft: `$generate` states a type beside the period it
 * drew, but a form opened before its skeleton lands - or after a refused `$generate` - still knows
 * what shape of period it takes, and that is what the control needs in order to ask for one.
 */
export function reportingPeriodTypeOf(questionnaire: Questionnaire | null): string | null {
    const declared = questionnaire?.extension?.find((candidate) =>
        candidate.url.endsWith(PERIOD_TYPE_EXTENSION_SUFFIX),
    )
    return declared?.valueCode ?? null
}

/**
 * Whether one enrollment may answer this stage form more than once, or null when it states nothing.
 *
 * Null is not false. A form compiled before the declaration was published says nothing about its
 * stage's repetition, and a screen that read silence as "once only" would state a rule about the
 * DHIS2 programme that nobody published.
 */
export function repeatsPerEnrollment(questionnaire: Questionnaire | null): boolean | null {
    const declared = questionnaire?.extension?.find((candidate) =>
        candidate.url.endsWith(REPEATABLE_EXTENSION_SUFFIX),
    )
    return declared?.valueBoolean ?? null
}

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

/** The concept property stating that DHIS2 mints this attribute's value rather than taking one. */
export const GENERATED_CONCEPT_PROPERTY = 'generated'

/** The concept property carrying the shape DHIS2 mints a generated attribute's value to. */
export const PATTERN_CONCEPT_PROPERTY = 'pattern'

/** The prefix a combo vocabulary declares one property per category under, the uid following it. */
export const CATEGORY_PROPERTY_PREFIX = 'category-'

/** The DHIS2 value type that stores `true` or no value at all - never `false`. */
export const TRUE_ONLY_VALUE_TYPE = 'TRUE_ONLY'

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
    /**
     * The description DHIS2 holds for this item's object, or null when it holds none.
     *
     * A data element's description and a section's description are the help text a form designer
     * wrote for the person filling the form in - "Count a dose once, on the day it was given" - and
     * they answer the questions a label has no room for. Absent far more often than present, because
     * DHIS2 requires none.
     */
    description: string | null
    required: boolean
    repeats: boolean
    readOnly: boolean
    maxLength: number | null
    /** The inclusive bounds the `minValue` / `maxValue` extensions state as numbers, or null for none. */
    minimum: number | null
    maximum: number | null
    /**
     * The inclusive bounds those same extensions state as calendar days, or null for none.
     *
     * Separate from the numeric pair rather than folded into it, because `2026-01-01` is not a
     * quantity: a date question is bounded by days and a numeric question by numbers, and no question
     * carries both. Which pair a control reads is decided by the question's own item type.
     */
    minimumDate: string | null
    maximumDate: string | null
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
     * Whether DHIS2 mints this question's value rather than taking one, as the dictionary states.
     *
     * True on a generated tracked entity attribute, which the form also marks `readOnly`: the
     * instance writes the value on import, so what a client sends for it is discarded. The two facts
     * come from different places on purpose - `readOnly` is the form's statement that the control
     * takes no input, and this is the dictionary's statement of why.
     */
    generated: boolean
    /** The shape DHIS2 mints a generated value to, as `ANC-#######`, or null when none is published. */
    pattern: string | null
    /**
     * How this question's category option combo decomposes: category and chosen option, in order.
     *
     * Empty on every question that is not a disaggregated cell. It is what lets the group above a run
     * of cells say what its columns are cut by - the one thing "Fixed, <1y" does not say - and what
     * lets the run decide its shape without reading that name at all.
     */
    decomposition: CategoryChoice[]
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
 * `dictionary` is what the served data dictionaries state about the concepts the questions are coded
 * in - see `dictionaryOfCodeSystems`. It is optional because the form is on screen before its
 * CodeSystems have been read, and because every reader works without it: a spec flattened with no
 * dictionary states no value type, no generated identifier, and no category axes, which is exactly
 * what an unread dictionary knows.
 */
export function flattenQuestionnaire(
    questionnaire: Questionnaire,
    dictionary: QuestionDictionary = NO_DICTIONARY,
): QuestionnaireSpec {
    const nodes: QuestionnaireNode[] = []
    const rootLinkIds = collectItems(questionnaire.item ?? [], [], nodes, dictionary)
    const byLinkId = new Map(nodes.map((node) => [node.linkId, node]))
    const questionLinkIds = nodes
        .filter((node) => node.type !== 'group' && node.type !== 'display')
        .map((node) => node.linkId)
    return { nodes, byLinkId, rootLinkIds, questionLinkIds }
}

/**
 * What the served data dictionaries state about one concept, beyond the display it carries.
 *
 * Everything here is optional on the wire and absent by default, which is the honest reading of a
 * guide compiled before a property was published: a dictionary that says nothing about a concept
 * leaves every question that codes into it rendering on what the form alone states.
 */
export interface ConceptFacts {
    /** The DHIS2 value type, as `TRUE_ONLY` or `INTEGER_POSITIVE`, or null when none is stated. */
    valueType: string | null
    /** True when DHIS2 mints this attribute's value on import rather than taking one from a client. */
    generated: boolean
    /** The shape DHIS2 mints a generated value to, as `ANC-#######`, or null when none is published. */
    pattern: string | null
    /**
     * How this concept decomposes: one entry per DHIS2 category, in the order the concept states them.
     *
     * Empty for every concept that is not a category option combo. A combo vocabulary declares one
     * property per category and carries the chosen option under it, and the category's own name is in
     * the declaration rather than in the property code - so this is the join of the two.
     */
    decomposition: CategoryChoice[]
}

/**
 * One category of a combo's decomposition: which category, and which option this combo takes in it.
 *
 * THIS IS WHAT MAKES THE RENDERER SAFE AGAINST A REORDER. A DHIS2 admin can reorder the categories
 * inside a category combo - gender then country one day, country then gender the next - and every
 * combo's *name* is rebuilt from that order, so `Female, Afghanistan` becomes `Afghanistan, Female`
 * and a renderer reading the name learns a different form. The decomposition does not move: the same
 * combo still takes `Female` in Gender and `Afghanistan` in Country, whichever order they are listed
 * in. So the shape of a run is decided from these and never from where a comma falls.
 */
export interface CategoryChoice {
    /** The DHIS2 category's name - `Gender` - which is the dimension's identity here. */
    axis: string
    /** The chosen category option's uid, which is what a reorder cannot change. */
    optionCode: string
    /** What that option is called - `Female` - which is what a band or a row is labelled with. */
    optionLabel: string
}

/** A concept the dictionaries say nothing about, which is also every concept before they are read. */
export const NO_CONCEPT_FACTS: ConceptFacts = { valueType: null, generated: false, pattern: null, decomposition: [] }

/** What the served dictionaries state about the concepts one form's questions are coded in. */
export interface QuestionDictionary {
    /** Keyed by the concept's system and code together - see `dictionaryOfCodeSystems`. */
    byConcept: ReadonlyMap<string, ConceptFacts>
}

/** Nothing read yet, which is what a form opens on before its dictionaries land. */
export const NO_DICTIONARY: QuestionDictionary = { byConcept: new Map() }

/**
 * Everything a set of served CodeSystems states about the concepts they hold.
 *
 * WHY THE KEY IS SYSTEM AND CODE. A question's `code` names both, and two dictionaries can hold the
 * same code for different objects - a data element and a tracked entity attribute are separate DHIS2
 * uid spaces. Keying by the pair is what makes this one map safe to build over every dictionary a
 * form draws from, rather than one map per system with a lookup order to get wrong.
 *
 * WHY ONE PASS AND NOT FOUR. A form reads its two or three dictionaries once and then asks four
 * different questions of them - what value type a tick has, whether DHIS2 mints an identifier, what
 * shape it mints it to, and which categories a disaggregated cell is cut by. Four maps built by four
 * walks would be four things to keep in step; one walk answering all four is one.
 *
 * A concept carrying none of the properties contributes an entry all the same, because a concept the
 * dictionary holds and says nothing about is a different fact from a concept it does not hold.
 */
export function dictionaryOfCodeSystems(codeSystems: CodeSystem[]): QuestionDictionary {
    const byConcept = new Map<string, ConceptFacts>()
    for (const codeSystem of codeSystems) {
        const categoryNames = declaredCategoryNames(codeSystem)
        for (const concept of codeSystem.concept ?? []) {
            byConcept.set(conceptKey(codeSystem.url, concept.code), {
                valueType: conceptPropertyValue(concept, VALUE_TYPE_CONCEPT_PROPERTY),
                generated: conceptPropertyValue(concept, GENERATED_CONCEPT_PROPERTY) === 'true',
                pattern: conceptPropertyValue(concept, PATTERN_CONCEPT_PROPERTY),
                // The concept's own order, never sorted: a combo decomposes in the order DHIS2
                // declares its category combo, and that is the order its cells read in. What the
                // renderer decides a shape from is the set of these, not their order - see
                // `facetColumns` - so a reordered combo is the same decomposition listed differently.
                decomposition: (concept.property ?? []).flatMap((property) => {
                    const axis = categoryNames.get(property.code)
                    if (axis === undefined) return []
                    // The option rides as a Coding, which is the one place its uid is stated. A
                    // property carrying no code still names a category the combo is cut by - worth
                    // saying above the run - but says nothing about which option it takes, so it
                    // arrives with an empty uid and `cutAxes` refuses to band a cut holding one.
                    const optionCode = property.valueCoding?.code ?? ''
                    return [{ axis, optionCode, optionLabel: property.valueCoding?.display ?? optionCode }]
                }),
            })
        }
    }
    return { byConcept }
}

/** The categories one CodeSystem declares a property for, keyed by that property's code. */
function declaredCategoryNames(codeSystem: CodeSystem): ReadonlyMap<string, string> {
    const names = new Map<string, string>()
    for (const property of codeSystem.property ?? []) {
        if (!property.code.startsWith(CATEGORY_PROPERTY_PREFIX)) continue
        // The declaration's description is where the category's name is; the code carries its uid.
        // A declaration wearing no name falls back to the uid, which is at least a thing to look up.
        names.set(property.code, declaredCategoryName(property.description) ?? property.code)
    }
    return names
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
 * in the set by the time its children are reached.
 *
 * R4 SEMANTICS FOR AN UNANSWERED QUESTION. A comparison needs two values, so a condition naming a
 * question nobody answered never holds - `=`, `!=`, and the four orderings are all false against
 * nothing. `exists` is the one operator that reads absence as a fact, and `exists=false` against an
 * unanswered question is true. A condition naming a question the form does not have never holds
 * either, which hides the dependent item rather than showing it unconditionally.
 *
 * What falls outside this set carries no answer: `clearedHiddenAnswers` is what enforces that, and
 * `buildQuestionnaireResponse` writes nothing outside it either.
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
 * The answers with every hidden question's cleared.
 *
 * A HIDDEN STALE ANSWER IS THE BUG DHIS2'S OWN RULES EXIST TO PREVENT. A question the form stopped
 * asking is a question whose answer is no longer about anything: a haemoglobin reading typed before
 * "was blood taken?" was set back to No describes a test nobody ran, and forwarded it becomes a real
 * DHIS2 data value against a real person. Program rules exist precisely so that instance never holds
 * such a value, so a capture screen that kept one in state until Submit would be the one place the
 * rule could not reach.
 *
 * SO THE ANSWER GOES WHEN THE QUESTION GOES. The alternative - keep it, and let
 * `buildQuestionnaireResponse` decline to write it - keeps the wire correct and the screen lying: the
 * form would say nothing was answered while the reducer held a value, and any second reader of the
 * state (a required-question sweep, a draft saved anywhere) would have to remember the same rule
 * independently. One rule in one place, and what is not asked is not answered.
 *
 * Re-enabling a question therefore brings it back empty. That is the honest reading: the conditions
 * changed, so the earlier answer was given under a form that was asking something else.
 *
 * The state object's identity is preserved when nothing is hidden, so the ordinary keystroke on an
 * ordinary form does not rerender every control for no reason.
 */
export function clearedHiddenAnswers(spec: QuestionnaireSpec, answers: AnswerState): AnswerState {
    const enabled = enabledLinkIds(spec, answers)
    const hidden = Object.keys(answers).filter((linkId) => spec.byLinkId.has(linkId) && !enabled.has(linkId))
    if (hidden.length === 0) return answers
    const next = { ...answers }
    for (const linkId of hidden) delete next[linkId]
    return next
}

/** One filled-in question whose value the submission could not carry as the form asks for it. */
export interface AnswerBreach {
    linkId: string
    /**
     * Which answer of a repeating question this is, counting from zero.
     *
     * The only thing that tells two breaches of one question apart: a repeating question can be
     * answered `137` twice, and both are outside the range in exactly the same words.
     */
    index: number
    /** The question as the form asks it, so the sentence names a question rather than a uid. */
    text: string
    /**
     * The whole fact in one sentence: the value, which end of the range it passed, and that value.
     *
     * Assembled here rather than in the component because it is the same sentence wherever it is
     * shown, and because the numbers in it are the form's own literals rather than anything reformatted.
     */
    fact: string
}

/**
 * Every enabled question filled in with something this submission cannot carry.
 *
 * WHY THE BROWSER CHECKS AT ALL. The server checks too, and DHIS2 checks after that - but a value
 * the form itself says it does not accept is a mistake the person who typed it can fix under the
 * cursor, and spending a round trip to be told what the form already published is the worst of the
 * three places to learn it. What comes back is the fact rather than an instruction: a reader is told
 * what they typed and what the form accepts, and decides for themselves what to do about it.
 *
 * TWO KINDS OF BREACH, AND THE SECOND IS THE ONE THAT USED TO VANISH. A value outside the range the
 * form's `minValue` / `maxValue` extensions publish is one. The other is a box holding text that is
 * not a value of the kind the question records at all - `5.5` in a whole-number question, `1.2.` in
 * a decimal one: `slotAnswer` converts those to null, null means unanswered everywhere below here,
 * and a submission would leave the answer behind without a word. So a slot holding text that
 * converts to nothing is stated here, which is the one place a person can still act on it.
 *
 * A DISABLED QUESTION IS NOT CHECKED, because it carries no answer once `clearedHiddenAnswers` has
 * run and would not be submitted if it did. An empty box is not checked either: that is an
 * unanswered question, which the required-question count is what says something about.
 */
export function answerBreaches(spec: QuestionnaireSpec, answers: AnswerState): AnswerBreach[] {
    const enabled = enabledLinkIds(spec, answers)
    const breaches: AnswerBreach[] = []
    for (const node of spec.nodes) {
        if (!enabled.has(node.linkId)) continue
        ;(answers[node.linkId] ?? []).forEach((slot, index) => {
            const fact = slotBreachFact(node, slot)
            if (fact !== null) breaches.push({ linkId: node.linkId, index, text: node.text ?? node.linkId, fact })
        })
    }
    return breaches
}

/** The sentence one answer's breach reads as, or null when the slot carries a value the form takes. */
function slotBreachFact(node: QuestionnaireNode, slot: AnswerSlot): string | null {
    const answer = slotAnswer(node, slot)
    if (answer === null) return slot.text.trim() === '' ? null : unconvertibleFact(node, slot.text)
    const number = answer.valueInteger ?? answer.valueDecimal
    if (number !== undefined) {
        if (node.minimum !== null && number < node.minimum) return belowFact(number, node.minimum)
        if (node.maximum !== null && number > node.maximum) return aboveFact(number, node.maximum)
        return null
    }
    const date = answer.valueDate
    if (date === undefined) return null
    if (node.minimumDate !== null && date < node.minimumDate) return belowFact(date, node.minimumDate)
    if (node.maximumDate !== null && date > node.maximumDate) return aboveFact(date, node.maximumDate)
    return null
}

/** What a value under the range says about itself. */
function belowFact(value: number | string, bound: number | string): string {
    return `${value} is below ${bound}, the lowest value this form accepts`
}

/** What a value over the range says about itself. */
function aboveFact(value: number | string, bound: number | string): string {
    return `${value} is above ${bound}, the highest value this form accepts`
}

/**
 * What a box holding text that is not a value of this question's kind says about itself.
 *
 * The wording names the kind rather than the R4 element, because the kind is what the person at the
 * keyboard can act on: a whole number, a number, a date and time, a time of day. A boolean and a
 * reference are absent from the list and answer null - neither control can hold a literal anybody
 * typed, so text in one of those slots came off a draft rather than off a keystroke, and a sentence
 * telling somebody to fix what they cannot see would be worse than saying nothing.
 */
function unconvertibleFact(node: QuestionnaireNode, text: string): string | null {
    switch (node.answerElement) {
        case 'valueInteger':
            return `${text} is not a whole number, which is what this question records`
        case 'valueDecimal':
            return `${text} is not a number, which is what this question records`
        case 'valueDate':
        case 'valueDateTime':
            return `${text} is not a date this question can record`
        case 'valueTime':
            return `${text} is not a time of day this question can record`
        case 'valueBoolean':
        case 'valueReference':
            return null
        default:
            return `${text} is not a value this question can record`
    }
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
 * THE SEED IDENTIFIER RIDES WITH THE REST OF THE ENVELOPE, because it says which draw this
 * submission started from and that is a fact about the submission whatever was typed over it
 * afterwards. It is what makes a captured receipt reproducible - the same form and the same seed
 * draw the same bytes - so the receipt states the seed, and a reported bug can be re-drawn from it.
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
        ...(envelope?.identifier ? { identifier: envelope.identifier } : {}),
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
 *
 * A read-only question is never waiting either, and for the same reason under a different fact: the
 * form states that DHIS2 owns the value - a generated tracked entity attribute is minted by the
 * instance on import - so there is nothing for anyone to answer. This is the same rule the capture
 * grading holds on the server (`_ItemValidator.run` in `dhis2w_fhir_serve.capture.validate`), which
 * is what keeps "unanswered" meaning one thing on both sides of the wire.
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
                !node.readOnly &&
                enabled.has(node.linkId) &&
                !exempt.has(node.linkId) &&
                !isAnswered(node, answers),
        )
        .map((node) => node.linkId)
}

/** One column of a disaggregation table: the category option combo every row is answered under. */
export interface DisaggregationColumn {
    /** The combo as the cell's own item text names it - `0-11m`, `Fixed, <1y`. */
    label: string
    /** The combo uid, or null on a cell the form codes with nothing. */
    code: string | null
    /**
     * How the combo decomposes, or empty when the served vocabulary has not been read.
     *
     * The label above is a name and this is the structure behind it. Everything about the shape of a
     * run is decided from here, because a name is rebuilt whenever an admin reorders the categories
     * inside the combo and this is not.
     */
    decomposition: CategoryChoice[]
}

/**
 * One run of sibling items, as the shape it is drawn in.
 *
 * A form is read as a sequence of these rather than item by item, because two of the three shapes
 * are facts about a *run* of items and not about any one of them: a table exists because several
 * data elements are cut the same way, and a column flow exists because several scalar questions can
 * share a line. `item` is the third and the fallback - one item, drawn on its own, the way every
 * item was drawn before the other two existed.
 */
export type FormBlock =
    | { kind: 'item'; key: string; linkId: string }
    /** Consecutive scalar questions that flow into columns on a wide screen. */
    | { kind: 'scalars'; key: string; linkIds: string[] }
    /** Consecutive data element groups cut by one set of combos: one table, one row each. */
    | { kind: 'disaggregation'; key: string; groupLinkIds: string[]; columns: DisaggregationColumn[] }

/**
 * A run of sibling items, partitioned into the shapes they are drawn in.
 *
 * A DISAGGREGATED SECTION IS A GRID AND DHIS2 DRAWS IT AS ONE. An aggregate data set nests a
 * question per category option combo under a group per data element, so fourteen elements cut by
 * four age bands is fifty-six questions - and stacked, each with its own label, its own uid, and its
 * own full row, it is a screen nobody can read across. The elements share one ordered set of combos,
 * which is exactly what a table's header row states once: the elements are the rows, the combos are
 * the columns, and the answer is the cell where they meet. That is the shape a DHIS2 data clerk
 * already knows, because it is the shape DHIS2's own data entry uses.
 *
 * WHAT MAKES A RUN A TABLE. Consecutive groups whose enabled children are numeric questions -
 * childless, single-answer, and carrying no help text of their own - with the same combo labels in
 * the same order, cut by identical uids. Anything else falls out: a group cut differently opens its
 * own table, and a group holding coded, dated or narrative cells stays stacked, because a table cell
 * is a box a number fits in and those answers need the room a stacked control has. A run of one
 * group is still a table - one row is the honest drawing of one element cut four ways.
 *
 * WHY THE PARTITION AND NOT THE DRAWING DECIDES. The link ids in each block stay in document order,
 * so the keyboard walks the form the way the form is written whichever shape it is drawn in, and
 * every question keeps its own linkId identity - the submission a table produces is the submission
 * the stack produced.
 */
export function formBlocks(
    spec: QuestionnaireSpec,
    linkIds: readonly string[],
    enabled: ReadonlySet<string>,
): FormBlock[] {
    const blocks: FormBlock[] = []
    let scalars: string[] = []
    let table: { groupLinkIds: string[]; columns: DisaggregationColumn[]; signature: string } | null = null
    const flushScalars = () => {
        if (scalars.length === 0) return
        blocks.push({ kind: 'scalars', key: `scalars-${scalars[0]}`, linkIds: scalars })
        scalars = []
    }
    const flushTable = () => {
        if (table === null) return
        blocks.push({
            kind: 'disaggregation',
            key: `disaggregation-${table.groupLinkIds[0]}`,
            groupLinkIds: table.groupLinkIds,
            columns: table.columns,
        })
        table = null
    }
    for (const linkId of linkIds) {
        if (!enabled.has(linkId)) continue
        const node = spec.byLinkId.get(linkId)
        if (node === undefined) continue
        const columns = disaggregationColumns(spec, node, enabled)
        if (columns !== null) {
            const signature = columnSignature(columns)
            if (table !== null && table.signature === signature) {
                table.groupLinkIds.push(linkId)
                continue
            }
            flushScalars()
            flushTable()
            table = { groupLinkIds: [linkId], columns, signature }
            continue
        }
        flushTable()
        if (flowsIntoColumns(node)) {
            scalars.push(linkId)
            continue
        }
        flushScalars()
        blocks.push({ kind: 'item', key: linkId, linkId })
    }
    flushScalars()
    flushTable()
    return blocks
}

/** One value of a cut's facet axis: the heading it stands under, and the columns it holds. */
export interface DisaggregationFacet {
    /** The value of the faceted dimension - `Female` - which is stated once, above the rest. */
    heading: string
    /** Where each of this facet's columns sits in the run's own column order. */
    indices: number[]
    /** What each of those columns is called with the heading's own category taken out. */
    labels: string[]
    /**
     * Which DHIS2 category the headings come from - `Gender`.
     *
     * Named rather than positioned. The facet axis is whichever category has fewest options, and an
     * instance is free to list it either side of its neighbours, so a caller that needs the category
     * the rows are still cut by subtracts this one from the run's axes rather than counting commas.
     */
    axis: string
}

/**
 * The widest cut a grid draws by default: four combos.
 *
 * Four numeric columns plus the element names is a table that fits the card a form is drawn in, and
 * the fifth column is where the card starts spending width it does not have. A wider cut is drawn
 * vertically instead, because a data-entry surface that side-scrolls is one where the row label
 * leaves the screen while the value is being typed.
 */
export const WIDEST_GRID_CUT = 4

/**
 * The count from which a two-dimensional cut is worth splitting at all.
 *
 * Derived rather than chosen: the split exists to bring a cut back inside the width a grid draws, so
 * it is offered exactly where a cut has left that width. A cut a grid already holds has nothing to be
 * rescued from, and splitting it would spend two headings to save a column nobody was short of.
 */
export const SPLITTABLE_CUT = WIDEST_GRID_CUT + 1

/**
 * The most values a dimension can have and still be the one that becomes headings.
 *
 * A facet axis is read as headings down the page, so it works while there are a few of them and stops
 * working when there are many: six bands is a form, and ninety-six is a scroll with no shape. A cut
 * whose dimensions are both wider than this has no facet form and is drawn as one list of full labels.
 */
export const WIDEST_FACET_AXIS = 6

/**
 * The columns of a cut, banded along whichever DHIS2 category has fewest options.
 *
 * ORDER-PROOF BY CONSTRUCTION, WHICH IS THE WHOLE POINT. A DHIS2 admin can reorder the categories
 * inside a category combo, and when they do, every combo in it is renamed - `Female, Afghanistan`
 * becomes `Afghanistan, Female` - and DHIS2 expands the cells in a different order too. A renderer
 * that read the names would band by gender one day and by country the next, which is the same data
 * set drawn as two columns of a hundred and ninety-two or as a hundred and ninety-two of two. So
 * nothing here reads a name: the band is chosen from the *set* of categories the decomposition
 * states, by option count, with the category's own name breaking a tie. The same set gives the same
 * answer whichever way round it is listed.
 *
 * AND THE ORDER WITHIN IT IS RECOVERED, NOT TAKEN. A reorder permutes the cells, so the bands and
 * their rows are put back in each category's own option order - the order `cutAxes` meets them in,
 * which is the one ordering a reorder leaves alone. That keeps `under 15y` before `over 49y` without
 * this module sorting anything into an order DHIS2 never stated.
 *
 * WHAT IS REFUSED. A cut whose vocabulary has not been read, or that decomposes over one category
 * only, because there is no second dimension to leave in the rows; a band axis with fewer than two
 * options or more than `WIDEST_FACET_AXIS`; and a cut whose bands do not all hold the same options of
 * every remaining category, because a band that dropped a column would be a different form wearing
 * the same heading. A refused cut has no band form: its columns stay one flat list, and the
 * orientation ladder decides whether that list is drawn across the page or down it.
 */
export function facetColumns(columns: DisaggregationColumn[]): DisaggregationFacet[] | null {
    if (columns.length < SPLITTABLE_CUT) return null
    const axes = cutAxes(columns)
    if (axes.length < 2) return null
    // Fewest options first, and the category's own name settles a tie - so two categories of the
    // same size do not swap places between one visit and the next.
    const banded = [...axes].sort(
        (left, right) => left.options.length - right.options.length || left.axis.localeCompare(right.axis),
    )[0]
    if (banded.options.length < 2 || banded.options.length > WIDEST_FACET_AXIS) return null
    // The categories left over are put in the same settled order for the same reason the band is
    // chosen that way: with three or more of them, the order they were met in is the order DHIS2
    // happened to list them, and a row label reading "Fixed, under 1y" must not become "under 1y,
    // Fixed" because somebody rearranged a combo.
    const rest = [...axes]
        .filter((axis) => axis.axis !== banded.axis)
        .sort((left, right) => left.options.length - right.options.length || left.axis.localeCompare(right.axis))

    const facets: DisaggregationFacet[] = banded.options.map((option) => ({
        heading: option.optionLabel,
        indices: [],
        labels: [],
        axis: banded.axis,
    }))
    for (const [position, option] of banded.options.entries()) {
        const held = columns
            .map((column, index) => ({ column, index }))
            .filter((each) => optionOf(each.column, banded.axis)?.optionCode === option.optionCode)
        // Each band reads down the remaining categories in their own option order, which is what
        // makes two spellings of one cut produce the same rows in the same places.
        held.sort((left, right) => restRank(left.column, rest) - restRank(right.column, rest))
        facets[position].indices = held.map((each) => each.index)
        facets[position].labels = held.map((each) =>
            rest.map((axis) => optionOf(each.column, axis.axis)?.optionLabel ?? '').join(', '),
        )
    }
    if (facets.some((facet) => facet.indices.length === 0)) return null
    const shape = facets[0].labels.join('\u001f')
    if (facets.some((facet) => facet.labels.join('\u001f') !== shape)) return null
    return facets
}

/** One category a run is cut by, with its options in the order the run first states them. */
interface CutAxis {
    axis: string
    options: CategoryChoice[]
}

/**
 * The categories a whole run decomposes over, each with its own options in first-seen order.
 *
 * First-seen rather than sorted, and it survives a reorder: DHIS2 expands a combo as a nested loop
 * over its categories, so whichever category is outermost, each category's options are still met in
 * that category's own order - Female before Male, `under 15y` before `over 49y`. A column missing a
 * category the others state leaves the run undecidable, and an empty answer here refuses the band.
 */
function cutAxes(columns: readonly DisaggregationColumn[]): CutAxis[] {
    const axes: CutAxis[] = []
    for (const column of columns) {
        if (column.decomposition.length === 0) return []
        for (const choice of column.decomposition) {
            // A category whose chosen option was never published leaves the cut undecidable: every
            // column would band under the same nameless option, which is not a band, it is a lie.
            if (choice.optionCode === '') return []
            const known = axes.find((candidate) => candidate.axis === choice.axis)
            if (known === undefined) {
                axes.push({ axis: choice.axis, options: [choice] })
                continue
            }
            if (!known.options.some((option) => option.optionCode === choice.optionCode)) {
                known.options.push(choice)
            }
        }
    }
    // Every column has to state every category, or the cut is not a grid of these dimensions at all.
    const complete = axes.every((axis) => columns.every((column) => optionOf(column, axis.axis) !== undefined))
    return complete ? axes : []
}

/** Which option one column takes in one category, or undefined when it states none. */
function optionOf(column: DisaggregationColumn, axis: string): CategoryChoice | undefined {
    return column.decomposition.find((choice) => choice.axis === axis)
}

/** Where one column sorts among the categories a band did not take, read as a mixed-radix number. */
function restRank(column: DisaggregationColumn, rest: readonly CutAxis[]): number {
    let rank = 0
    for (const axis of rest) {
        const option = optionOf(column, axis.axis)
        const place = option === undefined ? 0 : axis.options.findIndex((each) => each.optionCode === option.optionCode)
        rank = rank * axis.options.length + Math.max(place, 0)
    }
    return rank
}

/**
 * The shape one run of disaggregated data elements is drawn in.
 *
 * TWO SHAPES, AND THE RUN IS THE UNIT THAT HAS ONE. `grid` is the table DHIS2's own data entry
 * draws - the elements are the rows, the combos are the columns - and it reads as one glance for as
 * long as the columns fit the card. `vertical` is one block per element - the element's name as a
 * band, and under it one row per combo - and it reads as a list that never scrolls sideways however
 * many combos there are. Neither is better; which one a run wants is decided by how wide its cut is,
 * and a person who disagrees says so with the switch on the run's own band.
 */
export type DisaggregationOrientation = 'grid' | 'vertical'

/**
 * The widest table this app will draw at all, however it is asked.
 *
 * Past a dozen numeric columns a grid is a horizontal scroll with a header row nobody can see beside
 * the value they are typing, which is not a shape a person chose - it is one they got. A run whose
 * grid form would be wider than this has no grid form, and its band offers no switch to one.
 */
export const WIDEST_DRAWABLE_GRID = 12

/**
 * The combo count from which a vertical run offers a filter box and an unfilled-only tick.
 *
 * A cut over thirty options is a list nobody scrolls to find one row in - a facility category with a
 * hundred options is a real DHIS2 cut, not a hypothetical - so from here the band gains the two ways
 * of getting to the row you want: name part of it, or ask for the ones still empty.
 */
export const FILTERED_CUT = 30

/** The namespace a run's chosen shape is kept under, the run's first group uid following it. */
export const ORIENTATION_STORAGE_KEY_PREFIX = 'd2w-fhir.disaggregation-orientation.'

/**
 * How wide the widest table of a run's grid form would be.
 *
 * The facet split is part of the grid form rather than an alternative to it, so a cut of eight
 * columns that slices into two fours is four columns wide and not eight. A cut with no facet form is
 * as wide as it is.
 */
export function widestGridTable(columns: DisaggregationColumn[]): number {
    const facets = facetColumns(columns)
    if (facets === null) return columns.length
    return Math.max(...facets.map((facet) => facet.labels.length))
}

/**
 * The shape a run is drawn in when nobody has said otherwise.
 *
 * THE LADDER, IN ONE LINE: a run is a grid while its widest table is four columns or fewer, and a
 * list of rows once it is not.
 *
 * FACETS ARE PART OF THE GRID FORM. Eight combos spelled "Female, under 15y" slice into one table per
 * gender, and two tables of four columns is four columns wide - so that run is a grid, drawn as the
 * facets `facetColumns` finds. A cut of gender by country slices the same way and leaves a hundred
 * and ninety-two columns inside each band, which is no rescue at all: that run is vertical, and the
 * facets it found still shape it - see `comboRows`.
 */
export function defaultDisaggregationOrientation(columns: DisaggregationColumn[]): DisaggregationOrientation {
    return widestGridTable(columns) <= WIDEST_GRID_CUT ? 'grid' : 'vertical'
}

/**
 * Whether this run's band offers the switch between the two shapes.
 *
 * A CONTROL WITH ONE HONEST STATE IS NOT A CONTROL. Most wide cuts have a grid form that is merely
 * not the default - eight columns is a table somebody may well prefer, and the switch is how they
 * say so. A cut of gender by country has no grid form in any arrangement: a hundred and ninety-two
 * numeric columns is not a table that was drawn and disliked, it is a table nothing can draw. So the
 * run is drawn as rows, the band states no alternative, and nobody is offered a way to make the page
 * worse.
 */
export function offersOrientationSwitch(columns: DisaggregationColumn[]): boolean {
    return widestGridTable(columns) <= WIDEST_DRAWABLE_GRID
}

/** The other shape, which is what the switch on a run's band asks for. */
export function otherOrientation(orientation: DisaggregationOrientation): DisaggregationOrientation {
    return orientation === 'grid' ? 'vertical' : 'grid'
}

/**
 * The shape this browser last chose for one run, or null when it has chosen none.
 *
 * Storage that refuses to be read is the same answer as storage holding nothing: the run is drawn in
 * whatever the ladder says, and the choice simply does not survive the reload.
 */
export function storedDisaggregationOrientation(runKey: string): DisaggregationOrientation | null {
    try {
        const stored = localStorage.getItem(`${ORIENTATION_STORAGE_KEY_PREFIX}${runKey}`)
        return stored === 'grid' || stored === 'vertical' ? stored : null
    } catch {
        return null
    }
}

/** Keep one run's shape for the next time this form is opened. */
export function rememberDisaggregationOrientation(runKey: string, orientation: DisaggregationOrientation): void {
    try {
        localStorage.setItem(`${ORIENTATION_STORAGE_KEY_PREFIX}${runKey}`, orientation)
    } catch {
        // A browser with storage denied still draws the run the way it was asked to, for as long as
        // this document is open. Only surviving the reload is lost.
    }
}

/** The shape a run opens in: what was chosen for it, and the ladder's answer when nothing was. */
export function openedDisaggregationOrientation(
    runKey: string,
    columns: DisaggregationColumn[],
): DisaggregationOrientation {
    return storedDisaggregationOrientation(runKey) ?? defaultDisaggregationOrientation(columns)
}

/** One row of a vertical block: which column of the run it answers, and what it is called there. */
export interface ComboRow {
    /** The position in the run's own column order, which is what finds the cell. */
    index: number
    /** What the row is called where it is drawn. */
    label: string
}

/**
 * The rows one vertical block draws: the whole cut, or the slice one facet band has already narrowed.
 *
 * THE BAND DOES NOT SAY ITS FACT TWICE. Under a band reading "Female", a row labelled "Female,
 * Afghanistan" states the gender for the ninety-sixth time on that screen - so inside a facet the
 * rows carry only the dimension the band did not name. With no facet there is no band and no such
 * saving, and each row carries the whole combo the form calls it by.
 */
export function comboRows(columns: DisaggregationColumn[], facet: DisaggregationFacet | null): ComboRow[] {
    if (facet === null) return columns.map((column, index) => ({ index, label: column.label }))
    return facet.indices.map((index, position) => ({ index, label: facet.labels[position] }))
}

/** Whether a block of this many rows offers the two ways of narrowing them. */
export function offersComboFilter(rows: readonly ComboRow[]): boolean {
    return rows.length >= FILTERED_CUT
}

/**
 * Which DHIS2 category the rows of a block are cut by, or null when there is no single one to name.
 *
 * Inside a band it is the category the band did not take, found by name rather than by position - a
 * cut by gender and country, banded by gender, has countries down the page whichever order the combo
 * lists the two in. Outside a band it is the cut's own single category, and a cut over two categories
 * drawn flat has no one name to give.
 */
export function rowAxisName(axes: readonly string[], facet: DisaggregationFacet | null): string | null {
    if (facet === null) return axes.length === 1 ? axes[0] : null
    const rest = axes.filter((axis) => axis !== facet.axis)
    return rest.length === 1 ? rest[0] : null
}

/**
 * What the filter box asks for, in the words of the cut it narrows.
 *
 * A block whose rows are cut by one named category says which one and how many of it there are,
 * because "Filter 96 Facility" tells a reader what they are typing into and a bare box does not. A
 * block whose vocabulary was never read has no name to offer, so it names what the rows are instead.
 */
export function comboFilterPlaceholder(rows: readonly ComboRow[], axisName: string | null): string {
    return axisName === null ? 'Filter options' : `Filter ${String(rows.length)} ${axisName}`
}

/**
 * What a decimal literal looks like, which is the only thing a total is willing to add.
 *
 * `Number` is a wider parser than a person typing counts means to reach: it reads `0x10` as sixteen,
 * ` ` as zero and `Infinity` as a quantity. A total that added any of those would be a figure nobody
 * could account for, so the literal has to look like a number before it is read as one.
 */
const DECIMAL_LITERAL = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/

/**
 * What the boxes of one row - or of one band - currently add up to, or null when they add to nothing.
 *
 * A CHECK FIGURE, NOT AN ANSWER. Nothing here is submitted: a data set's own totals are DHIS2's to
 * compute, and this is the arithmetic the person filling the form was going to do on paper anyway -
 * the one that catches a 1370 typed where 137 was meant. It recomputes from the literals the boxes
 * hold, so it follows the typing rather than the submission.
 *
 * A BLANK IS NOTHING AND COUNTS AS NOTHING. A row of four boxes with two filled in totals the two,
 * because the other two are unanswered rather than zero. A row where nothing has been typed at all
 * has no total - `0` there would be a claim of zero cases made by the screen - and one holding
 * something that is not a number has none either, because a total that quietly skipped `1.2.3` would
 * be a figure that disagrees with what is on screen and says nothing about why.
 */
export function liveTotal(values: readonly string[]): number | null {
    let total = 0
    let counted = false
    for (const value of values) {
        const trimmed = value.trim()
        if (trimmed === '') continue
        if (!DECIMAL_LITERAL.test(trimmed)) return null
        const parsed = Number(trimmed)
        if (!Number.isFinite(parsed)) return null
        total += parsed
        counted = true
    }
    if (!counted) return null
    // Binary floating point makes 0.1 + 0.2 read as 0.30000000000000004, which is a total nobody
    // would write down. Whole numbers are exact and left alone; the rest are cut to the precision a
    // person could have typed in the first place.
    return Number.isInteger(total) ? total : Number(total.toFixed(6))
}

/** Whether one row label answers what was typed into the filter box - an empty box asks for all. */
export function matchesComboFilter(label: string, query: string): boolean {
    const wanted = query.trim().toLowerCase()
    return wanted === '' || label.toLowerCase().includes(wanted)
}

/**
 * Which rows of one block are on screen, given what the band's two controls are asking for.
 *
 * FILTERING IS A FACT ABOUT THE SCREEN AND NOTHING ELSE. What comes back is a subset of the same
 * rows, so every combo the block holds keeps its own link id and its own answer whether it is drawn
 * or not: emptying the box brings the same rows back with the same values in them, and a submission
 * made under a filter carries exactly what a submission made under none would.
 *
 * `filled` answers whether the row at one column position already holds a value, which is the only
 * thing the unfilled-only tick reads. It is a callback rather than a set because the caller holds the
 * answers and this module holds the rule.
 */
export function visibleComboRows(
    rows: readonly ComboRow[],
    query: string,
    unfilledOnly: boolean,
    filled: (index: number) => boolean,
): ComboRow[] {
    return rows
        .filter((row) => matchesComboFilter(row.label, query))
        .filter((row) => !unfilledOnly || !filled(row.index))
}

/** The enabled cells of one group, in document order - the answers one table row holds. */
export function disaggregationCells(
    spec: QuestionnaireSpec,
    groupLinkId: string,
    enabled: ReadonlySet<string>,
): string[] {
    return (spec.byLinkId.get(groupLinkId)?.childLinkIds ?? []).filter((linkId) => enabled.has(linkId))
}

/** Whether this question's answer is a number, whichever DHIS2 value type the form emitted it from. */
export function isNumericQuestion(node: QuestionnaireNode): boolean {
    return node.type === 'integer' || node.type === 'decimal'
}

/**
 * The columns one group would be a table row of, or null when the group is not one.
 *
 * The whole test of "this is a disaggregated data element" lives here, so the rule is stated once
 * and read the same way by the partition and by any caller checking a single group.
 */
function disaggregationColumns(
    spec: QuestionnaireSpec,
    node: QuestionnaireNode,
    enabled: ReadonlySet<string>,
): DisaggregationColumn[] | null {
    if (node.type !== 'group') return null
    const cells = disaggregationCells(spec, node.linkId, enabled)
    if (cells.length < 2) return null
    const columns: DisaggregationColumn[] = []
    for (const cellLinkId of cells) {
        const cell = spec.byLinkId.get(cellLinkId)
        if (cell === undefined) return null
        if (!isNumericQuestion(cell) || !cell.fillable) return null
        if (cell.repeats || cell.childLinkIds.length > 0 || cell.description !== null) return null
        columns.push({
            label: cell.text ?? cell.linkId,
            code: cell.code?.code ?? null,
            decomposition: cell.decomposition,
        })
    }
    return columns
}

/**
 * What makes two groups the same cut: the same combos, spelled the same, in the same order.
 *
 * Joined on control characters rather than on punctuation, because a category option combo is named
 * by whoever configured the DHIS2 instance - `Fixed, <1y` carries a comma of its own - and a
 * separator a label can contain is a separator that reads two different cuts as one.
 */
function columnSignature(columns: readonly DisaggregationColumn[]): string {
    return columns.map((column) => `${column.code ?? ''}\u0000${column.label}`).join('\u001f')
}

/**
 * Whether this question shares a line with its neighbours on a wide screen.
 *
 * WIDTH IS A STATEMENT ABOUT THE ANSWER. A count, a day, and a picked concept are all answers a
 * measured control holds, so a column of them beside empty space says the space is unusable when it
 * is only unused. A narrative is the other case and keeps the full width on purpose: `text` is what
 * DHIS2's `LONG_TEXT` emits, the answer is paragraphs, and a paragraph box narrowed to a third of
 * the screen is a worse box. A group, a display, and a question that takes more than one answer or
 * carries questions under it all grow downwards, so each keeps a line of its own.
 */
function flowsIntoColumns(node: QuestionnaireNode): boolean {
    if (node.type === 'group' || node.type === 'display' || node.type === 'text') return false
    return !node.repeats && node.childLinkIds.length === 0
}

/**
 * The DHIS2 categories a group's disaggregated cells are cut by, named, in first-seen order.
 *
 * WHY THE GROUP AND NOT THE CELL. A data element group holds one cell per category option combo, and
 * each cell's label is the combo's own name - "Fixed, <1y". That names the corner of the grid and
 * says nothing about the axes it is a corner of, which is the one fact a reader needs and none of the
 * sixteen labels carries. The axes are the same for every cell of one group, so they are stated once,
 * above them.
 *
 * Read off the cells rather than off the group, because the group codes a data element and the
 * decomposition belongs to the combos underneath it. First-seen order and no sorting: DHIS2 declares
 * a category combo's categories in an order, and that is the order its cells read in.
 */
export function groupCategoryAxes(spec: QuestionnaireSpec, groupLinkId: string): string[] {
    const axes: string[] = []
    for (const childLinkId of spec.byLinkId.get(groupLinkId)?.childLinkIds ?? []) {
        for (const choice of spec.byLinkId.get(childLinkId)?.decomposition ?? []) {
            if (!axes.includes(choice.axis)) axes.push(choice.axis)
        }
    }
    return axes
}

/**
 * The shape a DHIS2 period identifier of one type takes, as far as a browser can check it.
 *
 * WHY A SHAPE AND NOT A PERIOD. `202607` is July 2026 and `2026W30` is a week, and turning either
 * into a date range is DHIS2 period arithmetic this UI does not have and will not grow - the server
 * owns that, and grades an edited period against the type the data set reports for. What a browser
 * can do is refuse to send `july` where a month identifier goes, which is the difference between a
 * mistake caught under the cursor and a round trip that comes back refused.
 */
export interface PeriodShape {
    /** What an unanswered control invites: the shape, spelled as an example of it. */
    placeholder: string
    /** The identifier a person can copy the shape from, as `202607` is a monthly one. */
    example: string
    /** What an identifier of this type looks like, checked in the browser and nowhere else. */
    pattern: RegExp
}

/**
 * The shapes this UI checks, one per DHIS2 period type, and what it does about the rest.
 *
 * SEVEN OF THE SIXTEEN. DHIS2 defines `Daily`, `Weekly`, `WeeklyWednesday`, `WeeklyThursday`,
 * `WeeklySaturday`, `WeeklySunday`, `BiWeekly`, `Monthly`, `BiMonthly`, `Quarterly`, `QuarterlyNov`,
 * `SixMonthly`, `SixMonthlyApril`, `SixMonthlyNov`, `Yearly`, `FinancialApril`, `FinancialJuly`,
 * `FinancialOct` and `FinancialNov`. The seven here are the ones whose identifiers have a shape worth
 * stating in a browser; the offset weeks and the financial years spell their offset into the
 * identifier (`2026WedW30`, `2026April`), and a half-checked pattern for one of those would refuse
 * identifiers DHIS2 accepts. So a type not named here is accepted as typed and graded by the server,
 * which names both types in its refusal - and the control says so rather than pretending to check.
 */
export const PERIOD_SHAPES: ReadonlyMap<string, PeriodShape> = new Map<string, PeriodShape>([
    ['Daily', { placeholder: '20260715', example: '20260715', pattern: /^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$/ }],
    ['Weekly', { placeholder: '2026W30', example: '2026W30', pattern: /^\d{4}W([1-9]|[1-4]\d|5[0-3])$/ }],
    ['BiWeekly', { placeholder: '2026BiW15', example: '2026BiW15', pattern: /^\d{4}BiW([1-9]|1\d|2[0-7])$/ }],
    ['Monthly', { placeholder: '202607', example: '202607', pattern: /^\d{4}(0[1-9]|1[0-2])$/ }],
    ['BiMonthly', { placeholder: '202604B', example: '202604B', pattern: /^\d{4}(0[13579]|11)B$/ }],
    ['Quarterly', { placeholder: '2026Q3', example: '2026Q3', pattern: /^\d{4}Q[1-4]$/ }],
    ['SixMonthly', { placeholder: '2026S2', example: '2026S2', pattern: /^\d{4}S[12]$/ }],
    ['Yearly', { placeholder: '2026', example: '2026', pattern: /^\d{4}$/ }],
])

/** The shape one period type takes, or null for a type whose identifiers this UI does not check. */
export function periodShape(periodType: string | null): PeriodShape | null {
    return periodType === null ? null : (PERIOD_SHAPES.get(periodType) ?? null)
}

/**
 * Whether one identifier is shaped like a period of the stated type.
 *
 * True for every non-empty identifier of a type with no shape here, because "this UI cannot check it"
 * is not "this is wrong" - the server checks it either way. False for an empty one whatever the type:
 * an aggregate submission reports for a period, and no period is not one.
 */
export function isWellShapedPeriod(iso: string, periodType: string | null): boolean {
    const trimmed = iso.trim()
    if (trimmed === '') return false
    const shape = periodShape(periodType)
    return shape === null || shape.pattern.test(trimmed)
}

/** One period a person can pick: the identifier DHIS2 keys by, and what it is called on screen. */
export interface PeriodOption {
    /** The DHIS2 ISO period identifier - `202607` - which is what a submission carries. */
    iso: string
    /** The same period in the words a person reports in - `July 2026`. */
    label: string
}

/** The months, spelled out, because a reporting period is read rather than parsed. */
const MONTH_NAMES = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
] as const

/** The months as a date carries them - `17 Aug` - where a full spelling would crowd the line. */
const SHORT_MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const

/** Two digits, which is how DHIS2 spells a month and a day inside an identifier. */
function twoDigits(value: number): string {
    return String(value).padStart(2, '0')
}

/** One calendar day as a UTC instant, so stepping back a day is never a daylight-saving hour. */
function utcDay(year: number, monthIndex: number, day: number): Date {
    return new Date(Date.UTC(year, monthIndex, day))
}

/** The day `today` falls on, read off the browser's own calendar and held as a UTC instant. */
function startOfDay(today: Date): Date {
    return utcDay(today.getFullYear(), today.getMonth(), today.getDate())
}

/** One day some number of days before another. */
function daysBefore(day: Date, count: number): Date {
    return new Date(day.getTime() - count * 86_400_000)
}

/**
 * Which ISO-8601 week a day falls in, and the week-year that week belongs to.
 *
 * The week-year is not always the calendar year: 1 January 2027 is a Friday, so it falls in the last
 * week of 2026 and DHIS2 spells that period `2026W53`. Found the standard way - the Thursday of the
 * week decides the year, and the week containing 4 January is week one.
 */
function isoWeekOf(day: Date): { weekYear: number; week: number } {
    const thursday = new Date(day.getTime())
    const mondayFirst = (day.getUTCDay() + 6) % 7
    thursday.setUTCDate(thursday.getUTCDate() - mondayFirst + 3)
    const firstThursday = utcDay(thursday.getUTCFullYear(), 0, 4)
    firstThursday.setUTCDate(firstThursday.getUTCDate() - ((firstThursday.getUTCDay() + 6) % 7) + 3)
    return {
        weekYear: thursday.getUTCFullYear(),
        week: 1 + Math.round((thursday.getTime() - firstThursday.getTime()) / (7 * 86_400_000)),
    }
}

/** One family of DHIS2 periods: how many of them are offered, and which one sits a given step back. */
interface PeriodFamily {
    /** How many periods the control offers, the current one included. */
    offered: number
    /** The period `back` steps before the one today falls in. */
    at: (today: Date, back: number) => PeriodOption
}

/** The period a month offset lands in, which is what every monthly, bimonthly and quarterly step is. */
function monthsBefore(today: Date, months: number): { year: number; monthIndex: number } {
    const absolute = today.getFullYear() * 12 + today.getMonth() - months
    return { year: Math.floor(absolute / 12), monthIndex: ((absolute % 12) + 12) % 12 }
}

/**
 * The period types whose recent periods this control can offer, and how it counts them back.
 *
 * SIX OF THE NINETEEN, AND THE REST KEEP THE BOX. A list of periods is a claim about which periods
 * exist, so a type is here only where the arithmetic is the calendar's own and nothing is guessed:
 * days, ISO weeks, months, two-month blocks, quarters, half-years and years. The offset weeks
 * (`2026WedW30`), the two-week periods and the financial years (`2026April`) all number themselves
 * from an offset this UI does not hold, and a list of them would be a list of periods a person could
 * pick that DHIS2 does not have - worse than no list. Those types get the identifier box instead.
 *
 * HOW MANY ARE OFFERED IS HOW FAR BACK ANYBODY REPORTS. A month of figures filed late is filed a
 * month or two late, not four years late, so a monthly data set offers this month and the twelve
 * before it. Coarser types count in what they measure - eight quarters, five years - and a period
 * older than the list is typed in, which is what the identifier box stays for.
 */
const PERIOD_FAMILIES: ReadonlyMap<string, PeriodFamily> = new Map<string, PeriodFamily>([
    [
        'Daily',
        {
            offered: 13,
            at: (today, back) => {
                const day = daysBefore(startOfDay(today), back)
                return {
                    iso: `${String(day.getUTCFullYear())}${twoDigits(day.getUTCMonth() + 1)}${twoDigits(day.getUTCDate())}`,
                    label: `${String(day.getUTCDate())} ${MONTH_NAMES[day.getUTCMonth()]} ${String(day.getUTCFullYear())}`,
                }
            },
        },
    ],
    [
        'Weekly',
        {
            offered: 13,
            at: (today, back) => {
                const day = startOfDay(today)
                const monday = daysBefore(day, ((day.getUTCDay() + 6) % 7) + back * 7)
                const { weekYear, week } = isoWeekOf(monday)
                // The week number alone names nothing a person recognises, so the Monday it opens on
                // rides with it - which is also what makes a mis-numbered week visible rather than
                // silently picked.
                const starts = `Mon ${String(monday.getUTCDate())} ${SHORT_MONTH_NAMES[monday.getUTCMonth()]}`
                return {
                    iso: `${String(weekYear)}W${String(week)}`,
                    label: `Week ${String(week)}, ${String(weekYear)} (starts ${starts})`,
                }
            },
        },
    ],
    [
        'Monthly',
        {
            offered: 13,
            at: (today, back) => {
                const { year, monthIndex } = monthsBefore(today, back)
                return {
                    iso: `${String(year)}${twoDigits(monthIndex + 1)}`,
                    label: `${MONTH_NAMES[monthIndex]} ${String(year)}`,
                }
            },
        },
    ],
    [
        'BiMonthly',
        {
            offered: 9,
            at: (today, back) => {
                const current = monthsBefore(today, 0)
                const { year, monthIndex } = monthsBefore(today, (current.monthIndex % 2) + back * 2)
                return {
                    iso: `${String(year)}${twoDigits(monthIndex + 1)}B`,
                    label: `${MONTH_NAMES[monthIndex]} to ${MONTH_NAMES[monthIndex + 1]} ${String(year)}`,
                }
            },
        },
    ],
    [
        'Quarterly',
        {
            offered: 9,
            at: (today, back) => {
                const current = monthsBefore(today, 0)
                const { year, monthIndex } = monthsBefore(today, (current.monthIndex % 3) + back * 3)
                return {
                    iso: `${String(year)}Q${String(monthIndex / 3 + 1)}`,
                    label: `${MONTH_NAMES[monthIndex]} to ${MONTH_NAMES[monthIndex + 2]} ${String(year)}`,
                }
            },
        },
    ],
    [
        'SixMonthly',
        {
            offered: 9,
            at: (today, back) => {
                const current = monthsBefore(today, 0)
                const { year, monthIndex } = monthsBefore(today, (current.monthIndex % 6) + back * 6)
                return {
                    iso: `${String(year)}S${String(monthIndex / 6 + 1)}`,
                    label: `${MONTH_NAMES[monthIndex]} to ${MONTH_NAMES[monthIndex + 5]} ${String(year)}`,
                }
            },
        },
    ],
    [
        'Yearly',
        {
            offered: 6,
            at: (today, back) => {
                const year = today.getFullYear() - back;
                return { iso: String(year), label: String(year) }
            },
        },
    ],
])

/**
 * The periods of one type a person is offered, most recent first, or none for a type with no list.
 *
 * THE CURRENT PERIOD IS FIRST AND IS NOT THE DEFAULT. A month is reported once it is over, so the
 * month in progress is offered - somebody filing early, or correcting a figure mid-month, is doing
 * something real - and the one the control opens on is the last complete one. See
 * `previousCompletePeriod`.
 *
 * AN EMPTY LIST IS AN ANSWER. A type this cannot count back through offers no periods at all, and
 * the control asks for the identifier instead: see `PERIOD_FAMILIES` for which types those are and
 * why guessing at their numbering would be worse than asking.
 */
export function recentPeriods(periodType: string | null, today: Date): PeriodOption[] {
    const family = periodType === null ? undefined : PERIOD_FAMILIES.get(periodType)
    if (family === undefined) return []
    return Array.from({ length: family.offered }, (_unused, back) => family.at(today, back))
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

/**
 * What `<input type="date">` will accept back from a stored R4 dateTime: the calendar half of it.
 *
 * A date-only value is itself an R4 dateTime, so a control that asks for a date hands one straight
 * to `normaliseDateTime` and nothing has to invent a clock reading. That is the point of asking for
 * a date: an enrollment begins on a day, and the minutes `$generate` drew for it were a number
 * nobody had a reason to believe.
 */
export function dateInputValue(text: string): string {
    return dateTimeInputValue(text).slice(0, 10)
}

/** One key press, in the four facts the implicit-submission rule below reads off it. */
export interface FormKeyPress {
    /** The key, as `KeyboardEvent.key` spells it. */
    key: string
    /** The tag name of the element the key was pressed in, as `Element.tagName` spells it - upper case. */
    tagName: string
    /** An input's `type`, lower case. Anything that is not an input states the empty string. */
    inputType: string
    /** True when Alt, Control, Meta or Shift was held, which is a different key press. */
    withModifier: boolean
}

/** The input types that are a button wearing an input's tag, and press rather than post. */
const BUTTON_INPUT_TYPES: ReadonlySet<string> = new Set(['button', 'submit', 'reset', 'image'])

/**
 * Whether this key press is the browser about to post the whole capture by itself.
 *
 * HTML's implicit submission: Enter in a text box of a form that has a submit button submits the
 * form, wherever in it the box sits. On a capture screen that means a person pressing Enter in a
 * search box, or after typing a period, files the submission they were still filling in - and the
 * receipt is permanent. So the form swallows exactly those presses, and nothing but the Submit
 * button submits a capture.
 *
 * WHAT IS LEFT ALONE, AND WHY EACH. A textarea takes Enter as a newline and never submits. A button
 * takes it as a press, which is how the keyboard reaches Submit. A select takes it as a choice. A
 * modifier held is a different key press altogether, and none of the combinations submits. And an
 * element that is none of these - the tree rows of the organisation-unit picker, a popover's own
 * list - handles its own keys and is not a form control the browser would post from.
 */
export function implicitlySubmits(press: FormKeyPress): boolean {
    if (press.key !== 'Enter' || press.withModifier) return false
    if (press.tagName !== 'INPUT') return false
    return !BUTTON_INPUT_TYPES.has(press.inputType)
}

/** The box a numeric question is filled in through, as the attributes that decide what it keeps. */
export interface NumericInputShape {
    /** The input's `type`. */
    type: 'text'
    /** Which keypad a touch device offers for it. */
    inputMode: 'numeric' | 'decimal'
}

/**
 * What kind of box an `integer` or a `decimal` question gets.
 *
 * A TEXT BOX FOR BOTH, WHICH IS THE WHOLE POINT. `<input type="number">` lets the browser decide
 * what a numeric literal is: it drops the character it cannot parse, so `1.2.3` becomes `1.23` under
 * the cursor and `abc` becomes nothing at all, with no signal either way. This app converts once, at
 * submit, and states what it could not carry (`answerBreaches`) - which only works if the box hands
 * over what was typed. So the type is text and the keypad is stated separately, which is what
 * `inputMode` is for.
 */
export function numericInputShape(itemType: QuestionnaireItemType): NumericInputShape {
    return { type: 'text', inputMode: itemType === 'integer' ? 'numeric' : 'decimal' }
}

/** Read one Questionnaire item and its subtree, returning the link ids of the items read at this level. */
function collectItems(
    items: QuestionnaireItem[],
    ancestorLinkIds: string[],
    nodes: QuestionnaireNode[],
    dictionary: QuestionDictionary,
): string[] {
    const linkIds: string[] = []
    for (const item of items) {
        const node = readItem(item, ancestorLinkIds, dictionary)
        nodes.push(node)
        linkIds.push(node.linkId)
        node.childLinkIds = collectItems(item.item ?? [], [...ancestorLinkIds, item.linkId], nodes, dictionary)
    }
    return linkIds
}

/**
 * The help text an item carries, and nothing where the help text is the question again.
 *
 * DHIS2 requires a description of nothing, so a great many objects are saved with the name typed
 * into the description box - a "First name" data element described as "First name". Rendered, that
 * is a label with a second, quieter label under it: it asks the reader to compare two strings to
 * find out that the second says nothing, and it does that on every question of a registration form.
 * Help text that repeats its own label is help text the form does not have.
 */
function helpText(item: QuestionnaireItem): string | null {
    const stated =
        item.extension?.find((candidate) => candidate.url.endsWith(DESCRIPTION_EXTENSION_SUFFIX))?.valueString ??
        null
    if (stated === null) return null
    return stated.trim() === (item.text ?? '').trim() ? null : stated
}

/** One item, read into the node a control renders from. */
function readItem(
    item: QuestionnaireItem,
    ancestorLinkIds: string[],
    dictionary: QuestionDictionary,
): QuestionnaireNode {
    const answerElement = ANSWER_ELEMENTS_BY_ITEM_TYPE[item.type] ?? null
    const code = item.code?.[0] ?? null
    const facts =
        (code === null ? undefined : dictionary.byConcept.get(conceptKey(code.system, code.code))) ??
        NO_CONCEPT_FACTS
    return {
        linkId: item.linkId,
        ancestorLinkIds,
        parentLinkId: ancestorLinkIds.at(-1) ?? null,
        depth: ancestorLinkIds.length,
        type: item.type,
        text: item.text ?? null,
        description: helpText(item),
        required: item.required === true,
        repeats: item.repeats === true,
        readOnly: item.readOnly === true,
        maxLength: item.maxLength ?? null,
        minimum: numericExtension(item, MINIMUM_VALUE_EXTENSION_URL),
        maximum: numericExtension(item, MAXIMUM_VALUE_EXTENSION_URL),
        minimumDate: datedExtension(item, MINIMUM_VALUE_EXTENSION_URL),
        maximumDate: datedExtension(item, MAXIMUM_VALUE_EXTENSION_URL),
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
        valueType: facts.valueType,
        generated: facts.generated,
        pattern: facts.pattern,
        decomposition: facts.decomposition,
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

/** The calendar day one bounds extension states, or null when it bounds a number rather than a day. */
function datedExtension(item: QuestionnaireItem, url: string): string | null {
    return item.extension?.find((candidate) => candidate.url === url)?.valueDate ?? null
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
