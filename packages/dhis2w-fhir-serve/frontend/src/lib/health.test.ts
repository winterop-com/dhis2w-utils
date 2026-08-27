import { describe, expect, it } from 'vitest'

import {
    countOf,
    coveragePercent,
    coverageRatio,
    coverageRatios,
    findingMessage,
    groupByResourceType,
    isClean,
    listedCount,
    matchingFindings,
    matchingObjects,
    matchingRatios,
    shelveFindings,
    EMPTY_METADATA_HEALTH,
    type LocaleCarrier,
    type LocaleCoverage,
    type LocaleUntranslated,
    type MetadataFinding,
    type MetadataHealth,
    type TranslationCoverage,
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
    return { locales: [], object_count: 0, form_named_count: 0, per_locale: [], ...overrides }
}

function locale(
    tag: string,
    nameCount: number,
    formNameCount = 0,
    overrides: Partial<LocaleCoverage> = {},
): LocaleCoverage {
    return {
        locale: tag,
        name_count: nameCount,
        form_name_count: formNameCount,
        standing: 'sparse',
        carriers: [],
        missing: [],
        ...overrides,
    }
}

function carrier(overrides: Partial<LocaleCarrier> = {}): LocaleCarrier {
    return {
        resource_type: 'dataElements',
        uid: 'DeAncVisit1',
        name: 'ANC 1st visit',
        carries_name: true,
        carries_form_name: false,
        ...overrides,
    }
}

function untranslated(overrides: Partial<LocaleUntranslated> = {}): LocaleUntranslated {
    return {
        resource_type: 'dataElements',
        uid: 'DeAncVisit1',
        name: 'ANC 1st visit',
        name_untranslated: true,
        form_name_untranslated: false,
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
    it('is clean when nothing was found and nothing carries a translation', () => {
        expect(isClean(EMPTY_METADATA_HEALTH)).toBe(true)
    })

    it('has a page to show for a locale in use, which is a fact rather than a defect', () => {
        const health: MetadataHealth = {
            ...EMPTY_METADATA_HEALTH,
            translations: coverage({ locales: ['lo'], object_count: 4, per_locale: [locale('lo', 1)] }),
        }
        expect(isClean(health)).toBe(false)
    })

    it('is not clean for a finding alone', () => {
        expect(isClean({ ...EMPTY_METADATA_HEALTH, findings: [finding()] })).toBe(false)
    })
})

describe('findingMessage', () => {
    it('cuts the head the Object and Field columns already carry, and raises the sentence', () => {
        const held = finding({
            field: 'name',
            name: 'CMC Post abortion related services',
            category: 'template-hostile-name',
            message:
                "name CMC Post abortion related services contains '&' which the IG publisher template injects into HTML unescaped",
        })
        expect(findingMessage(held)).toBe(
            "Contains '&' which the IG publisher template injects into HTML unescaped",
        )
    })

    it('leaves a message that does not open with that exact head alone', () => {
        const held = finding({
            field: 'code',
            message: 'code is not a valid FHIR code: code has leading whitespace',
        })
        expect(findingMessage(held)).toBe('code is not a valid FHIR code: code has leading whitespace')
    })

    it('leaves a form-name message alone where the form name differs from the object name', () => {
        const held = finding({
            field: 'form name',
            name: 'Weight',
            message: "form name Weight in kg contains '<' which the IG publisher template injects into HTML",
        })
        expect(findingMessage(held)).toBe(
            "form name Weight in kg contains '<' which the IG publisher template injects into HTML",
        )
    })

    it('leaves a message alone where the finding is about no field of the object', () => {
        const held = finding({ field: null, message: 'attribute has no code; every extension omits it' })
        expect(findingMessage(held)).toBe('attribute has no code; every extension omits it')
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

describe('matchingObjects', () => {
    it('narrows a translation list by the same two strings the findings are narrowed by', () => {
        const carriers = [carrier({ uid: 'DeAncVisit1' }), carrier({ uid: 'OuClinic001', name: 'Ngelehun CHC' })]
        expect(matchingObjects(carriers, 'clinic').map((held) => held.uid)).toEqual(['OuClinic001'])
        expect(matchingObjects(carriers, '')).toHaveLength(2)
    })
})

describe('matchingRatios', () => {
    it('narrows the objects a locale lists and leaves its counts where they are', () => {
        const held = coverage({
            locales: ['es'],
            object_count: 40,
            per_locale: [
                locale('es', 2, 0, {
                    standing: 'sparse',
                    carriers: [carrier({ uid: 'DeAncVisit1' }), carrier({ uid: 'OuClinic001', name: 'Ngelehun' })],
                }),
            ],
        })
        const [ratio] = matchingRatios(held, 'ngelehun')
        expect(ratio.carriers.map((carried) => carried.uid)).toEqual(['OuClinic001'])
        expect(ratio.covered).toBe(2)
    })
})

describe('listedCount', () => {
    it('counts the carriers of a sparse locale and the objects short of a majority one', () => {
        const held = coverage({
            locales: ['es', 'fr'],
            object_count: 4,
            per_locale: [
                locale('es', 1, 0, { standing: 'sparse', carriers: [carrier()] }),
                locale('fr', 3, 0, { standing: 'majority', missing: [untranslated(), untranslated({ uid: 'Ou1' })] }),
            ],
        })
        const [sparse, majority] = coverageRatios(held).toSorted((left, right) =>
            left.locale.localeCompare(right.locale),
        )
        expect(listedCount(sparse)).toBe(1)
        expect(listedCount(majority)).toBe(2)
    })
})

describe('coverageRatio', () => {
    it('counts every translatable string, so a form name is a second string on one object', () => {
        const held = coverage({ object_count: 10, form_named_count: 4 })
        expect(coverageRatio(held, locale('fr', 10, 4, { standing: 'majority' }))).toEqual({
            locale: 'fr',
            covered: 14,
            total: 14,
            share: 1,
            standing: 'majority',
            carriers: [],
            missing: [],
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
        const held = { standing: 'sparse' as const, carriers: [], missing: [] }
        expect(coveragePercent({ locale: 'lo', covered: 1, total: 3, share: 1 / 3, ...held })).toBe(33)
        expect(coveragePercent({ locale: 'fr', covered: 2, total: 3, share: 2 / 3, ...held })).toBe(67)
    })
})
