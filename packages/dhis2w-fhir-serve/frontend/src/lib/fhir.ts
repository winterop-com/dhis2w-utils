/**
 * The FHIR R4 shapes this UI actually reads, hand-typed and deliberately narrow.
 *
 * WHY NOT CODEGEN. The full R4 type set is ~150 resources and several thousand
 * elements, and `d2w fhir serve` answers for six of them. A generated tree would
 * put every optional element of every resource in front of the renderer, which
 * is precisely the wrong shape for a form UI: what matters here is which handful
 * of elements the DHIS2 capture contract actually populates. So these interfaces
 * are the contract as this server serves it, and anything outside them is either
 * absent from the wire or none of this UI's business. `[key: string]: unknown`
 * index signatures are avoided on purpose - an unknown element should be a
 * compile error that gets a field added here, not a silent `any`.
 *
 * Everything in this module is pure. Nothing fetches; the network lives behind
 * the single choke point in lib/api.ts. That split is what makes the parsing
 * rules testable without a server.
 */

import type { CapabilitySecurity } from '@/lib/auth'

/** A coded value: the system that defines the code, the code, and its display. */
export interface Coding {
    system?: string
    code?: string
    display?: string
    version?: string
}

/** A business identifier - how every generated resource carries its DHIS2 uid and code. */
export interface Identifier {
    system?: string
    value?: string
}

/**
 * A reference to another resource, by relative or absolute URL.
 *
 * `type` is how a tracker response names its subject: the DHIS2 tracked entity has no FHIR
 * resource published for it, so the reference carries an identifier and the type it would
 * have been - `{"type": "Patient", "identifier": {...}}` - rather than a resolvable URL.
 */
export interface Reference {
    reference?: string
    type?: string
    display?: string
    identifier?: Identifier
}

/** A time range, as the D2Period extension states the reporting period it covers. */
export interface Period {
    start?: string
    end?: string
}

/** A concept stated as one or more codings plus the text it was chosen from. */
export interface CodeableConcept {
    coding?: Coding[]
    text?: string
}

/**
 * Binary content by reference or inline; no control here fills one, but an answer can carry one.
 *
 * `data` is base64, and this is also how a Location carries its boundary polygon - the official
 * `location-boundary-geojson` extension puts a whole GeoJSON Feature in here rather than giving
 * geometry an element of its own. lib/orgunits.ts is what decodes it.
 */
export interface Attachment {
    contentType?: string
    url?: string
    title?: string
    data?: string
    size?: number
}

/**
 * One extension slot.
 *
 * The DHIS2 IG carries its out-of-band facts here - the form kind, the period,
 * the organisation unit, the tracker enrollment - so the renderer meets these
 * constantly. Only the `value[x]` variants the generated resources actually use
 * are typed; add a variant here when a generator starts emitting one.
 */
export interface Extension {
    url: string
    valueCode?: string
    valueString?: string
    valueDecimal?: number
    valueInteger?: number
    valueBoolean?: boolean
    valueDate?: string
    valueDateTime?: string
    valueTime?: string
    valueUri?: string
    /** A bare FHIR id - how a form names the DHIS2 program rule one `d2-program-rule` repeat is about. */
    valueId?: string
    /** A url naming a definitional resource - how a form binds its attribute-combo vocabulary. */
    valueCanonical?: string
    valueCoding?: Coding
    valueCodeableConcept?: CodeableConcept
    valueReference?: Reference
    valueIdentifier?: Identifier
    valuePeriod?: Period
    valueAttachment?: Attachment
    extension?: Extension[]
}

/** Publication status, as every definitional resource this server serves carries it. */
export type PublicationStatus = 'draft' | 'active' | 'retired' | 'unknown'

/** The `item.type` values R4 defines; the DHIS2 generator emits a subset of them. */
export type QuestionnaireItemType =
    | 'group'
    | 'display'
    | 'boolean'
    | 'decimal'
    | 'integer'
    | 'date'
    | 'dateTime'
    | 'time'
    | 'string'
    | 'text'
    | 'url'
    | 'choice'
    | 'open-choice'
    | 'attachment'
    | 'reference'
    | 'quantity'

/** One question, display element, or group of them. */
export interface QuestionnaireItem {
    linkId: string
    text?: string
    type: QuestionnaireItemType
    required?: boolean
    repeats?: boolean
    readOnly?: boolean
    maxLength?: number
    answerValueSet?: string
    answerOption?: QuestionnaireAnswerOption[]
    initial?: QuestionnaireInitial[]
    enableWhen?: QuestionnaireEnableWhen[]
    enableBehavior?: QuestionnaireEnableBehavior
    code?: Coding[]
    extension?: Extension[]
    item?: QuestionnaireItem[]
}

/** One inline answer choice, for a question whose options are not a ValueSet. */
export interface QuestionnaireAnswerOption {
    valueCoding?: Coding
    valueString?: string
    valueInteger?: number
}

/** The value a question starts out holding, before anyone has answered it. */
export interface QuestionnaireInitial {
    valueBoolean?: boolean
    valueDecimal?: number
    valueInteger?: number
    valueDate?: string
    valueDateTime?: string
    valueTime?: string
    valueString?: string
    valueUri?: string
    valueCoding?: Coding
}

/** The comparisons an `enableWhen` condition can make against another question's answer. */
export type QuestionnaireEnableWhenOperator = 'exists' | '=' | '!=' | '>' | '<' | '>=' | '<='

/** How several `enableWhen` conditions on one item combine. */
export type QuestionnaireEnableBehavior = 'all' | 'any'

/**
 * One condition under which an item is asked at all.
 *
 * The DHIS2 generator emits none of these today - a compiled form asks every question
 * unconditionally - so nothing in the goldens exercises this. It is typed and evaluated
 * anyway because a hand-written or hand-edited Questionnaire served by `--live` may carry
 * them, and a renderer that ignored `enableWhen` would silently ask questions the form
 * says not to ask.
 */
export interface QuestionnaireEnableWhen {
    question: string
    operator: QuestionnaireEnableWhenOperator
    answerBoolean?: boolean
    answerDecimal?: number
    answerInteger?: number
    answerDate?: string
    answerDateTime?: string
    answerTime?: string
    answerString?: string
    answerCoding?: Coding
}

/** A capture form: what `GET /Questionnaire/{id}` answers with. */
export interface Questionnaire {
    resourceType: 'Questionnaire'
    id?: string
    url?: string
    name?: string
    title?: string
    status: PublicationStatus
    experimental?: boolean
    description?: string
    subjectType?: string[]
    identifier?: Identifier[]
    extension?: Extension[]
    item?: QuestionnaireItem[]
}

/** One answer to one question. */
export interface QuestionnaireResponseAnswer {
    valueBoolean?: boolean
    valueDecimal?: number
    valueInteger?: number
    valueDate?: string
    valueDateTime?: string
    valueTime?: string
    valueString?: string
    valueUri?: string
    valueCoding?: Coding
    valueReference?: Reference
    valueAttachment?: Attachment
    item?: QuestionnaireResponseItem[]
}

/** One answered question, or a group holding answered questions. */
export interface QuestionnaireResponseItem {
    linkId: string
    text?: string
    answer?: QuestionnaireResponseAnswer[]
    item?: QuestionnaireResponseItem[]
}

/** The two statuses the DHIS2 capture contract writes, plus the rest of the R4 set. */
export type QuestionnaireResponseStatus =
    | 'in-progress'
    | 'completed'
    | 'amended'
    | 'entered-in-error'
    | 'stopped'

/** A filled-in form: what a capture client POSTs, and what a receipt reads back as. */
export interface QuestionnaireResponse {
    resourceType: 'QuestionnaireResponse'
    id?: string
    meta?: { profile?: string[] }
    identifier?: Identifier
    questionnaire?: string
    status: QuestionnaireResponseStatus
    authored?: string
    subject?: Reference
    extension?: Extension[]
    item?: QuestionnaireResponseItem[]
}

/** Where a place is, as a single point - what DHIS2 holds for a facility. */
export interface LocationPosition {
    longitude: number
    latitude: number
    altitude?: number
}

/**
 * One DHIS2 organisation unit as a place.
 *
 * `partOf` is the hierarchy - it names the parent unit's Location - and is the only element the
 * tree is folded from. The level and the boundary polygon both ride on `extension`; lib/orgunits.ts
 * is what reads them.
 */
export interface Location {
    resourceType: 'Location'
    id?: string
    name?: string
    description?: string
    status?: string
    identifier?: Identifier[]
    position?: LocationPosition
    extension?: Extension[]
    partOf?: Reference
    managingOrganization?: Reference
}

/** The classification elements a resource carries in `meta` - this UI reads the tags. */
export interface Meta {
    profile?: string[]
    tag?: Coding[]
}

/**
 * One person in the DHIS2 instance behind a live facade.
 *
 * Identity and nothing else, which is what `dhis2w_fhir_serve.register.projection` publishes and
 * why: DHIS2 has no attribute that means a name, a gender, or a birth date, so those elements are
 * absent rather than guessed at. `id` is the tracked entity uid, `identifier` opens with that uid
 * and then carries one entry per value of an attribute DHIS2 declares unique, `meta.tag` states
 * the tracked entity type, and every remaining attribute value rides an extension.
 */
export interface Patient {
    resourceType: 'Patient'
    id?: string
    meta?: Meta
    identifier?: Identifier[]
    extension?: Extension[]
}

/** One member of a List: the resource it names. */
export interface ResourceListEntry {
    item: Reference
}

/**
 * A curated set of references - which is how this IG publishes a form's organisation-unit assignment.
 *
 * Named `ResourceList` rather than `List` because the FHIR type name is a word every reader will
 * mistake for a collection. `dhis2w_fhir_serve.capture.index` spells the Python side the same way.
 */
export interface ResourceList {
    resourceType: 'List'
    id?: string
    status?: string
    mode?: string
    title?: string
    entry?: ResourceListEntry[]
}

/** One property a CodeSystem declares its concepts may carry, as `CodeSystem.property`. */
export interface CodeSystemPropertyDefinition {
    code: string
    uri?: string
    description?: string
    type?: string
}

/**
 * One property value on one concept.
 *
 * The DHIS2 emitter writes `valueString` (the option code, the DHIS2 uid), but a hand-written
 * CodeSystem served with `--live` may use any of R4's variants, so the ones a concept table can
 * render as text are all read.
 */
export interface CodeSystemConceptProperty {
    code: string
    valueString?: string
    valueCode?: string
    valueInteger?: number
    valueBoolean?: boolean
    valueDecimal?: number
    valueDateTime?: string
    valueCoding?: Coding
}

/** One concept: its code, how it is displayed, and whatever properties the system declares. */
export interface CodeSystemConcept {
    code: string
    display?: string
    definition?: string
    property?: CodeSystemConceptProperty[]
}

/** A terminology resource, with the concepts a browser shows and the properties they carry. */
export interface CodeSystem {
    resourceType: 'CodeSystem'
    id?: string
    url?: string
    name?: string
    title?: string
    description?: string
    status: PublicationStatus
    identifier?: Identifier[]
    caseSensitive?: boolean
    content?: string
    count?: number
    valueSet?: string
    property?: CodeSystemPropertyDefinition[]
    concept?: CodeSystemConcept[]
}

/**
 * A value set, read for what a listing needs to say about it and for what a choice question offers.
 *
 * `compose.include[].concept` is the enumerated form - a subset of one system. The DHIS2
 * emitter writes the whole-system form (a bare `system`), and the option expander in
 * hooks/use-valueset-options.ts reads the named CodeSystem when no concepts are enumerated.
 */
export interface ValueSet {
    resourceType: 'ValueSet'
    id?: string
    url?: string
    name?: string
    title?: string
    description?: string
    status: PublicationStatus
    identifier?: Identifier[]
    compose?: { include?: ValueSetInclude[] }
}

/** One `compose.include` of a ValueSet: a system, and optionally the concepts of it that are in. */
export interface ValueSetInclude {
    system?: string
    concept?: { code: string; display?: string }[]
}

/** One concept a mapping lands on, in the target system its group names. */
export interface ConceptMapTarget {
    code?: string
    display?: string
    equivalence?: string
    comment?: string
}

/** One source concept and everything the map takes it to. */
export interface ConceptMapElement {
    code?: string
    display?: string
    target?: ConceptMapTarget[]
}

/** One source-system to target-system block of mappings. */
export interface ConceptMapGroup {
    source?: string
    target?: string
    element?: ConceptMapElement[]
}

/**
 * A concept map: a generated concept taken back to the DHIS2 identifiers it stands for.
 *
 * `identifier` is a single element here rather than a list - R4 gives `ConceptMap.identifier`
 * a cardinality of 0..1 where every other definitional resource gets 0..*, and the emitter
 * writes it as the DHIS2 object the map was generated from.
 */
export interface ConceptMap {
    resourceType: 'ConceptMap'
    id?: string
    url?: string
    name?: string
    title?: string
    description?: string
    status: PublicationStatus
    identifier?: Identifier
    sourceCanonical?: string
    targetCanonical?: string
    group?: ConceptMapGroup[]
}

/**
 * One parameter of an operation's input or output, with the `value[x]` variants this UI meets.
 *
 * `$translate` answers with `result`, an optional `message`, and one `match` per mapping - and a
 * match carries its own parts, which is why this shape is recursive.
 */
export interface ParametersParameter {
    name: string
    valueBoolean?: boolean
    valueString?: string
    valueCode?: string
    valueUri?: string
    valueCoding?: Coding
    part?: ParametersParameter[]
}

/** The R4 envelope every operation on this server answers in. */
export interface Parameters {
    resourceType: 'Parameters'
    parameter?: ParametersParameter[]
}

/** Every resource type this UI can meet inside a Bundle entry. */
export type FhirResource =
    | Questionnaire
    | QuestionnaireResponse
    | CodeSystem
    | ValueSet
    | ConceptMap
    | Location
    | Patient
    | ResourceList
    | OperationOutcome

/** One result inside a search Bundle. */
export interface BundleEntry<T = FhirResource> {
    fullUrl?: string
    resource?: T
    search?: { mode?: string }
}

/** A search result set, as `GET /{type}` answers with. */
export interface Bundle<T = FhirResource> {
    resourceType: 'Bundle'
    type: string
    total?: number
    link?: { relation: string; url: string }[]
    entry?: BundleEntry<T>[]
}

/** One thing that went wrong, or one warning about something that did not. */
export interface OperationOutcomeIssue {
    severity: 'fatal' | 'error' | 'warning' | 'information'
    code: string
    diagnostics?: string
    expression?: string[]
    details?: { text?: string; coding?: Coding[] }
}

/** How this server states every refusal, and every warning on an accepted capture. */
export interface OperationOutcome {
    resourceType: 'OperationOutcome'
    issue: OperationOutcomeIssue[]
}

/** One operation a CapabilityStatement declares, at rest or resource level. */
export interface CapabilityStatementOperation {
    name: string
    definition?: string
    documentation?: string
}

/** One interaction code a resource entry declares. */
export interface CapabilityStatementInteraction {
    code: string
    documentation?: string
}

/** One search parameter a resource entry declares. */
export interface CapabilityStatementSearchParam {
    name: string
    type: string
    documentation?: string
}

/** What the server says it can do with one resource type. */
export interface CapabilityStatementResource {
    type: string
    supportedProfile?: string[]
    documentation?: string
    interaction?: CapabilityStatementInteraction[]
    searchParam?: CapabilityStatementSearchParam[]
    operation?: CapabilityStatementOperation[]
}

/** The server-mode REST block; this server declares exactly one. */
export interface CapabilityStatementRest {
    mode: string
    documentation?: string
    security?: CapabilitySecurity
    resource?: CapabilityStatementResource[]
    operation?: CapabilityStatementOperation[]
}

/** The conformance document at `GET /metadata` - the served IG's identity and contract. */
export interface CapabilityStatement {
    resourceType: 'CapabilityStatement'
    status: PublicationStatus
    date?: string
    kind: string
    description?: string
    instantiates?: string[]
    software?: { name: string; version?: string }
    implementation?: { description?: string; url?: string }
    fhirVersion?: string
    format?: string[]
    rest?: CapabilityStatementRest[]
}

/**
 * The extension the DHIS2 IG carries a Questionnaire's form kind on.
 *
 * The full url is `{canonical}/StructureDefinition/d2-form-type`, and the
 * canonical is per-project - it is whatever `[ig] canonical` says in that
 * project's fhir.toml. The UI is served by the very server that published those
 * resources but has no reason to hard-code its canonical, so the match is on the
 * suffix. That is stricter than it looks: `/StructureDefinition/d2-form-type` is
 * a path the IG defines, and no other extension the generator emits ends in it.
 */
export const FORM_TYPE_EXTENSION_SUFFIX = '/StructureDefinition/d2-form-type'

/**
 * The kinds of DHIS2 object a generated Questionnaire can have come from.
 *
 * These are the codes of the `D2FormType` CodeSystem verbatim - see
 * `FORM_TYPE_DEFINITIONS` in dhis2w_fhir.foundation.schemas. `tracker-event`
 * (a program stage) is the one that catches people out: it is not spelled
 * `tracker`, which is the registration form, and the goldens use the former.
 * `tracked-entity` is the third one-person kind and the only one that enrols
 * nobody: it is generated from a DHIS2 tracked entity type rather than from a
 * program, so its response carries a subject and an organisation unit and no
 * enrollment at all.
 */
export const FORM_TYPES = ['aggregate', 'event', 'tracker', 'tracker-event', 'tracked-entity'] as const

/** One code of the `D2FormType` terminology. */
export type FormType = (typeof FORM_TYPES)[number]

/**
 * How each form kind is named in the UI, since the codes are terse.
 *
 * `tracked-entity` reads as "Person registration" rather than as its DHIS2 artifact name: what a
 * reader needs from a badge is that the form registers a person, and that it says nothing about a
 * program is the very fact "Tracker registration" beside it does not carry.
 */
export const FORM_TYPE_LABELS: Record<FormType, string> = {
    aggregate: 'Aggregate data set',
    event: 'Event program',
    tracker: 'Tracker registration',
    'tracker-event': 'Tracker program stage',
    'tracked-entity': 'Person registration',
}

/** The form kinds whose submission is about one person rather than about a place or a period. */
export const PERSON_FORM_TYPES: readonly FormType[] = ['tracker', 'tracked-entity']

/** Whether a form kind registers a person - the two kinds a patient picker sits on. */
export function registersAPerson(formKind: FormType | null): boolean {
    return formKind !== null && PERSON_FORM_TYPES.includes(formKind)
}

/**
 * The extension a Questionnaire names its attribute-option-combo vocabulary on.
 *
 * The full url is `{canonical}/StructureDefinition/d2-attribute-option-combos`, and it is valued
 * `canonical(ValueSet)` - the set of attribute option combos a data set on a non-default category
 * combo files each of its responses under. Matched on the suffix for the same reason the form-type
 * extension is: the canonical is whatever that project's fhir.toml declares.
 */
export const ATTRIBUTE_OPTION_COMBOS_EXTENSION_SUFFIX = '/StructureDefinition/d2-attribute-option-combos'

/**
 * The extension a QuestionnaireResponse states the one combo it reports for on.
 *
 * Singular, `valueCoding`, and one character away from the form-side url above - which is a
 * property of the IG worth reading twice, because `endsWith` on the singular suffix is exactly
 * what tells the two apart: `...d2-attribute-option-combos` does not end in `...d2-attribute-option-combo`.
 */
export const ATTRIBUTE_OPTION_COMBO_EXTENSION_SUFFIX = '/StructureDefinition/d2-attribute-option-combo'

/**
 * The ValueSet canonical a form draws its reporting combos from, or null when it declares none.
 *
 * Null is the ordinary case and it means the default combo: a data set on the default category
 * combo publishes no vocabulary, and absence is how the guide spells "there is nothing to pick".
 */
export function attributeOptionCombosOf(questionnaire: Questionnaire): string | null {
    const extension = questionnaire.extension?.find((candidate) =>
        candidate.url.endsWith(ATTRIBUTE_OPTION_COMBOS_EXTENSION_SUFFIX),
    )
    return extension?.valueCanonical ?? null
}

/** The combo one response reports for, or null when it states none. */
export function attributeOptionComboOf(response: QuestionnaireResponse): Coding | null {
    const extension = response.extension?.find((candidate) =>
        candidate.url.endsWith(ATTRIBUTE_OPTION_COMBO_EXTENSION_SUFFIX),
    )
    return extension?.valueCoding ?? null
}

/**
 * The url a response states its combo under, derived from the form that declared the vocabulary.
 *
 * Both extensions are published under the same canonical, so the response-side url is the
 * form-side url with its own suffix in place of the plural one. Deriving it rather than
 * hard-coding a canonical is what keeps this UI working against any project's fhir.toml, and
 * deriving it from the *form* rather than from the served base url is what keeps it right when a
 * facade serves a guide compiled under a different canonical than it answers on.
 */
export function attributeOptionComboExtensionUrl(questionnaire: Questionnaire): string | null {
    const declared = questionnaire.extension?.find((candidate) =>
        candidate.url.endsWith(ATTRIBUTE_OPTION_COMBOS_EXTENSION_SUFFIX),
    )
    if (declared === undefined) return null
    const canonical = declared.url.slice(0, declared.url.length - ATTRIBUTE_OPTION_COMBOS_EXTENSION_SUFFIX.length)
    return `${canonical}${ATTRIBUTE_OPTION_COMBO_EXTENSION_SUFFIX}`
}

/**
 * What the reporting-context control is called, on the form and on the receipt.
 *
 * The DHIS2 word is "attribute option combo", which is the artifact's name rather than anything a
 * data clerk says out loud; the combo's own name - the category combo the data set rides, "Project"
 * - is what the person filling the form is actually choosing between. So the title of the published
 * vocabulary leads whenever there is one, and the artifact name is the honest fallback for a
 * project whose ValueSet states no title. One function, so the picker and the receipt say the same
 * thing about the same fact.
 */
export function attributeOptionComboLabel(title: string | null | undefined): string {
    const stated = (title ?? '').trim()
    return stated === '' ? 'Attribute option combo' : `Reporting for ${stated}`
}

/**
 * How one concept of a served CodeSystem is displayed, or null when it holds no such code.
 *
 * A stored coding carries its own `display`, but a receipt read months later is better served by
 * what the system says now - and a coding written by a client that sent code and system alone has
 * no display at all. Null rather than the code, so the caller decides what an unresolvable concept
 * renders as.
 */
export function conceptDisplay(codeSystem: CodeSystem | null, code: string | null | undefined): string | null {
    if (codeSystem === null || code === null || code === undefined) return null
    const concept = codeSystem.concept?.find((candidate) => candidate.code === code)
    return concept?.display ?? null
}

/**
 * The extension a tracker response names the DHIS2 enrollment it belongs to on.
 *
 * Valued `Identifier` rather than `Reference`, because this guide publishes no resource for a
 * DHIS2 enrollment: the identifier *is* the enrollment. A registration response mints the value
 * itself - a client-generated DHIS2 uid - which is what lets a stage response answer against an
 * enrollment before either of them has reached DHIS2.
 */
export const TRACKER_ENROLLMENT_EXTENSION_SUFFIX = '/StructureDefinition/d2-tracker-enrollment'

/**
 * The extension a registration question states its DHIS2 import level on.
 *
 * True means the answer is written onto the tracked entity itself - the person - and false means
 * it is written onto the enrollment. The distinction is invisible on an ordinary registration,
 * where both land in the same import, and decisive on one answering for a person the instance
 * already holds: DHIS2 has that person's entity-level values already, and the conversion layer
 * refuses one that states its subject already exists and carries one anyway.
 */
export const ENTITY_LEVEL_EXTENSION_SUFFIX = '/StructureDefinition/d2-entity-level'

/** The extension a registration response dates its enrollment with - required on that profile. */
export const ENROLLED_AT_EXTENSION_SUFFIX = '/StructureDefinition/d2-enrolled-at'

/**
 * The extension a registration response dates the incident its enrollment follows with.
 *
 * Optional, and absence is a fact about the *program*: one that does not display an incident date
 * generates a form whose responses carry none, so a missing value here is not a gap in the
 * capture.
 */
export const INCIDENT_AT_EXTENSION_SUFFIX = '/StructureDefinition/d2-incident-at'

/**
 * The identifier system a tracker response names its tracked entity under.
 *
 * `{identifier_system_base}/id/tracked-entity`, on `subject.identifier` rather than on a
 * reference - the person has no published resource, so the identifier is the subject. Matched on
 * the tail like every other derived system this UI meets. `/id/tracked-entity-type` is a
 * different system and does not match, because the suffix comparison is exact at the end.
 */
export const TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX = '/id/tracked-entity'

/**
 * The identifier system a person-only registration form names the DHIS2 tracked entity type under.
 *
 * The one place the guide publishes a name for a tracked entity type: a `tracked-entity` form is
 * generated from the type itself, carries its uid here, and is titled with the type's own name. A
 * served Patient states the same uid as a `meta.tag` and carries no display for it, so this
 * identifier is what a screen joins through to say "Person" rather than "TetPerson01".
 *
 * `/id/tracked-entity` is a different system and does not match, because the suffix comparison is
 * exact at the end - `/id/tracked-entity-type` does not end in `/id/tracked-entity`.
 */
export const TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM_SUFFIX = '/id/tracked-entity-type'

/** The DHIS2 tracked entity type uid a person-only form was generated from, or null. */
export function trackedEntityTypeOf(questionnaire: Questionnaire): string | null {
    const identifier = questionnaire.identifier?.find((candidate) =>
        candidate.system?.endsWith(TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM_SUFFIX),
    )
    return identifier?.value ?? null
}

/** The identifier system the enrollment extension's `valueIdentifier` names its uid under. */
export const TRACKER_ENROLLMENT_IDENTIFIER_SYSTEM_SUFFIX = '/id/tracker-enrollment'

/**
 * The identifier system a Questionnaire names the DHIS2 program it belongs to under.
 *
 * A program-stage form carries it as a grouping identifier and a registration form carries it as
 * its own identity - which is exactly the join a stage form needs to find the registrations of
 * its program. `/id/program-stage` and `/id/program-code` are different systems and do not
 * match, because the suffix comparison is exact at the end.
 */
export const PROGRAM_IDENTIFIER_SYSTEM_SUFFIX = '/id/program'

/**
 * The DHIS2 program uid a Questionnaire belongs to, or null when it names none.
 *
 * The value alone does not say the form is a tracker one - an event program's form carries the
 * program identifier too, because the form IS the program - so callers joining tracker surfaces
 * pair this with `formTypeOf`.
 */
export function programOf(questionnaire: Questionnaire): string | null {
    const identifier = questionnaire.identifier?.find((candidate) =>
        candidate.system?.endsWith(PROGRAM_IDENTIFIER_SYSTEM_SUFFIX),
    )
    return identifier?.value ?? null
}

/** The identifier system an aggregate form names the DHIS2 data set it was generated from under. */
export const DATA_SET_IDENTIFIER_SYSTEM_SUFFIX = '/id/data-set'

/** The identifier system a tracker stage form names the DHIS2 program stage it was generated from under. */
export const PROGRAM_STAGE_IDENTIFIER_SYSTEM_SUFFIX = '/id/program-stage'

/**
 * The DHIS2 data set uid an aggregate form was generated from, or null when it names none.
 *
 * `/id/data-set-code` is a different system and does not match, because the suffix comparison is
 * exact at the end - the same rule `programOf` relies on.
 */
export function dataSetOf(questionnaire: Questionnaire): string | null {
    const identifier = questionnaire.identifier?.find((candidate) =>
        candidate.system?.endsWith(DATA_SET_IDENTIFIER_SYSTEM_SUFFIX),
    )
    return identifier?.value ?? null
}

/** The DHIS2 program stage uid a stage form was generated from, or null when it names none. */
export function programStageOf(questionnaire: Questionnaire): string | null {
    const identifier = questionnaire.identifier?.find((candidate) =>
        candidate.system?.endsWith(PROGRAM_STAGE_IDENTIFIER_SYSTEM_SUFFIX),
    )
    return identifier?.value ?? null
}

/**
 * The identifier-system base a form's DHIS2 identifiers are published under, or null.
 *
 * Read off the form's own program identifier rather than configured, on the same argument every
 * other canonical-derived url follows: the base is whatever that project's fhir.toml declares,
 * and the form already states it. This is what lets a chosen tracker context be written onto a
 * response even when `$generate` was refused and there is no envelope to copy the spelling from.
 */
export function identifierSystemBaseOf(questionnaire: Questionnaire): string | null {
    const identifier = questionnaire.identifier?.find((candidate) =>
        candidate.system?.endsWith(PROGRAM_IDENTIFIER_SYSTEM_SUFFIX),
    )
    const system = identifier?.system
    if (system === undefined) return null
    return system.slice(0, system.length - PROGRAM_IDENTIFIER_SYSTEM_SUFFIX.length)
}

/**
 * The url a response states its enrollment under, derived from the form's own declarations.
 *
 * The extension is published under the IG canonical, and the one canonical-rooted url every
 * served form carries is its form-type extension - so the response-side url is that url with the
 * enrollment suffix in place of the form-type one. Derived rather than hard-coded for the same
 * reason `attributeOptionComboExtensionUrl` is, and null for a form that declares no kind at all
 * - which is a form this server refuses to capture against anyway.
 */
export function trackerEnrollmentExtensionUrl(questionnaire: Questionnaire): string | null {
    const declared = questionnaire.extension?.find((candidate) => candidate.url.endsWith(FORM_TYPE_EXTENSION_SUFFIX))
    if (declared === undefined) return null
    const canonical = declared.url.slice(0, declared.url.length - FORM_TYPE_EXTENSION_SUFFIX.length)
    return `${canonical}${TRACKER_ENROLLMENT_EXTENSION_SUFFIX}`
}

/** When the enrollment a registration response creates begins, or null when it states none. */
export function enrolledAtOf(response: QuestionnaireResponse): string | null {
    return responseExtension(response, ENROLLED_AT_EXTENSION_SUFFIX)?.valueDateTime ?? null
}

/** When the incident the enrollment follows occurred, or null - which most programs are. */
export function incidentAtOf(response: QuestionnaireResponse): string | null {
    return responseExtension(response, INCIDENT_AT_EXTENSION_SUFFIX)?.valueDateTime ?? null
}

/**
 * The DHIS2 enrollment uid a tracker response names, or null when it names none.
 *
 * The same read for both tracker kinds: a registration response mints the uid and a stage
 * response quotes one that was minted for it, and the extension is spelled identically either
 * way.
 */
export function trackerEnrollmentOf(response: QuestionnaireResponse): string | null {
    return responseExtension(response, TRACKER_ENROLLMENT_EXTENSION_SUFFIX)?.valueIdentifier?.value ?? null
}

/**
 * The DHIS2 tracked-entity uid a response is about, or null when its subject is not one.
 *
 * The system is checked rather than assumed: an aggregate or event response's subject is a
 * `Location`, and reading its identifier as a person would be wrong in a way nothing downstream
 * could catch.
 */
export function trackedEntityOf(response: QuestionnaireResponse): string | null {
    const identifier = response.subject?.identifier
    if (!identifier?.system?.endsWith(TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX)) return null
    return identifier.value ?? null
}

/** One extension of a response by the url tail the IG publishes it under. */
function responseExtension(response: QuestionnaireResponse, suffix: string): Extension | undefined {
    return response.extension?.find((candidate) => candidate.url.endsWith(suffix))
}

/**
 * The identifier-system suffix `$generate` states its seed under.
 *
 * The full system is `{canonical}/id/generate-seed`, and like every other canonical-derived url
 * this UI meets it is matched on the suffix rather than hard-coded - the canonical is whatever
 * that project's fhir.toml declares. `GENERATE_SEED_IDENTIFIER_SEGMENT` in
 * `dhis2w_fhir_serve.capture.naming` is the Python side of the same string.
 */
export const GENERATE_SEED_IDENTIFIER_SUFFIX = '/id/generate-seed'

/**
 * The seed a generated response was drawn from, or null when it states none.
 *
 * Worth surfacing because it is the whole of the operation's reproducibility promise: the same
 * form and the same seed answer with the same bytes, so a seed shown after a fill is a handle
 * on data someone can ask for again.
 */
export function generateSeedOf(response: QuestionnaireResponse): string | null {
    const identifier = response.identifier
    if (!identifier?.system?.endsWith(GENERATE_SEED_IDENTIFIER_SUFFIX)) return null
    return identifier.value ?? null
}

/**
 * The search mode an entry carries when it is one of the things the search was about.
 *
 * R4 defines three - `match`, `include`, `outcome` - and leaves the element optional, so an entry
 * stating no mode at all is a match by omission. That reading is the whole of the rule below.
 */
export const MATCH_SEARCH_MODE = 'match'

/**
 * Whether one Bundle entry is a result rather than something the searchset carries beside its results.
 *
 * WHY THIS EXISTS. A searchset is not a list of results: it is a list of results plus whatever the
 * server needed to say about them. The projection backend appends an `outcome` entry - an
 * OperationOutcome naming when the synced copy last read the DHIS2 instance - and R4 lets any server
 * append `include` entries for resources a result referred to. Neither is a row, and a reader that
 * took every entry as one would show an empty person for the outcome and count it in "Showing N
 * people". So the mode is checked once, here, and every caller that turns a Bundle into rows goes
 * through `bundleResources`.
 *
 * ABSENT COUNTS AS A MATCH, because R4 says so: `search.mode` is 0..1, and a server that answers a
 * plain searchset without stating a mode per entry has still answered with matches. Reading absence
 * as "not a match" would empty every listing this server answers from its store.
 */
export function isMatchEntry<T>(entry: BundleEntry<T>): boolean {
    const mode = entry.search?.mode
    return mode === undefined || mode === MATCH_SEARCH_MODE
}

/** Pull the matched resources out of a search Bundle, dropping entries that are not results. */
export function bundleResources<T>(bundle: Bundle<T> | undefined): T[] {
    if (!bundle?.entry) return []
    return bundle.entry.flatMap((entry) => (entry.resource && isMatchEntry(entry) ? [entry.resource] : []))
}

/**
 * The OperationOutcome a searchset carries beside its results, or null when it carries none.
 *
 * The other half of the rule above: an `outcome` entry is dropped from the rows precisely so it can
 * be read as what it is. This server appends one on every projection-served search to say when the
 * synced copy last read the DHIS2 instance, and a page that showed the rows and threw the sentence
 * away would be hiding the one fact that says how old they are.
 */
export function bundleOutcome<T>(bundle: Bundle<T> | undefined): OperationOutcome | null {
    for (const entry of bundle?.entry ?? []) {
        if (entry.search?.mode !== 'outcome') continue
        const resource = entry.resource as OperationOutcome | undefined
        if (resource?.resourceType === 'OperationOutcome') return resource
    }
    return null
}

/**
 * The url one relation of a searchset Bundle states, or null when the Bundle states none.
 *
 * A paged search states where its neighbours are and this is the only place a caller learns it:
 * `next` absent means there is no page after this one, which is a fact the server is stating rather
 * than something a page count can be derived from. R4 allows several links, so the relation is
 * matched rather than positioned.
 */
export function bundleLink<T>(bundle: Bundle<T> | undefined, relation: string): string | null {
    return bundle?.link?.find((candidate) => candidate.relation === relation)?.url ?? null
}

/**
 * The form kind a Questionnaire declares, or null when it declares none.
 *
 * Null is a real answer, not a failure: a Questionnaire without the extension is
 * one `d2w fhir serve` will refuse to capture against, and saying so in a
 * listing is more useful than guessing a kind for it.
 */
export function formTypeOf(questionnaire: Questionnaire): FormType | null {
    const extension = questionnaire.extension?.find((candidate) =>
        candidate.url.endsWith(FORM_TYPE_EXTENSION_SUFFIX),
    )
    const code = extension?.valueCode
    return FORM_TYPES.find((candidate) => candidate === code) ?? null
}

/**
 * How many questions a form asks, counting through groups and ignoring display items.
 *
 * `display` items are prose the form shows rather than something it asks, so
 * counting them would overstate every form that carries a section heading.
 */
export function questionCount(items: QuestionnaireItem[] | undefined): number {
    if (!items) return 0
    return items.reduce((total, item) => {
        const self = item.type === 'group' || item.type === 'display' ? 0 : 1
        return total + self + questionCount(item.item)
    }, 0)
}

/** The last path segment of a canonical URL - the resource id, for display. */
export function canonicalId(url: string | undefined): string | null {
    if (!url) return null
    const segment = url.split('/').pop()
    return segment ? segment : null
}

/**
 * The id a served form is reachable under.
 *
 * `Questionnaire.id` when the resource states one, then the canonical's last segment - which is
 * how this server ids everything it publishes. Empty string for a form carrying neither, which
 * is a resource no route can open and a listing renders as such rather than linking nowhere.
 */
export function formIdentifier(questionnaire: Questionnaire): string {
    return questionnaire.id ?? canonicalId(questionnaire.url) ?? ''
}

/**
 * What a form is called, as page text.
 *
 * Title, then name, then the id it is served under - each spelled exactly as the server sends it,
 * because every served element carries the DHIS2 text byte for byte. One function so a form is
 * spelled the same on the overview, in the listing, and wherever else it is named.
 */
export function formTitle(questionnaire: Questionnaire): string {
    return questionnaire.title ?? questionnaire.name ?? formIdentifier(questionnaire)
}

/**
 * Every served form in title order.
 *
 * Sorted on the same string that is rendered - so the order a reader sees is the order the
 * comparison made, rather than one taken on the raw escaped title and shown unescaped.
 */
export function formsByTitle(questionnaires: Questionnaire[]): Questionnaire[] {
    return questionnaires.toSorted((left, right) => formTitle(left).localeCompare(formTitle(right)))
}

/** What a fixed-size list of forms shows, and how much of the set it is leaving out. */
export interface FormSlice {
    /** The first `limit` forms in title order. */
    shown: Questionnaire[]
    /** How many forms the project publishes in total. */
    total: number
    /** How many of them the slice is not showing - zero when it shows all of them. */
    hidden: number
}

/**
 * The first `limit` forms in title order, with the size of the tail it is hiding.
 *
 * A quick-entry grid is a shortcut, not a listing: past a handful of cards the grid stops being
 * faster to read than the Forms table. So the caller gets a slice plus the number it dropped,
 * and can say "all N forms" honestly instead of implying the project publishes only what fits.
 */
export function formSlice(questionnaires: Questionnaire[], limit: number): FormSlice {
    const ordered = formsByTitle(questionnaires)
    const shown = ordered.slice(0, Math.max(limit, 0))
    return { shown, total: ordered.length, hidden: ordered.length - shown.length }
}

/** Every operation a CapabilityStatement declares, rest-level and resource-level alike. */
export function declaredOperations(
    capability: CapabilityStatement | null,
): { name: string; on: string; documentation?: string }[] {
    const rest = capability?.rest?.[0]
    if (!rest) return []
    const restLevel = (rest.operation ?? []).map((operation) => ({
        name: operation.name,
        on: 'server',
        documentation: operation.documentation,
    }))
    const resourceLevel = (rest.resource ?? []).flatMap((resource) =>
        (resource.operation ?? []).map((operation) => ({
            name: operation.name,
            on: resource.type,
            documentation: operation.documentation,
        })),
    )
    return [...restLevel, ...resourceLevel]
}

/**
 * Every operation the statement declares, named once each, in declaration order.
 *
 * `declaredOperations` keeps the resource an operation hangs off, because the Server page states
 * it per row. A one-line summary wants the other reading: `$translate` and `$generate` are two
 * capabilities, and which resource type each is declared on is not what a strip of badges is
 * saying. Declaration order rather than alphabetical, so the order follows the statement's own.
 */
export function operationNames(capability: CapabilityStatement | null): string[] {
    const seen = new Set<string>()
    for (const operation of declaredOperations(capability)) seen.add(operation.name)
    return [...seen]
}

/** The one search parameter a live facade answers a register lookup on. */
export const REGISTER_IDENTIFIER_SEARCH_PARAMETER = 'identifier'

/**
 * Whether this server publishes an identifier search over one register resource type.
 *
 * `/metadata` is the whole of the answer and it is stated ahead of any request: a live process over
 * a project that publishes a registration form declares one entry per served register - `Patient`
 * by default, `Specimen` or `Device` where the guide maps a tracked entity type onto it - each with
 * a `search-type` interaction and an `identifier` search parameter, and a compiled process declares
 * none of them. So a control that finds a record in the instance is offered exactly when the
 * conformance document says a search over that register would be answered, rather than offered and
 * then refused. The caller names the register, because which one a form registers into is the
 * form's own `subjectType`.
 *
 * Both halves are checked, not only the resource type. A statement that named the register with a
 * read interaction alone would be a server that resolves a record by uid and cannot look one up,
 * which is not a search control a person can use.
 */
export function declaresRegisterSearch(capability: CapabilityStatement | null, resourceType: string): boolean {
    const entry = capability?.rest?.[0]?.resource?.find((resource) => resource.type === resourceType)
    if (entry === undefined) return false
    const searchable = entry.interaction?.some((interaction) => interaction.code === 'search-type') === true
    const byIdentifier =
        entry.searchParam?.some((parameter) => parameter.name === REGISTER_IDENTIFIER_SEARCH_PARAMETER) === true
    return searchable && byIdentifier
}

/**
 * The search parameter that matches any value a record holds rather than only the ones that name it.
 *
 * Spelled `_content` and not `name`, which is the same refusal to guess that runs through the whole
 * register: DHIS2 states no attribute that means a name, so a server offering `name` would be
 * choosing one of an instance's attributes to be it. `_content` says what it does - it searches the
 * content - and the server's own declaration documents it in those terms.
 */
export const REGISTER_CONTENT_SEARCH_PARAMETER = '_content'

/**
 * The two keys a register search can be sent under, and the one this server publishes for a register.
 *
 * `identifier` is what every live facade answers: the tracked entity uid, and the values of the
 * attributes DHIS2 declares unique. `_content` is answered only where the project keeps a synced copy
 * of the instance to search, because matching a substring of any value a person holds is a question a
 * DHIS2 API round trip cannot answer. Which one is on offer is stated in `/metadata` ahead of any
 * request, exactly like whether the register is searchable at all.
 */
export type RegisterSearchKey = typeof REGISTER_IDENTIFIER_SEARCH_PARAMETER | typeof REGISTER_CONTENT_SEARCH_PARAMETER

/**
 * Which key a search over one register is sent under, per what the conformance document declares.
 *
 * `_content` wins where it is declared, because it is the strictly wider question: every identifier
 * value a person holds is one of the values it matches, so a reader who types a uid still finds them
 * - and a reader who types the fragment on the card that is not a unique attribute's value finds them
 * too, which `identifier` cannot do. Where it is not declared this answers `identifier`, which is
 * what every live facade publishes and what the box has always sent.
 *
 * A capability that is still in flight, or a server that declares no search at all, also answers
 * `identifier`: the caller has already asked `declaresRegisterSearch` whether to offer the control,
 * and this decides only how a search that is offered is spelled.
 */
export function registerSearchKey(
    capability: CapabilityStatement | null,
    resourceType: string,
): RegisterSearchKey {
    const entry = capability?.rest?.[0]?.resource?.find((resource) => resource.type === resourceType)
    const byContent =
        entry?.searchParam?.some((parameter) => parameter.name === REGISTER_CONTENT_SEARCH_PARAMETER) === true
    return byContent ? REGISTER_CONTENT_SEARCH_PARAMETER : REGISTER_IDENTIFIER_SEARCH_PARAMETER
}

/**
 * The served IG's name and version, as the status menu shows it.
 *
 * `software.name` is the command, not the guide, so the guide's identity comes
 * from `description` - which this server writes as "<IG title> served as a FHIR
 * capture facade: ...". Everything before " served as" is the title; when that
 * marker is absent the whole description is shown rather than a truncation
 * guess.
 */
export function servedIgLabel(capability: CapabilityStatement | null): string | null {
    const description = capability?.description
    if (!description) return null
    const marker = description.indexOf(' served as')
    return marker > 0 ? description.slice(0, marker) : description
}
