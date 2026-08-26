import { useMemo, useRef, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronRight, Search } from 'lucide-react'

import { IdentifierBadges } from '@/components/IdentifierBadges'
import { ApiLink } from '@/components/ApiLink'
import { PageHeader, PageState } from '@/components/PageState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { useStatusLine } from '@/hooks/use-status-bar'
import { canonicalId, type CodeSystem, type ConceptMap, type ValueSet } from '@/lib/fhir'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    TERMINOLOGY_FILTER_PARAMETER,
    TERMINOLOGY_ORIGINS,
    composedSystems,
    identifierBadges,
    mappingCount,
    matchesQuery,
    matchingCodeCount,
    nothingMatchesMessage,
    terminologyOrigin,
    terminologyRowLink,
    type IdentifierBadge,
} from '@/lib/terminology'

/** Where the listing carries which resource type is on screen, so a narrowed listing is a link. */
const TERMINOLOGY_TYPE_PARAMETER = 'type'

/** The three tabs, each carrying the words its tables are headed by. */
const TERMINOLOGY_TYPES = ['CodeSystem', 'ValueSet', 'ConceptMap'] as const
type TerminologyType = (typeof TERMINOLOGY_TYPES)[number]
import { countedNoun, formatCount } from '@/lib/utils'

/**
 * The vocabulary behind the forms: what a coded answer is allowed to be, and what it means to DHIS2.
 *
 * All three terminology types are read here, ConceptMap included. The maps are published IG
 * artifacts sitting in the same store as the code systems, and `d2w fhir serve` serves them as a
 * read type - `GET /ConceptMap` answers a searchset like every other type, and `$translate`
 * answers the one question a forwarder has over the same documents. A page that only reported
 * whether `$translate` was declared could say that the mappings exist; this one shows them.
 *
 * The rows link into `/terminology/:resourceType/:id`, which is where the actual codes are. This
 * page is the index: what was published, how much of it there is, and which DHIS2 object each
 * artifact came from.
 */
export function Terminology() {
    const codeSystems = useFhirSearch<CodeSystem>('CodeSystem')
    const valueSets = useFhirSearch<ValueSet>('ValueSet')
    const conceptMaps = useFhirSearch<ConceptMap>('ConceptMap')
    // The search lives in the address bar, the way every detail page keeps its own: a reader who
    // opened a row and pressed Back gets the search they were reading back, and a listing narrowed
    // to one vocabulary can be handed to someone as it stands.
    const [searchParameters, setSearchParameters] = useSearchParams()
    // The last parameter write asked for, and the address it was asked from - see `writeParameter`.
    const asked = useRef<{ from: string; name: string; value: string } | null>(null)
    const query = searchParameters.get(TERMINOLOGY_FILTER_PARAMETER) ?? ''
    // TYPING REPLACES, CHOOSING PUSHES. A filter box writes a parameter per keystroke, and a
    // history entry per character is a Back button that walks a word backwards; a tab is one
    // discrete choice, and Back is what a reader expects to return them to the tab they left.
    const writeParameter = (name: string, next: string | null, discrete: boolean) => {
        // A REPEAT IS NOT A NAVIGATION. Radix fires a tab's change on the focus a click gives it and
        // again on the click itself, so one press asks for the same tab twice - and a push per ask
        // stacks two identical history entries, which is a Back button that does nothing the first
        // time it is pressed. The address is checked first; the second ask arrives before React has
        // re-rendered, so it is caught by the address it was asked from instead.
        const wanted = next ?? ''
        if ((searchParameters.get(name) ?? '') === wanted) return
        const askedFrom = searchParameters.toString()
        if (asked.current?.from === askedFrom && asked.current.name === name && asked.current.value === wanted) {
            return
        }
        asked.current = { from: askedFrom, name, value: wanted }
        setSearchParameters(
            (current) => {
                const written = new URLSearchParams(current)
                if (next === null || next === '') written.delete(name)
                else written.set(name, next)
                return written
            },
            { replace: !discrete },
        )
    }
    const setQuery = (next: string) => {
        writeParameter(TERMINOLOGY_FILTER_PARAMETER, next, false)
    }
    // Which resource type is on screen. Validated against the vocabulary rather than trusted, and
    // the default is spelled by absence so the plain address stays the plain listing.
    const askedType = searchParameters.get(TERMINOLOGY_TYPE_PARAMETER)
    const activeType: TerminologyType = TERMINOLOGY_TYPES.find((candidate) => candidate === askedType) ?? 'CodeSystem'
    const setActiveType = (next: TerminologyType) => {
        writeParameter(TERMINOLOGY_TYPE_PARAMETER, next === 'CodeSystem' ? null : next, true)
    }

    const codeSystemRows = useMemo(
        () =>
            codeSystems.resources.map((resource) => ({
                ...listingRow(resource.title, resource.name, resource.id, resource.url),
                resource,
                count: resource.count ?? resource.concept?.length ?? null,
                identifiers: identifierBadges(resource.identifier),
            })),
        [codeSystems.resources],
    )

    const valueSetRows = useMemo(
        () =>
            valueSets.resources.map((resource) => ({
                ...listingRow(resource.title, resource.name, resource.id, resource.url),
                resource,
                // The column is headed "Systems", so it states systems: a set that enumerated its
                // own concepts would otherwise print a concept count under that heading.
                count: composedSystems(resource).length,
                identifiers: identifierBadges(resource.identifier),
            })),
        [valueSets.resources],
    )

    const conceptMapRows = useMemo(
        () =>
            conceptMaps.resources.map((resource) => ({
                ...listingRow(resource.title, resource.name, resource.id, resource.url),
                resource,
                count: mappingCount(resource),
                identifiers: identifierBadges(resource.identifier),
            })),
        [conceptMaps.resources],
    )

    // The filter is asked once per section rather than once per section per render: the bar states
    // how many rows the whole page admitted, and a bar counting one thing while the sections count
    // another is two answers to one question. So the matching is done here and handed down.
    const matchingCodeSystems = useMemo(() => matchingRows(codeSystemRows, query), [codeSystemRows, query])
    const matchingValueSets = useMemo(() => matchingRows(valueSetRows, query), [valueSetRows, query])
    const matchingConceptMaps = useMemo(() => matchingRows(conceptMapRows, query), [conceptMapRows, query])
    const reading = codeSystems.loading || valueSets.loading || conceptMaps.loading

    // What each tab is made of, in one place: the tab bar reads the counts, the active tab reads
    // the rest, and the two cannot disagree because they read the same record.
    const tabs: Record<
        TerminologyType,
        {
            label: string
            countLabel: string
            loading: boolean
            error: string | null
            rows: TerminologyRow[]
            matching: MatchingRow[]
            emptyMessage: ReactNode
        }
    > = {
        CodeSystem: {
            label: 'Code systems',
            countLabel: 'Concepts',
            loading: codeSystems.loading,
            error: codeSystems.error,
            rows: codeSystemRows,
            matching: matchingCodeSystems,
            emptyMessage: 'This project published no code systems.',
        },
        ValueSet: {
            label: 'Value sets',
            countLabel: 'Systems',
            loading: valueSets.loading,
            error: valueSets.error,
            rows: valueSetRows,
            matching: matchingValueSets,
            emptyMessage: 'This project published no value sets.',
        },
        ConceptMap: {
            label: 'Concept maps',
            countLabel: 'Mappings',
            loading: conceptMaps.loading,
            error: conceptMaps.error,
            rows: conceptMapRows,
            matching: matchingConceptMaps,
            emptyMessage: (
                <>
                    No concept maps are published here. They appear once the project's terminology
                    has been generated and compiled:{' '}
                    <code className="font-mono">d2w fhir generate</code>
                </>
            ),
        },
    }
    const active = tabs[activeType]
    const matched = active.matching.length

    // The active tab shelved by origin - an option set, a category, a registry of the instance's
    // own metadata, and a hardcoded platform vocabulary are different kinds of thing, and two
    // hundred rows in one flat list is what this page used to be.
    const shelves = TERMINOLOGY_ORIGINS.map((shelf) => ({
        ...shelf,
        rows: active.rows.filter((row) => terminologyOrigin(row.identifier) === shelf.origin),
        matching: active.matching.filter((entry) => terminologyOrigin(entry.row.identifier) === shelf.origin),
        // A shelf the filter emptied steps aside rather than each saying "nothing matches" in turn;
        // when every shelf is empty the single-section branch below states it once.
    })).filter((shelf) => shelf.rows.length > 0 && (query.trim() === '' || shelf.matching.length > 0))

    useStatusLine(
        reading
            ? null
            : [
                  countedNoun(codeSystemRows.length, 'code system'),
                  countedNoun(valueSetRows.length, 'value set'),
                  countedNoun(conceptMapRows.length, 'concept map'),
              ].join(' - '),
        query.trim() === '' ? null : matched === 1 ? '1 row matches' : `${formatCount(matched)} rows match`,
    )

    return (
        <>
            <PageHeader
                title="Terminology"
                description="The code systems, value sets, and concept maps this server publishes - and the codes inside them."
                aside={<ApiLink path={`/${activeType}`} />}
            />

            <div className="mb-6 flex items-center gap-2">
                <div className="relative w-full max-w-sm">
                    <Search
                        className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                        aria-hidden
                    />
                    <Input
                        className="pl-9"
                        placeholder="Filter by title, ID, or DHIS2 identifier"
                        aria-label="Filter terminology"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                    />
                </div>
                {query !== '' && (
                    <Button variant="ghost" size="sm" onClick={() => setQuery('')}>
                        Clear
                    </Button>
                )}
            </div>

            <Tabs
                value={activeType}
                onValueChange={(next) => {
                    setActiveType(next as TerminologyType)
                }}
                className="mb-6"
            >
                <TabsList>
                    {TERMINOLOGY_TYPES.map((type) => (
                        <TabsTrigger key={type} value={type}>
                            {tabs[type].label}
                            <span className="text-muted-foreground ml-1.5 font-mono text-xs">
                                {formatCount(tabs[type].rows.length)}
                            </span>
                        </TabsTrigger>
                    ))}
                </TabsList>
            </Tabs>

            <section className="space-y-8">
                {shelves.length === 0 ? (
                    <TerminologySection
                        title={active.label}
                        caption=""
                        resourceType={activeType}
                        countLabel={active.countLabel}
                        loading={active.loading}
                        error={active.error}
                        rows={active.rows}
                        matching={active.matching}
                        query={query}
                        emptyMessage={active.emptyMessage}
                    />
                ) : (
                    shelves.map((shelf) => (
                        <TerminologySection
                            key={shelf.origin}
                            title={shelf.title}
                            caption={shelf.caption}
                            resourceType={activeType}
                            countLabel={active.countLabel}
                            loading={active.loading}
                            error={active.error}
                            rows={shelf.rows}
                            matching={shelf.matching}
                            query={query}
                            emptyMessage={active.emptyMessage}
                        />
                    ))
                )}
            </section>
        </>
    )
}

/** One resource as the listing states it: what it is called, and where it is read from. */
interface TerminologyRow {
    key: string
    title: string
    identifier: string
    count: number | null
    identifiers: IdentifierBadge[]
    resource: CodeSystem | ValueSet | ConceptMap
}

/** The naming every listing row shares: a title to sort by, and the id the detail route uses. */
function listingRow(
    title: string | undefined,
    name: string | undefined,
    id: string | undefined,
    url: string | undefined,
): { key: string; title: string; identifier: string } {
    const identifier = id ?? canonicalId(url) ?? ''
    return { key: url ?? identifier, title: title ?? name ?? identifier, identifier }
}

/**
 * One row the filter admitted, and why it was admitted.
 *
 * `codeMatches` is what a filter found INSIDE the artifact rather than on its face, which is what
 * makes a search for a code find the system holding it. It rides back out of here because the row
 * says how many, and because the link it opens carries the query on to the page that holds them.
 */
interface MatchingRow {
    row: TerminologyRow
    codeMatches: number
}

/** The rows one filter admits, in title order - the one reading of the box the whole page shares. */
function matchingRows(rows: TerminologyRow[], query: string): MatchingRow[] {
    return rows
        .map((row) => ({
            row,
            codeMatches: matchingCodeCount(row.resource, query),
            shallow: matchesQuery(query, row.title, row.identifier, ...row.identifiers.map((badge) => badge.value)),
        }))
        .filter((entry) => entry.shallow || entry.codeMatches > 0)
        .toSorted((left, right) => left.row.title.localeCompare(right.row.title))
        .map((entry) => ({ row: entry.row, codeMatches: entry.codeMatches }))
}

/** One titled table of terminology resources, in whichever of the three states it is in. */
function TerminologySection({
    title,
    caption,
    resourceType,
    countLabel,
    loading,
    error,
    rows,
    matching,
    query,
    emptyMessage,
}: {
    title: string
    caption: string
    resourceType: string
    countLabel: string
    loading: boolean
    error: string | null
    rows: TerminologyRow[]
    /** The rows the filter admitted, read once for the whole page - see `matchingRows`. */
    matching: MatchingRow[]
    query: string
    /** What this section states when it holds nothing - a node, because it names commands. */
    emptyMessage: ReactNode
}) {
    const navigate = useNavigate()
    const filteredAway = query.trim() !== '' && rows.length > 0 && matching.length === 0

    return (
        <div className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="space-y-0.5">
                    <h3 className="text-base font-semibold">{title}</h3>
                    <p className="text-muted-foreground text-sm">{caption}</p>
                </div>
                {rows.length > 0 && (
                    <p className="text-muted-foreground text-xs">
                        {matching.length === rows.length
                            ? `${String(rows.length)} published`
                            : `${String(matching.length)} of ${String(rows.length)}`}
                    </p>
                )}
            </div>
            <PageState
                loading={loading}
                error={error}
                empty={matching.length === 0}
                emptyMessage={filteredAway ? nothingMatchesMessage(query) : emptyMessage}
            >
                <div className="show-scrollbars overflow-x-auto md:overflow-x-visible rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Title</TableHead>
                                <TableHead>ID</TableHead>
                                <TableHead>DHIS2 identifiers</TableHead>
                                <TableHead className="text-right">{countLabel}</TableHead>
                                <TableHead className="w-8" aria-hidden />
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {matching.map(({ row, codeMatches }) => {
                                // A search that found codes inside this artifact opens it showing
                                // them: the reader asked about those codes, and typing the word a
                                // second time on the page that holds them is the listing dropping
                                // the question it just answered.
                                const opens = terminologyRowLink(
                                    resourceType,
                                    row.identifier,
                                    codeMatches > 0 ? query : '',
                                )
                                return (
                                    <TableRow
                                        key={row.key}
                                        className="interactive"
                                        tabIndex={0}
                                        aria-label={`Open ${row.title}`}
                                        onClick={() => navigate(opens)}
                                        onKeyDown={(event) => {
                                            if (event.key === 'Enter' || event.key === ' ') {
                                                event.preventDefault()
                                                navigate(opens)
                                            }
                                        }}
                                    >
                                        <TableCell>
                                            <span className="interactive-title">{row.title}</span>
                                            {codeMatches > 0 && (
                                                <span className="text-muted-foreground ml-2 text-xs">
                                                    {countedNoun(codeMatches, 'matching code')}
                                                </span>
                                            )}
                                        </TableCell>
                                        <TableCell className="machine-identifier text-xs">
                                            {row.identifier}
                                        </TableCell>
                                        <TableCell>
                                            <IdentifierBadges badges={row.identifiers} />
                                        </TableCell>
                                        <TableCell className="text-right font-mono text-xs">
                                            {row.count ?? '-'}
                                        </TableCell>
                                        <TableCell className="w-8" aria-hidden>
                                            <ChevronRight className="interactive-mark size-4" />
                                        </TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                    </Table>
                </div>
            </PageState>
        </div>
    )
}

