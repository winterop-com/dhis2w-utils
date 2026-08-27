/**
 * What `POST /facade/evaluate` takes and answers, and the worked examples the screen opens with.
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

/**
 * One worked example: what it is called, which shelf it sits on, and the whole form it loads.
 *
 * `label` is what the example ANSWERS rather than what it demonstrates - "The email address on the
 * record", not "the where() function" - because a reader picking from a list of two dozen is looking
 * for a question like theirs, not for a feature name. `group` is the shelf, and it is what turns two
 * dozen into something a person reads: retrieves together, intervals together, refusals together.
 */
export interface EvaluationExample {
    id: string
    label: string
    /** The heading this example sits under in the picker and in the reference panel. */
    group: string
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

/**
 * A larger Bundle, for the examples that need something to count, filter, and compare.
 *
 * Three people, four Observations with values on them, two Conditions and an Immunization - enough
 * that a `where` clause leaves some rows behind and an aggregate answers a number nobody could have
 * guessed from one record. Still generic: no DHIS2 in it, so every example built on it runs against
 * any served guide, including one that publishes nothing at all.
 */
export const EXAMPLE_CLINICAL_BUNDLE = JSON.stringify(
    {
        resourceType: 'Bundle',
        type: 'collection',
        entry: [
            {
                resource: {
                    resourceType: 'Patient',
                    id: 'p1',
                    active: true,
                    gender: 'female',
                    birthDate: '1990-04-11',
                    name: [{ given: ['Amara'], family: 'Okonkwo' }],
                },
            },
            {
                resource: {
                    resourceType: 'Patient',
                    id: 'p2',
                    active: true,
                    gender: 'male',
                    birthDate: '2019-09-02',
                    name: [{ given: ['Tomas'], family: 'Bergstrom' }],
                },
            },
            {
                resource: {
                    resourceType: 'Patient',
                    id: 'p3',
                    active: false,
                    gender: 'female',
                    birthDate: '1954-01-30',
                    name: [{ given: ['Ingrid'], family: 'Halvorsen' }],
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'o1',
                    status: 'final',
                    subject: { reference: 'Patient/p1' },
                    effectiveDateTime: '2024-03-04T09:00:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 61.5, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'o2',
                    status: 'final',
                    subject: { reference: 'Patient/p2' },
                    effectiveDateTime: '2024-03-11T09:00:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 14.2, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'o3',
                    status: 'final',
                    subject: { reference: 'Patient/p3' },
                    effectiveDateTime: '2024-07-19T09:00:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 70.0, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'o4',
                    status: 'preliminary',
                    subject: { reference: 'Patient/p1' },
                    effectiveDateTime: '2024-09-30T09:00:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '8310-5', display: 'Body temperature' }] },
                    valueQuantity: { value: 38.4, unit: 'Cel' },
                },
            },
            {
                resource: {
                    resourceType: 'Condition',
                    id: 'c1',
                    subject: { reference: 'Patient/p1' },
                    recordedDate: '2024-03-04',
                    code: { coding: [{ system: 'http://snomed.info/sct', code: '386661006', display: 'Fever' }] },
                },
            },
            {
                resource: {
                    resourceType: 'Condition',
                    id: 'c2',
                    subject: { reference: 'Patient/p3' },
                    recordedDate: '2023-11-20',
                    code: { coding: [{ system: 'http://snomed.info/sct', code: '73211009', display: 'Diabetes' }] },
                },
            },
            {
                resource: {
                    resourceType: 'Immunization',
                    id: 'i1',
                    status: 'completed',
                    patient: { reference: 'Patient/p2' },
                    occurrenceDateTime: '2020-06-15',
                    vaccineCode: {
                        coding: [{ system: 'http://snomed.info/sct', code: '396429000', display: 'Measles vaccine' }],
                    },
                },
            },
        ],
    },
    null,
    2,
)

/**
 * A household and the records one clinic holds about it, for the examples that ask a realistic Bundle.
 *
 * WHY A SECOND BUNDLE, AND A LARGER ONE. The clinical Bundle above is built so that a filter leaves
 * rows behind; this one is built so that a QUESTION has an answer. A mother and her child, thirteen
 * entries between them: two identifiers on the mother, her name in Latin script and in the script her
 * family writes it in, six Observations across three codes with dates spread over a year, three doses
 * of one vaccine numbered in the order they were given, the Condition the anaemia reading led to, and
 * the visit all of it was recorded at. Latest-by-date, values above a threshold, doses counted,
 * everyone named - each of those is a question somebody asks of real data, and none of them can be
 * asked of a single Patient.
 *
 * Still generic: no DHIS2 in it, so every example built on it runs against any served guide, including
 * one that publishes nothing at all.
 */
export const EXAMPLE_HOUSEHOLD_BUNDLE = JSON.stringify(
    {
        resourceType: 'Bundle',
        type: 'collection',
        entry: [
            {
                resource: {
                    resourceType: 'Patient',
                    id: 'selam',
                    active: true,
                    gender: 'female',
                    birthDate: '1991-07-14',
                    identifier: [
                        { system: 'http://example.org/national-id', value: 'NID-4471-2290' },
                        { system: 'http://example.org/medical-record', value: 'MRN-00714' },
                    ],
                    name: [
                        { use: 'official', given: ['Selam'], family: 'Tadesse' },
                        { use: 'usual', given: ['ሰላም'], family: 'ታደሰ' },
                    ],
                    telecom: [{ system: 'phone', value: '+251911234567' }],
                    address: [{ city: 'Hawassa', country: 'ET' }],
                },
            },
            {
                resource: {
                    resourceType: 'Patient',
                    id: 'dawit',
                    active: true,
                    gender: 'male',
                    birthDate: '2023-02-08',
                    identifier: [{ system: 'http://example.org/medical-record', value: 'MRN-00902' }],
                    name: [
                        { use: 'official', given: ['Dawit'], family: 'Tadesse' },
                        { use: 'usual', given: ['ዳዊት'], family: 'ታደሰ' },
                    ],
                },
            },
            {
                resource: {
                    resourceType: 'Encounter',
                    id: 'visit-may',
                    status: 'finished',
                    class: { system: 'http://terminology.hl7.org/CodeSystem/v3-ActCode', code: 'AMB', display: 'ambulatory' },
                    subject: { reference: 'Patient/selam' },
                    period: { start: '2024-05-06T08:30:00Z', end: '2024-05-06T09:15:00Z' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'weight-jan',
                    status: 'final',
                    subject: { reference: 'Patient/selam' },
                    effectiveDateTime: '2024-01-15T09:05:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 58.2, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'weight-may',
                    status: 'final',
                    subject: { reference: 'Patient/selam' },
                    encounter: { reference: 'Encounter/visit-may' },
                    effectiveDateTime: '2024-05-06T08:40:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 61.0, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'weight-sep',
                    status: 'final',
                    subject: { reference: 'Patient/selam' },
                    effectiveDateTime: '2024-09-23T10:10:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 63.4, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'weight-dawit',
                    status: 'final',
                    subject: { reference: 'Patient/dawit' },
                    effectiveDateTime: '2024-06-02T11:00:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '29463-7', display: 'Body weight' }] },
                    valueQuantity: { value: 9.8, unit: 'kg' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'temperature-may',
                    status: 'final',
                    subject: { reference: 'Patient/selam' },
                    encounter: { reference: 'Encounter/visit-may' },
                    effectiveDateTime: '2024-05-06T08:45:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '8310-5', display: 'Body temperature' }] },
                    valueQuantity: { value: 38.6, unit: 'Cel' },
                },
            },
            {
                resource: {
                    resourceType: 'Observation',
                    id: 'haemoglobin-may',
                    status: 'final',
                    subject: { reference: 'Patient/selam' },
                    encounter: { reference: 'Encounter/visit-may' },
                    effectiveDateTime: '2024-05-06T09:00:00Z',
                    code: { coding: [{ system: 'http://loinc.org', code: '718-7', display: 'Haemoglobin' }] },
                    valueQuantity: { value: 10.4, unit: 'g/dL' },
                },
            },
            {
                resource: {
                    resourceType: 'Condition',
                    id: 'anaemia',
                    subject: { reference: 'Patient/selam' },
                    encounter: { reference: 'Encounter/visit-may' },
                    recordedDate: '2024-05-06',
                    onsetDateTime: '2024-05-06',
                    clinicalStatus: {
                        coding: [
                            {
                                system: 'http://terminology.hl7.org/CodeSystem/condition-clinical',
                                code: 'active',
                            },
                        ],
                    },
                    code: { coding: [{ system: 'http://snomed.info/sct', code: '271737000', display: 'Anaemia' }] },
                },
            },
            {
                resource: {
                    resourceType: 'Immunization',
                    id: 'penta-1',
                    status: 'completed',
                    patient: { reference: 'Patient/dawit' },
                    occurrenceDateTime: '2023-03-22',
                    vaccineCode: {
                        coding: [{ system: 'http://hl7.org/fhir/sid/cvx', code: '110', display: 'DTaP-hepatitis B-IPV' }],
                    },
                    protocolApplied: [{ series: 'Pentavalent', doseNumberPositiveInt: 1 }],
                },
            },
            {
                resource: {
                    resourceType: 'Immunization',
                    id: 'penta-2',
                    status: 'completed',
                    patient: { reference: 'Patient/dawit' },
                    occurrenceDateTime: '2023-04-19',
                    vaccineCode: {
                        coding: [{ system: 'http://hl7.org/fhir/sid/cvx', code: '110', display: 'DTaP-hepatitis B-IPV' }],
                    },
                    protocolApplied: [{ series: 'Pentavalent', doseNumberPositiveInt: 2 }],
                },
            },
            {
                resource: {
                    resourceType: 'Immunization',
                    id: 'penta-3',
                    status: 'completed',
                    patient: { reference: 'Patient/dawit' },
                    occurrenceDateTime: '2023-05-17',
                    vaccineCode: {
                        coding: [{ system: 'http://hl7.org/fhir/sid/cvx', code: '110', display: 'DTaP-hepatitis B-IPV' }],
                    },
                    protocolApplied: [{ series: 'Pentavalent', doseNumberPositiveInt: 3 }],
                },
            },
        ],
    },
    null,
    2,
)

/**
 * One filled-in capture form, for the examples about what a submission actually says.
 *
 * The shape this facade receives all day: a QuestionnaireResponse with answers on it, some of them
 * inside a group. Reading one with FHIRPath is the nearest thing this screen has to a DHIS2 question,
 * and it needs no instance behind it - the document carries everything the expression touches.
 */
export const EXAMPLE_RESPONSE = JSON.stringify(
    {
        resourceType: 'QuestionnaireResponse',
        id: 'example',
        status: 'completed',
        authored: '2024-05-06T11:20:00Z',
        questionnaire: 'Questionnaire/anc-visit',
        item: [
            { linkId: 'weight', text: 'Weight in kilograms', answer: [{ valueDecimal: 61.5 }] },
            { linkId: 'fever', text: 'Fever reported', answer: [{ valueBoolean: true }] },
            { linkId: 'visit-date', text: 'Date of visit', answer: [{ valueDate: '2024-05-06' }] },
            {
                linkId: 'household',
                text: 'Household',
                item: [
                    { linkId: 'people', text: 'People in the household', answer: [{ valueInteger: 5 }] },
                    { linkId: 'water', text: 'Improved water source', answer: [{ valueBoolean: false }] },
                ],
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

/** One example before it is a form: the fields that differ, with the rest filled in below. */
interface ExampleSeed {
    id: string
    label: string
    group: string
    source: string
    context: EvaluationContextChoice
}

/** A CQL library written as a block, with the leading indentation of this file taken back off. */
function cql(source: string): string {
    return source
        .split('\n')
        .map((line) => line.replace(/^ {8}/, ''))
        .join('\n')
        .trim()
}

/** One ELM library, written out as the JSON another CQL compiler would have emitted. */
function elm(name: string, definitions: { name: string; expression: unknown }[]): string {
    return JSON.stringify(
        {
            library: {
                identifier: { id: name, version: '1.0' },
                statements: { def: definitions.map((definition) => ({ ...definition, context: 'Unfiltered' })) },
            },
        },
        null,
        2,
    )
}

/** One ELM integer, in the spelling ELM writes every literal in - a type name and a string. */
function elmInteger(value: number): unknown {
    return { type: 'Literal', valueType: '{urn:hl7-org:elm-types:r1}Integer', value: String(value) }
}

/** One ELM string. */
function elmString(value: string): unknown {
    return { type: 'Literal', valueType: '{urn:hl7-org:elm-types:r1}String', value }
}

/** One ELM boolean. */
function elmBoolean(value: boolean): unknown {
    return { type: 'Literal', valueType: '{urn:hl7-org:elm-types:r1}Boolean', value: String(value) }
}

/** One ELM `Retrieve`, which is what a CQL retrieve compiles to - a type named as a FHIR url. */
function elmRetrieve(resourceType: string): unknown {
    return { type: 'Retrieve', dataType: `{http://hl7.org/fhir}${resourceType}` }
}

/**
 * One ELM `If` node, with its two branches under the names ELM gives them.
 *
 * Built through a record rather than an object literal because `then` as a literal key makes an
 * object a lint tool reads as a promise. It is not one: it is a document, and ELM's element is
 * called `then`, so the name is kept and the construction is moved here once.
 */
function elmConditional(condition: unknown, whenTrue: unknown, whenFalse: unknown): unknown {
    // `then` is ELM's own element name for the branch taken, and this object is a document being
    // written rather than anything that will be awaited. The rule exists to stop an accidental
    // thenable; here the name is the format's, so it is kept and the rule is answered once.
    // oxlint-disable-next-line unicorn/no-thenable
    return { type: 'If', condition, then: whenTrue, else: whenFalse }
}

/**
 * Every FHIRPath example, on five shelves.
 *
 * The first is what the screen opens with, so it is the one that has to teach: a short expression
 * over a resource a reader can see in full, answering something obviously right. Everything after it
 * is arranged by the question it answers rather than by the feature it happens to use.
 */
const FHIRPATH_SEEDS: ExampleSeed[] = [
    // Reading one record: the path is the whole expression, and the answer is a collection.
    {
        id: 'fhirpath-given-names',
        label: 'The given names on a Patient',
        group: 'Reading one record',
        source: 'Patient.name.given',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-family-name',
        label: 'The family name',
        group: 'Reading one record',
        source: 'Patient.name.family',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-active',
        label: 'Whether the record is active',
        group: 'Reading one record',
        source: 'Patient.active',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-birth-date',
        label: 'The birth date, and whether the record states one',
        group: 'Reading one record',
        source: 'Patient.birthDate.exists()',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-telecom-email',
        label: 'The email address, out of every way of reaching the person',
        group: 'Reading one record',
        source: "Patient.telecom.where(system = 'email').value",
        context: inline(EXAMPLE_PATIENT),
    },

    // Counting and picking: what turns a collection into one value.
    {
        id: 'fhirpath-count-given',
        label: 'How many given names the record carries',
        group: 'Counting and picking',
        source: 'Patient.name.given.count()',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-first-given',
        label: 'The first given name alone',
        group: 'Counting and picking',
        source: 'Patient.name.given.first()',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-last-given',
        label: 'The last given name alone',
        group: 'Counting and picking',
        source: 'Patient.name.given.last()',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-distinct-types',
        label: 'Each resource type in a Bundle, named once',
        group: 'Counting and picking',
        source: 'Bundle.entry.resource.resourceType.distinct()',
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },

    // Text and dates: the two kinds of value a DHIS2 attribute usually holds.
    {
        id: 'fhirpath-upper-family',
        label: 'The family name in capitals',
        group: 'Text and dates',
        source: 'Patient.name.family.upper()',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-full-name',
        label: 'The whole name as one string',
        group: 'Text and dates',
        source: "Patient.name.select(given.join(' ') & ' ' & family)",
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-birth-year',
        label: 'The year of birth alone',
        group: 'Text and dates',
        source: 'Patient.birthDate.year()',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-family-prefix',
        label: 'The first few letters of the family name',
        group: 'Text and dates',
        source: 'Patient.name.family.substring(0, 4)',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-born-before',
        label: 'Active, and born before 1900',
        group: 'Text and dates',
        source: 'Patient.active and Patient.birthDate < @1900-01-01',
        context: inline(EXAMPLE_PATIENT),
    },
    {
        id: 'fhirpath-name-starts',
        label: 'Whether the family name starts with a given letter',
        group: 'Text and dates',
        source: "Patient.name.family.startsWith('Love')",
        context: inline(EXAMPLE_PATIENT),
    },

    // Reading a Bundle: several resources at once, which is what a search answers with.
    {
        id: 'fhirpath-bundle-types',
        label: 'Every resource type in a Bundle',
        group: 'Reading a Bundle',
        source: 'Bundle.entry.resource.resourceType',
        context: inline(EXAMPLE_BUNDLE),
    },
    {
        id: 'fhirpath-bundle-observations',
        label: 'Only the Observations, and what each one measured',
        group: 'Reading a Bundle',
        source: 'Bundle.entry.resource.ofType(Observation).code.coding.display',
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'fhirpath-bundle-final',
        label: 'The final Observations, not the preliminary ones',
        group: 'Reading a Bundle',
        source: "Bundle.entry.resource.ofType(Observation).where(status = 'final').id",
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'fhirpath-bundle-weights',
        label: 'Every weight the Bundle records',
        group: 'Reading a Bundle',
        source: "Bundle.entry.resource.ofType(Observation).where(code.coding.code = '29463-7').valueQuantity.value",
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'fhirpath-bundle-active-people',
        label: 'The people the Bundle holds who are still active',
        group: 'Reading a Bundle',
        source: 'Bundle.entry.resource.ofType(Patient).where(active = true).name.family',
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'fhirpath-bundle-subjects',
        label: 'Who each Condition is about',
        group: 'Reading a Bundle',
        source: 'Bundle.entry.resource.ofType(Condition).subject.reference',
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },

    // Ask a Bundle: the questions a person asks of a register rather than of a record.
    {
        id: 'fhirpath-household-observations',
        label: 'Every Observation the household Bundle holds, as it stands',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Observation)',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-count',
        label: 'How many Observations were recorded in all',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Observation).count()',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-codes',
        label: 'Each thing that was measured, named once',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Observation).code.coding.display.distinct()',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-weights',
        label: 'Every weight recorded, whoever it was measured on',
        group: 'Ask a Bundle',
        source: "Bundle.entry.resource.ofType(Observation).where(code.coding.code = '29463-7').valueQuantity.value",
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-above-threshold',
        label: 'The weights above sixty kilograms',
        group: 'Ask a Bundle',
        source: "Bundle.entry.resource.ofType(Observation).where(code.coding.code = '29463-7' and valueQuantity.value > 60).valueQuantity.value",
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-latest-weight',
        label: 'The most recent weight, by the date it was taken',
        group: 'Ask a Bundle',
        source: "Bundle.entry.resource.ofType(Observation).where(code.coding.code = '29463-7').sort(-effectiveDateTime).first().valueQuantity.value",
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-names',
        label: 'Everyone the Bundle holds, by name',
        group: 'Ask a Bundle',
        source: "Bundle.entry.resource.ofType(Patient).name.where(use = 'official').select(given.join(' ') & ' ' & family)",
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-native-script',
        label: 'The same names, in the script the family writes them in',
        group: 'Ask a Bundle',
        source: "Bundle.entry.resource.ofType(Patient).name.where(use = 'usual').select(given.join(' ') & ' ' & family)",
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-identifiers',
        label: 'Every identifier the Bundle holds for a person',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Patient).identifier.value',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-doses',
        label: 'Which doses of the vaccine were given, in order',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Immunization).protocolApplied.doseNumberPositiveInt',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-visit-day',
        label: 'What was measured on the day of the visit',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Observation).where(effectiveDateTime.toDate() = @2024-05-06).code.coding.display',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'fhirpath-household-conditions',
        label: 'Who the Bundle records a Condition about',
        group: 'Ask a Bundle',
        source: 'Bundle.entry.resource.ofType(Condition).subject.reference',
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },

    // A filled-in form: the document this facade actually receives.
    {
        id: 'fhirpath-response-answers',
        label: 'Every question a submission answered',
        group: 'A filled-in form',
        source: 'QuestionnaireResponse.descendants().linkId',
        context: inline(EXAMPLE_RESPONSE),
    },
    {
        id: 'fhirpath-response-one-answer',
        label: 'What one question was answered with',
        group: 'A filled-in form',
        source: "QuestionnaireResponse.item.where(linkId = 'weight').answer.valueDecimal",
        context: inline(EXAMPLE_RESPONSE),
    },
    {
        id: 'fhirpath-response-nested',
        label: 'An answer inside a group of questions',
        group: 'A filled-in form',
        source: "QuestionnaireResponse.descendants().where(linkId = 'people').answer.valueInteger",
        context: inline(EXAMPLE_RESPONSE),
    },
    {
        id: 'fhirpath-response-unanswered',
        label: 'The questions that carry no answer at all',
        group: 'A filled-in form',
        source: 'QuestionnaireResponse.descendants().where(answer.empty()).linkId',
        context: inline(EXAMPLE_RESPONSE),
    },
    {
        id: 'fhirpath-response-completed',
        label: 'Whether the submission was completed rather than left in progress',
        group: 'A filled-in form',
        source: "QuestionnaireResponse.status = 'completed'",
        context: inline(EXAMPLE_RESPONSE),
    },

    // Arithmetic: an expression with no resource under it at all.
    {
        id: 'fhirpath-arithmetic',
        label: 'Arithmetic, over no resource at all',
        group: 'Arithmetic, over nothing',
        source: '(2 + 3) * 4',
        context: { ...NO_CONTEXT },
    },
    {
        id: 'fhirpath-string-join',
        label: 'Three strings joined into one',
        group: 'Arithmetic, over nothing',
        source: "('one' | 'two' | 'three').join(', ')",
        context: { ...NO_CONTEXT },
    },
    {
        id: 'fhirpath-today',
        label: 'Today, as the server reads its own clock',
        group: 'Arithmetic, over nothing',
        source: 'today()',
        context: { ...NO_CONTEXT },
    },
]

/**
 * Every CQL example, on five shelves.
 *
 * The refusals are a shelf of their own and are examples on purpose: an unresolved valueset is the
 * mistake this engine is loudest about, and meeting it once here - with the whole refusal on screen -
 * is cheaper than meeting it for the first time in a measure nobody can explain.
 */
const CQL_SEEDS: ExampleSeed[] = [
    // The library itself: what the header lines are for.
    {
        id: 'cql-retrieve-people',
        label: 'Everyone a Bundle holds',
        group: 'The library, line by line',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define People: [Patient]
        define HasCondition: exists [Condition]
        `),
        context: inline(EXAMPLE_BUNDLE),
    },
    {
        id: 'cql-arithmetic',
        label: 'Arithmetic, over no data at all',
        group: 'The library, line by line',
        source: cql(`
        library Example version '1.0'

        define Sum: 1 + 2 * 3
        define Greeting: 'hello'
        `),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'cql-define-reads-define',
        label: 'One define reading another',
        group: 'The library, line by line',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define People: [Patient]
        define HowMany: Count(People)
        define AnyAtAll: HowMany > 0
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-parameter',
        label: 'A parameter with a default the library states itself',
        group: 'The library, line by line',
        source: cql(`
        library Example version '1.0'

        parameter Threshold Integer default 20

        define Threshold20: Threshold
        define Over: 25 > Threshold
        `),
        context: { ...NO_CONTEXT },
    },

    // Retrieves: how a library reaches data.
    {
        id: 'cql-retrieve-observations',
        label: 'Every Observation the Bundle holds',
        group: 'Retrieves',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Measurements: [Observation]
        define HowMany: Count([Observation])
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-retrieve-exists',
        label: 'Whether the Bundle holds an Immunization at all',
        group: 'Retrieves',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Vaccinated: exists [Immunization]
        define NoProcedures: not exists [Procedure]
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-retrieve-empty',
        label: 'A retrieve for a type the data holds none of',
        group: 'Retrieves',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Encounters: [Encounter]
        define HowMany: Count([Encounter])
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },

    // Queries: the clauses that narrow a retrieve.
    {
        id: 'cql-query-where',
        label: 'The people born before a given date',
        group: 'Queries',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        // A FHIR date arrives as text, so it is converted before it is compared.
        define Older:
          [Patient] P
            where ToDate(P.birthDate) < @1980-01-01
            return P.id
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-query-sort',
        label: 'Every weight recorded, largest first',
        group: 'Queries',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Weights:
          [Observation] O
            where O.code.coding[0].code = '29463-7'
            return O.value.value
            sort descending
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-query-return-all',
        label: 'A return that keeps its duplicates, because it said all',
        group: 'Queries',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Statuses: [Observation] O return all O.status
        define Deduplicated: [Observation] O return O.status
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },

    // Lists, intervals, and the temporal vocabulary.
    {
        id: 'cql-list-aggregate',
        label: 'A list added up, and its largest member',
        group: 'Lists and intervals',
        source: cql(`
        library Example version '1.0'

        define Total: Sum({ 1, 2, 3, 4 })
        define Biggest: Max({ 4, 9, 2 })
        define HowMany: Count({ 4, 9, 2 })
        `),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'cql-interval-membership',
        label: 'Whether a date falls inside a period',
        group: 'Lists and intervals',
        source: cql(`
        library Example version '1.0'

        define Year2024: Interval[@2024-01-01, @2024-12-31]
        define Midsummer: @2024-06-21 during Year2024
        define NewYearsEve2023: @2023-12-31 during Year2024
        `),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'cql-interval-boundaries',
        label: 'Where a period begins, where it ends, and how wide it is',
        group: 'Lists and intervals',
        source: cql(`
        library Example version '1.0'

        define Quarter: Interval[@2024-01-01, @2024-03-31]
        define Opens: start of Quarter
        define Closes: end of Quarter
        define Days: duration in days between start of Quarter and end of Quarter
        `),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'cql-interval-observations',
        label: 'The Conditions recorded inside one period',
        group: 'Lists and intervals',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Year2024: Interval[@2024-01-01, @2024-12-31]

        define Recent:
          [Condition] C
            where ToDate(C.recordedDate) during Year2024
            return C.id
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },

    // A population in a Bundle: the shape a measure is actually written in.
    {
        id: 'cql-household-people',
        label: 'Everyone the household Bundle holds, and how many',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        define People: [Patient]
        define HowMany: Count([Patient])
        define Names: [Patient] P return P.name[0].given[0]
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'cql-household-one-person',
        label: 'One person, and the readings that are hers',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        define Mother: singleton from ([Patient] P where P.id = 'selam')
        define HerWeights:
          [Observation] O
            where O.subject.reference = 'Patient/selam'
              and O.code.coding[0].code = '29463-7'
            return O.value.value
        define HowManyReadings: Count(HerWeights)
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'cql-household-born-after',
        label: 'The children, from a birth date compared without a conversion',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        // A FHIR birthDate arrives as text and is read as a date where a date is expected,
        // so the comparison is written the way it would be said.
        define Children: [Patient] P where P.birthDate > @2020-01-01
        define ChildNames: Children C return C.name[0].given[0]
        define HowManyChildren: Count(Children)
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'cql-household-date-window',
        label: 'The readings taken inside one period',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        define SecondQuarter: Interval[@2024-04-01T00:00:00, @2024-06-30T23:59:59]

        define InTheQuarter:
          [Observation] O
            where O.effective in SecondQuarter
            return O.id
        define HowMany: Count(InTheQuarter)
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'cql-household-doses',
        label: 'How many doses of the vaccine the child received',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        define Doses: [Immunization] I return all I.protocolApplied[0].doseNumberPositiveInt
        define HowManyDoses: Count([Immunization])
        define WholeSeries: Count([Immunization]) >= 3
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'cql-household-exists',
        label: 'Whether anyone ran a fever, and the first visit on record',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        define Febrile:
          exists ([Observation] O
            where O.code.coding[0].code = '8310-5'
              and O.value.value > 38.0)

        define FirstVisit: First([Encounter] E return E.period.start)
        define NoProcedures: not exists [Procedure]
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'cql-household-highest-weight',
        label: 'The largest weight recorded, out of everyone',
        group: 'A population in a Bundle',
        source: cql(`
        library Household version '1.0'
        using FHIR version '4.0.1'

        define Weights:
          [Observation] O
            where O.code.coding[0].code = '29463-7'
            return all O.value.value

        define Heaviest: Max(Weights)
        define Average: Avg(Weights)
        `),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },

    // Terminology, and the two ways it is refused.
    {
        id: 'cql-terminology-declared',
        label: 'A codesystem and a code the library declares',
        group: 'Terminology, and what it refuses',
        source: cql(`
        library Example version '1.0'

        codesystem "SNOMED": 'http://snomed.info/sct'
        code "Fever": '386661006' from "SNOMED" display 'Fever'

        define TheCode: "Fever"
        `),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'cql-terminology-undeclared',
        label: 'A retrieve naming terminology the library never declared, refused',
        group: 'Terminology, and what it refuses',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define MeaslesCases: [Condition: "Measles Codes"]
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-terminology-unexpanded',
        label: 'A valueset the data holds no expansion for, refused',
        group: 'Terminology, and what it refuses',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        valueset "Fevers": 'http://example.org/ValueSet/fevers'

        define Febrile: [Condition: "Fevers"]
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
    {
        id: 'cql-string-in-terminology',
        label: 'A bare string where a terminology reference belongs, refused',
        group: 'Terminology, and what it refuses',
        source: cql(`
        library Example version '1.0'
        using FHIR version '4.0.1'

        define Fevers: [Condition: '386661006']
        `),
        context: inline(EXAMPLE_CLINICAL_BUNDLE),
    },
]

/**
 * Every ELM example.
 *
 * ELM is not a language anybody writes by hand, and these do not pretend otherwise: what they teach
 * is the SHAPE a compiled library arrives in, so a reader posting the output of another compiler
 * knows what this endpoint is reading. Each is small enough to see whole - one library, one or two
 * statements, one expression tree - and each answers a value that could not have come from anywhere
 * else.
 */
const ELM_SEEDS: ExampleSeed[] = [
    {
        id: 'elm-sum',
        label: 'A compiled library that adds two numbers',
        group: 'The shape of a compiled library',
        source: EXAMPLE_ELM,
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-two-statements',
        label: 'Two statements in one library',
        group: 'The shape of a compiled library',
        source: elm('Example', [
            { name: 'Answer', expression: elmInteger(42) },
            { name: 'Greeting', expression: elmString('hello') },
        ]),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-comparison',
        label: 'A comparison, which answers a boolean',
        group: 'The shape of a compiled library',
        source: elm('Example', [
            { name: 'Greater', expression: { type: 'Greater', operand: [elmInteger(7), elmInteger(3)] } },
            { name: 'Stated', expression: elmBoolean(true) },
        ]),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-conditional',
        label: 'A conditional, with only the taken branch evaluated',
        group: 'Expressions, one node at a time',
        source: elm('Example', [
            {
                name: 'Verdict',
                expression: elmConditional(
                    { type: 'Greater', operand: [elmInteger(5), elmInteger(2)] },
                    elmString('larger'),
                    elmString('smaller'),
                ),
            },
        ]),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-list-count',
        label: 'A list, and the count of what is in it',
        group: 'Expressions, one node at a time',
        source: elm('Example', [
            {
                name: 'Numbers',
                expression: { type: 'List', element: [elmInteger(3), elmInteger(1), elmInteger(4)] },
            },
            {
                name: 'HowMany',
                expression: {
                    type: 'Count',
                    source: { type: 'List', element: [elmInteger(3), elmInteger(1), elmInteger(4)] },
                },
            },
        ]),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-nested-arithmetic',
        label: 'Arithmetic nested two levels deep',
        group: 'Expressions, one node at a time',
        source: elm('Example', [
            {
                name: 'Total',
                expression: {
                    type: 'Multiply',
                    operand: [
                        { type: 'Add', operand: [elmInteger(2), elmInteger(3)] },
                        elmInteger(4),
                    ],
                },
            },
        ]),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-string-concatenate',
        label: 'Two strings concatenated',
        group: 'Expressions, one node at a time',
        source: elm('Example', [
            {
                name: 'Line',
                expression: {
                    type: 'Concatenate',
                    operand: [elmString('Ward '), elmString('B')],
                },
            },
        ]),
        context: { ...NO_CONTEXT },
    },
    {
        id: 'elm-household-counts',
        label: 'A compiled library counting what a Bundle holds',
        group: 'A compiled library over a Bundle',
        source: elm('Household', [
            { name: 'HowManyPeople', expression: { type: 'Count', source: elmRetrieve('Patient') } },
            { name: 'HowManyDoses', expression: { type: 'Count', source: elmRetrieve('Immunization') } },
            { name: 'AnyObservations', expression: { type: 'Exists', operand: elmRetrieve('Observation') } },
        ]),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'elm-household-query',
        label: 'A compiled query, reading one element off everyone',
        group: 'A compiled library over a Bundle',
        source: elm('Household', [
            {
                name: 'BirthDates',
                expression: {
                    type: 'Query',
                    source: [{ alias: 'P', expression: elmRetrieve('Patient') }],
                    return: {
                        expression: { type: 'Property', path: 'birthDate', source: { type: 'AliasRef', name: 'P' } },
                        distinct: true,
                    },
                },
            },
        ]),
        context: inline(EXAMPLE_HOUSEHOLD_BUNDLE),
    },
    {
        id: 'elm-no-identifier',
        label: 'A library carrying no identifier, refused',
        group: 'What a library has to carry',
        source: JSON.stringify({ library: { statements: { def: [{ name: 'Answer' }] } } }, null, 2),
        context: { ...NO_CONTEXT },
    },
]

/** The seeds of one language, in the order the picker offers them. */
function seedsFor(language: EvaluationLanguage): ExampleSeed[] {
    if (language === 'fhirpath') return FHIRPATH_SEEDS
    return language === 'cql' ? CQL_SEEDS : ELM_SEEDS
}

/**
 * The examples that run against any served guide, because they carry their own data.
 *
 * The first of each language is what the screen opens with, so it is the one that has to teach: a
 * short expression over a resource a reader can see in full, answering something obviously right.
 * Everything after it is on a shelf named for the kind of question it answers, because a flat list of
 * two dozen is a list nobody reads to the bottom of.
 */
export function genericExamples(language: EvaluationLanguage): EvaluationExample[] {
    return seedsFor(language).map((seed) => ({
        id: seed.id,
        label: seed.label,
        group: seed.group,
        form: { language, source: seed.source, expressionName: '', context: seed.context },
    }))
}

/** The shelves one language's examples sit on, in the order they were declared. */
export function exampleGroups(examples: readonly EvaluationExample[]): { group: string; examples: EvaluationExample[] }[] {
    const shelves: { group: string; examples: EvaluationExample[] }[] = []
    for (const example of examples) {
        const shelf = shelves.find((candidate) => candidate.group === example.group)
        if (shelf === undefined) shelves.push({ group: example.group, examples: [example] })
        else shelf.examples.push(example)
    }
    return shelves
}

/** What the picker calls the shelf built from resources this particular server was found to hold. */
export const GUIDE_PRESET_GROUP = "This guide's own resources"

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
        group: GUIDE_PRESET_GROUP,
        form: {
            language,
            source: presetSource(language, resource.resourceType),
            expressionName: '',
            context: stored(resource.resourceType, resource.resourceId),
        },
    }))
}

/**
 * What a guide preset is called: what it asks, and which of this server's own resources it asks it of.
 *
 * THE RESOURCE TYPE IS PART OF THE NAME IN BOTH LANGUAGES. Two resources of different types can
 * carry the same title - a CodeSystem and the ValueSet composed from it routinely do - and a CQL
 * label built from the title alone then names two examples identically, which is one shelf holding
 * two rows a reader cannot tell apart. The FHIRPath label leads with the element it reads, which
 * says the type by saying what it asks for; the CQL label retrieves a whole type, so it says it.
 */
export function presetLabel(language: EvaluationLanguage, resource: ServedResource): string {
    const named = resource.title ?? resource.resourceId
    return language === 'fhirpath'
        ? `${elementLabel(resource.resourceType)} ${named}`
        : `${named} (${resource.resourceType}), through a CQL retrieve`
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
