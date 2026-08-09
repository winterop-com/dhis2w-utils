import { useEffect } from 'react'

import { PageHeader, PageState } from '@/components/PageState'
import { Card, CardContent } from '@/components/ui/card'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { refreshServerStatus, useServerStatus } from '@/hooks/use-server-status'
import { canonicalId, declaredOperations, type CodeSystem, type ValueSet } from '@/lib/fhir'

/**
 * The vocabulary behind the forms: what a coded answer is allowed to be.
 *
 * CodeSystems define the concepts and ValueSets bind a question to a subset of
 * them, so both are listed from a search. ConceptMaps are the third piece - they
 * carry a concept back to the DHIS2 option uid and code the forwarder needs -
 * but they are deliberately NOT listed the same way, because
 * `d2w fhir serve` does not serve ConceptMap as a read type: it is translated
 * through rather than read, and `GET /ConceptMap` is refused as an unserved
 * type. Searching it anyway would put a 404 in the console of every project.
 *
 * What the server does say about them is on the CapabilityStatement:
 * `$translate` is declared if and only if the store holds ConceptMaps. So that
 * is what this page reads, and it is a stronger statement than a count - it says
 * whether the operation a client would use is actually answerable here.
 */
export function Terminology() {
    const codeSystems = useFhirSearch<CodeSystem>('CodeSystem')
    const valueSets = useFhirSearch<ValueSet>('ValueSet')
    const { reachability, capability } = useServerStatus()

    useEffect(() => {
        if (reachability === 'unknown') void refreshServerStatus()
    }, [reachability])

    const translate = declaredOperations(capability).find((operation) => operation.name === 'translate')

    return (
        <>
            <PageHeader
                title="Terminology"
                description="The code systems, value sets, and concept maps this project published."
            />

            <section className="space-y-8">
                <TerminologySection
                    title="Code systems"
                    caption="Concepts, one set per DHIS2 option set plus the data-dictionary systems."
                    loading={codeSystems.loading}
                    error={codeSystems.error}
                    countLabel="Concepts"
                    rows={codeSystems.resources.map((resource) => ({
                        key: resource.url ?? resource.id ?? '',
                        title: resource.title ?? resource.name ?? resource.id ?? '',
                        identifier: resource.id ?? canonicalId(resource.url) ?? '',
                        count: resource.count ?? resource.concept?.length ?? null,
                    }))}
                    emptyMessage="This project published no CodeSystems."
                />

                <TerminologySection
                    title="Value sets"
                    caption="What a coded question may be answered from."
                    loading={valueSets.loading}
                    error={valueSets.error}
                    countLabel="Systems"
                    rows={valueSets.resources.map((resource) => ({
                        key: resource.url ?? resource.id ?? '',
                        title: resource.title ?? resource.name ?? resource.id ?? '',
                        identifier: resource.id ?? canonicalId(resource.url) ?? '',
                        count: resource.compose?.include?.length ?? null,
                    }))}
                    emptyMessage="This project published no ValueSets."
                />

                <div className="space-y-3">
                    <div className="space-y-0.5">
                        <h3 className="text-base font-semibold">Concept maps</h3>
                        <p className="text-muted-foreground text-sm">
                            Concept to DHIS2 option uid and code. This server translates through them
                            rather than serving them as a read type, so what it states about them is
                            whether it declares $translate.
                        </p>
                    </div>
                    <Card>
                        <CardContent className="space-y-2 py-6 text-sm">
                            {translate ? (
                                <>
                                    <p className="font-medium">
                                        <code className="font-mono">$translate</code> is declared.
                                    </p>
                                    <p className="text-muted-foreground">{translate.documentation}</p>
                                    <p className="text-muted-foreground font-mono text-xs break-all">
                                        GET /ConceptMap/$translate?system=...&amp;code=...
                                    </p>
                                </>
                            ) : (
                                <p className="text-muted-foreground">
                                    This server declares no <code className="font-mono">$translate</code>,
                                    which means its store holds no ConceptMaps. Generate the option sets or
                                    categories the forms bind, then recompile and restart.
                                </p>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </section>
        </>
    )
}

/** One resource type's row set, as the listing renders it. */
interface TerminologyRow {
    key: string
    title: string
    identifier: string
    count: number | null
}

/** One titled table of terminology resources, in whichever of the three states it is in. */
function TerminologySection({
    title,
    caption,
    loading,
    error,
    countLabel,
    rows,
    emptyMessage,
}: {
    title: string
    caption: string
    loading: boolean
    error: string | null
    countLabel: string
    rows: TerminologyRow[]
    emptyMessage: string
}) {
    const sorted = rows.toSorted((left, right) => left.title.localeCompare(right.title))
    return (
        <div className="space-y-3">
            <div className="space-y-0.5">
                <h3 className="text-base font-semibold">{title}</h3>
                <p className="text-muted-foreground text-sm">{caption}</p>
            </div>
            <PageState loading={loading} error={error} empty={sorted.length === 0} emptyMessage={emptyMessage}>
                <div className="show-scrollbars overflow-x-auto rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Title</TableHead>
                                <TableHead>Id</TableHead>
                                <TableHead className="text-right">{countLabel}</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {sorted.map((row) => (
                                <TableRow key={row.key}>
                                    <TableCell className="font-medium">{row.title}</TableCell>
                                    <TableCell className="text-muted-foreground font-mono text-xs">
                                        {row.identifier}
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
