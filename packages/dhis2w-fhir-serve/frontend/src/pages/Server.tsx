import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { CodeBlock } from '@/components/CodeEditor'
import { ApiLink } from '@/components/ApiLink'
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
    type CapabilityStatementResource,
    type CapabilityStatementSearchParam,
} from '@/lib/fhir'
import {
    authSettings,
    registerFilterAttributes,
    trackedEntitySettings,
    type FilterAttribute,
} from '@/lib/uiconfig'
import { countedNoun } from '@/lib/utils'

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
    const uiConfig = useUiConfig().config
    const authentication = authSettings(uiConfig)
    // The same attribute catalog the statement writes as prose, structured - see the register rows.
    const registers = trackedEntitySettings(uiConfig).registers

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
                aside={<ApiLink path="/metadata" />}
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
                            <div className="show-scrollbars overflow-x-auto md:overflow-x-visible rounded-lg border">
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
                                                    {/* EVERY ROW IN THIS COLUMN IS A CHIP. The column
                                                        answers one question - where is this operation
                                                        declared - and a column that answered it in a
                                                        pill on one row and in loose words on the next
                                                        read as two columns sharing a heading. The
                                                        outline says the service base is not a resource
                                                        type without leaving the shape. */}
                                                    {operation.on === null ? (
                                                        <Badge variant="outline">{SERVICE_BASE_LABEL}</Badge>
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
                        <div className="show-scrollbars overflow-x-auto md:overflow-x-visible rounded-lg border">
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
                                    {(rest?.resource ?? []).map((resource) => {
                                        const register = registers.find(
                                            (candidate) => candidate.resource === resource.type,
                                        )
                                        return (
                                            <ResourceRows
                                                key={resource.type}
                                                resource={resource}
                                                attributes={
                                                    register === undefined
                                                        ? []
                                                        : registerFilterAttributes(register)
                                                }
                                            />
                                        )
                                    })}
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
 * One resource type's rows: the scannable line, and its contract unfolded on demand.
 *
 * THE NAMES ARE AMBIENT, THE PROSE WAITS. A name is not a contract - `d2-attribute` is a whole
 * grammar with an exact-match rule attached - but nine types each stating every parameter's whole
 * paragraph is a page nobody can scan, and most of those paragraphs are the same sentence about the
 * identifier token. So the row shows what a caller scans for - the type, the interactions, the
 * parameter names - and the type's own paragraph with every parameter's contract unfolds under it,
 * still saving the trip to the raw document without charging every reader for it.
 */
function ResourceRows({
    resource,
    attributes,
}: {
    resource: CapabilityStatementResource
    /** The register's filterable attributes from /uiconfig, empty for a type that is no register. */
    attributes: FilterAttribute[]
}) {
    const [unfolded, setUnfolded] = useState(false)
    const parameters = resource.searchParam ?? []
    return (
        <Fragment>
            <TableRow className={unfolded ? 'border-b-0' : undefined}>
                <TableCell className="align-top font-medium">
                    {/* The button carries no label of its own, so the cell's accessible name stays
                        the bare type - which is also what the tests find a row by. */}
                    <button
                        type="button"
                        aria-expanded={unfolded}
                        onClick={() => setUnfolded(!unfolded)}
                        className="hover:text-foreground focus-visible:ring-ring/50 -mx-1 flex items-center gap-1 rounded px-1 focus-visible:ring-[3px] focus-visible:outline-none"
                    >
                        {unfolded ? (
                            <ChevronDown className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                        ) : (
                            <ChevronRight className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                        )}
                        {resource.type}
                    </button>
                </TableCell>
                <TableCell className="align-top font-mono text-xs">
                    {(resource.interaction ?? []).map((interaction) => interaction.code).join(', ') || '-'}
                </TableCell>
                <TableCell className="align-top">
                    {parameters.length === 0 ? (
                        <span className="font-mono text-xs">-</span>
                    ) : (
                        <div className="flex flex-wrap gap-1">
                            {parameters.map((parameter) => (
                                <Badge key={parameter.name} variant="outline" className="font-mono text-[11px]">
                                    {parameter.name}
                                </Badge>
                            ))}
                        </div>
                    )}
                </TableCell>
                <TableCell className="align-top text-right font-mono text-xs">
                    {resource.supportedProfile?.length ?? 0}
                </TableCell>
            </TableRow>
            {unfolded && (
                <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={4} className="space-y-3 px-4 pt-0 pb-4 whitespace-normal">
                        {resource.documentation !== undefined && (
                            <p className="text-muted-foreground max-w-prose text-xs">
                                <ProseText text={resource.documentation} />
                            </p>
                        )}
                        {parameters.length > 0 && (
                            <dl className="grid gap-2">
                                {parameters.map((parameter) => (
                                    <div key={parameter.name} className="grid gap-0.5">
                                        <dt className="font-mono text-xs font-medium">{parameter.name}</dt>
                                        <dd className="text-muted-foreground max-w-prose text-xs">
                                            <ParameterDocumentation
                                                parameter={parameter}
                                                attributes={attributes}
                                            />
                                        </dd>
                                    </div>
                                ))}
                            </dl>
                        )}
                    </TableCell>
                </TableRow>
            )}
        </Fragment>
    )
}

/** The one parameter whose catalog this screen states as a table - the register's value filter. */
const ATTRIBUTE_FILTER_PARAMETER = 'd2-attribute'

/** One parameter's contract - its prose, with the attribute catalog as a table when it is one. */
function ParameterDocumentation({
    parameter,
    attributes,
}: {
    parameter: CapabilityStatementSearchParam
    attributes: FilterAttribute[]
}) {
    if (parameter.documentation === undefined) return <>-</>
    // The declaration states the grammar and points at the registration Questionnaires for the
    // catalog; this screen has the same catalog structured, from /uiconfig, and states it as a
    // table under the prose - the one place a person reads the contract and the columns together.
    const catalog = parameter.name === ATTRIBUTE_FILTER_PARAMETER && attributes.length > 0
    if (!catalog) return <ProseText text={parameter.documentation} />
    return (
        <div className="space-y-2">
            <ProseText text={parameter.documentation} />
            <div className="show-scrollbars overflow-x-auto rounded-md border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead className="h-8 text-xs">Attribute</TableHead>
                            <TableHead className="h-8 text-xs">UID</TableHead>
                            <TableHead className="h-8 text-xs">Values</TableHead>
                            <TableHead className="h-8 text-xs">Value set</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {attributes.map((attribute) => (
                            <TableRow key={attribute.uid}>
                                <TableCell className="py-1.5 text-xs">
                                    {attribute.name ?? attribute.uid}
                                </TableCell>
                                <TableCell className="py-1.5 font-mono text-[11px]">
                                    {attribute.uid}
                                </TableCell>
                                <TableCell className="py-1.5 font-mono text-[11px]">
                                    {attribute.value_type ?? '-'}
                                </TableCell>
                                <TableCell className="py-1.5 font-mono text-[11px] break-all">
                                    {attribute.value_set ?? '-'}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
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
