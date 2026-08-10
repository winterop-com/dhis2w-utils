/**
 * Reading terminology: what a code system holds, what a map states, what $translate answered.
 *
 * WHY THIS IS A MODULE AND NOT PAGE CODE. Three of the rules here are the kind that look
 * obvious until the wire disagrees. Property columns are *declared* by a CodeSystem and
 * *carried* by its concepts, and the two sets are allowed to differ - a concept can carry a
 * property the system never declared, and a declared property can go unused. Concept property
 * values are a `value[x]` choice, so `dhis2-code` arrives as `valueString` and `domain` as
 * `valueCode` in the very same document. And `$translate` states its failure as a 200 with
 * `result: false` plus a `message`, not as an error - a caller that only catches would report
 * "the server refused" for a code the maps simply say nothing about.
 *
 * Everything here is pure, so all three rules are tested against harvested documents with no
 * server involved. The network stays behind the choke point in lib/api.ts.
 */

import type {
    CodeSystem,
    CodeSystemConcept,
    ConceptMap,
    ConceptMapGroup,
    Identifier,
    Parameters,
    ParametersParameter,
    ValueSet,
} from '@/lib/fhir'

/** How many concepts one page of a code-system detail shows. */
export const CONCEPT_PAGE_SIZE = 200

/** One property column a concept table shows: the concept property code, and how it is headed. */
export interface ConceptPropertyColumn {
    code: string
    label: string
    /** The declared description, tooltip-length, when the CodeSystem states one. */
    description?: string
    uri?: string
    /** False when no concept of the system declaring it carries a value. */
    declared: boolean
}

/** One page of rows, with the counts a "showing X of Y" line is written from. */
export interface RowPage<T> {
    rows: T[]
    page: number
    pageCount: number
    shown: number
    total: number
}

/** One DHIS2 identifier as a badge: the tail of its system, and the uid or code it carries. */
export interface IdentifierBadge {
    label: string
    value: string
}

/** One row of a concept map: a source concept, and the one target it lands on. */
export interface MappingRow {
    code: string
    display: string | null
    targetCode: string
    targetDisplay: string | null
    equivalence: string | null
}

/** One mapping `$translate` answered with. */
export interface TranslationMatch {
    system: string | null
    code: string
    display: string | null
    equivalence: string | null
    source: string | null
}

/** What one `$translate` call said: whether it found anything, what, and why not when it did not. */
export interface TranslationResult {
    matched: boolean
    matches: TranslationMatch[]
    message: string | null
}

/**
 * The property columns a concept table shows, declarations first.
 *
 * A CodeSystem's `property` is the authority on order; the column is HEADED by the property
 * code said as words ("dhis2-code" is "Code", "value-type" is "Value type") because the page
 * already names the system - repeating "DHIS2 data element" in every header says nothing. The
 * declared `description` keeps the full sentence as the header's tooltip. A property carried
 * by a concept and declared nowhere is real data, and dropping it would silently hide a
 * column, so those follow in first-seen order and are marked undeclared.
 */
/** A property code said as words: the dhis2- prefix dropped, hyphens spaced, first letter up. */
export function propertyColumnLabel(code: string): string {
    const bare = code.replace(/^dhis2-/, '').replaceAll('-', ' ').trim()
    return bare === '' ? code : bare.charAt(0).toUpperCase() + bare.slice(1)
}

export function conceptPropertyColumns(codeSystem: CodeSystem): ConceptPropertyColumn[] {
    const carried = new Set<string>()
    for (const concept of codeSystem.concept ?? []) {
        for (const property of concept.property ?? []) carried.add(property.code)
    }
    const columns: ConceptPropertyColumn[] = (codeSystem.property ?? []).map((property) => ({
        code: property.code,
        label: propertyColumnLabel(property.code),
        description: property.description?.replace(/\.$/, '') ?? undefined,
        uri: property.uri,
        declared: true,
    }))
    const known = new Set(columns.map((column) => column.code))
    for (const code of carried) {
        if (known.has(code)) continue
        columns.push({ code, label: propertyColumnLabel(code), declared: false })
    }
    return columns
}

/** One concept's value for one property column, as text, or null when it carries none. */
export function conceptPropertyValue(concept: CodeSystemConcept, code: string): string | null {
    const property = concept.property?.find((candidate) => candidate.code === code)
    if (property === undefined) return null
    if (property.valueString !== undefined) return property.valueString
    if (property.valueCode !== undefined) return property.valueCode
    if (property.valueInteger !== undefined) return String(property.valueInteger)
    if (property.valueDecimal !== undefined) return String(property.valueDecimal)
    if (property.valueBoolean !== undefined) return property.valueBoolean ? 'true' : 'false'
    if (property.valueDateTime !== undefined) return property.valueDateTime
    if (property.valueCoding?.code !== undefined) return property.valueCoding.code
    return null
}

/** Whether any of the given texts contains the query, case-insensitively; an empty query matches all. */
export function matchesQuery(query: string, ...texts: (string | null | undefined)[]): boolean {
    const needle = query.trim().toLowerCase()
    if (needle === '') return true
    return texts.some((text) => (text ?? '').toLowerCase().includes(needle))
}

/** The concepts a filter box admits: matched on the code, the display, and every property value. */
export function filterConcepts(concepts: CodeSystemConcept[], query: string): CodeSystemConcept[] {
    if (query.trim() === '') return concepts
    return concepts.filter((concept) =>
        matchesQuery(
            query,
            concept.code,
            concept.display,
            ...(concept.property ?? []).map((property) => conceptPropertyValue(concept, property.code)),
        ),
    )
}

/**
 * One page of a long list, with the page clamped into range.
 *
 * A filter that shrinks the list under the current page would otherwise leave an empty table
 * with no way back, so the page is clamped rather than trusted. There is no virtualization
 * dependency here on purpose: an organisation-unit code system runs to thousands of concepts,
 * and a page of a couple hundred rows renders instantly with nothing to keep in sync.
 */
export function pageOf<T>(rows: T[], page: number, size: number = CONCEPT_PAGE_SIZE): RowPage<T> {
    const pageCount = Math.max(1, Math.ceil(rows.length / size))
    const current = Math.min(Math.max(page, 1), pageCount)
    const shown = rows.slice((current - 1) * size, current * size)
    return { rows: shown, page: current, pageCount, shown: shown.length, total: rows.length }
}

/**
 * The DHIS2 identifiers a resource carries, as badges.
 *
 * `ConceptMap.identifier` is a single element where every other definitional resource gets a
 * list - R4's own cardinality, not the emitter's choice - so both shapes are read. The label is
 * the last two segments of the identifier system (`.../id/option-set` reads as `id/option-set`),
 * which is what tells a uid identifier apart from a code identifier at a glance.
 */
export function identifierBadges(identifier: Identifier | Identifier[] | undefined): IdentifierBadge[] {
    const identifiers = identifier === undefined ? [] : Array.isArray(identifier) ? identifier : [identifier]
    return identifiers.flatMap((candidate) =>
        candidate.value === undefined
            ? []
            : [{ label: systemLabel(candidate.system), value: candidate.value }],
    )
}

/** The last two path segments of a system url, which is how a DHIS2 identifier system reads. */
export function systemLabel(system: string | undefined): string {
    if (system === undefined || system === '') return 'identifier'
    const segments = system.split('/').filter((segment) => segment !== '')
    return segments.slice(-2).join('/')
}

/** How many mappings a map states, counting one per target rather than one per source concept. */
export function mappingCount(conceptMap: ConceptMap): number {
    return (conceptMap.group ?? []).reduce(
        (total, group) =>
            total + (group.element ?? []).reduce((rows, element) => rows + (element.target ?? []).length, 0),
        0,
    )
}

/** Every target system the map's groups land on, in the order the map states them. */
export function targetSystems(conceptMap: ConceptMap): string[] {
    const systems: string[] = []
    for (const group of conceptMap.group ?? []) {
        if (group.target !== undefined && !systems.includes(group.target)) systems.push(group.target)
    }
    return systems
}

/** One group's mappings, flattened to one row per target so a table can show them. */
export function mappingRows(group: ConceptMapGroup): MappingRow[] {
    return (group.element ?? []).flatMap((element) =>
        (element.target ?? []).flatMap((target) =>
            target.code === undefined
                ? []
                : [
                      {
                          code: element.code ?? '',
                          display: element.display ?? null,
                          targetCode: target.code,
                          targetDisplay: target.display ?? null,
                          equivalence: target.equivalence ?? null,
                      },
                  ],
        ),
    )
}

/** Every system a ValueSet composes, whether it enumerates concepts or takes a whole system. */
export function composedSystems(valueSet: ValueSet): string[] {
    const systems: string[] = []
    for (const include of valueSet.compose?.include ?? []) {
        if (include.system !== undefined && !systems.includes(include.system)) systems.push(include.system)
    }
    return systems
}

/** How many concepts a ValueSet names outright, which is zero for the whole-system form. */
export function enumeratedConceptCount(valueSet: ValueSet): number {
    return (valueSet.compose?.include ?? []).reduce((total, include) => total + (include.concept ?? []).length, 0)
}

/**
 * What one `$translate` answer says, read off the Parameters it came back as.
 *
 * `result` is the operation's own verdict and is trusted over the match count: a server that
 * answered false with matches attached, or true with none, is stating something this UI should
 * report rather than second-guess.
 */
export function translationResult(parameters: Parameters): TranslationResult {
    const found = parameters.parameter ?? []
    const result = found.find((parameter) => parameter.name === 'result')?.valueBoolean ?? false
    const message = found.find((parameter) => parameter.name === 'message')?.valueString ?? null
    const matches = found
        .filter((parameter) => parameter.name === 'match')
        .flatMap((parameter) => {
            const parts = parameter.part ?? []
            const coding = namedPart(parts,'concept')?.valueCoding
            if (coding?.code === undefined) return []
            return [
                {
                    system: coding.system ?? null,
                    code: coding.code,
                    display: coding.display ?? null,
                    equivalence: namedPart(parts,'equivalence')?.valueCode ?? null,
                    source: namedPart(parts,'source')?.valueUri ?? null,
                },
            ]
        })
    return { matched: result, matches, message }
}

/** One named part of a `match` parameter. */
function namedPart(parts: ParametersParameter[], name: string): ParametersParameter | undefined {
    return parts.find((part) => part.name === name)
}

/**
 * How many of a resource's own codes a query matches - the deep half of the listing filter.
 *
 * The listing rows are systems, but the thing a user often remembers is a code inside one:
 * searching "first" should surface the CodeSystem holding the concept "First name (Play)"
 * rather than answer nothing because no system is *titled* first. CodeSystems count matching
 * concepts (code and display), ConceptMaps matching mapping rows (source and target codes and
 * displays), and enumerated ValueSet compositions their stated concepts; a ValueSet that only
 * composes whole systems carries no codes of its own and counts zero.
 */
export function matchingCodeCount(
    resource: CodeSystem | ValueSet | ConceptMap,
    query: string,
): number {
    if (query.trim() === '') return 0
    if (resource.resourceType === 'CodeSystem') {
        return (resource.concept ?? []).filter((concept) =>
            matchesQuery(query, concept.code, concept.display),
        ).length
    }
    if (resource.resourceType === 'ValueSet') {
        return (resource.compose?.include ?? [])
            .flatMap((include) => include.concept ?? [])
            .filter((concept) => matchesQuery(query, concept.code, concept.display)).length
    }
    return (resource.group ?? [])
        .flatMap((group) => group.element ?? [])
        .filter(
            (element) =>
                matchesQuery(query, element.code, element.display) ||
                (element.target ?? []).some((target) => matchesQuery(query, target.code, target.display)),
        ).length
}
