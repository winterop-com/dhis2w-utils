import { describe, expect, it } from 'vitest'

import { CQL_KEYWORDS, FHIRPATH_KEYWORDS, tokenise } from '@/lib/codelang'

/**
 * The colouring rules, checked without a browser.
 *
 * What is worth pinning here is the part of an editor that can be wrong invisibly: a tokeniser that
 * read `'hello'` as a keyword and two operators, or `@1900-01-01` as a number and four minus signs,
 * would still render - just wrongly, in a way nobody notices until they are reading a library at
 * eleven at night. Mounting an editor to assert on its painted spans would be testing CodeMirror;
 * running the same rules over a plain string is testing ours.
 */

/** The token one fragment of a source is given, or undefined when the tokeniser emitted none. */
function tokenFor(source: string, text: string, language: 'fhirpath' | 'cql'): string | undefined {
    return tokenise(source, language).find((token) => token.text === text)?.token ?? undefined
}

describe('colouring FHIRPath', () => {
    it('marks the word operators as keywords and leaves path steps alone', () => {
        const tokens = tokenise('Patient.active and Patient.birthDate', 'fhirpath')
        expect(tokenFor('Patient.active and x', 'and', 'fhirpath')).toBe('keyword')
        expect(tokens.find((token) => token.text === 'active')).toBeUndefined()
    })

    it('marks a resource type as a type, because it is the noun the path starts at', () => {
        expect(tokenFor('Patient.name.given', 'Patient', 'fhirpath')).toBe('typeName')
    })

    it('reads a quoted string to its closing quote, in one token', () => {
        const tokens = tokenise("Patient.telecom.where(system = 'email').value", 'fhirpath')
        const string = tokens.find((token) => token.token === 'string')
        expect(string?.text).toBe("'email'")
    })

    it('keeps an escaped quote inside the string rather than ending it', () => {
        const tokens = tokenise("f('it\\'s')", 'fhirpath')
        expect(tokens.find((token) => token.token === 'string')?.text).toBe("'it\\'s'")
    })

    it('reads a date literal as one literal, not as a number and a run of operators', () => {
        const tokens = tokenise('Patient.birthDate < @1900-01-01', 'fhirpath')
        const literal = tokens.find((token) => token.token === 'literal')
        expect(literal?.text).toBe('@1900-01-01')
        expect(tokens.filter((token) => token.token === 'number')).toHaveLength(0)
    })

    it('reads a dateTime literal whole, offset and all', () => {
        expect(tokenise('@2024-01-01T09:30:00Z', 'fhirpath')[0]).toEqual({
            text: '@2024-01-01T09:30:00Z',
            token: 'literal',
        })
    })

    it('marks true and false as literals rather than as names', () => {
        expect(tokenFor('true', 'true', 'fhirpath')).toBe('literal')
        expect(tokenFor('false', 'false', 'fhirpath')).toBe('literal')
    })

    it('marks the special names and the environment constants as values', () => {
        expect(tokenFor('$this.given', '$this', 'fhirpath')).toBe('variableName')
        expect(tokenFor('%ucum', '%ucum', 'fhirpath')).toBe('variableName')
    })

    it('takes a line comment to the end of the line', () => {
        const tokens = tokenise('Patient.name // the names', 'fhirpath')
        expect(tokens.at(-1)).toEqual({ text: '// the names', token: 'comment' })
    })

    it('reads a two-character comparison as one operator', () => {
        const tokens = tokenise('a <= b', 'fhirpath')
        expect(tokens.find((token) => token.token === 'operator')?.text).toBe('<=')
    })
})

describe('colouring CQL', () => {
    it('marks the declaration keywords', () => {
        for (const word of ['library', 'using', 'define', 'valueset', 'context', 'parameter']) {
            expect(tokenFor(word, word, 'cql')).toBe('keyword')
        }
    })

    it('marks a keyword whatever case it was written in, because CQL does not care', () => {
        expect(tokenFor('DEFINE', 'DEFINE', 'cql')).toBe('keyword')
    })

    it('marks the query clauses, which are what tell one part of a query from the next', () => {
        for (const word of ['where', 'return', 'sort', 'with', 'without', 'let', 'aggregate']) {
            expect(tokenFor(word, word, 'cql')).toBe('keyword')
        }
    })

    it('marks the temporal vocabulary, which is spelled as words rather than as punctuation', () => {
        for (const word of ['during', 'overlaps', 'before', 'after', 'within', 'duration']) {
            expect(tokenFor(word, word, 'cql')).toBe('keyword')
        }
    })

    it('marks the retrieved type as a type', () => {
        expect(tokenFor('define People: [Patient]', 'Patient', 'cql')).toBe('typeName')
    })

    it('reads a version string whole', () => {
        const tokens = tokenise("library Example version '1.0'", 'cql')
        expect(tokens.find((token) => token.token === 'string')?.text).toBe("'1.0'")
    })

    it('marks a double-quoted name as a name rather than as a string', () => {
        expect(tokenFor('define "Fever Cases": 1', '"Fever Cases"', 'cql')).toBe('variableName')
    })

    it('marks null as a literal', () => {
        expect(tokenFor('null', 'null', 'cql')).toBe('literal')
    })

    it('reads a number as a number', () => {
        expect(tokenFor('define Sum: 42', '42', 'cql')).toBe('number')
    })
})

describe('the keyword sets', () => {
    it('spells every FHIRPath keyword in lower case, which is what the lookup compares against', () => {
        for (const word of FHIRPATH_KEYWORDS) expect(word).toBe(word.toLowerCase())
    })

    it('spells every CQL keyword in lower case, for the same reason', () => {
        for (const word of CQL_KEYWORDS) expect(word).toBe(word.toLowerCase())
    })

    it('keeps the two sets apart: CQL reserves words FHIRPath does not', () => {
        expect(CQL_KEYWORDS.has('define')).toBe(true)
        expect(FHIRPATH_KEYWORDS.has('define')).toBe(false)
    })
})

describe('tokenising a whole library', () => {
    it('runs to the end of a multi-line source without losing a line', () => {
        const source = [
            "library Example version '1.0'",
            "using FHIR version '4.0.1'",
            'define People: [Patient]',
        ].join('\n')
        const tokens = tokenise(source, 'cql')
        expect(tokens.filter((token) => token.token === 'keyword').map((token) => token.text)).toContain(
            'define',
        )
        expect(tokens.map((token) => token.text)).toContain('Patient')
    })

    it('terminates on an empty source rather than spinning', () => {
        expect(tokenise('', 'cql')).toEqual([])
        expect(tokenise('   ', 'fhirpath')).toEqual([])
    })
})
