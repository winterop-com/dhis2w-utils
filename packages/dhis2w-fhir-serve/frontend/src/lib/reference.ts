/**
 * What this engine answers, per language, as the reference panel beside the editor states it.
 *
 * WHY THIS IS OUR SUBSET AND NOT THE SPECIFICATION. FHIRPath and CQL are both large languages with
 * published grammars, and a panel that listed the whole of either would be a panel that lies: a
 * reader would type a function from it, meet `Unknown function: foo()`, and learn that the reference
 * on the screen is not about the server on the other end of the button. So every entry below is
 * something `dhis2w-fhir-engine` implements - the function registry, the CQL visitor's builtins, the
 * ELM evaluator's dispatch table - and the pages under docs/fhir/501-* are the long form of the same
 * material.
 *
 * WHY THE REFUSALS ARE IN IT. A reference that lists only what works teaches half a language. The
 * mistakes this engine is loud about - a name a library never declared, a valueset with no expansion,
 * an ELM document with no identifier - are the ones a reader will actually make, and each is stated
 * here beside the thing it is a refusal of, so meeting one is recognition rather than surprise.
 *
 * Everything here is data. Nothing fetches, nothing renders; `components/EvaluateReference.tsx` is
 * what draws it, and `lib/evaluate.ts` holds the runnable examples the same panel offers.
 */

import type { EvaluationLanguage } from '@/lib/evaluate'

/** One thing the engine answers: how it is written, and what it does. */
export interface ReferenceEntry {
    /** The name, operator, or clause, exactly as it is typed. */
    name: string
    /** What it does, in one line. */
    meaning: string
}

/** One shelf of the reference: a heading, an optional sentence, and the entries under it. */
export interface ReferenceSection {
    title: string
    /** What the whole shelf is about, when the title alone does not say it. */
    note?: string
    entries: ReferenceEntry[]
}

/** One language's reference: what it is, how it answers, and the shelves. */
export interface LanguageReference {
    /** The language's own name, as its community writes it. */
    title: string
    /** What the language is, in the two or three sentences a reader needs before the first example. */
    summary: string[]
    sections: ReferenceSection[]
    /** Where the long form lives, for a reader who wants the whole argument. */
    reading: string
}

/**
 * FHIRPath, as this engine answers it.
 *
 * The one rule the summary leads with is the one that explains every surprise a newcomer meets: an
 * expression answers a COLLECTION, always, so `count()` answers a collection holding one number
 * rather than a number, and a path that matched nothing answers an empty collection rather than an
 * error.
 */
const FHIRPATH_REFERENCE: LanguageReference = {
    title: 'FHIRPath',
    summary: [
        'A path expression over one resource. It is what a Questionnaire uses to decide whether a question is asked, and what a measure uses to reach a value inside a record.',
        'Every expression answers a collection - never a single value. A path that matched nothing answers an empty collection, which is why `exists()` and `empty()` are the two things worth asking first, and why `count()` answers a collection holding one number.',
        'Comparisons and arithmetic propagate emptiness: an operand that is empty makes the whole expression empty rather than false.',
    ],
    sections: [
        {
            title: 'Navigating',
            note: 'The path itself, and the two ways of stepping sideways out of it.',
            entries: [
                { name: '.', meaning: 'Step into an element - `Patient.name.given`' },
                { name: '[n]', meaning: 'The element at one position, counted from zero' },
                { name: 'children()', meaning: 'Every immediate child node of every item' },
                { name: 'descendants()', meaning: 'Every node below every item, at any depth' },
                { name: 'resolve()', meaning: 'Follow a Reference to the resource it names' },
                { name: 'extension(url)', meaning: 'The extensions carrying one url' },
            ],
        },
        {
            title: 'Existence and counting',
            entries: [
                { name: 'exists([criteria])', meaning: 'Whether the collection holds anything, optionally matching a test' },
                { name: 'empty()', meaning: 'Whether the collection holds nothing' },
                { name: 'count()', meaning: 'How many elements the collection holds' },
                { name: 'all(criteria)', meaning: 'Whether every element matches the test' },
                { name: 'allTrue() / anyTrue()', meaning: 'Whether every / any element is true' },
                { name: 'allFalse() / anyFalse()', meaning: 'Whether every / any element is false' },
                { name: 'hasValue()', meaning: 'Whether the input holds a value at all' },
            ],
        },
        {
            title: 'Filtering and choosing',
            entries: [
                { name: 'where(criteria)', meaning: 'Keep the elements matching a test' },
                { name: 'select(expression)', meaning: 'Answer one expression for each element' },
                { name: 'repeat(expression)', meaning: 'Apply an expression over and over until nothing new appears' },
                { name: 'first() / last()', meaning: 'The first / last element alone' },
                { name: 'tail()', meaning: 'Everything except the first element' },
                { name: 'take(n) / skip(n)', meaning: 'The first n elements / everything after them' },
                { name: 'single()', meaning: 'The one element, when there is exactly one' },
                { name: 'ofType(Type)', meaning: 'Keep only the elements of one type' },
                { name: 'is(Type) / as(Type)', meaning: 'Test the type / cast to it, answering empty when it does not fit' },
                { name: 'type()', meaning: 'The type of the input, as a type specifier' },
                { name: 'iif(test, then [, else])', meaning: 'A conditional; only the branch taken is evaluated' },
            ],
        },
        {
            title: 'Working with collections',
            entries: [
                { name: 'distinct() / isDistinct()', meaning: 'Drop duplicates / test whether there are any' },
                { name: 'union(other) / |', meaning: 'Both collections, duplicates removed' },
                { name: 'intersect(other)', meaning: 'Only what both hold' },
                { name: 'exclude(other)', meaning: 'What the left holds and the right does not' },
                { name: 'combine(other)', meaning: 'Both collections, duplicates kept' },
                { name: 'flatten()', meaning: 'Flatten nested collections by one level' },
                { name: 'subsetOf / supersetOf', meaning: 'Whether one collection contains the other' },
                { name: 'sort([keys])', meaning: 'Sort; a key written `-expression` sorts descending' },
                { name: 'aggregate(expression [, start])', meaning: 'Fold the collection, with `$this` and `$total`' },
            ],
        },
        {
            title: 'Text',
            entries: [
                { name: 'length() / upper() / lower() / trim()', meaning: 'The size and the casing of a string' },
                { name: 'startsWith / endsWith / contains', meaning: 'Whether a string begins with, ends with, or holds a fragment' },
                { name: 'substring(start [, length])', meaning: 'Part of a string, counted from zero' },
                { name: 'indexOf(fragment)', meaning: 'Where a fragment starts, or -1' },
                { name: 'split(separator) / join([separator])', meaning: 'One string into many / many into one' },
                { name: 'matches / matchesFull', meaning: 'A regular expression, matched partly / over the whole string' },
                { name: 'replace / replaceMatches', meaning: 'Replace a fragment / every regular expression match' },
                { name: 'toChars()', meaning: 'A string as a collection of single characters' },
                { name: 'encode / decode / escape / unescape', meaning: 'Base64, hex, HTML and JSON escaping' },
                { name: '&', meaning: 'Join two strings, reading an empty operand as an empty string' },
            ],
        },
        {
            title: 'Numbers',
            entries: [
                { name: '+ - * /', meaning: 'Arithmetic, in decimal' },
                { name: 'div / mod', meaning: 'Whole division and its remainder' },
                { name: 'abs() / ceiling() / floor() / round([n]) / truncate()', meaning: 'Rounding, each in its own direction' },
                { name: 'sqrt() / power(n) / exp() / ln() / log(base)', meaning: 'Roots, powers and logarithms' },
                { name: 'precision()', meaning: 'How precise a decimal, date, dateTime or time is' },
                { name: 'lowBoundary / highBoundary', meaning: 'The lowest and highest value a stated precision covers' },
            ],
        },
        {
            title: 'Dates, times and quantities',
            note: 'A literal date starts with `@`. Adding a quantity to one is how a window is moved.',
            entries: [
                { name: '@2024-01-01', meaning: 'A date literal; `@2024` and `@2024-06` are the partial forms' },
                { name: '@2024-01-01T09:30:00Z', meaning: 'A dateTime literal, with an optional offset' },
                { name: '@T09:30:00', meaning: 'A time literal' },
                { name: "5 'mg' / 5 days", meaning: 'A quantity, with a UCUM code or a calendar unit' },
                { name: 'today() / now() / timeOfDay()', meaning: 'The server clock, read as a date, a dateTime, or a time' },
                { name: 'year() month() day()', meaning: 'One component of a date or dateTime' },
                { name: 'hour() minute() second() millisecond()', meaning: 'One component of a dateTime or time' },
                { name: 'date + 3 months', meaning: 'Date arithmetic; the calendar units and their UCUM codes are both accepted' },
            ],
        },
        {
            title: 'Comparing and combining',
            entries: [
                { name: '= != < <= > >=', meaning: 'Comparison; an empty operand makes the whole comparison empty' },
                { name: '~ / !~', meaning: 'Equivalence, which ignores case and trailing precision' },
                { name: 'in / contains', meaning: 'Whether a value is in a collection, and the same test the other way round' },
                { name: 'and or xor implies', meaning: 'Three-valued logic - true, false, and empty' },
                { name: 'not()', meaning: 'Negation' },
                { name: 'comparable(other)', meaning: 'Whether two quantities have units that can be compared' },
            ],
        },
        {
            title: 'Converting',
            entries: [
                { name: 'toString() toInteger() toDecimal() toBoolean()', meaning: 'Convert, answering empty when the value will not convert' },
                { name: 'toDate() toDateTime() toTime() toQuantity([unit])', meaning: 'The same, for the temporal types' },
                { name: 'convertsToInteger() and the rest', meaning: 'Ask whether a conversion would work, without doing it' },
            ],
        },
        {
            title: 'FHIR-specific',
            note: 'The tests a profile asks; each needs whatever the engine was given to answer it with.',
            entries: [
                { name: 'conformsTo(profile)', meaning: 'Whether the resource conforms to a profile' },
                { name: 'memberOf(valueset)', meaning: 'Whether a code, Coding or CodeableConcept is in a value set' },
                { name: 'subsumes / subsumedBy', meaning: 'Whether one code stands above or below another' },
                { name: 'elementDefinition() / slice() / checkModifiers()', meaning: 'The definitional reads a profile validator makes' },
                { name: 'htmlChecks()', meaning: 'Whether a Narrative holds valid HTML' },
            ],
        },
        {
            title: 'Named values',
            entries: [
                { name: '$this / $index / $total', meaning: 'The current item, its position, and the accumulator inside `aggregate`' },
                { name: '%resource / %rootResource / %context', meaning: 'The resource the expression is running over' },
                { name: '%sct %loinc %ucum', meaning: 'The canonical urls of SNOMED CT, LOINC, and UCUM' },
                { name: '%vs-administrative-gender', meaning: 'The url of the administrative gender value set' },
            ],
        },
        {
            title: 'What it refuses',
            note: 'Each of these answers a diagnostic with a line and a column on it, not an error page.',
            entries: [
                { name: 'Unknown function: foo()', meaning: 'A name this engine does not implement. The lists above are the whole of what it does.' },
                { name: 'Syntax error at line L:C', meaning: 'The parser stopped on a character. The screen shows the line with a caret under it.' },
                { name: 'defineVariable()', meaning: 'Not implemented. Use `select()` to carry a value forward.' },
                { name: 'Lambdas (=>)', meaning: 'Not part of the grammar this engine parses.' },
            ],
        },
    ],
    reading: 'docs/fhir/501-fhirpath.md',
}

/**
 * CQL, as this engine answers it.
 *
 * The summary leads with the two facts that actually catch people out: a `return` de-duplicates
 * unless it says `all`, and a `context Patient` narrows every retrieve underneath it. Both are
 * correct CQL and both surprise a reader who assumed a query is a filter and nothing more.
 */
const CQL_REFERENCE: LanguageReference = {
    title: 'CQL',
    summary: [
        'A library of named definitions. Each `define` is a question, and asking the library asks all of them unless one is named.',
        'A retrieve - `[Observation]` - is how a library reaches data. What it reaches is whatever this run was given: a Bundle posted as the context becomes the data behind every retrieve, and a run with no data answers every retrieve with an empty list.',
        'Two behaviours worth knowing before the first surprise: a `return` clause removes duplicates unless it says `return all`, and a `context Patient` narrows every retrieve in the library to one person.',
    ],
    sections: [
        {
            title: 'The header',
            note: 'Everything above the first `define`. Only the library line is required.',
            entries: [
                { name: "library Name version '1.0'", meaning: 'What the library is called' },
                { name: "using FHIR version '4.0.1'", meaning: 'Which data model the retrieves are written against' },
                { name: "include Other version '1.0' called Alias", meaning: 'Another library, reached through a name of your choosing' },
                { name: 'parameter Name Type default expression', meaning: 'A value the caller may supply, with a default the library states' },
                { name: "codesystem \"SNOMED\": 'http://snomed.info/sct'", meaning: 'A code system, named for the rest of the library' },
                { name: "valueset \"Fevers\": 'http://example.org/ValueSet/fevers'", meaning: 'A value set a retrieve can be scoped to' },
                { name: "code \"Fever\": '386661006' from \"SNOMED\"", meaning: 'One code, named' },
                { name: 'concept "Fever": { "Fever" }', meaning: 'One concept, over one or more codes' },
                { name: 'context Patient | Unfiltered | Encounter', meaning: 'What the library is about; `Patient` evaluates it once per person' },
            ],
        },
        {
            title: 'Definitions',
            entries: [
                { name: 'define "Name": expression', meaning: 'One question the library answers' },
                { name: 'define private "Name": expression', meaning: 'A definition the library keeps to itself' },
                { name: 'define function Name(a Integer) returns Integer: expression', meaning: 'A function other definitions call' },
                { name: 'define fluent function', meaning: 'A function callable as `value.Name()`' },
            ],
        },
        {
            title: 'Retrieves',
            note: 'Every form scopes a resource type. The code path defaults per type - `code` for Condition and Observation, `vaccineCode` for Immunization.',
            entries: [
                { name: '[Patient]', meaning: 'Every resource of a type' },
                { name: '[Condition: "Fevers"]', meaning: 'Scoped to a value set, code, or concept the library declares' },
                { name: '[Observation: code in "Weights"]', meaning: 'Scoped on a named element rather than on the default one' },
                { name: '[Immunization: vaccineCode ~ "Measles"]', meaning: 'Scoped to one code by equivalence' },
                { name: 'Alias.[Condition: "Fevers"]', meaning: 'Terminology resolved through an included library' },
            ],
        },
        {
            title: 'Queries',
            note: 'Clauses in this order. Every one of them is optional except the source.',
            entries: [
                { name: 'from [Observation] O, [Patient] P', meaning: 'One or more sources, each with an alias' },
                { name: 'let name: expression', meaning: 'A value computed once per row' },
                { name: 'with [Encounter] E such that ...', meaning: 'Keep rows that have a match' },
                { name: 'without [Encounter] E such that ...', meaning: 'Keep rows that have no match' },
                { name: 'where expression', meaning: 'Keep the rows matching a test' },
                { name: 'return [all | distinct] expression', meaning: 'What each row answers. Duplicates go unless `all` is written.' },
                { name: 'sort by expression asc | desc', meaning: 'Order the answer, on one key or several' },
                { name: 'aggregate A starting expression: expression', meaning: 'Fold the rows into one value' },
            ],
        },
        {
            title: 'Intervals and the temporal vocabulary',
            note: 'Square brackets include the boundary, round brackets exclude it, and the two can be mixed.',
            entries: [
                { name: 'Interval[@2024-01-01, @2024-12-31]', meaning: 'A closed interval' },
                { name: 'Interval(@2024-01-01, @2024-12-31]', meaning: 'Open at the start, closed at the end' },
                { name: 'start of / end of / width of / size of', meaning: 'The boundaries of an interval and how wide it is' },
                { name: 'point from / singleton from', meaning: 'The one value inside a unit interval / a one-element list' },
                { name: 'during / included in / includes', meaning: 'Containment, either way round' },
                { name: 'before / after / on or before / on or after', meaning: 'Order, with the boundary in or out' },
                { name: 'same as / same or before / same or after', meaning: 'Comparison at a stated precision' },
                { name: 'overlaps / meets / starts / ends', meaning: 'How two intervals sit against each other' },
                { name: 'properly includes / properly included in', meaning: 'Containment that refuses the equal case' },
                { name: 'within 3 days of', meaning: 'Proximity, at a stated quantity' },
                {
                    name: 'P.birthDate < @2000-01-01',
                    meaning: 'A date read off a FHIR resource arrives as text and is read as a date where a date is expected, so no conversion is written',
                },
                { name: 'duration in days between A and B', meaning: 'Whole units between two values' },
                { name: 'difference in days between A and B', meaning: 'Boundaries crossed between two values' },
                { name: 'collapse / expand', meaning: 'Merge overlapping intervals / break one into per-unit intervals' },
            ],
        },
        {
            title: 'Operators',
            entries: [
                { name: '+ - * / div mod ^', meaning: 'Arithmetic, with `^` for powers' },
                { name: '= != ~ !~ < <= > >=', meaning: 'Comparison and equivalence' },
                { name: 'and or xor not implies', meaning: 'Three-valued logic' },
                { name: 'in / contains / between A and B', meaning: 'Membership and range' },
                { name: 'union / intersect / except', meaning: 'Set operations over lists' },
                { name: 'exists', meaning: 'Whether a list holds anything' },
                { name: 'is / as / cast X as T', meaning: 'Type tests and casts' },
                { name: 'if ... then ... else', meaning: 'A conditional' },
                { name: 'case ... when ... then ... else ... end', meaning: 'A conditional with several arms' },
                { name: 'successor of / predecessor of', meaning: 'The next and previous value of a type' },
                { name: 'minimum Integer / maximum Integer', meaning: 'The extremes a type can hold' },
                { name: 'convert X to T', meaning: 'A conversion written as an operator' },
            ],
        },
        {
            title: 'Literals',
            entries: [
                { name: "true false null 'text' 42 3.14", meaning: 'The plain values' },
                { name: '@2024-01-01 / @2024-01-01T09:30:00 / @T09:30:00', meaning: 'Date, dateTime, and time' },
                { name: "5 'mg' / 1 'mg' : 2 'mL'", meaning: 'A quantity and a ratio' },
                { name: '{ 1, 2, 3 }', meaning: 'A list' },
                { name: 'Tuple { name: \'Ada\', year: 1815 }', meaning: 'A tuple' },
                { name: 'Interval[1, 10]', meaning: 'An interval' },
            ],
        },
        {
            title: 'Built-in functions',
            note: 'Names are matched without regard to case.',
            entries: [
                { name: 'Count Sum Avg Min Max Median Mode Product', meaning: 'Aggregates over a list' },
                { name: 'Variance StdDev PopulationVariance PopulationStdDev GeometricMean', meaning: 'The rest of the statistics' },
                { name: 'AllTrue AnyTrue AllFalse AnyFalse', meaning: 'Aggregates over a list of booleans' },
                { name: 'First Last Tail Take Skip Length Reverse Slice', meaning: 'Picking from a list' },
                { name: 'Distinct Flatten Sort IndexOf Singleton Combine Union Intersect Except', meaning: 'Reshaping a list' },
                { name: 'Concatenate Split Upper Lower Substring Trim Replace ReplaceMatches Matches', meaning: 'Text' },
                { name: 'StartsWith EndsWith PositionOf LastPositionOf Indexer', meaning: 'Text, positionally' },
                { name: 'Today Now TimeOfDay Date DateTime Time', meaning: 'The clock and the constructors' },
                { name: 'Year Month Day Hour Minute Second Millisecond TimezoneOffset', meaning: 'Components of a date or time' },
                { name: 'AgeInYears AgeInMonths AgeInDays AgeInYearsAt', meaning: 'Age, from the context patient or from a stated date' },
                { name: 'ToString ToInteger ToDecimal ToBoolean ToDate ToDateTime ToQuantity ToConcept', meaning: 'Conversions' },
                { name: 'Coalesce IsNull IsNotNull IsTrue IsFalse', meaning: 'Tests over a value that may be null' },
                { name: 'Abs Ceiling Floor Round Truncate Ln Log Exp Power Sqrt Precision', meaning: 'Numbers' },
                { name: 'Message(source, condition, code, severity, text)', meaning: 'Emit a message; `Error` severity stops the run' },
            ],
        },
        {
            title: 'What it refuses, and why loudly',
            note: 'A retrieve whose terminology resolves to nothing would widen from the set the library named to every resource of that type - the loudest possible wrong answer, delivered silently. So it is refused instead.',
            entries: [
                {
                    name: 'A name the library does not declare',
                    meaning: '`[Condition: "Measles"]` with no `valueset "Measles"` above it is refused, naming the declaration to add.',
                },
                {
                    name: 'A value set with no expansion',
                    meaning: 'A declared value set whose url this run holds no codes for is refused rather than treated as empty.',
                },
                {
                    name: 'A string where terminology belongs',
                    meaning: "`[Condition: '386661006']` is refused: name a value set, code, or concept the library declares.",
                },
                { name: 'A recursive definition', meaning: 'A define that reaches itself is refused rather than run until the stack ends.' },
                { name: 'A define name that does not exist', meaning: 'Asking for one define the library never declared answers a diagnostic saying so.' },
            ],
        },
    ],
    reading: 'docs/fhir/501-cql.md',
}

/**
 * ELM, as this engine answers it.
 *
 * Nobody writes ELM by hand, so this reference is about SHAPE rather than about vocabulary: what a
 * compiled library has to carry for this endpoint to run it, and which expression nodes the evaluator
 * knows. The node list is grouped because a flat list of a hundred and seventy names is a list nobody
 * reads.
 */
const ELM_REFERENCE: LanguageReference = {
    title: 'ELM',
    summary: [
        'The compiled form of a CQL library, as JSON. This endpoint runs one; it does not compile one - paste what another CQL compiler emitted.',
        'Both shapes are accepted: a document wrapped in a `library` element, and the library object on its own.',
        'Only `identifier` is required, and it must carry an `id`. Unknown attributes are carried through rather than refused, so a document from a compiler that writes more than this engine reads still runs.',
    ],
    sections: [
        {
            title: 'What a library carries',
            entries: [
                { name: 'identifier: { id, version }', meaning: 'Required. A library with no identifier is refused.' },
                { name: 'schemaIdentifier', meaning: 'Optional. Checked only as advice.' },
                { name: 'statements: { def: [...] }', meaning: 'The definitions. Each needs a `name`.' },
                { name: 'usings / includes / parameters', meaning: 'The header, as ELM writes it. A bare list is accepted in place of the `def` wrapper.' },
                { name: 'codeSystems / valueSets / codes / concepts / contexts', meaning: 'The terminology declarations, same two shapes' },
            ],
        },
        {
            title: 'What a definition carries',
            entries: [
                { name: 'name', meaning: 'Required. This is what the answer is labelled with.' },
                { name: 'expression', meaning: 'The expression tree. A definition with none is an external declaration.' },
                { name: 'context', meaning: 'Which context the definition is evaluated in' },
                { name: 'accessLevel: "Private"', meaning: 'Hides the definition from a run that asks for every define' },
                { name: 'operand: [...]', meaning: 'Present on a function rather than on a plain definition' },
            ],
        },
        {
            title: 'Literals and selectors',
            note: 'A literal states its type as a url and its value as a string - `{urn:hl7-org:elm-types:r1}Integer`.',
            entries: [
                { name: 'Literal Null', meaning: 'One value, and the absence of one' },
                { name: 'List Tuple Instance', meaning: 'The structured selectors' },
                { name: 'Interval Quantity Ratio Code Concept', meaning: 'The clinical and temporal selectors' },
            ],
        },
        {
            title: 'Expression nodes',
            note: 'Every node the evaluator dispatches on. Anything else answers "Unsupported expression type".',
            entries: [
                { name: 'Add Subtract Multiply Divide TruncatedDivide Modulo Power Negate', meaning: 'Arithmetic' },
                { name: 'Abs Ceiling Floor Truncate Round Ln Log Exp Successor Predecessor MinValue MaxValue', meaning: 'Numbers' },
                { name: 'Equal NotEqual Equivalent Less LessOrEqual Greater GreaterOrEqual', meaning: 'Comparison' },
                { name: 'And Or Xor Not Implies IsTrue IsFalse IsNull', meaning: 'Logic' },
                { name: 'If Case Coalesce', meaning: 'Conditionals' },
                { name: 'Concatenate Combine Split Length Upper Lower Substring StartsWith EndsWith', meaning: 'Text' },
                { name: 'Matches ReplaceMatches Indexer PositionOf LastPositionOf', meaning: 'Text, positionally' },
                { name: 'First Last IndexOf Contains In Includes IncludedIn ProperIncludes ProperIncludedIn', meaning: 'Membership' },
                { name: 'Distinct Flatten Exists SingletonFrom ToList Union Intersect Except', meaning: 'Lists and sets' },
                { name: 'Count Sum Avg Min Max Median Mode Variance StdDev AllTrue AnyTrue Product GeometricMean', meaning: 'Aggregates' },
                { name: 'ExpressionRef FunctionRef ParameterRef OperandRef Property AliasRef QueryLetRef IdentifierRef', meaning: 'References' },
                { name: 'Query Retrieve ForEach Repeat Filter Times', meaning: 'Queries' },
                { name: 'As Is ToBoolean ToInteger ToDecimal ToString ToDateTime ToDate ToTime ToQuantity ToConcept', meaning: 'Types and conversions' },
                { name: 'ConvertsToBoolean and the rest of the ConvertsTo family', meaning: 'Conversion tests' },
                { name: 'Today Now TimeOfDay Date DateTime Time DateFrom TimeFrom TimezoneOffsetFrom DateTimeComponentFrom', meaning: 'The clock and its components' },
                { name: 'DurationBetween DifferenceBetween SameAs SameOrBefore SameOrAfter', meaning: 'Temporal comparison' },
                { name: 'Start End Width Size PointFrom Collapse Expand', meaning: 'Interval boundaries' },
                { name: 'Overlaps OverlapsBefore OverlapsAfter Meets MeetsBefore MeetsAfter Before After Starts Ends', meaning: 'Interval relationships' },
                { name: 'CodeRef CodeSystemRef ValueSetRef ConceptRef InValueSet InCodeSystem', meaning: 'Terminology' },
                { name: 'CalculateAge CalculateAgeAt Message', meaning: 'Age, and messages' },
            ],
        },
        {
            title: 'What it refuses',
            entries: [
                { name: "ELM library missing required 'identifier' field", meaning: 'A library with no identifier will not load.' },
                { name: 'Unsupported expression type: X', meaning: 'A node this evaluator does not implement. The list above is the whole of what it does.' },
                { name: 'External function not implemented: X', meaning: 'A definition declared external, with nothing behind it.' },
                { name: 'A source that is not JSON', meaning: 'The document is parsed before the engine sees it, so a bad document is a JSON error with a line and a column.' },
            ],
        },
    ],
    reading: 'docs/fhir/501-version-binding.md',
}

/** The reference for one language. */
export function languageReference(language: EvaluationLanguage): LanguageReference {
    if (language === 'fhirpath') return FHIRPATH_REFERENCE
    return language === 'cql' ? CQL_REFERENCE : ELM_REFERENCE
}

/** How many things a reference states, which is what a panel's own heading counts. */
export function referenceEntryCount(reference: LanguageReference): number {
    return reference.sections.reduce((total, section) => total + section.entries.length, 0)
}
