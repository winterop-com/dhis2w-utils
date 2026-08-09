import { useEffect } from 'react'

import { PageHeader, PageState } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { refreshServerStatus, useServerStatus } from '@/hooks/use-server-status'
import { declaredOperations } from '@/lib/fhir'

/**
 * What the server says about itself, read straight off `GET /metadata`.
 *
 * The CapabilityStatement is the facade's actual contract - it has no OpenAPI
 * document, on purpose - so this page is the honest answer to "what can I do
 * against this thing". It states the declared operations (`$translate` when the
 * store holds ConceptMaps, `$generate` when it holds Questionnaires) and the
 * interactions and search parameters per resource type, because both are
 * conditional on what the project actually published.
 */
export function Server() {
    const { reachability, capability, checking } = useServerStatus()

    useEffect(() => {
        if (reachability === 'unknown') void refreshServerStatus()
    }, [reachability])

    const rest = capability?.rest?.[0]
    const operations = declaredOperations(capability)

    return (
        <>
            <PageHeader
                title="Server"
                description="The CapabilityStatement this process serves, which is the contract - there is no OpenAPI document."
            />
            <PageState
                loading={checking && capability === null}
                error={
                    reachability === 'unreachable'
                        ? 'No answer from /metadata. Is `d2w fhir serve --ui` still running?'
                        : null
                }
                empty={capability === null}
                emptyMessage="The server answered, but not with a CapabilityStatement."
            >
                <div className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">{capability?.software?.name}</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2 text-sm">
                            <p>{capability?.description}</p>
                            <p className="text-muted-foreground">{capability?.implementation?.description}</p>
                            <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-xs">
                                <dt>version</dt>
                                <dd>{capability?.software?.version ?? '-'}</dd>
                                <dt>fhirVersion</dt>
                                <dd>{capability?.fhirVersion ?? '-'}</dd>
                                <dt>kind</dt>
                                <dd>{capability?.kind ?? '-'}</dd>
                                <dt>date</dt>
                                <dd>{capability?.date ?? '-'}</dd>
                                {capability?.instantiates?.map((canonical) => (
                                    <ReferenceRow key={canonical} canonical={canonical} />
                                ))}
                            </dl>
                        </CardContent>
                    </Card>

                    <div className="space-y-3">
                        <h3 className="text-base font-semibold">Declared operations</h3>
                        {operations.length === 0 ? (
                            <p className="text-muted-foreground text-sm">
                                This server declares no operations, which means its store holds neither
                                ConceptMaps nor Questionnaires.
                            </p>
                        ) : (
                            <div className="show-scrollbars overflow-x-auto rounded-lg border">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Operation</TableHead>
                                            <TableHead>Declared on</TableHead>
                                            <TableHead>What it does</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {operations.map((operation) => (
                                            <TableRow key={`${operation.on}-${operation.name}`}>
                                                <TableCell className="font-mono text-xs font-medium">
                                                    ${operation.name}
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="secondary">{operation.on}</Badge>
                                                </TableCell>
                                                <TableCell className="text-muted-foreground text-sm whitespace-normal">
                                                    {operation.documentation ?? '-'}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </div>

                    <div className="space-y-3">
                        <h3 className="text-base font-semibold">Resource types</h3>
                        <div className="show-scrollbars overflow-x-auto rounded-lg border">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Type</TableHead>
                                        <TableHead>Interactions</TableHead>
                                        <TableHead>Search parameters</TableHead>
                                        <TableHead className="text-right">Profiles</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {(rest?.resource ?? []).map((resource) => (
                                        <TableRow key={resource.type}>
                                            <TableCell className="font-medium">{resource.type}</TableCell>
                                            <TableCell className="font-mono text-xs">
                                                {(resource.interaction ?? [])
                                                    .map((interaction) => interaction.code)
                                                    .join(', ') || '-'}
                                            </TableCell>
                                            <TableCell className="font-mono text-xs">
                                                {(resource.searchParam ?? [])
                                                    .map((parameter) => parameter.name)
                                                    .join(', ') || '-'}
                                            </TableCell>
                                            <TableCell className="text-right font-mono text-xs">
                                                {resource.supportedProfile?.length ?? 0}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    </div>
                </div>
            </PageState>
        </>
    )
}

/** One canonical the statement says it instantiates - the IG's own requirements statement. */
function ReferenceRow({ canonical }: { canonical: string }) {
    return (
        <>
            <dt>instantiates</dt>
            <dd className="break-all">{canonical}</dd>
        </>
    )
}
