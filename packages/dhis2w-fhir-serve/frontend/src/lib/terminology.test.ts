import { describe, expect, it } from 'vitest'

import attributeComboFixture from '@/lib/__fixtures__/codesystem-d2-aoc-idcDPkDtepR-cs.json'
import codeSystemFixture from '@/lib/__fixtures__/codesystem-d2-de-cs.json'
import conceptMapFixture from '@/lib/__fixtures__/conceptmap-d2-os-OsSymptom01-cm.json'
import optionSetFixture from '@/lib/__fixtures__/codesystem-d2-os-OsSymptom01-cs.json'
import translateFoundFixture from '@/lib/__fixtures__/translate-OpFever0001.json'
import translateNotFoundFixture from '@/lib/__fixtures__/translate-not-found.json'
import valueSetFixture from '@/lib/__fixtures__/valueset-d2-os-OsSymptom01-vs.json'
import type { CodeSystem, ConceptMap, Parameters, ValueSet } from '@/lib/fhir'
import {
    CONCEPT_FILTER_PARAMETER,
    composedSystems,
    conceptPropertyCoding,
    conceptPropertyCodingLink,
    conceptPropertyColumns,
    conceptPropertyValue,
    enumeratedConceptCount,
    filterConcepts,
    identifierBadges,
    mappingCount,
    mappingRows,
    matchesQuery,
    pageOf,
    systemLabel,
    targetSystems,
    translationResult, matchingCodeCount } from '@/lib/terminology'

/**
 * The terminology reading rules, checked against what the server actually answers.
 *
 * Every fixture here was harvested from a running `d2w fhir serve` over the capture project the
 * Python suite serves (packages/dhis2w-fhir-serve/tests/fixture_project.py) - the data-dictionary
 * CodeSystem with its two property kinds, the ConceptMap the option-set emitter writes, and both
 * shapes `$translate` answers in. So these are the wire shapes, not approximations of them.
 */

const dataElements = codeSystemFixture as CodeSystem
const attributeCombos = attributeComboFixture as CodeSystem
const optionSet = optionSetFixture as CodeSystem
const conceptMap = conceptMapFixture as ConceptMap
const symptomValueSet = valueSetFixture as ValueSet
const translateFound = translateFoundFixture as Parameters
const translateNotFound = translateNotFoundFixture as Parameters

describe('concept property columns', () => {
    it('discovers a column per declared property, headed by the code as words with the description as tooltip', () => {
        expect(conceptPropertyColumns(dataElements)).toEqual([
            {
                code: 'dhis2-code',
                label: 'DHIS2 code',
                description: 'DHIS2 data element code',
                uri: 'http://dhis2.org/fhir/property/dhis2-code',
                declared: true,
            },
            {
                code: 'domain',
                label: 'Domain',
                description: 'DHIS2 data element domain type',
                uri: 'http://dhis2.org/fhir/property/domain',
                declared: true,
            },
        ])
    })

    it('heads a per-object column with the name its declaration states, never the uid', () => {
        const combos = {
            resourceType: 'CodeSystem',
            property: [
                {
                    code: 'category-yY2bQYqNt0o',
                    uri: 'http://dhis2.org/fhir/property/category-yY2bQYqNt0o',
                    description: 'DHIS2 category Project.',
                    type: 'Coding',
                },
                {
                    code: 'searchable-IpHINAT79UW',
                    uri: 'http://dhis2.org/fhir/property/searchable-IpHINAT79UW',
                    description:
                        'Whether DHIS2 declares the tracked entity attribute searchable in tracker program Child Programme (IpHINAT79UW).',
                    type: 'boolean',
                },
            ],
            concept: [],
        } as unknown as typeof dataElements
        expect(conceptPropertyColumns(combos).map((column) => column.label)).toEqual([
            'Project',
            'Searchable in Child Programme',
        ])
    })

    it('heads the column from the code alone when the system describes none', () => {
        expect(conceptPropertyColumns(optionSet)).toEqual([
            {
                code: 'dhis2-code',
                label: 'DHIS2 code',
                description: undefined,
                uri: 'http://dhis2.org/fhir/property/dhis2-code',
                declared: true,
            },
        ])
    })

    it('keeps a property a concept carries but the system never declared', () => {
        const columns = conceptPropertyColumns({
            resourceType: 'CodeSystem',
            status: 'draft',
            property: [{ code: 'dhis2-code' }],
            concept: [{ code: 'X', property: [{ code: 'undeclared', valueString: 'here anyway' }] }],
        })
        expect(columns.map((column) => [column.code, column.declared])).toEqual([
            ['dhis2-code', true],
            ['undeclared', false],
        ])
    })

    it('answers nothing for a system with no properties at all', () => {
        expect(conceptPropertyColumns({ resourceType: 'CodeSystem', status: 'draft' })).toEqual([])
    })
})

describe('concept property values', () => {
    it('reads both value[x] variants one generated system uses', () => {
        const concept = dataElements.concept?.[0]
        expect(concept).toBeDefined()
        // `dhis2-code` is a string property and `domain` a code property, in the same document.
        expect(conceptPropertyValue(concept!, 'dhis2-code')).toBe('DeAncDanger')
        expect(conceptPropertyValue(concept!, 'domain')).toBe('tracker')
    })

    it('answers null for a property the concept does not carry', () => {
        expect(conceptPropertyValue({ code: 'X' }, 'dhis2-code')).toBeNull()
        expect(conceptPropertyValue({ code: 'X', property: [{ code: 'empty' }] }, 'empty')).toBeNull()
    })

    it('renders the remaining variants as text', () => {
        const concept = {
            code: 'X',
            property: [
                { code: 'count', valueInteger: 3 },
                { code: 'ratio', valueDecimal: 1.5 },
                { code: 'flag', valueBoolean: false },
                { code: 'coded', valueCoding: { code: 'CODED' } },
            ],
        }
        expect(conceptPropertyValue(concept, 'count')).toBe('3')
        expect(conceptPropertyValue(concept, 'ratio')).toBe('1.5')
        expect(conceptPropertyValue(concept, 'flag')).toBe('false')
        expect(conceptPropertyValue(concept, 'coded')).toBe('CODED')
    })
})

describe('a property valued as a coding', () => {
    it('reads the coding a category option combo states each of its axes as', () => {
        const concept = attributeCombos.concept?.[0]
        expect(concept).toBeDefined()
        expect(conceptPropertyCoding(concept!, 'category-yY2bQYqNt0o')).toEqual({
            system: 'http://localhost:8080/fhir/CodeSystem/d2-cat-yY2bQYqNt0o-cs',
            code: 'i4Nbp8S2G6A',
            display: 'Improve access to clean water',
        })
        expect(conceptPropertyCoding(concept!, 'dhis2-code')).toBeNull()
    })

    it('links to the code system the coding names, filtered to the concept it codes', () => {
        const concept = attributeCombos.concept?.[0]
        expect(conceptPropertyCodingLink(conceptPropertyCoding(concept!, 'category-yY2bQYqNt0o')!)).toEqual({
            label: 'Improve access to clean water',
            isCode: false,
            to: '/terminology/CodeSystem/d2-cat-yY2bQYqNt0o-cs?code=i4Nbp8S2G6A',
        })
    })

    it('works for any coding-valued property, not just the ones the category axes emit', () => {
        expect(
            conceptPropertyCodingLink({
                system: 'https://example.org/fhir/CodeSystem/some-other-system',
                code: 'A code with spaces',
            }),
        ).toEqual({
            label: 'A code with spaces',
            isCode: true,
            to: '/terminology/CodeSystem/some-other-system?code=A%20code%20with%20spaces',
        })
    })

    it('names the filter parameter the concept table reads its filter from', () => {
        expect(CONCEPT_FILTER_PARAMETER).toBe('code')
    })

    it('leaves a coding this server publishes no page for as plain text', () => {
        // A ValueSet canonical, an external terminology, and a coding with no system at all: each
        // is real data with nowhere to go, and a link to nowhere is worse than the code itself.
        expect(conceptPropertyCodingLink({ system: 'http://localhost:8080/fhir/ValueSet/d2-cat-x-vs', code: 'A' }))
            .toBeNull()
        expect(conceptPropertyCodingLink({ system: 'http://snomed.info/sct', code: '260385009' })).toBeNull()
        expect(conceptPropertyCodingLink({ code: 'A' })).toBeNull()
        expect(
            conceptPropertyCodingLink({ system: 'http://localhost:8080/fhir/CodeSystem/d2-cat-x-cs' }),
        ).toBeNull()
    })
})

describe('filtering concepts', () => {
    it('matches a code, a display, or a property value', () => {
        expect(filterConcepts(optionSet.concept ?? [], 'fever').map((concept) => concept.code)).toEqual([
            'OpFever0001',
        ])
        expect(filterConcepts(optionSet.concept ?? [], 'COUGH').map((concept) => concept.code)).toEqual([
            'OpCough0001',
        ])
        expect(filterConcepts(optionSet.concept ?? [], 'OpFever').map((concept) => concept.code)).toEqual([
            'OpFever0001',
        ])
    })

    it('keeps everything for an empty query', () => {
        expect(filterConcepts(dataElements.concept ?? [], '   ')).toHaveLength(70)
    })

    it('answers nothing when the query matches nothing', () => {
        expect(filterConcepts(optionSet.concept ?? [], 'nothing here')).toEqual([])
    })
})

describe('client pagination', () => {
    it('slices a long system into pages and counts what is on screen', () => {
        const concepts = dataElements.concept ?? []
        const first = pageOf(concepts, 1, 25)
        expect(first.rows).toHaveLength(25)
        expect(first).toMatchObject({ page: 1, pageCount: 3, shown: 25, total: 70 })
        expect(pageOf(concepts, 3, 25)).toMatchObject({ page: 3, shown: 20, total: 70 })
    })

    it('clamps a page beyond the end rather than showing an empty table', () => {
        // What a filter does: the rows shrink under a page number the user is already on.
        expect(pageOf(dataElements.concept ?? [], 9, 25).page).toBe(3)
        expect(pageOf(dataElements.concept ?? [], 0, 25).page).toBe(1)
    })

    it('reports one empty page for no rows at all', () => {
        expect(pageOf([], 1, 25)).toEqual({ rows: [], page: 1, pageCount: 1, shown: 0, total: 0 })
    })

    it('leaves a list shorter than one page whole', () => {
        expect(pageOf(optionSet.concept ?? [], 1).total).toBe(2)
        expect(pageOf(optionSet.concept ?? [], 1).pageCount).toBe(1)
    })
})

describe('a real ConceptMap', () => {
    it('counts one mapping per target, not per source concept', () => {
        // Two concepts, two groups (option uid and option code), so four mappings.
        expect(mappingCount(conceptMap)).toBe(4)
    })

    it('names the target systems in the order the map states them', () => {
        expect(targetSystems(conceptMap)).toEqual([
            'http://dhis2.org/fhir/id/option',
            'http://dhis2.org/fhir/id/option-code',
        ])
    })

    it('flattens one group into rows a table can show', () => {
        const codeGroup = (conceptMap.group ?? []).find(
            (group) => group.target === 'http://dhis2.org/fhir/id/option-code',
        )
        expect(codeGroup).toBeDefined()
        expect(mappingRows(codeGroup!)).toEqual([
            {
                code: 'OpFever0001',
                display: 'Fever',
                targetCode: 'FEVER',
                targetDisplay: null,
                equivalence: 'equal',
            },
            {
                code: 'OpCough0001',
                display: 'Cough',
                targetCode: 'COUGH',
                targetDisplay: null,
                equivalence: 'equal',
            },
        ])
    })

    it('drops a target that maps a concept onto no code at all', () => {
        expect(mappingRows({ element: [{ code: 'X', target: [{ equivalence: 'unmatched' }] }] })).toEqual([])
    })

    it('reads the single-element identifier R4 gives a map', () => {
        expect(identifierBadges(conceptMap.identifier)).toEqual([
            { label: 'id/option-set', value: 'OsSymptom01' },
        ])
    })
})

describe('identifier badges', () => {
    it('reads the list form every other definitional resource uses', () => {
        expect(
            identifierBadges([
                { system: 'http://dhis2.org/fhir/id/program', value: 'ZzYYXq4fJie' },
                { system: 'http://dhis2.org/fhir/code/program', value: 'ANC_VISIT' },
            ]),
        ).toEqual([
            { label: 'id/program', value: 'ZzYYXq4fJie' },
            { label: 'code/program', value: 'ANC_VISIT' },
        ])
    })

    it('skips an identifier carrying no value, and names a system-less one', () => {
        expect(identifierBadges([{ system: 'http://x/id/thing' }, { value: 'bare' }])).toEqual([
            { label: 'identifier', value: 'bare' },
        ])
        expect(identifierBadges(undefined)).toEqual([])
    })
})

describe('systemLabel', () => {
    it('reads the last two segments, which is what names a DHIS2 identifier system', () => {
        expect(systemLabel('http://dhis2.org/fhir/id/option-code')).toBe('id/option-code')
        expect(systemLabel('http://localhost:8080/fhir/CodeSystem/d2-de-cs')).toBe('CodeSystem/d2-de-cs')
        expect(systemLabel(undefined)).toBe('identifier')
    })
})

describe('a real ValueSet', () => {
    it('names the system it composes without enumerating any concept', () => {
        expect(composedSystems(symptomValueSet)).toEqual([
            'http://localhost:8080/fhir/CodeSystem/d2-os-OsSymptom01-cs',
        ])
        expect(enumeratedConceptCount(symptomValueSet)).toBe(0)
    })

    it('counts the concepts an enumerating set names outright', () => {
        expect(
            enumeratedConceptCount({
                resourceType: 'ValueSet',
                status: 'draft',
                compose: { include: [{ system: 'http://x', concept: [{ code: 'a' }, { code: 'b' }] }] },
            }),
        ).toBe(2)
    })
})

describe('a real $translate answer', () => {
    it('reads both DHIS2 identifiers one concept maps onto', () => {
        expect(translationResult(translateFound)).toEqual({
            matched: true,
            message: null,
            matches: [
                {
                    system: 'http://dhis2.org/fhir/id/option',
                    code: 'OpFever0001',
                    display: 'Fever',
                    equivalence: 'equal',
                    source: 'http://localhost:8080/fhir/ConceptMap/d2-os-OsSymptom01-cm',
                },
                {
                    system: 'http://dhis2.org/fhir/id/option-code',
                    code: 'FEVER',
                    display: 'Fever',
                    equivalence: 'equal',
                    source: 'http://localhost:8080/fhir/ConceptMap/d2-os-OsSymptom01-cm',
                },
            ],
        })
    })

    it('reads a miss as an answer with a message, not as a failure', () => {
        const result = translationResult(translateNotFound)
        expect(result.matched).toBe(false)
        expect(result.matches).toEqual([])
        expect(result.message).toContain('no ConceptMap served here maps `NoSuchCode`')
    })

    it('drops a match whose concept carries no code, and answers empty for no parameters', () => {
        expect(
            translationResult({
                resourceType: 'Parameters',
                parameter: [
                    { name: 'result', valueBoolean: true },
                    { name: 'match', part: [{ name: 'concept', valueCoding: { system: 'http://x' } }] },
                ],
            }).matches,
        ).toEqual([])
        expect(translationResult({ resourceType: 'Parameters' })).toEqual({
            matched: false,
            matches: [],
            message: null,
        })
    })
})

describe('matchesQuery', () => {
    it('matches case-insensitively across every text it is given', () => {
        expect(matchesQuery('FEV', 'OpFever0001', 'Fever')).toBe(true)
        expect(matchesQuery('cough', 'OpFever0001', 'Fever')).toBe(false)
    })

    it('admits everything for a blank query', () => {
        expect(matchesQuery('  ', undefined, null)).toBe(true)
    })
})

/**
 * The support CodeSystem behind a tracker registration form, and its one boolean column.
 *
 * `D2TEA_CS` is the data dictionary of tracked entity attributes - the terminology the questions
 * of a registration Questionnaire are coded through - and it declares one property no other
 * generated system does: `unique`, valued `valueBoolean`, saying whether DHIS2 enforces the
 * attribute as unique across the instance. A table that read only the string variants would show
 * an empty column for it, and an empty cell reads as "not unique" rather than as "not rendered",
 * which is the wrong answer twice over. Written from the emitter
 * (dhis2w_fhir's questionnaires/templates/support-terminology.fsh.jinja) rather than harvested, so
 * the column rules are pinned without a server; the e2e terminology walkthrough checks the same
 * columns against the `d2-tea-cs` the fixture project really publishes.
 */
describe('a tracked-entity-attribute support system', () => {
    const attributes: CodeSystem = {
        resourceType: 'CodeSystem',
        id: 'd2-tea-cs',
        status: 'active',
        property: [
            { code: 'dhis2-code', type: 'string', description: 'The DHIS2 code.' },
            { code: 'value-type', type: 'code', description: 'The DHIS2 value type.' },
            { code: 'unique', type: 'boolean', description: 'Whether DHIS2 enforces uniqueness.' },
        ],
        concept: [
            {
                code: 'TeaNatId001',
                display: 'National identifier',
                property: [
                    { code: 'dhis2-code', valueString: 'TEA_NAT_ID' },
                    { code: 'value-type', valueCode: 'TEXT' },
                    { code: 'unique', valueBoolean: true },
                ],
            },
            {
                code: 'TeaFirstNm1',
                display: 'First name',
                property: [
                    { code: 'dhis2-code', valueString: 'TEA_FIRST_NAME' },
                    { code: 'value-type', valueCode: 'TEXT' },
                    { code: 'unique', valueBoolean: false },
                ],
            },
        ],
    }

    it('heads the boolean column with the property code said as words', () => {
        expect(conceptPropertyColumns(attributes).map((column) => column.label)).toEqual([
            'DHIS2 code',
            'Value type',
            'Unique',
        ])
    })

    it('renders both booleans, so an unset column is not read as a false one', () => {
        const unique = attributes.concept?.[0]
        const ordinary = attributes.concept?.[1]
        expect(conceptPropertyValue(unique!, 'unique')).toBe('true')
        expect(conceptPropertyValue(ordinary!, 'unique')).toBe('false')
    })

    it('finds a concept by its boolean property, because the filter reads every column', () => {
        expect(filterConcepts(attributes.concept ?? [], 'true').map((concept) => concept.code)).toEqual([
            'TeaNatId001',
        ])
    })
})

describe('matching codes inside a listed resource', () => {
    it('counts concepts a query matches by code or display', () => {
        expect(matchingCodeCount(dataElements, 'DeAncDanger')).toBe(1)
        expect(matchingCodeCount(dataElements, 'zzz-nothing')).toBe(0)
    })

    it('answers zero for an empty query - the deep filter only bites while searching', () => {
        expect(matchingCodeCount(dataElements, '')).toBe(0)
    })

    it('counts mapping rows on a concept map by source and target spellings', () => {
        expect(matchingCodeCount(conceptMap, 'OpFever0001')).toBeGreaterThan(0)
        expect(matchingCodeCount(conceptMap, 'FEVER')).toBeGreaterThan(0)
    })
})
