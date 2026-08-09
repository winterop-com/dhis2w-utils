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

/** A reference to another resource, by relative or absolute URL. */
export interface Reference {
    reference?: string
    display?: string
    identifier?: Identifier
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
    valueCoding?: Coding
    valueReference?: Reference
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

/** A terminology resource, read only for what a listing needs to say about it. */
export interface CodeSystem {
    resourceType: 'CodeSystem'
    id?: string
    url?: string
    name?: string
    title?: string
    status: PublicationStatus
    count?: number
    valueSet?: string
    concept?: { code: string; display?: string }[]
}

/** A value set, read only for what a listing needs to say about it. */
export interface ValueSet {
    resourceType: 'ValueSet'
    id?: string
    url?: string
    name?: string
    title?: string
    status: PublicationStatus
    compose?: { include?: { system?: string }[] }
}

/** A concept map, read only for what a listing needs to say about it. */
export interface ConceptMap {
    resourceType: 'ConceptMap'
    id?: string
    url?: string
    name?: string
    title?: string
    status: PublicationStatus
    sourceCanonical?: string
    targetCanonical?: string
    group?: { element?: unknown[] }[]
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
