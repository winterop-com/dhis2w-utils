import { describe, expect, it } from 'vitest'

import type { EvaluationLanguage } from '@/lib/evaluate'
import { languageReference, referenceEntryCount } from '@/lib/reference'

/**
 * The reference panel's content, checked for the two ways a reference goes wrong.
 *
 * The first is emptiness: a shelf with no entries, or a language with no shelves, renders as a
 * heading over nothing. The second is a name stated twice, which on a page whose whole job is
 * "here is the vocabulary" reads as a mistake in the vocabulary rather than as a mistake in the page.
 *
 * What is NOT tested here is whether the engine implements what these lists claim - a unit test in
 * the browser cannot know that, and asserting it against a hard-coded copy would only prove the copy
 * matches itself. The pages under docs/fhir/501-* and the engine's own suites are what hold that
 * line; the docstring in lib/reference.ts names the sources each shelf was drawn from.
 */

const LANGUAGES: EvaluationLanguage[] = ['fhirpath', 'cql', 'elm']

describe('the language reference', () => {
    it('answers for every language the screen offers, so no tab opens empty', () => {
        for (const language of LANGUAGES) {
            const reference = languageReference(language)
            expect(reference.title.trim()).not.toBe('')
            expect(reference.sections.length).toBeGreaterThan(0)
        }
    })

    it('opens with a summary rather than dropping a reader straight into a word list', () => {
        for (const language of LANGUAGES) {
            const reference = languageReference(language)
            expect(reference.summary.length).toBeGreaterThanOrEqual(2)
            for (const paragraph of reference.summary) expect(paragraph.trim()).not.toBe('')
        }
    })

    it('names the page the long form lives on', () => {
        for (const language of LANGUAGES) {
            expect(languageReference(language).reading).toMatch(/^docs\/fhir\/5\d\d-/)
        }
    })

    it('puts something under every heading', () => {
        for (const language of LANGUAGES) {
            for (const section of languageReference(language).sections) {
                expect(section.title.trim()).not.toBe('')
                expect(section.entries.length).toBeGreaterThan(0)
            }
        }
    })

    it('states each entry once per shelf, and says something about each', () => {
        for (const language of LANGUAGES) {
            for (const section of languageReference(language).sections) {
                const names = section.entries.map((entry) => entry.name)
                expect(new Set(names).size).toBe(names.length)
                for (const entry of section.entries) {
                    expect(entry.name.trim()).not.toBe('')
                    expect(entry.meaning.trim()).not.toBe('')
                }
            }
        }
    })

    it('names each shelf once within a language', () => {
        for (const language of LANGUAGES) {
            const titles = languageReference(language).sections.map((section) => section.title)
            expect(new Set(titles).size).toBe(titles.length)
        }
    })

    it('says what each language refuses, because half of learning one is learning that', () => {
        for (const language of LANGUAGES) {
            const refusals = languageReference(language).sections.filter((section) =>
                section.title.toLowerCase().includes('refuse'),
            )
            expect(refusals.length).toBeGreaterThan(0)
            expect(refusals[0].entries.length).toBeGreaterThan(0)
        }
    })

    it('carries enough of a vocabulary to be worth opening', () => {
        expect(referenceEntryCount(languageReference('fhirpath'))).toBeGreaterThanOrEqual(50)
        expect(referenceEntryCount(languageReference('cql'))).toBeGreaterThanOrEqual(50)
        expect(referenceEntryCount(languageReference('elm'))).toBeGreaterThanOrEqual(20)
    })

    it('is a different reference per language, not one list with three titles', () => {
        const [fhirpath, cql, elm] = LANGUAGES.map((language) => languageReference(language))
        expect(fhirpath.title).toBe('FHIRPath')
        expect(cql.title).toBe('CQL')
        expect(elm.title).toBe('ELM')
        expect(fhirpath.sections).not.toEqual(cql.sections)
        expect(cql.sections).not.toEqual(elm.sections)
    })

    it('states the CQL refusals this engine is deliberately loud about', () => {
        const refusals = languageReference('cql').sections.find((section) =>
            section.title.toLowerCase().includes('refuse'),
        )
        const said = (refusals?.entries ?? []).map((entry) => `${entry.name} ${entry.meaning}`).join(' ')
        expect(said).toContain('value set')
        expect(said).toContain('declare')
    })

    it('states that a date read off a FHIR resource is compared without a conversion around it', () => {
        // The CQL shelf that asks a realistic Bundle is written on this, so a reader meeting
        // `P.birthDate < @2000-01-01` there finds the rule stated rather than inferred.
        const temporal = languageReference('cql').sections.find((section) =>
            section.title.toLowerCase().includes('temporal'),
        )
        const said = (temporal?.entries ?? []).map((entry) => `${entry.name} ${entry.meaning}`).join(' ')
        expect(said).toContain('birthDate')
        expect(said).toContain('no conversion is written')
    })

    it('states the one thing an ELM library cannot be posted without', () => {
        const said = languageReference('elm')
            .sections.flatMap((section) => section.entries)
            .map((entry) => `${entry.name} ${entry.meaning}`)
            .join(' ')
        expect(said).toContain('identifier')
    })
})
