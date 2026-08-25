import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { CodeBlock } from '@/components/CodeEditor'
import { PageHeader, PageState } from '@/components/PageState'
import { ProseText } from '@/components/ProseText'
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
import { useStatusLine } from '@/hooks/use-status-bar'
import { useUiConfig } from '@/hooks/use-ui-config'
import {
    declaredOperations,
    type CapabilityStatement,
    type CapabilityStatementSearchParam,
} from '@/lib/fhir'
import { authSettings } from '@/lib/uiconfig'
import { cn, countedNoun } from '@/lib/utils'

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
 * against this thing". It states every operation the document declares, whether
 * the service base answers it (`$evaluate`, which every run declares) or one
 * resource type's URL does (`$generate` on Questionnaire, `$translate` on
 * ConceptMap, each only when the store holds that type), and the interactions,
 * search parameters and profile counts per resource type, because all three are
 * conditional on what the project actually published.
 *
 * TWO COUNTS OF "TYPES" LIVE ON THIS SCREEN AND THEY COUNT DIFFERENT THINGS.
 * The description the server wrote counts the types its store holds; the table
 * below counts the types the REST block answers for, and a live run answers for
 * register types it stores none of. Each is named where it is drawn, so the
 * table is not read as contradicting the sentence above it.
 *
 * EVERY SENTENCE THIS PAGE PRINTS IS THE SERVER'S OWN PROSE, and the server
 * marks its machine spellings with backticks. They are drawn through `ProseText`
 * for that reason - a mark is a change of face, never a character on the screen.
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

    // The two tables under the identity card, counted. "Served" and "declared" are the words the
    // document itself uses, and the types counted here are the ones the REST block answers for -
    // the set the page's own heading distinguishes from the set the description counts.
    useStatusLine(
        capability === null
            ? null
            : `${countedNoun(rest?.resource?.length ?? 0, 'resource type')} served - ${countedNoun(operations.length, 'operation')} declared`,
    )

    return (
        <>
            <PageHeader
                title="Server"
                description="The CapabilityStatement this server publishes at /metadata. It is the server's whole contract: there is no OpenAPI document."
            />
            <PageState
                loading={checking && capability === null}
                status={reachability === 'unreachable' ? 'unreachable' : null}
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
                            <p>{capability?.description !== undefined && <ProseText text={capability.description} />}</p>
                            <p className="text-muted-foreground">
                                {capability?.implementation?.description !== undefined && (
                                    <ProseText text={capability.implementation.description} />
                                )}
                            </p>
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
                                <p className="text-muted-foreground">
                                    <ProseText text={rest.security.description} />
                                </p>
                            )}
                        </CardContent>
                    </Card>

                    <div className="space-y-3">
                        <h3 className="text-base font-semibold">Declared operations</h3>
                        {operations.length === 0 ? (
                            <p className="text-muted-foreground text-sm">
                                This server declares no operations.
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
                                            <TableRow key={`${operation.on ?? SERVICE_BASE_LABEL}-${operation.name}`}>
                                                <TableCell className="font-mono text-xs font-medium">
                                                    ${operation.name}
                                                </TableCell>
                                                <TableCell>
                                                    {/* A resource type wears the badge every other
                                                        table gives one; the service base is not a
                                                        resource type and is said in words. */}
                                                    {operation.on === null ? (
                                                        <span className="text-muted-foreground text-sm">
                                                            {SERVICE_BASE_LABEL}
                                                        </span>
                                                    ) : (
                                                        <Badge variant="secondary">{operation.on}</Badge>
                                                    )}
                                                </TableCell>
                                                <TableCell className="text-muted-foreground text-sm whitespace-normal">
                                                    {operation.documentation === undefined ? (
                                                        '-'
                                                    ) : (
                                                        <ProseText text={operation.documentation} />
                                                    )}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </div>

                    <div className="space-y-3">
                        <div className="space-y-0.5">
                            <h3 className="text-base font-semibold">Resource types this server answers for</h3>
                            <p className="text-muted-foreground text-sm">
                                What a caller can read from this server, and how. The count in the
                                description above is of the types this server stores, which is a
                                different set.
                            </p>
                        </div>
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
                                        <Fragment key={resource.type}>
                                            <TableRow
                                                className={cn(resource.documentation !== undefined && 'border-b-0')}
                                            >
                                                <TableCell className="align-top font-medium">
                                                    {resource.type}
                                                </TableCell>
                                                <TableCell className="align-top font-mono text-xs">
                                                    {(resource.interaction ?? [])
                                                        .map((interaction) => interaction.code)
                                                        .join(', ') || '-'}
                                                </TableCell>
                                                <TableCell className="align-top">
                                                    <SearchParameters
                                                        parameters={resource.searchParam ?? []}
                                                    />
                                                </TableCell>
                                                <TableCell className="align-top text-right font-mono text-xs">
                                                    {resource.supportedProfile?.length ?? 0}
                                                </TableCell>
                                            </TableRow>
                                            {/* The type's own paragraph is the one place a register
                                                states which DHIS2 tracked entity types it serves
                                                under this resource, so it is on the screen rather
                                                than only in the raw document. It runs under its own
                                                row instead of inside the type cell, because it is a
                                                sentence and the cell above it is a name. */}
                                            {resource.documentation !== undefined && (
                                                <TableRow>
                                                    <TableCell
                                                        colSpan={4}
                                                        className="text-muted-foreground max-w-prose px-2 pt-0 pb-2 text-xs whitespace-normal"
                                                    >
                                                        <ProseText text={resource.documentation} />
                                                    </TableCell>
                                                </TableRow>
                                            )}
                                        </Fragment>
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

/** What the Declared operations table calls the address that is the server itself. */
const SERVICE_BASE_LABEL = 'The service base'

/**
 * One type's search parameters, each with what the server wrote about it.
 *
 * WHY THE PARAGRAPH AND NOT JUST THE NAME. A name is not a contract: `d2-attribute` is a whole
 * grammar with an exact-match rule attached, and the server states that rule in the parameter's own
 * documentation. A page that printed the names alone sent a reader to the raw document to find out
 * what any of them takes - which is the one thing this page exists to save them.
 */
function SearchParameters({ parameters }: { parameters: CapabilityStatementSearchParam[] }) {
    if (parameters.length === 0) return <span className="font-mono text-xs">-</span>
    return (
        <dl className="grid gap-1.5">
            {parameters.map((parameter) => (
                <div key={parameter.name} className="grid gap-0.5">
                    <dt className="font-mono text-xs">{parameter.name}</dt>
                    {parameter.documentation !== undefined && (
                        <dd className="text-muted-foreground max-w-prose text-xs whitespace-normal">
                            <ProseText text={parameter.documentation} />
                        </dd>
                    )}
                </div>
            ))}
        </dl>
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
