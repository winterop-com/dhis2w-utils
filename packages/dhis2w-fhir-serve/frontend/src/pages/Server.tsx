import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { CodeBlock } from '@/components/CodeEditor'
import { PageHeader, PageState } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { useUiConfig } from '@/hooks/use-ui-config'
import { declaredOperations, type CapabilityStatement } from '@/lib/fhir'
import { authSettings } from '@/lib/uiconfig'

/** What each posture is called on this page. Name the fact, not the config value. */
const AUTHENTICATION_LABELS: Record<string, string> = {
    none: 'Every caller is served',
    token: 'A token this deployment issued',
    dhis2: 'The DHIS2 credentials of whoever is calling',
    jwt: 'A token from an OpenID Connect issuer',
}

/** What each scope is called. `write` is the default and covers the one state-changing address. */
const SCOPE_LABELS: Record<string, string> = {
    write: 'Required to submit a response; every read is open',
    all: 'Required for every interaction except reading this document',
}

/**
 * What the server says about itself, read straight off `GET /metadata`.
 *
 * The CapabilityStatement is the facade's actual contract - it has no OpenAPI
 * document, on purpose - so this page is the honest answer to "what can I do
 * against this thing". It states the declared operations - each on the resource
 * type whose URL answers it, `$generate` on Questionnaire and `$translate` on
 * ConceptMap, and each only when the store holds that type - and the interactions
 * and search parameters per resource type, because both are conditional on what
 * the project actually published.
 */
export function Server() {
    const { reachability, capability, checking } = useServerStatus()

    useEffect(() => {
        if (reachability === 'unknown') void refreshServerStatus()
    }, [reachability])

    const rest = capability?.rest?.[0]
    const operations = declaredOperations(capability)
    // The posture comes off `/uiconfig` rather than off the document above, because the scope is a
    // fact `/metadata` states only in prose - see `lib/uiconfig`.
    const authentication = authSettings(useUiConfig().config)

    return (
        <>
            <PageHeader
                title="Server"
                description="The CapabilityStatement this server publishes at /metadata. It is the server's whole contract: there is no OpenAPI document."
            />
            <PageState
                loading={checking && capability === null}
                error={
                    reachability === 'unreachable' ? (
                        <>
                            No answer from <code className="font-mono">/metadata</code>. Is{' '}
                            <code className="font-mono">d2w fhir serve --ui</code> still running?
                        </>
                    ) : null
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

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Authentication</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2 text-sm">
                            <p>{AUTHENTICATION_LABELS[authentication.posture] ?? authentication.posture}</p>
                            {/* The issuer is the one part of `[serve.jwt]` that crosses, and the one a
                                caller needs: a token has to be got from somewhere before it can be sent. */}
                            {authentication.issuer && (
                                <p className="font-mono text-xs break-all">{authentication.issuer}</p>
                            )}
                            {authentication.posture !== 'none' && (
                                <p className="text-muted-foreground">
                                    {SCOPE_LABELS[authentication.scope] ?? authentication.scope}
                                </p>
                            )}
                            {rest?.security?.description && (
                                <p className="text-muted-foreground">{rest.security.description}</p>
                            )}
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

                    {capability !== null && <RawCapability capability={capability} />}
                </div>
            </PageState>
        </>
    )
}

/**
 * The conformance document itself, behind a toggle.
 *
 * The same escape hatch the receipt page carries, for the same reason: everything above is a reading
 * of this document, and a reading can be wrong in a way that is invisible until the bytes are on
 * screen. It matters more here than anywhere else in the app, because this document IS the contract -
 * a caller writing against this server has to be able to see exactly what it declares, and the tables
 * above show the parts a browser needed rather than the whole of it.
 */
function RawCapability({ capability }: { capability: CapabilityStatement }) {
    const [shown, setShown] = useState(false)
    return (
        <section className="space-y-2">
            <Button variant="outline" size="sm" aria-expanded={shown} onClick={() => setShown(!shown)}>
                {shown ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
                Raw CapabilityStatement
            </Button>
            {shown && (
                <CodeBlock
                    value={JSON.stringify(capability, null, 2)}
                    testId="raw-capability-statement"
                    maxHeight="32rem"
                />
            )}
        </section>
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
