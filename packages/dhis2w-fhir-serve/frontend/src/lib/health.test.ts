import { describe, expect, it } from 'vitest'

import {
    countOf,
    coveragePercent,
    coverageRatio,
    coverageRatios,
    groupByResourceType,
    isClean,
    matchingFindings,
    matchingGaps,
    shelveFindings,
    EMPTY_METADATA_HEALTH,
    type LocaleCoverage,
    type MetadataFinding,
    type MetadataHealth,
    type TranslationCoverage,
    type TranslationGap,
} from '@/lib/health'

/**
 * The arrangement and the arithmetic behind the metadata health page.
 *
 * The wording is never asserted here: every finding carries the sentence `d2w fhir validate` wrote,
 * and the Python suite is what pins that. What this file holds is the two things the browser decides
 * on its own - which shelf a row lands on, and what the coverage strip is a share of.
 */

function finding(overrides: Partial<MetadataFinding> = {}): MetadataFinding {
    return {
        severity: 'warning',
        scope: 'selection',
        category: 'invalid-code',
        resource_type: 'dataElements',
        uid: 'DeAncVisit1',
        name: 'ANC 1st visit',
        code: 'ANC 1',
        field: 'code',
        message: 'code is not a valid FHIR code: code has leading whitespace',
        cost: 'The build finishes, and what it publishes for this object is degraded.',
        ...overrides,
    }
}

function coverage(overrides: Partial<TranslationCoverage> = {}): TranslationCoverage {
    return { locales: [], object_count: 0, form_named_count: 0, per_locale: [], gaps: [], ...overrides }
}

function locale(tag: string, nameCount: number, formNameCount = 0): LocaleCoverage {
    return { locale: tag, name_count: nameCount, form_name_count: formNameCount }
}

function gap(overrides: Partial<TranslationGap> = {}): TranslationGap {
    return {
        resource_type: 'dataElements',
        uid: 'DeAncVisit1',
        name: 'ANC 1st visit',
        missing_name_locales: ['lo'],
        missing_form_name_locales: [],
        ...overrides,
    }
}

describe('countOf', () => {
    it('reads each severity off the counts the server stated', () => {
        const counts = { errors: 3, warnings: 2, infos: 7 }
        expect(countOf(counts, 'error')).toBe(3)
        expect(countOf(counts, 'warning')).toBe(2)
        expect(countOf(counts, 'info')).toBe(7)
    })
})

describe('isClean', () => {
    it('is clean when there is no finding and no translation gap', () => {
        expect(isClean(EMPTY_METADATA_HEALTH)).toBe(true)
    })

    it('is not clean for a translation gap alone', () => {
        const health: MetadataHealth = {
            ...EMPTY_METADATA_HEALTH,
            translations: coverage({ locales: ['lo'], gaps: [gap()] }),
        }
        expect(isClean(health)).toBe(false)
    })

    it('is not clean for a finding alone', () => {
        expect(isClean({ ...EMPTY_METADATA_HEALTH, findings: [finding()] })).toBe(false)
    })
})

describe('shelveFindings', () => {
    it('puts the errors first, whichever kind of object they are about', () => {
        const shelves = shelveFindings([
            finding({ severity: 'info', uid: 'Aaa11111111' }),
            finding({ severity: 'error', uid: 'Bbb11111111', resource_type: 'organisationUnits' }),
            finding({ severity: 'warning', uid: 'Ccc11111111' }),
        ])
        expect(shelves.map((shelf) => shelf.severity)).toEqual(['error', 'warning', 'info'])
    })

    it('drops a severity nothing was found at rather than rendering an empty shelf', () => {
        const shelves = shelveFindings([finding({ severity: 'error' })])
        expect(shelves).toHaveLength(1)
        expect(shelves[0].total).toBe(1)
    })

    it('shelves one severity by the DHIS2 collection each object belongs to', () => {
        const shelves = shelveFindings([
            finding({ severity: 'error', uid: 'Aaa11111111', resource_type: 'organisationUnits' }),
            finding({ severity: 'error', uid: 'Bbb11111111', resource_type: 'dataElements' }),
            finding({ severity: 'error', uid: 'Ccc11111111', resource_type: 'dataElements' }),
        ])
        expect(shelves[0].groups.map((group) => group.resourceType)).toEqual([
            'dataElements',
            'organisationUnits',
        ])
        expect(shelves[0].groups[0].findings).toHaveLength(2)
    })

    it('answers nothing for nothing', () => {
        expect(shelveFindings([])).toEqual([])
    })
})

describe('groupByResourceType', () => {
    it('keeps the order the server sent inside one group', () => {
        const groups = groupByResourceType([
            finding({ uid: 'Bbb11111111' }),
            finding({ uid: 'Aaa11111111' }),
        ])
        expect(groups[0].findings.map((held) => held.uid)).toEqual(['Bbb11111111', 'Aaa11111111'])
    })
})

describe('matchingFindings', () => {
    const findings = [
        finding({ uid: 'DeAncVisit1', name: 'ANC 1st visit' }),
        finding({ uid: 'OuClinic001', name: 'Ngelehun CHC' }),
    ]

    it('leaves everything alone for an empty filter', () => {
        expect(matchingFindings(findings, '   ')).toHaveLength(2)
    })

    it('matches part of a name, whatever the case', () => {
        expect(matchingFindings(findings, 'ngelehun').map((held) => held.uid)).toEqual(['OuClinic001'])
    })

    it('matches a uid somebody copied out of a build log', () => {
        expect(matchingFindings(findings, 'DeAncVisit1').map((held) => held.uid)).toEqual(['DeAncVisit1'])
    })
})

describe('matchingGaps', () => {
    it('narrows the gaps by the same two strings the findings are narrowed by', () => {
        const gaps = [gap({ uid: 'DeAncVisit1' }), gap({ uid: 'OuClinic001', name: 'Ngelehun CHC' })]
        expect(matchingGaps(gaps, 'clinic').map((held) => held.uid)).toEqual(['OuClinic001'])
        expect(matchingGaps(gaps, '')).toHaveLength(2)
    })
})

describe('coverageRatio', () => {
    it('counts every translatable string, so a form name is a second string on one object', () => {
        const held = coverage({ object_count: 10, form_named_count: 4 })
        expect(coverageRatio(held, locale('fr', 10, 4))).toEqual({
            locale: 'fr',
            covered: 14,
            total: 14,
            share: 1,
        })
    })

    it('reads a locale that has the names and none of the form names as half done', () => {
        const held = coverage({ object_count: 6, form_named_count: 6 })
        expect(coverageRatio(held, locale('lo', 6, 0)).share).toBe(0.5)
    })

    it('reads a selection with nothing to translate as complete rather than dividing by zero', () => {
        const ratio = coverageRatio(coverage(), locale('lo', 0, 0))
        expect(ratio.total).toBe(0)
        expect(ratio.share).toBe(1)
    })
})

describe('coverageRatios', () => {
    it('puts the language somebody stopped translating first', () => {
        const held = coverage({
            locales: ['fr', 'lo', 'pt-BR'],
            object_count: 4,
            form_named_count: 0,
            per_locale: [locale('fr', 4), locale('lo', 1), locale('pt-BR', 2)],
        })
        expect(coverageRatios(held).map((ratio) => ratio.locale)).toEqual(['lo', 'pt-BR', 'fr'])
    })

    it('breaks a tie on the locale tag, so the strip does not reorder between reads', () => {
        const held = coverage({
            locales: ['lo', 'fr'],
            object_count: 2,
            per_locale: [locale('lo', 1), locale('fr', 1)],
        })
        expect(coverageRatios(held).map((ratio) => ratio.locale)).toEqual(['fr', 'lo'])
    })

    it('answers nothing for an instance nobody has translated', () => {
        expect(coverageRatios(coverage({ object_count: 12 }))).toEqual([])
    })
})

describe('coveragePercent', () => {
    it('rounds to the whole percent a strip this size can carry', () => {
        expect(coveragePercent({ locale: 'lo', covered: 1, total: 3, share: 1 / 3 })).toBe(33)
        expect(coveragePercent({ locale: 'fr', covered: 2, total: 3, share: 2 / 3 })).toBe(67)
    })
})
