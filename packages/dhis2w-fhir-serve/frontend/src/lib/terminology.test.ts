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
    CONCEPTS_ELSEWHERE,
    NOTHING_ASKED,
    TERMINOLOGY_FILTER_PARAMETER,
    TERMINOLOGY_ORIGINS,
    terminologyShelfCaption,
    TRANSLATE_QUESTION,
    askedConcept,
    codeSystemContentLabel,
    composedSystems,
    conceptPropertyCoding,
    conceptPropertyCodingLink,
    conceptPropertyColumns,
    conceptPropertyTreatment,
    conceptPropertyValue,
    declaredColumnLabel,
    enumeratedConceptCount,
    filterConcepts,
    identifierBadges,
    mappingCount,
    mappingRows,
    mapsFromSystem,
    matchesQuery,
    nothingMatchesMessage,
    pageOf,
    statedBooleanLabel,
    systemLabel,
    targetSystems,
    terminologyRowLink,
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

/**
 * Which property columns hold a value out of a small fixed set.
 *
 * KEYED ON THE PROPERTY CODE, WHICH IS THE PART THE SERVED DOCUMENT GUARANTEES. `d2-de-cs` declares
 * `domain` and `value-type` with their own `uri` and a type of `code`; nothing guarantees a value
 * anywhere else in the guide will not read like one of theirs, and a category option named
 * "Aggregate" must not turn into a tinted chip because a string matched.
 */
describe('the treatment a concept property column wears', () => {
    it('chips the two columns whose values come out of a fixed set', () => {
        expect(conceptPropertyTreatment('domain')).toBe('domain')
        expect(conceptPropertyTreatment('value-type')).toBe('value-type')
    })

    it('leaves every other property of the generated systems plain', () => {
        for (const code of ['dhis2-code', 'unique', 'searchable', 'generated', 'pattern', 'display-in-list']) {
            expect(conceptPropertyTreatment(code), code).toBe('plain')
        }
    })

    it('leaves a per-object column plain, whatever the object is called', () => {
        expect(conceptPropertyTreatment('category-fMZEcRHuamy')).toBe('plain')
        expect(conceptPropertyTreatment('searchable-IpHINAT79UW')).toBe('plain')
    })

    it('reads the code rather than the value, so a lookalike display stays plain', () => {
        expect(conceptPropertyTreatment('Domain')).toBe('plain')
        expect(conceptPropertyTreatment('aggregate')).toBe('plain')
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

    it('draws one badge for a DHIS2 object whose code is its uid', () => {
        // Two chips reading `id/option-set OsSymptom01` and `code/option-set OsSymptom01` are one
        // identifier wearing two prefixes, and telling them apart costs a character-by-character
        // read. The first system the resource states keeps the value.
        expect(
            identifierBadges([
                { system: 'http://dhis2.org/fhir/id/option-set', value: 'OsSymptom01' },
                { system: 'http://dhis2.org/fhir/code/option-set', value: 'OsSymptom01' },
            ]),
        ).toEqual([{ label: 'id/option-set', value: 'OsSymptom01' }])
    })
})

/**
 * A shelf's caption on each of the three tabs.
 *
 * The shelf is a DHIS2 origin and the tab is a FHIR resource, and a caption naming only the first
 * told a reader of the concept maps that they were looking at option sets.
 */
describe('a terminology shelf caption', () => {
    const optionSets = TERMINOLOGY_ORIGINS[0]

    it('names the resource the tab shows', () => {
        expect(terminologyShelfCaption(optionSets, 'ConceptMap')).toBe(
            'The concept maps published for the option sets this DHIS2 instance declares. What a coded question is answered from.',
        )
        expect(terminologyShelfCaption(optionSets, 'CodeSystem')).toBe(
            'The code systems published for the option sets this DHIS2 instance declares. What a coded question is answered from.',
        )
    })

    it('stops at the subject where the shelf states nothing further', () => {
        const other = TERMINOLOGY_ORIGINS[TERMINOLOGY_ORIGINS.length - 1]
        expect(terminologyShelfCaption(other, 'ValueSet')).toBe(
            'The value sets published for DHIS2 objects outside the identifier conventions the shelves above are read from.',
        )
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

/**
 * The column header a category vocabulary gets, which its own prose argues against.
 *
 * Every category and combo system describes its `dhis2-code` property as "DHIS2 category option
 * code." - a sentence shaped exactly like a category-axis declaration and naming nothing of the
 * kind. Reading the prose first heads the DHIS2-code column "option code" on all 25 category
 * systems and "option combo code" on the combo one, and the deliberate "DHIS2 code" header is
 * never reached. The property code is what says which kind of column this is.
 */
describe('a column headed off a declaration that reads like another one', () => {
    it('heads the DHIS2-code column by its subject, whatever the category prose says', () => {
        expect(declaredColumnLabel('dhis2-code', 'DHIS2 category option code.')).toBe('DHIS2 code')
        expect(declaredColumnLabel('dhis2-code', 'DHIS2 category option combo code.')).toBe('DHIS2 code')
    })

    it('reads a category name only off a property published as a category axis', () => {
        expect(declaredColumnLabel('category-fMZEcRHuamy', 'DHIS2 category Sex.')).toBe('Sex')
        expect(declaredColumnLabel('dhis2-id', 'DHIS2 category option UID.')).toBe('ID')
    })

    it('heads a real combo vocabulary with both of its columns named', () => {
        expect(conceptPropertyColumns(attributeCombos).map((column) => column.label)).toEqual([
            'DHIS2 code',
            'Project',
        ])
    })
})

/**
 * Asking twice about the same row, which is a real question and used to be a no-op.
 *
 * A row asks by handing the tester a code. Held as a bare string, the second press on one row sets
 * the state it already holds, React keeps the render, and the tester never re-runs - so a reader
 * who typed over the box cannot get their row's answer back. The ask carries a number instead.
 */
describe('what a concept row asks', () => {
    it('is a different ask every time, even about the same code', () => {
        const first = askedConcept(NOTHING_ASKED, 'OpFever0001')
        const again = askedConcept(first, 'OpFever0001')
        expect(again.code).toBe('OpFever0001')
        expect(again.nonce).not.toBe(first.nonce)
        expect(again).not.toEqual(first)
    })

    it('carries no target from a code system, and the target of its group from a map', () => {
        expect(askedConcept(NOTHING_ASKED, 'OpFever0001').targetSystem).toBeNull()
        expect(
            askedConcept(NOTHING_ASKED, 'OpFever0001', 'http://dhis2.org/fhir/id/option-code')
                .targetSystem,
        ).toBe('http://dhis2.org/fhir/id/option-code')
    })

    it('starts from nothing asked', () => {
        expect(NOTHING_ASKED).toEqual({ code: '', targetSystem: null, nonce: 0 })
    })
})

describe('which systems have a translation to offer', () => {
    it('says yes for a system a served map names as a group source', () => {
        expect(mapsFromSystem([conceptMap], optionSet.url)).toBe(true)
    })

    it('says no for the data dictionary, which no map translates from', () => {
        expect(mapsFromSystem([conceptMap], dataElements.url)).toBe(false)
    })

    it('says no for a system that is only ever a map target, and for no system at all', () => {
        expect(mapsFromSystem([conceptMap], 'http://dhis2.org/fhir/id/option')).toBe(false)
        expect(mapsFromSystem([conceptMap], undefined)).toBe(false)
        expect(mapsFromSystem([], optionSet.url)).toBe(false)
    })
})

describe('how a listing row opens', () => {
    it('carries the search that found codes inside the artifact', () => {
        expect(terminologyRowLink('CodeSystem', 'd2-de-cs', 'Fever')).toBe(
            '/terminology/CodeSystem/d2-de-cs?code=Fever',
        )
    })

    it('carries nothing when there is nothing to carry', () => {
        expect(terminologyRowLink('ValueSet', 'd2-os-OsSymptom01-vs', '   ')).toBe(
            '/terminology/ValueSet/d2-os-OsSymptom01-vs',
        )
    })

    it('escapes what it carries, so a query is never a second parameter', () => {
        expect(terminologyRowLink('CodeSystem', 'd2-de-cs', 'a&b c')).toBe(
            '/terminology/CodeSystem/d2-de-cs?code=a%26b%20c',
        )
    })

    it('keeps the listing filter apart from the concept filter it hands on', () => {
        expect(TERMINOLOGY_FILTER_PARAMETER).toBe('q')
        expect(TERMINOLOGY_FILTER_PARAMETER).not.toBe(CONCEPT_FILTER_PARAMETER)
    })
})

describe('how a count and a code are said', () => {
    it('states the query a filter admitted nothing for', () => {
        expect(nothingMatchesMessage('zzzz')).toBe('Nothing here matches "zzzz".')
        expect(nothingMatchesMessage(' Fever ')).toBe('Nothing here matches "Fever".')
    })

    it('says what a content code means rather than printing the code', () => {
        // The ordinary vocabulary holds its concepts, and a fact saying so on every page is one
        // nobody reads - so the complete case, and a system declaring nothing, both say nothing.
        expect(codeSystemContentLabel('complete')).toBeNull()
        expect(codeSystemContentLabel(undefined)).toBeNull()
        // The page that does not carry its concepts is the one worth a sentence, and both codes
        // that mean it get the same one.
        expect(codeSystemContentLabel('not-present')).toBe(CONCEPTS_ELSEWHERE)
        expect(codeSystemContentLabel('fragment')).toBe(CONCEPTS_ELSEWHERE)
        // A code this server has never published is stated as it stands rather than guessed at.
        expect(codeSystemContentLabel('brand-new')).toBe('brand-new')
    })

    it('answers a declared boolean, and states the dash where nothing is declared', () => {
        expect(statedBooleanLabel(true)).toBe('Yes')
        expect(statedBooleanLabel(false)).toBe('No')
        expect(statedBooleanLabel(undefined)).toBe('-')
    })

    it('asks the translation question of an instance, not of the platform', () => {
        expect(TRANSLATE_QUESTION).toContain('this DHIS2 instance')
    })
})
