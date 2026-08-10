import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'

import { IdentifierBadges } from '@/components/IdentifierBadges'
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
import { canonicalId, type CodeSystem, type ConceptMap, type ValueSet, unescapeMarkup } from '@/lib/fhir'
import {
    composedSystems,
    enumeratedConceptCount,
    identifierBadges,
    mappingCount,
    matchesQuery,
    matchingCodeCount,
    type IdentifierBadge,
} from '@/lib/terminology'

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
    const [query, setQuery] = useState('')

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
                count: enumeratedConceptCount(resource) || composedSystems(resource).length,
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

    return (
        <>
            <PageHeader
                title="Terminology"
                description="The code systems, value sets, and concept maps this project published - and the codes inside them."
            />

            <div className="mb-6 flex items-center gap-2">
                <div className="relative w-full max-w-sm">
                    <Search
                        className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                        aria-hidden
                    />
                    <Input
                        className="pl-9"
                        placeholder="Filter by title, id, or DHIS2 identifier"
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

            <section className="space-y-8">
                <TerminologySection
                    title="Code systems"
                    caption="Concepts, one set per DHIS2 option set plus the data-dictionary systems."
                    resourceType="CodeSystem"
                    countLabel="Concepts"
                    loading={codeSystems.loading}
                    error={codeSystems.error}
                    rows={codeSystemRows}
                    query={query}
                    emptyMessage="This project published no CodeSystems."
                />

                <TerminologySection
                    title="Value sets"
                    caption="What a coded question may be answered from."
                    resourceType="ValueSet"
                    countLabel="Systems"
                    loading={valueSets.loading}
                    error={valueSets.error}
                    rows={valueSetRows}
                    query={query}
                    emptyMessage="This project published no ValueSets."
                />

                <TerminologySection
                    title="Concept maps"
                    caption="Every concept taken back to the DHIS2 option uid and code the forwarder writes."
                    resourceType="ConceptMap"
                    countLabel="Mappings"
                    loading={conceptMaps.loading}
                    error={conceptMaps.error}
                    rows={conceptMapRows}
                    query={query}
                    emptyMessage="This project published no ConceptMaps. Generate the option sets or categories the forms bind, then recompile and restart."
                />
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
    return { key: url ?? identifier, title: unescapeMarkup(title ?? name ?? identifier), identifier }
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
    query: string
    emptyMessage: string
}) {
    const navigate = useNavigate()
    const matching = rows
        .map((row) => ({
            row,
            codeMatches: matchingCodeCount(row.resource, query),
            shallow: matchesQuery(query, row.title, row.identifier, ...row.identifiers.map((badge) => badge.value)),
        }))
        .filter((entry) => entry.shallow || entry.codeMatches > 0)
        .toSorted((left, right) => left.row.title.localeCompare(right.row.title))
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
                emptyMessage={filteredAway ? `Nothing here matches "${query}".` : emptyMessage}
            >
                <div className="show-scrollbars overflow-x-auto rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Title</TableHead>
                                <TableHead>Id</TableHead>
                                <TableHead>DHIS2 identifiers</TableHead>
                                <TableHead className="text-right">{countLabel}</TableHead>
                                                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {matching.map(({ row, codeMatches }) => (
                                <TableRow
                                    key={row.key}
                                    className="hover:bg-accent cursor-pointer"
                                    tabIndex={0}
                                    aria-label={`Open ${row.title}`}
                                    onClick={() => navigate(`/terminology/${resourceType}/${row.identifier}`)}
                                    onKeyDown={(event) => {
                                        if (event.key === 'Enter' || event.key === ' ') {
                                            event.preventDefault()
                                            navigate(`/terminology/${resourceType}/${row.identifier}`)
                                        }
                                    }}
                                >
                                    <TableCell className="font-medium">
                                        {row.title}
                                        {codeMatches > 0 && (
                                            <span className="text-muted-foreground ml-2 text-xs font-normal">
                                                {codeMatches} matching {codeMatches === 1 ? 'code' : 'codes'}
                                            </span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground font-mono text-xs">
                                        {row.identifier}
                                    </TableCell>
                                    <TableCell>
                                        <IdentifierBadges badges={row.identifiers} />
                                    </TableCell>
                                    <TableCell className="text-right font-mono text-xs">
                                        {row.count ?? '-'}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            </PageState>
        </div>
    )
}

