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

/** Binary content by reference or inline; no control here fills one, but an answer can carry one. */
export interface Attachment {
    contentType?: string
    url?: string
    title?: string
    data?: string
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
    valueCoding?: Coding
    valueCodeableConcept?: CodeableConcept
    valueReference?: Reference
    valueIdentifier?: Identifier
    valuePeriod?: Period
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
 */
export const FORM_TYPES = ['aggregate', 'event', 'tracker', 'tracker-event'] as const

/** One code of the `D2FormType` terminology. */
export type FormType = (typeof FORM_TYPES)[number]

/** How each form kind is named in the UI, since the codes are terse. */
export const FORM_TYPE_LABELS: Record<FormType, string> = {
    aggregate: 'Aggregate data set',
    event: 'Event program',
    tracker: 'Tracker registration',
    'tracker-event': 'Tracker program stage',
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

/** Pull the resources out of a search Bundle, dropping entries that carry none. */
export function bundleResources<T>(bundle: Bundle<T> | undefined): T[] {
    if (!bundle?.entry) return []
    return bundle.entry.flatMap((entry) => (entry.resource ? [entry.resource] : []))
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
