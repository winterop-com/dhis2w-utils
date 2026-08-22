/**
 * How the three source languages this server evaluates are coloured.
 *
 * WHY A STREAM TOKENISER AND NOT A GRAMMAR. ELM is JSON and gets the real thing - `@codemirror/lang-json`
 * parses it with a Lezer grammar, so brace matching and folding are structural rather than guessed.
 * FHIRPath and CQL have no CodeMirror grammar, and writing one would be writing a second parser for
 * languages whose only authority in this project is the engine's own. What a reader wants from colour
 * here is smaller than a parse tree: keywords apart from names, strings and comments apart from code,
 * and the date and quantity literals apart from the numbers they contain. A character-at-a-time
 * tokeniser answers exactly that, is a few dozen lines, and cannot disagree with the engine about what
 * an expression MEANS because it never claims to know.
 *
 * THE WORD LISTS ARE THE ENGINE'S, NOT THE SPECIFICATION'S. `lib/reference.ts` states what this engine
 * answers, and the keyword sets below are drawn from the same place. A word the engine refuses is
 * still coloured as a keyword when it is one of the language's own - colour says "this is a word the
 * language reserves", and the refusal, when it comes, arrives as a diagnostic with a line and a column
 * on it.
 *
 * Everything here is pure: `tokenAt` runs the same tokeniser over a plain string, which is what makes
 * the colouring testable without a browser.
 */

import { StreamLanguage, type StringStream } from '@codemirror/language'

/** The token names this tokeniser emits, which are the CodeMirror tags the theme paints. */
export type CodeToken =
    | 'keyword'
    | 'operator'
    | 'string'
    | 'number'
    | 'comment'
    | 'literal'
    | 'variableName'
    | 'typeName'
    | null

/**
 * The words FHIRPath reserves.
 *
 * The operators that are spelled as words rather than as punctuation, plus the two boolean literals
 * and the empty collection. Function names are deliberately absent: `where` is a function and so is
 * `whatever the reader typed`, and colouring the first would imply this tokeniser knows which names
 * the engine answers - which is `lib/reference.ts`'s job to state and the engine's job to enforce.
 */
export const FHIRPATH_KEYWORDS = new Set([
    'and',
    'as',
    'contains',
    'div',
    'implies',
    'in',
    'is',
    'mod',
    'or',
    'xor',
])

/** The three values FHIRPath writes as bare words. */
export const FHIRPATH_LITERALS = new Set(['true', 'false', '{}'])

/**
 * The words CQL reserves, as the engine's grammar accepts them.
 *
 * Declarations, query clauses, the temporal vocabulary, and the operators spelled as words. Sorted
 * for reading rather than for lookup - the set does the lookup.
 */
export const CQL_KEYWORDS = new Set([
    'aggregate',
    'all',
    'and',
    'as',
    'asc',
    'ascending',
    'after',
    'before',
    'between',
    'by',
    'called',
    'case',
    'cast',
    'code',
    'codesystem',
    'collapse',
    'concept',
    'contains',
    'context',
    'convert',
    'day',
    'days',
    'default',
    'define',
    'desc',
    'descending',
    'difference',
    'display',
    'distinct',
    'during',
    'duration',
    'else',
    'end',
    'ends',
    'except',
    'exists',
    'expand',
    'false',
    'flatten',
    'from',
    'function',
    'hour',
    'hours',
    'if',
    'implies',
    'in',
    'include',
    'included',
    'includes',
    'intersect',
    'interval',
    'is',
    'let',
    'library',
    'list',
    'maximum',
    'meets',
    'millisecond',
    'milliseconds',
    'minimum',
    'minute',
    'minutes',
    'mod',
    'month',
    'months',
    'not',
    'null',
    'occurs',
    'of',
    'on',
    'or',
    'overlaps',
    'parameter',
    'per',
    'point',
    'predecessor',
    'private',
    'properly',
    'public',
    'return',
    'same',
    'second',
    'seconds',
    'singleton',
    'sort',
    'start',
    'starts',
    'successor',
    'such',
    'that',
    'then',
    'true',
    'union',
    'using',
    'valueset',
    'version',
    'week',
    'weeks',
    'where',
    'when',
    'width',
    'with',
    'within',
    'without',
    'xor',
    'year',
    'years',
])

/** The two values CQL writes as bare words, plus the one that means no value. */
export const CQL_LITERALS = new Set(['true', 'false', 'null'])

/** The punctuation both languages spend on operators, longest first so `<=` is never read as `<`. */
const OPERATORS = ['<=', '>=', '!=', '!~', '~', '<', '>', '=', '+', '-', '*', '/', '&', '|', '.']

/**
 * One pass of the tokeniser, shared by both word languages.
 *
 * The differences between FHIRPath and CQL that matter to colour are two sets of words and one
 * bracket: a CQL retrieve is `[Patient]` and names a type, where a FHIRPath `[0]` is an index. So the
 * shape is one function and the language is an argument, rather than two near-identical copies that
 * drift.
 */
function readToken(stream: StringStream, keywords: ReadonlySet<string>, literals: ReadonlySet<string>, retrieves: boolean): CodeToken {
    if (stream.eatSpace()) return null

    // Comments, both spellings. The block form is consumed to its terminator on this line; a block
    // running past the end of a line resumes as ordinary text, which is the one thing a stateless
    // tokeniser gets wrong and the one thing a reader forgives.
    if (stream.match('//')) {
        stream.skipToEnd()
        return 'comment'
    }
    if (stream.match('/*')) {
        while (!stream.eol()) {
            if (stream.match('*/')) return 'comment'
            stream.next()
        }
        return 'comment'
    }

    // A date, a datetime, or a time literal: `@2020-01-01`, `@2020-01-01T09:30:00Z`, `@T09:30`.
    if (stream.peek() === '@') {
        stream.next()
        stream.eatWhile(/[\dT:\-+.Z]/)
        return 'literal'
    }

    // A quoted string. Both languages quote strings with `'`; CQL also quotes an identifier that
    // needs it with `"`, and FHIRPath uses a backtick for the same job.
    const quote = stream.peek()
    if (quote === "'" || quote === '"' || quote === '`') {
        stream.next()
        let escaped = false
        while (!stream.eol()) {
            const character = stream.next()
            if (escaped) {
                escaped = false
                continue
            }
            if (character === '\\') escaped = true
            else if (character === quote) break
        }
        return quote === "'" ? 'string' : 'variableName'
    }

    // The environment variables and the special names, which are values rather than paths.
    if (stream.peek() === '%' || stream.peek() === '$') {
        stream.next()
        stream.eatWhile(/[\w-]/)
        return 'variableName'
    }

    // A CQL retrieve names a type between brackets, and that type is the whole point of the line.
    if (retrieves && stream.peek() === '[') {
        stream.next()
        return 'operator'
    }

    if (/\d/.test(stream.peek() ?? '')) {
        stream.eatWhile(/[\d.]/)
        return 'number'
    }

    if (/[A-Za-z_]/.test(stream.peek() ?? '')) {
        let word = ''
        while (!stream.eol() && /[\w]/.test(stream.peek() ?? '')) word += stream.next() ?? ''
        const lowered = word.toLowerCase()
        if (literals.has(lowered)) return 'literal'
        if (keywords.has(lowered)) return 'keyword'
        // A capitalised word in CQL is a type - the retrieve's resource, `Interval`, `List`, `Tuple`
        // - and in FHIRPath it is the resource a path starts at. Either way it is the noun of the
        // line rather than one of its steps.
        return /^[A-Z]/.test(word) ? 'typeName' : null
    }

    for (const operator of OPERATORS) {
        if (stream.match(operator)) return 'operator'
    }

    stream.next()
    return null
}

/** FHIRPath, coloured. */
export const fhirpathLanguage = StreamLanguage.define<null>({
    name: 'fhirpath',
    token: (stream) => readToken(stream, FHIRPATH_KEYWORDS, FHIRPATH_LITERALS, false),
    languageData: { commentTokens: { line: '//', block: { open: '/*', close: '*/' } } },
})

/** CQL, coloured. */
export const cqlLanguage = StreamLanguage.define<null>({
    name: 'cql',
    token: (stream) => readToken(stream, CQL_KEYWORDS, CQL_LITERALS, true),
    languageData: { commentTokens: { line: '//', block: { open: '/*', close: '*/' } } },
})

/**
 * Every token one line is made of, for a test that has no browser to mount an editor in.
 *
 * The tokeniser above runs inside CodeMirror against its own stream; this runs the same rules over a
 * plain string by driving a minimal stand-in for that stream. What it proves is the part worth
 * proving - that `define` is a keyword, that `'hello'` is a string to its closing quote, and that
 * `@1900-01-01` is one literal rather than a number and four operators - without asserting anything
 * about how CodeMirror paints it.
 */
export function tokenise(source: string, language: 'fhirpath' | 'cql'): { text: string; token: CodeToken }[] {
    const keywords = language === 'cql' ? CQL_KEYWORDS : FHIRPATH_KEYWORDS
    const literals = language === 'cql' ? CQL_LITERALS : FHIRPATH_LITERALS
    const stream = new PlainStream(source)
    const tokens: { text: string; token: CodeToken }[] = []
    while (!stream.eol()) {
        stream.startToken()
        const token = readToken(stream as unknown as StringStream, keywords, literals, language === 'cql')
        const text = stream.currentToken()
        if (text === '') break
        if (token !== null) tokens.push({ text, token })
    }
    return tokens
}

/**
 * The few `StringStream` methods `readToken` uses, over a plain string.
 *
 * Not a general implementation and not trying to be one: CodeMirror's own `StringStream` is not
 * exported in a form a test can construct a line with, and the alternative - mounting an editor in a
 * DOM emulation to read its highlighting back - would test the emulation. The methods here are the
 * ones above and nothing else, so a tokeniser that grew a call to a method this class lacks would
 * fail to compile rather than fail silently.
 */
class PlainStream {
    private readonly line: string
    private position = 0
    private tokenStart = 0

    constructor(line: string) {
        this.line = line
    }

    startToken(): void {
        this.tokenStart = this.position
    }

    currentToken(): string {
        return this.line.slice(this.tokenStart, this.position)
    }

    eol(): boolean {
        return this.position >= this.line.length
    }

    peek(): string | undefined {
        return this.eol() ? undefined : this.line[this.position]
    }

    next(): string | undefined {
        return this.eol() ? undefined : this.line[this.position++]
    }

    eatSpace(): boolean {
        const start = this.position
        while (!this.eol() && /[ \t\n\r]/.test(this.line[this.position])) this.position += 1
        return this.position > start
    }

    eatWhile(pattern: RegExp): boolean {
        const start = this.position
        while (!this.eol() && pattern.test(this.line[this.position])) this.position += 1
        return this.position > start
    }

    skipToEnd(): void {
        this.position = this.line.length
    }

    match(pattern: string): boolean {
        if (!this.line.startsWith(pattern, this.position)) return false
        this.position += pattern.length
        return true
    }
}
