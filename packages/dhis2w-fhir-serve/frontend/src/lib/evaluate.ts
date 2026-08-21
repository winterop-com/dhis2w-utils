/**
 * What `POST /evaluate` takes and answers, and the worked examples the screen opens with.
 *
 * The Python side is `dhis2w_fhir_serve.routes.evaluate` and `dhis2w_fhir_serve.evaluation`, and the
 * interfaces here are its models field for field, in the wire's own spelling.
 *
 * WHY THE EXAMPLES LIVE HERE. An expression box that opens empty teaches nothing: a reader who does
 * not already know FHIRPath cannot type their first expression, and a reader who does still has to
 * invent a resource to run it against. So the screen opens with a worked example already loaded, and
 * the picker beside it holds the rest.
 *
 * TWO KINDS OF EXAMPLE, AND THE DIFFERENCE MATTERS. The generic ones carry their own data - a
 * Patient, a Bundle, an ELM document written out in full - so they run identically against every
 * served guide, including one that publishes nothing at all. The guide presets name resources this
 * particular server holds, so they can only be built once the server has said what it has; a guide
 * with no Questionnaires simply offers none. Neither kind ever opens a box the reader has to fill in
 * before the first click does something.
 */

/** Which of the three languages a source is written in. */
export type EvaluationLanguage = 'fhirpath' | 'cql' | 'elm'

/** Whether the source never parsed, or parsed and then refused to run. */
export type DiagnosticKind = 'parse' | 'evaluation'

/** One thing that stopped the run, at the position the parser stated one. */
export interface EvaluationDiagnostic {
    kind: DiagnosticKind
    /** What the engine said, verbatim - including the token set a parser named as expected. */
    message: string
    /** The line the parser stopped on, counted from one, or null for a refusal with no position. */
    line: number | null
    /** The column on that line, counted from one. The server converts ANTLR's zero-based one. */
    column: number | null
    /** The define this is about, for a name the library does not declare. */
    expression_name: string | null
}

/** What one expression or one define answered. `values` is always a collection. */
export interface EvaluationResultRow {
    name: string
    values: unknown[]
    /** Why this one define answered nothing, when the rest of the library still answered. */
    refusal: string | null
}

/** One evaluation, whole. Results and diagnostics are not exclusive. */
export interface EvaluationOutcome {
    language: EvaluationLanguage
    results: EvaluationResultRow[]
    diagnostics: EvaluationDiagnostic[]
    /** Every define the library declares, in declaration order. Empty for FHIRPath, which has none. */
    definitions: string[]
}

/**
 * Which resource an expression runs over.
 *
 * `none` is the fourth state the server has no name for, because on the wire it is the context being
 * absent - an expression over no resource at all, which is what a library doing arithmetic wants.
 */
export type EvaluationContextKind = 'none' | 'inline' | 'stored' | 'registered'

/** The context as the screen holds it: every field of every kind, with the picked kind saying which count. */
export interface EvaluationContextChoice {
    kind: EvaluationContextKind
    /** The resource as pasted JSON, for the `inline` kind. */
    resource: string
    /** The type and id of a resource this guide publishes, for the `stored` kind. */
    resourceType: string
    resourceId: string
    /** The DHIS2 tracked entity to read from the instance, for the `registered` kind. */
    trackedEntityUid: string
    /** The FHIR resource that entity is served as - `Patient` unless the guide's map says otherwise. */
    registerResource: string
}

/** The whole form, which is what an example loads and what a request is built from. */
export interface EvaluationForm {
    language: EvaluationLanguage
    source: string
    /** Which define to answer. Empty asks for every define the library declares. */
    expressionName: string
    context: EvaluationContextChoice
}

/** One worked example: what it is called, and the whole form it loads. */
export interface EvaluationExample {
    id: string
    label: string
    form: EvaluationForm
}

/** One resource this server was found to hold, which is what a guide preset is built around. */
export interface ServedResource {
    resourceType: string
    resourceId: string
    /** What the guide calls it, for the example's own label. Null when the resource states no title. */
    title: string | null
}

/** The empty context - no resource at all, which every field defaults to. */
export const NO_CONTEXT: EvaluationContextChoice = {
    kind: 'none',
    resource: '',
    resourceType: '',
    resourceId: '',
    trackedEntityUid: '',
    registerResource: 'Patient',
}

/** The generic Patient the FHIRPath examples run over - no DHIS2 in it, so it works on any guide. */
export const EXAMPLE_PATIENT = JSON.stringify(
    {
        resourceType: 'Patient',
        id: 'example',
        active: true,
        birthDate: '1815-12-10',
        name: [{ given: ['Ada', 'Byron'], family: 'Lovelace' }],
        telecom: [{ system: 'email', value: 'ada@example.org' }],
    },
    null,
    2,
)

/** The generic Bundle the retrieve examples read through - two resources, two types. */
export const EXAMPLE_BUNDLE = JSON.stringify(
    {
        resourceType: 'Bundle',
        type: 'collection',
        entry: [
            { resource: { resourceType: 'Patient', id: 'example', birthDate: '1815-12-10' } },
            {
                resource: {
                    resourceType: 'Condition',
                    id: 'c1',
                    subject: { reference: 'Patient/example' },
                },
            },
        ],
    },
    null,
    2,
)

/** A compiled library, written out as the JSON another CQL compiler would have emitted. */
export const EXAMPLE_ELM = JSON.stringify(
    {
        library: {
            identifier: { id: 'Example', version: '1.0' },
            statements: {
                def: [
                    {
                        name: 'Sum',
                        expression: {
                            type: 'Add',
                            operand: [
                                {
                                    type: 'Literal',
                                    valueType: '{urn:hl7-org:elm-types:r1}Integer',
                                    value: '1',
                                },
                                {
                                    type: 'Literal',
                                    valueType: '{urn:hl7-org:elm-types:r1}Integer',
                                    value: '2',
                                },
                            ],
                        },
                    },
                ],
            },
        },
    },
    null,
    2,
)

function inline(resource: string): EvaluationContextChoice {
    return { ...NO_CONTEXT, kind: 'inline', resource }
}

function stored(resourceType: string, resourceId: string): EvaluationContextChoice {
    return { ...NO_CONTEXT, kind: 'stored', resourceType, resourceId }
}

/**
 * The examples that run against any served guide, because they carry their own data.
 *
 * The first of each language is what the screen opens with, so it is the one that has to teach: a
 * short expression over a resource a reader can see in full, answering something obviously right.
 */
export function genericExamples(language: EvaluationLanguage): EvaluationExample[] {
    if (language === 'fhirpath') {
        return [
            {
                id: 'fhirpath-given-names',
                label: 'The given names on a Patient',
                form: {
                    language,
                    source: 'Patient.name.given',
                    expressionName: '',
                    context: inline(EXAMPLE_PATIENT),
                },
            },
            {
                id: 'fhirpath-born-before',
                label: 'Active, and born before 1900',
                form: {
                    language,
                    source: 'Patient.active and Patient.birthDate < @1900-01-01',
                    expressionName: '',
                    context: inline(EXAMPLE_PATIENT),
                },
            },
            {
                id: 'fhirpath-bundle-types',
                label: 'Every resource type in a Bundle',
                form: {
                    language,
                    source: 'Bundle.entry.resource.resourceType',
                    expressionName: '',
                    context: inline(EXAMPLE_BUNDLE),
                },
            },
        ]
    }
    if (language === 'cql') {
        return [
            {
                id: 'cql-retrieve-people',
                label: 'Everyone a Bundle holds',
                form: {
                    language,
                    source: [
                        "library Example version '1.0'",
                        "using FHIR version '4.0.1'",
                        '',
                        'define People: [Patient]',
                        'define HasCondition: exists [Condition]',
                    ].join('\n'),
                    expressionName: '',
                    context: inline(EXAMPLE_BUNDLE),
                },
            },
            {
                id: 'cql-arithmetic',
                label: 'Arithmetic, over no data at all',
                form: {
                    language,
                    source: [
                        "library Example version '1.0'",
                        '',
                        'define Sum: 1 + 2 * 3',
                        "define Greeting: 'hello'",
                    ].join('\n'),
                    expressionName: '',
                    context: { ...NO_CONTEXT },
                },
            },
        ]
    }
    return [
        {
            id: 'elm-sum',
            label: 'A compiled library that adds two numbers',
            form: {
                language,
                source: EXAMPLE_ELM,
                expressionName: '',
                context: { ...NO_CONTEXT },
            },
        },
    ]
}

/**
 * The examples built from what this particular server holds, one per resource it was found to have.
 *
 * ELM gets none, and that is not an omission: an ELM library is compiled JSON, and there is no short
 * one to write about a resource type this guide happens to publish. The generic one already shows
 * what the language is; the guide's own data is reached through FHIRPath and CQL.
 */
export function guidePresets(language: EvaluationLanguage, served: ServedResource[]): EvaluationExample[] {
    if (language === 'elm') return []
    return served.map((resource) => ({
        id: `guide-${language}-${resource.resourceType}-${resource.resourceId}`,
        label: presetLabel(language, resource),
        form: {
            language,
            source: presetSource(language, resource.resourceType),
            expressionName: '',
            context: stored(resource.resourceType, resource.resourceId),
        },
    }))
}

/** What a guide preset is called: what it asks, and which of this server's own resources it asks it of. */
export function presetLabel(language: EvaluationLanguage, resource: ServedResource): string {
    const named = resource.title ?? resource.resourceId
    return language === 'fhirpath'
        ? `${elementLabel(resource.resourceType)} ${named}`
        : `${named}, through a CQL retrieve`
}

/** The expression a guide preset loads for one resource type. */
export function presetSource(language: EvaluationLanguage, resourceType: string): string {
    if (language === 'cql') {
        return [
            "library Example version '1.0'",
            "using FHIR version '4.0.1'",
            '',
            `define Served: [${resourceType}]`,
        ].join('\n')
    }
    return `${resourceType}.${elementFor(resourceType)}`
}

/** The element a FHIRPath preset reads off one resource type - something every instance of it carries. */
export function elementFor(resourceType: string): string {
    if (resourceType === 'Questionnaire') return 'item.linkId'
    if (resourceType === 'CodeSystem') return 'concept.code'
    if (resourceType === 'ValueSet') return 'compose.include.system'
    if (resourceType === 'ConceptMap') return 'group.element.code'
    if (resourceType === 'Location' || resourceType === 'Organization') return 'name'
    return 'id'
}

/** That element said as words, for the label a reader picks from. */
export function elementLabel(resourceType: string): string {
    if (resourceType === 'Questionnaire') return 'Every question asked by'
    if (resourceType === 'CodeSystem') return 'Every code in'
    if (resourceType === 'ValueSet') return 'The systems composed by'
    if (resourceType === 'ConceptMap') return 'Every concept mapped by'
    if (resourceType === 'Location' || resourceType === 'Organization') return 'The name of'
    return 'The id of'
}

/**
 * The request body one filled-in form posts.
 *
 * The `inline` kind is the one that can fail before the network: what a reader pasted has to be a
 * JSON object, and saying so here is a better answer than a 400 from the server about a body it
 * could not read.
 */
export function evaluationRequest(form: EvaluationForm): Record<string, unknown> {
    const request: Record<string, unknown> = { language: form.language, source: form.source }
    if (form.expressionName.trim() !== '' && form.language !== 'fhirpath') {
        request.expression_name = form.expressionName.trim()
    }
    const context = evaluationContext(form.context)
    if (context !== null) request.context = context
    return request
}

/** The context element of the request, or null when the expression runs over no resource. */
export function evaluationContext(choice: EvaluationContextChoice): Record<string, unknown> | null {
    if (choice.kind === 'stored') {
        return { kind: 'stored', resource_type: choice.resourceType, resource_id: choice.resourceId }
    }
    if (choice.kind === 'registered') {
        return {
            kind: 'registered',
            resource_type: choice.registerResource,
            tracked_entity_uid: choice.trackedEntityUid,
        }
    }
    if (choice.kind === 'inline') {
        return { kind: 'inline', resource: JSON.parse(choice.resource) as unknown }
    }
    return null
}

/** Why a filled-in form cannot be sent yet, or null when it can. */
export function whyNotReady(form: EvaluationForm): string | null {
    if (form.source.trim() === '') return 'Write an expression, or pick an example.'
    const context = form.context
    if (context.kind === 'inline') {
        if (context.resource.trim() === '') return 'Paste the resource to evaluate over.'
        try {
            const parsed: unknown = JSON.parse(context.resource)
            if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
                return 'The context is one FHIR resource, which is a JSON object.'
            }
        } catch {
            return 'The pasted context is not valid JSON.'
        }
    }
    if (context.kind === 'stored' && (context.resourceType.trim() === '' || context.resourceId.trim() === '')) {
        return 'Name the resource type and the id of the resource to evaluate over.'
    }
    if (context.kind === 'registered' && context.trackedEntityUid.trim() === '') {
        return 'Name the tracked entity to evaluate over.'
    }
    return null
}

/** How a collection is rendered: as a table of values, as JSON, or as the statement that it is empty. */
export type ResultShape = 'empty' | 'table' | 'json'

/**
 * Which of the three a collection gets.
 *
 * A collection of primitives is a table, because that is what it is - a list of values with nothing
 * inside them. Anything with structure is JSON, because a table of resources is a table with one
 * unreadable cell per row.
 */
export function resultShape(values: unknown[]): ResultShape {
    if (values.length === 0) return 'empty'
    return values.every(isPrimitive) ? 'table' : 'json'
}

/** Whether one value is something a table cell can hold whole. */
export function isPrimitive(value: unknown): boolean {
    return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

/** One primitive as the text a table cell shows. */
export function cellText(value: unknown): string {
    if (value === null) return 'null'
    return typeof value === 'string' ? value : JSON.stringify(value)
}

/** How many things a collection holds, said the way a person reads it. */
export function matchSummary(count: number): string {
    if (count === 0) return 'No matches'
    return count === 1 ? '1 match' : `${String(count)} matches`
}

/** One diagnostic's headline: what went wrong, and where the parser said it went wrong. */
export function diagnosticHeadline(diagnostic: EvaluationDiagnostic): string {
    const kind = diagnostic.kind === 'parse' ? 'Parse error' : 'Evaluation refused'
    if (diagnostic.line === null) return kind
    if (diagnostic.column === null) return `${kind} at line ${String(diagnostic.line)}`
    return `${kind} at line ${String(diagnostic.line)}, column ${String(diagnostic.column)}`
}

/** The line of a source a diagnostic names, or null when it names none this source has. */
export function sourceLine(source: string, line: number | null): string | null {
    if (line === null || line < 1) return null
    const lines = source.split('\n')
    return line > lines.length ? null : lines[line - 1]
}

/** The caret that points at the column a diagnostic named, as the text under that line. */
export function caretUnder(line: string, column: number | null): string {
    if (column === null || column < 1) return ''
    // A tab in the source is one character but many columns wide, so it is carried into the marker:
    // a run of spaces under a tab would put the caret somewhere the reader is not looking.
    const before = line.slice(0, column - 1).replace(/[^\t]/g, ' ')
    return `${before}^`
}
