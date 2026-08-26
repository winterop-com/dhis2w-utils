import { describe, expect, it } from 'vitest'

import type { EvaluationLanguage } from '@/lib/evaluate'
import {
    DOCUMENTATION_SITE,
    languageReference,
    markConfigurationKeys,
    proseRuns,
    referenceEntryCount,
} from '@/lib/reference'

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

    it('links the long form to a page a browser can open, or says nothing', () => {
        // A repository path is unreachable from the panel it is printed in. Every reading that is
        // stated is a published page; ELM states none, because no published page is about ELM.
        for (const language of LANGUAGES) {
            const reading = languageReference(language).reading
            if (reading === null) continue
            expect(reading.title.trim()).not.toBe('')
            expect(reading.url.startsWith(DOCUMENTATION_SITE)).toBe(true)
            expect(reading.url).not.toMatch(/\.md$/)
        }
    })

    it('states no long form for ELM, rather than a page about something else', () => {
        expect(languageReference('elm').reading).toBeNull()
        expect(languageReference('fhirpath').reading).not.toBeNull()
        expect(languageReference('cql').reading).not.toBeNull()
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

/** Every sentence the panel draws, from all three languages, as one flat list. */
function everySentence(): string[] {
    const sentences: string[] = []
    for (const language of LANGUAGES) {
        const reference = languageReference(language)
        sentences.push(...reference.summary)
        for (const section of reference.sections) {
            if (section.note !== undefined) sentences.push(section.note)
            for (const entry of section.entries) sentences.push(entry.meaning)
        }
    }
    return sentences
}

describe('the mono spellings inside the prose', () => {
    it('closes every mark it opens, so no sentence trails off into the mono face', () => {
        for (const sentence of everySentence()) {
            const marks = [...sentence].filter((character) => character === '`').length
            expect(marks % 2, `unclosed mark in: ${sentence}`).toBe(0)
        }
    })

    it('hands back no mark at all, so a reader sees a face rather than a character', () => {
        for (const sentence of everySentence()) {
            for (const run of proseRuns(sentence)) expect(run.text).not.toContain('`')
        }
    })

    it('rebuilds the sentence it was given, so nothing is lost between data and screen', () => {
        for (const sentence of everySentence()) {
            const rebuilt = proseRuns(sentence)
                .map((run) => run.text)
                .join('')
            expect(rebuilt).toBe(sentence.replaceAll('`', ''))
        }
    })

    it('marks the inside of a pair and nothing else', () => {
        expect(proseRuns('Step into an element - `Patient.name.given`')).toEqual([
            { text: 'Step into an element - ', code: false },
            { text: 'Patient.name.given', code: true },
        ])
    })

    it('opens on a mono spelling without a blank run in front of it', () => {
        expect(proseRuns('`exists()` answers a boolean')).toEqual([
            { text: 'exists()', code: true },
            { text: ' answers a boolean', code: false },
        ])
    })

    it('leaves an unmarked sentence as the one run it is', () => {
        expect(proseRuns('Age, and messages')).toEqual([{ text: 'Age, and messages', code: false }])
    })

    it('finds something to set in mono, or the mechanism is drawing nothing', () => {
        const marked = everySentence().flatMap((sentence) => proseRuns(sentence).filter((run) => run.code))
        expect(marked.length).toBeGreaterThan(20)
    })
})

/**
 * A fhir.toml setting named in server prose, marked as the machine spelling it is.
 *
 * The `none` authentication posture's own sentence writes `[serve] auth` bare, and a key set in the
 * same face as the words around it asks the reader to notice a bracket.
 */
describe('the settings server prose names', () => {
    it('marks a bare table-and-key so it reads as a machine spelling', () => {
        expect(markConfigurationKeys('unless the project states [serve] auth in its fhir.toml.')).toBe(
            'unless the project states `[serve] auth` in its fhir.toml.',
        )
    })

    it('leaves a key the server already marked exactly as it marked it', () => {
        const stated = 'this project sets `[serve.tracked_entities] enabled` to false'
        expect(markConfigurationKeys(stated)).toBe(stated)
    })

    it('leaves prose naming no setting alone', () => {
        expect(markConfigurationKeys('This server checks no credential.')).toBe(
            'This server checks no credential.',
        )
    })
})

