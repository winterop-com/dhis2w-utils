import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Search } from 'lucide-react'

import { IdentifierBadges } from '@/components/IdentifierBadges'
import { MaintenanceLink } from '@/components/MaintenanceLink'
import { PageState } from '@/components/PageState'
import { TranslateTester } from '@/components/TranslateTester'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Input } from '@/components/ui/input'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirResource } from '@/hooks/use-fhir-resource'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { useUiConfig } from '@/hooks/use-ui-config'
import { useValueSetOptions } from '@/hooks/use-valueset-options'
import { holdsDataElementConcepts } from '@/lib/dhis2'
import {
    canonicalId,
    type CodeSystem,
    type CodeSystemConcept,
    type ConceptMap,
    type ValueSet,
} from '@/lib/fhir'
import {
    CONCEPT_FILTER_PARAMETER,
    NOTHING_ASKED,
    TRANSLATE_QUESTION,
    askedConcept,
    codeSystemContentLabel,
    composedSystems,
    conceptPropertyCoding,
    conceptPropertyCodingLink,
    conceptPropertyColumns,
    conceptPropertyValue,
    countedNoun,
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
    type AskedConcept,
    type IdentifierBadge,
    type MappingRow,
    type RowPage,
} from '@/lib/terminology'

/** The three terminology types this route opens, which is exactly what the listing links to. */
const TERMINOLOGY_TYPES = ['CodeSystem', 'ValueSet', 'ConceptMap'] as const

/**
 * One terminology resource, opened: the actual codes.
 *
 * The listing says how much of each artifact there is; this is where the contents are. A code
 * system shows its concepts with every property the system declares as its own column - which is
 * how the DHIS2 option code rides alongside the concept code, and the only place in this UI where
 * both halves of a generated coding are visible at once. A value set shows what it composes,
 * expanded through the code systems it names. A concept map shows every mapping it states, per
 * target system, with `$translate` right there to ask the server the same question.
 *
 * One route for all three rather than three routes: they are read the same way (`/{type}/{id}`),
 * they are reached from the same listing, and a type outside the three is a link that should not
 * exist - so it goes back to the listing rather than rendering a page that cannot load.
 */
export function TerminologyDetail() {
    const { resourceType = '', resourceId = '' } = useParams()
    const known = TERMINOLOGY_TYPES.find((candidate) => candidate === resourceType)
    if (known === undefined) return <Navigate to="/terminology" replace />
    return <TerminologyResource resourceType={known} resourceId={resourceId} />
}

/** The read itself, in its own component so the route guard above can return before any hook runs. */
function TerminologyResource({
    resourceType,
    resourceId,
}: {
    resourceType: (typeof TERMINOLOGY_TYPES)[number]
    resourceId: string
}) {
    const { resource, loading, error, status } = useFhirResource<CodeSystem | ValueSet | ConceptMap>(
        resourceType,
        resourceId,
    )

    return (
        <>
            <div className="mb-6 space-y-2">
                <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                    <Link to="/terminology">
                        <ArrowLeft className="size-4" />
                        All terminology
                    </Link>
                </Button>
                <h2 className="text-xl font-semibold tracking-tight">
                    {resource === null ? resourceId : (title(resource) ?? resourceId)}
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{resourceType}</Badge>
                    <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
                        {resourceId}
                    </Badge>
                </div>
            </div>

            <PageState
                loading={loading}
                error={error}
                status={status}
                empty={resource === null && error === null && !loading}
                emptyMessage={`This server holds no ${resourceType} under that id.`}
            >
                {resource !== null && resource.resourceType === 'CodeSystem' && (
                    <CodeSystemDetail codeSystem={resource} />
                )}
                {resource !== null && resource.resourceType === 'ValueSet' && (
                    <ValueSetDetail valueSet={resource} />
                )}
                {resource !== null && resource.resourceType === 'ConceptMap' && (
                    <ConceptMapDetail conceptMap={resource} />
                )}
            </PageState>
        </>
    )
}

/** What a terminology resource is called, whichever of the three it is. */
function title(resource: CodeSystem | ValueSet | ConceptMap): string | null {
    const raw = resource.title ?? resource.name ?? resource.id ?? null
    return raw === null ? null : raw
}

/**
 * A code system: what it declares about itself, then every concept it holds.
 *
 * The concept filter lives in the address bar rather than in local state, because that is what a
 * coding-valued property links to: a reader following one lands here with the filter already
 * naming the coded concept, and can hand the address on unchanged.
 */
function CodeSystemDetail({ codeSystem }: { codeSystem: CodeSystem }) {
    const [query, setQuery] = useConceptFilter()
    const [page, setPage] = useState(1)
    const [asked, setAsked] = useState<AskedConcept>(NOTHING_ASKED)
    const settings = useUiConfig()

    // WHICH SYSTEMS HAVE AN ANSWER TO GIVE. `$translate` reads the served maps, so a system no map
    // names as a group source refuses every ask - and the identifier enumerations are worse than
    // that, since their canonical is a map *target* and can never be a source. Reading the maps is
    // the only way to know: the CodeSystem document says nothing about who translates it.
    const conceptMaps = useFhirSearch<ConceptMap>('ConceptMap')
    const translatable = mapsFromSystem(conceptMaps.resources, codeSystem.url)

    // THE ONE VOCABULARY WHOSE CODES ARE DHIS2 OBJECTS THIS UI HOLDS A ROUTE TO. A data dictionary's
    // concept codes are data element uids, so each row can open the data element itself; the option
    // sets, the category option combos, and the attribute pair beside it are edited on screens this
    // UI knows no by-uid route for, and their rows link nowhere rather than somewhere wrong.
    const dataElements = holdsDataElementConcepts(codeSystem)
    const dhis2BaseUrl = settings.config.dhis2_base_url
    const columns = useMemo(() => conceptPropertyColumns(codeSystem), [codeSystem])
    const concepts = useMemo(() => codeSystem.concept ?? [], [codeSystem])
    const matching = useMemo(() => filterConcepts(concepts, query), [concepts, query])
    const shown = pageOf(matching, page)

    return (
        <div className="space-y-6">
            <ResourceFacts
                url={codeSystem.url}
                description={codeSystem.description}
                identifiers={identifierBadges(codeSystem.identifier)}
                facts={[
                    { label: 'Concepts', value: String(codeSystem.count ?? concepts.length) },
                    { label: 'Content', value: codeSystemContentLabel(codeSystem.content), mono: false },
                    {
                        label: 'Case sensitive',
                        value: statedBooleanLabel(codeSystem.caseSensitive),
                        mono: false,
                    },
                ]}
            >
                {codeSystem.valueSet !== undefined && (
                    <TerminologyLink resourceType="ValueSet" canonical={codeSystem.valueSet}>
                        Its value set
                    </TerminologyLink>
                )}
            </ResourceFacts>

            <div
                className={
                    translatable ? 'grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]' : undefined
                }
            >
            <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-base font-semibold">Concepts</h3>
                    <FilterBox
                        label="Filter concepts"
                        placeholder="Filter by code, display, or property"
                        value={query}
                        onChange={(next) => {
                            setQuery(next)
                            setPage(1)
                        }}
                    />
                </div>

                {concepts.length === 0 ? (
                    <p className="text-muted-foreground rounded-lg border px-4 py-8 text-sm">
                        This CodeSystem carries no concepts. A{' '}
                        <code className="font-mono">content</code> of{' '}
                        <code className="font-mono">not-present</code> means the concepts live
                        somewhere else; <code className="font-mono">complete</code> with none is an
                        empty system.
                    </p>
                ) : matching.length === 0 ? (
                    <p className="text-muted-foreground rounded-lg border px-4 py-8 text-sm">
                        {nothingMatchesMessage(query)}
                    </p>
                ) : (
                    <>
                        <div className="show-scrollbars max-h-[65vh] overflow-auto rounded-lg border">
                            <Table>
                                <TableHeader className="bg-background sticky top-0 z-10">
                                    <TableRow>
                                        <TableHead>Code</TableHead>
                                        <TableHead>Display</TableHead>
                                        {columns.map((column) => (
                                            <TableHead key={column.code} title={column.description ?? column.uri}>
                                                {column.label}
                                            </TableHead>
                                        ))}
                                        {translatable && <TableHead className={PINNED_ACTION_CELL} />}
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {shown.rows.map((concept) => (
                                        <TableRow key={concept.code}>
                                            <TableCell className="font-mono text-xs font-medium">
                                                <span className="inline-flex items-center gap-1.5">
                                                    {concept.code}
                                                    {dataElements && (
                                                        <MaintenanceLink
                                                            baseUrl={dhis2BaseUrl}
                                                            object="dataElement"
                                                            uid={concept.code}
                                                            subject={concept.display ?? concept.code}
                                                        />
                                                    )}
                                                </span>
                                            </TableCell>
                                            <TableCell>{concept.display ?? '-'}</TableCell>
                                            {columns.map((column) => (
                                                <ConceptPropertyCell
                                                    key={column.code}
                                                    concept={concept}
                                                    code={column.code}
                                                />
                                            ))}
                                            {translatable && (
                                                <TableCell className={PINNED_ACTION_CELL}>
                                                    <Tooltip>
                                                        <TooltipTrigger asChild>
                                                            <Button
                                                                variant="outline"
                                                                size="sm"
                                                                aria-label={`Details for ${concept.code}`}
                                                                onClick={() =>
                                                                    setAsked((previous) =>
                                                                        askedConcept(previous, concept.code),
                                                                    )
                                                                }
                                                            >
                                                                Details
                                                                <ArrowRight aria-hidden />
                                                            </Button>
                                                        </TooltipTrigger>
                                                        <TooltipContent>{TRANSLATE_QUESTION}</TooltipContent>
                                                    </Tooltip>
                                                </TableCell>
                                            )}
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                        <Pagination page={shown} onPage={setPage} noun="concept" />
                    </>
                )}
            </div>

            {codeSystem.url !== undefined && translatable && (
                <div className="xl:sticky xl:top-6">
                    <TranslateTester system={codeSystem.url} asked={asked} targetSystems={[]} />
                </div>
            )}
            </div>
        </div>
    )
}

/**
 * The action column, pinned to the right edge of the table's own scroll box.
 *
 * A category option combo vocabulary is nineteen property columns wide and thousands of rows long,
 * so an action column sitting at the end of the row is off the screen at every ordinary window
 * width - and the horizontal scrollbar that would reach it is at the bottom of a page-tall element.
 * Pinned, it is where the reader is, whatever the table is doing sideways. It stays its own column
 * rather than moving in beside the concept code, because the code cell already carries the way out
 * to the DHIS2 instance and two marks with different destinations in one cell name neither.
 */
const PINNED_ACTION_CELL = 'bg-background sticky right-0 w-0 border-l'

/**
 * The concept filter, kept in the address bar rather than in local state.
 *
 * That is what a coding-valued property links to, what the listing hands on when a search matched
 * codes inside an artifact, and what the browser's Back button restores. One rule for all three
 * detail types: a filtered table is an address, and an address can be handed to someone.
 */
function useConceptFilter(): [string, (next: string) => void] {
    const [searchParameters, setSearchParameters] = useSearchParams()
    const query = searchParameters.get(CONCEPT_FILTER_PARAMETER) ?? ''
    const setQuery = useCallback(
        (next: string) => {
            setSearchParameters(next === '' ? {} : { [CONCEPT_FILTER_PARAMETER]: next }, {
                replace: true,
            })
        },
        [setSearchParameters],
    )
    return [query, setQuery]
}

/**
 * One concept property, in its cell: a coding into a published CodeSystem digs down to it.
 *
 * The link carries the coded concept as the target page's filter, so following a category axis off
 * a category option combo lands on that category's own vocabulary showing the one option. A coding
 * naming a display keeps that display in prose; everything else is machine spelling and stays mono.
 */
function ConceptPropertyCell({ concept, code }: { concept: CodeSystemConcept; code: string }) {
    const coding = conceptPropertyCoding(concept, code)
    const link = coding === null ? null : conceptPropertyCodingLink(coding)
    if (link !== null) {
        return (
            <TableCell className={link.isCode ? 'font-mono text-xs' : 'text-xs'}>
                <Link className="interactive-link" to={link.to}>
                    {link.label}
                </Link>
            </TableCell>
        )
    }
    return (
        <TableCell className="text-muted-foreground font-mono text-xs">
            {conceptPropertyValue(concept, code) ?? '-'}
        </TableCell>
    )
}

/** A value set: the systems it composes, and the concepts those systems turn out to hold. */
function ValueSetDetail({ valueSet }: { valueSet: ValueSet }) {
    const [query, setQuery] = useConceptFilter()
    const [page, setPage] = useState(1)
    const systems = composedSystems(valueSet)
    // The expansion is the same two reads a choice question makes when it renders its options,
    // through the same cache - so opening a value set here warms exactly what a form needs.
    const expansion = useValueSetOptions(valueSet.url ?? null)
    const matching = expansion.options.filter((option) =>
        matchesQuery(query, option.coding.code, option.label),
    )
    const shown = pageOf(matching, page)

    return (
        <div className="space-y-6">
            <ResourceFacts
                url={valueSet.url}
                description={valueSet.description}
                identifiers={identifierBadges(valueSet.identifier)}
                facts={[
                    { label: 'Systems', value: String(systems.length) },
                    { label: 'Concepts', value: expansion.loading ? '...' : String(expansion.options.length) },
                ]}
            >
                {systems.map((system) => (
                    <TerminologyLink key={system} resourceType="CodeSystem" canonical={system}>
                        {systemLabel(system)}
                    </TerminologyLink>
                ))}
            </ResourceFacts>

            <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="space-y-0.5">
                        <h3 className="text-base font-semibold">Concepts</h3>
                        <p className="text-muted-foreground text-sm">
                            Expanded by reading the code systems it composes - this server publishes no
                            $expand, so the concepts come from the same reads a form makes.
                        </p>
                    </div>
                    <FilterBox
                        label="Filter concepts"
                        placeholder="Filter by code or display"
                        value={query}
                        onChange={(next) => {
                            setQuery(next)
                            setPage(1)
                        }}
                    />
                </div>

                <PageState
                    loading={expansion.loading}
                    error={expansion.error}
                    empty={matching.length === 0}
                    emptyMessage={
                        expansion.options.length === 0
                            ? 'Nothing expanded. The systems this set composes are not published here, or hold no concepts.'
                            : nothingMatchesMessage(query)
                    }
                >
                    <div className="show-scrollbars max-h-[65vh] overflow-auto rounded-lg border">
                        <Table>
                            <TableHeader className="bg-background sticky top-0 z-10">
                                <TableRow>
                                    <TableHead>Code</TableHead>
                                    <TableHead>Display</TableHead>
                                    <TableHead>System</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {shown.rows.map((option) => (
                                    <TableRow key={`${option.coding.system ?? ''}-${option.coding.code ?? ''}`}>
                                        <TableCell className="font-mono text-xs font-medium">
                                            {option.coding.code}
                                        </TableCell>
                                        <TableCell>{option.label}</TableCell>
                                        <TableCell className="text-muted-foreground font-mono text-xs">
                                            {systemLabel(option.coding.system)}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                    <Pagination page={shown} onPage={setPage} noun="concept" />
                </PageState>
            </div>
        </div>
    )
}

/** A concept map: every mapping it states, grouped the way the map groups them. */
function ConceptMapDetail({ conceptMap }: { conceptMap: ConceptMap }) {
    const [query, setQuery] = useConceptFilter()
    const [asked, setAsked] = useState<AskedConcept>(NOTHING_ASKED)
    const groups = conceptMap.group ?? []
    const sourceSystem = groups.find((group) => group.source !== undefined)?.source

    return (
        <div className="space-y-6">
            <ResourceFacts
                url={conceptMap.url}
                description={conceptMap.description}
                identifiers={identifierBadges(conceptMap.identifier)}
                facts={[
                    { label: 'Mappings', value: String(mappingCount(conceptMap)) },
                    { label: 'Groups', value: String(groups.length) },
                ]}
            >
                {conceptMap.sourceCanonical !== undefined && (
                    <TerminologyLink resourceType="ValueSet" canonical={conceptMap.sourceCanonical}>
                        Source value set
                    </TerminologyLink>
                )}
                {sourceSystem !== undefined && (
                    <TerminologyLink resourceType="CodeSystem" canonical={sourceSystem}>
                        Source code system
                    </TerminologyLink>
                )}
            </ResourceFacts>

            <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
            <div className="min-w-0 space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold">Mappings</h3>
                <FilterBox
                    label="Filter mappings"
                    placeholder="Filter by code or display"
                    value={query}
                    onChange={setQuery}
                />
            </div>

            {groups.map((group, index) => (
                <MappingGroup
                    // A map can state two groups with the same source and target pair, so the
                    // position is what tells them apart. Groups are never reordered in place.
                    // oxlint-disable-next-line react/no-array-index-key
                    key={`${group.target ?? ''}-${index}`}
                    source={group.source}
                    target={group.target}
                    rows={mappingRows(group)}
                    query={query}
                    onAsk={(code, targetSystem) => {
                        setAsked((previous) => askedConcept(previous, code, targetSystem))
                    }}
                />
            ))}

            </div>

            {sourceSystem !== undefined && (
                <div className="xl:sticky xl:top-6">
                    <TranslateTester
                        system={sourceSystem}
                        asked={asked}
                        targetSystems={targetSystems(conceptMap)}
                    />
                </div>
            )}
            </div>
        </div>
    )
}

/** One group of a map: what it maps into, and every row it states. */
function MappingGroup({
    source,
    target,
    rows,
    query,
    onAsk,
}: {
    source: string | undefined
    target: string | undefined
    rows: MappingRow[]
    query: string
    /** Asks about one row, in the direction of the group it is in. */
    onAsk: (code: string, targetSystem: string | null) => void
}) {
    const [page, setPage] = useState(1)
    const matching = rows.filter((row) => matchesQuery(query, row.code, row.display, row.targetCode))
    const shown = pageOf(matching, page)

    return (
        <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground font-mono text-xs">{systemLabel(source)}</span>
                <ArrowRight className="text-muted-foreground size-3.5" aria-hidden />
                <span className="font-mono text-xs font-medium">{systemLabel(target)}</span>
                <span className="text-muted-foreground text-xs">
                    {countedNoun(matching.length, 'mapping')}
                </span>
            </div>
            {matching.length === 0 ? (
                <p className="text-muted-foreground rounded-lg border px-4 py-8 text-sm">
                    {query.trim() === ''
                        ? 'This group states no mappings.'
                        : nothingMatchesMessage(query)}
                </p>
            ) : (
                <>
                    <div className="show-scrollbars max-h-[65vh] overflow-auto rounded-lg border">
                        <Table>
                            <TableHeader className="bg-background sticky top-0 z-10">
                                <TableRow>
                                    <TableHead>Concept</TableHead>
                                    <TableHead>Display</TableHead>
                                    <TableHead>Maps to</TableHead>
                                    <TableHead>Equivalence</TableHead>
                                    <TableHead className={PINNED_ACTION_CELL} />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {shown.rows.map((row) => (
                                    <TableRow key={`${row.code}-${row.targetCode}`}>
                                        <TableCell className="font-mono text-xs font-medium">
                                            {row.code}
                                        </TableCell>
                                        <TableCell>{row.display ?? '-'}</TableCell>
                                        <TableCell className="font-mono text-xs">{row.targetCode}</TableCell>
                                        <TableCell>
                                            {row.equivalence === null ? (
                                                <span className="text-muted-foreground text-xs">-</span>
                                            ) : (
                                                <Badge variant="secondary" className="text-[10px]">
                                                    {row.equivalence}
                                                </Badge>
                                            )}
                                        </TableCell>
                                        <TableCell className={PINNED_ACTION_CELL}>
                                            <Tooltip>
                                                <TooltipTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        aria-label={`Details for ${row.code}`}
                                                        onClick={() => onAsk(row.code, target ?? null)}
                                                    >
                                                        Details
                                                        <ArrowRight aria-hidden />
                                                    </Button>
                                                </TooltipTrigger>
                                                <TooltipContent>{TRANSLATE_QUESTION}</TooltipContent>
                                            </Tooltip>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                    <Pagination page={shown} onPage={setPage} noun="mapping" />
                </>
            )}
        </div>
    )
}

/** The header block every detail shares: canonical, identifiers, counts, and the links out. */
function ResourceFacts({
    url,
    description,
    identifiers,
    facts,
    children,
}: {
    url: string | undefined
    description: string | undefined
    identifiers: IdentifierBadge[]
    /** One stated fact each. `mono` is false where the value is a sentence rather than a machine spelling. */
    facts: { label: string; value: string; mono?: boolean }[]
    children?: ReactNode
}) {
    return (
        <div className="space-y-3 rounded-lg border p-4">
            {description !== undefined && <p className="text-sm">{description}</p>}
            {url !== undefined && (
                <p className="text-muted-foreground font-mono text-xs break-all">{url}</p>
            )}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                {facts.map((fact) => (
                    <div key={fact.label} className="text-sm">
                        <span className="text-muted-foreground">{fact.label} </span>
                        <span className={fact.mono === false ? undefined : 'font-mono'}>{fact.value}</span>
                    </div>
                ))}
            </div>
            {identifiers.length > 0 && <IdentifierBadges badges={identifiers} />}
            <div className="flex flex-wrap gap-2">{children}</div>
        </div>
    )
}

/**
 * A link to another terminology resource by its canonical url.
 *
 * The id is the canonical's last segment, which is how this server ids everything it publishes -
 * the same rule hooks/use-valueset-options.ts resolves a binding by. A canonical that names a
 * resource this project never published still renders a link, and the detail page states the
 * 404 the server answers with, which is more useful than a dead-looking span.
 */
function TerminologyLink({
    resourceType,
    canonical,
    children,
}: {
    resourceType: 'CodeSystem' | 'ValueSet' | 'ConceptMap'
    canonical: string
    children: ReactNode
}) {
    const id = canonicalId(canonical)
    if (id === null) return null
    return (
        <Button asChild variant="outline" size="sm">
            <Link to={`/terminology/${resourceType}/${id}`}>{children}</Link>
        </Button>
    )
}

/** A filter box, the same shape wherever a long table needs narrowing. */
function FilterBox({
    label,
    placeholder,
    value,
    onChange,
}: {
    label: string
    placeholder: string
    value: string
    onChange: (next: string) => void
}) {
    return (
        <div className="relative w-full max-w-xs">
            <Search
                className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                aria-hidden
            />
            <Input
                className="pl-9"
                aria-label={label}
                placeholder={placeholder}
                value={value}
                onChange={(event) => onChange(event.target.value)}
            />
        </div>
    )
}

/**
 * How much of a long list is on screen, and how to see the rest.
 *
 * Client-side, over rows the server already sent: `d2w fhir serve` answers a read with the whole
 * document, so there is nothing to fetch per page. What this solves is rendering - an
 * organisation-unit code system runs to thousands of concepts - and a page count is a cheaper
 * answer to that than a virtualization dependency.
 */
function Pagination({
    page,
    onPage,
    noun,
}: {
    page: RowPage<unknown>
    onPage: (next: number) => void
    /** What one row is, in the singular - the line says one of them as "1 concept", not "1 concepts". */
    noun: string
}) {
    if (page.total === 0) return null
    return (
        <div className="flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground text-xs">
                Showing {page.shown} of {countedNoun(page.total, noun)}
                {page.pageCount > 1 ? ` (page ${String(page.page)} of ${String(page.pageCount)})` : ''}
            </p>
            {page.pageCount > 1 && (
                <div className="flex gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={page.page <= 1}
                        onClick={() => onPage(page.page - 1)}
                    >
                        Previous
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={page.page >= page.pageCount}
                        onClick={() => onPage(page.page + 1)}
                    >
                        Next
                    </Button>
                </div>
            )}
        </div>
    )
}
