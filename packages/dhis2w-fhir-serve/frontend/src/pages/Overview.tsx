import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

import { PageHeader, PageState } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { refreshServerStatus, useServerStatus } from '@/hooks/use-server-status'
import { useSpool } from '@/hooks/use-spool'
import {
    FORM_TYPE_LABELS,
    formIdentifier,
    formSlice,
    formTitle,
    formTypeOf,
    operationNames,
    questionCount,
    servedIgLabel,
    type CapabilityStatement,
    type Questionnaire,
} from '@/lib/fhir'
import {
    LIFECYCLE_LABELS,
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    topRejectionCause,
    type RejectionCause,
    type ResponseLifecycle,
    type SpoolCounts,
    type SpoolResponseSummary,
} from '@/lib/spool'
import { cn } from '@/lib/utils'

/**
 * The root route: the state of capture, right now, in one screen.
 *
 * THE QUESTION THIS PAGE ANSWERS is "is there anything for me to do" - and the answer is one
 * number, the count of receipts sitting in `received`. That is the queue `d2w fhir forward`
 * drains, so a non-zero received count is the only thing on this page that is a task. Everything
 * else here is context for it: what became of the ones already drained, which forms a new capture
 * can be started from, and which guide this process is actually serving.
 *
 * THREE SECTIONS THAT FAIL SEPARATELY. The spool is read from `GET /spool`, the forms from
 * `GET /Questionnaire`, the identity from `GET /metadata` - three reads, three `PageState`s. A
 * server that has stopped answering the spool must not blank the form cards, because opening a
 * form is still the useful thing to do; a project that publishes no Questionnaires must not hide
 * the receipts it already holds. So no section is allowed to gate another's render.
 *
 * WHY THE PULSE IS TILES AND NOT A CHART. Three counts of one quantity, with no time axis behind
 * them - the spool stores no history, only where each file is now. A bar chart of three bars would
 * be three numbers drawn as rectangles, and a trend line would be inventing data the server does
 * not keep. So the numbers are the form, `received` is emphasised as the one that is actionable,
 * and no tile carries a delta.
 */
export function Overview() {
    const { listing, loading: spoolLoading, error: spoolError } = useSpool()
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const { reachability, capability, checking } = useServerStatus()

    useEffect(() => {
        if (reachability === 'unknown') void refreshServerStatus()
    }, [reachability])

    return (
        <>
            <PageHeader
                title="Overview"
                description="What this server holds right now: the receipts waiting to be forwarded, the forms a capture starts from, and the guide behind both."
            />

            <div className="space-y-8">
                <SpoolPulse
                    counts={listing.counts}
                    total={listing.total}
                    responses={listing.responses}
                    loading={spoolLoading}
                    error={spoolError}
                />
                <CaptureSection
                    questionnaires={forms.resources}
                    loading={forms.loading}
                    error={forms.error}
                />
                <ServerIdentity
                    capability={capability}
                    reachability={reachability}
                    checking={checking}
                />
            </div>
        </>
    )
}

/** How many forms the quick-entry grid shows before it defers to the Forms table. */
const QUICK_ENTRY_FORMS = 8

/**
 * The spool pulse: three counts, one of which is a task.
 *
 * Each tile opens the Responses listing already filtered to its state, which is what makes a
 * count a starting point rather than a fact to go and re-find. The rejected tile also names the
 * error code most of its receipts share, because "Rejected 12" and "Rejected 12, mostly E1029"
 * lead to different afternoons.
 */
function SpoolPulse({
    counts,
    total,
    responses,
    loading,
    error,
}: {
    counts: SpoolCounts
    total: number
    responses: SpoolResponseSummary[]
    loading: boolean
    error: string | null
}) {
    const cause = topRejectionCause(responses)

    return (
        <section className="space-y-3">
            <SectionHeading
                title="The spool"
                description="Every receipt this server stored, by which of the spool's three directories its file is in."
            />
            <PageState
                loading={loading}
                error={error}
                empty={total === 0}
                emptyRender={<NothingCaptured />}
            >
                <div className="grid gap-3 sm:grid-cols-3">
                    {RESPONSE_LIFECYCLES.map((lifecycle) => (
                        <StatTile
                            key={lifecycle}
                            lifecycle={lifecycle}
                            count={counts[lifecycle]}
                            subtitle={subtitleFor(lifecycle, counts, cause)}
                        />
                    ))}
                </div>
            </PageState>
        </section>
    )
}

/**
 * One count, as the thing you click to go and act on it.
 *
 * TILE ANATOMY. A status dot carries the state's colour, the label names it in ink, and the value
 * is the number and nothing else - no delta, no sparkline, because the spool keeps no history and
 * a trend drawn over data that does not exist is a lie. `received` is set at hero size and given
 * the only tinted border on the page: it is the one number that means work is pending, and the
 * other two are what already happened. Values take the font's proportional figures rather than
 * `tabular-nums`, which makes a large standalone number read loose.
 */
function StatTile({
    lifecycle,
    count,
    subtitle,
}: {
    lifecycle: ResponseLifecycle
    count: number
    subtitle: string
}) {
    const actionable = lifecycle === 'received'
    return (
        <Link
            to={`/responses?lifecycle=${lifecycle}`}
            aria-label={`${LIFECYCLE_LABELS[lifecycle]} ${String(count)} - ${subtitle}. Open the responses filtered to this state.`}
            className={cn(
                'bg-card hover:bg-accent/40 focus-visible:ring-ring/50 block rounded-lg border p-4 transition-colors focus-visible:ring-[3px] focus-visible:outline-none',
                actionable && 'border-status-received/40',
            )}
        >
            <span className="flex items-center gap-2">
                <span
                    className={cn('size-2 shrink-0 rounded-full', LIFECYCLE_TINTS[lifecycle].dot)}
                    aria-hidden
                />
                <span className="text-sm font-medium">{LIFECYCLE_LABELS[lifecycle]}</span>
            </span>
            <span
                data-testid={`spool-${lifecycle}-count`}
                className={cn(
                    'mt-2 block font-semibold tracking-tight',
                    actionable ? 'text-5xl' : 'text-3xl',
                )}
            >
                {count}
            </span>
            <span className="text-muted-foreground mt-1 block text-sm">{subtitle}</span>
        </Link>
    )
}

/** The line under each count - what the state means, and for a rejection what it was mostly about. */
function subtitleFor(
    lifecycle: ResponseLifecycle,
    counts: SpoolCounts,
    cause: RejectionCause | null,
): string {
    if (lifecycle === 'received') return 'awaiting forward'
    if (lifecycle === 'forwarded') return 'accepted by DHIS2'
    if (counts.rejected === 0 || cause === null) return 'refused by DHIS2'
    const message = cause.message === null ? null : generalisedCauseMessage(cause.message)
    const named = message === null || message === '' ? cause.code : `${cause.code} ${message}`
    return cause.receipts === counts.rejected ? named : `mostly ${named}`
}

/**
 * A DHIS2 issue message with its backtick-quoted instances generalised away.
 *
 * The tile summarises a cause, and DHIS2 writes each message about one object - "Event `abc` ..."
 * - so the verbatim first message reads as a single event's story on a tile counting many. The
 * quoted uids become an ellipsis, which is the same generalisation the forward report's rollup
 * groups rejections by.
 */
function generalisedCauseMessage(message: string): string {
    return message
        .replace(/`[^`]*`/g, '...')
        .replace(/\s+/g, ' ')
        .trim()
}

/**
 * Zero receipts, as an invitation rather than three zeroes.
 *
 * Three tiles reading 0 would state the same thing three times and imply the interesting part is
 * the split between them. On an empty project the only useful next move is to open a form, so
 * that is what the section says.
 */
function NothingCaptured() {
    return (
        <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-4 py-6">
                <p className="text-muted-foreground text-sm">
                    No responses captured yet - open a form to capture the first. A receipt arrives
                    here the moment a client POSTs a QuestionnaireResponse.
                </p>
                <Button asChild variant="outline" size="sm">
                    <Link to="/forms">
                        All forms
                        <ArrowRight aria-hidden />
                    </Link>
                </Button>
            </CardContent>
        </Card>
    )
}

/** The served forms as quick entry: the shortcut into the capture loop, not a second listing. */
function CaptureSection({
    questionnaires,
    loading,
    error,
}: {
    questionnaires: Questionnaire[]
    loading: boolean
    error: string | null
}) {
    const slice = formSlice(questionnaires, QUICK_ENTRY_FORMS)

    return (
        <section className="space-y-3">
            <SectionHeading
                title="Capture a response"
                description="Every Questionnaire this server publishes is a form you can fill in and post back."
            />
            <PageState
                loading={loading}
                error={error}
                empty={slice.total === 0}
                emptyMessage="This project publishes no Questionnaires, so there is nothing to capture against. Run `make generate` then `make sushi` to compile the IG, or serve it with --live."
            >
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {slice.shown.map((questionnaire) => (
                        <FormCard
                            key={questionnaire.url ?? formIdentifier(questionnaire)}
                            questionnaire={questionnaire}
                        />
                    ))}
                </div>
                {slice.hidden > 0 && (
                    <div className="mt-3">
                        <Button asChild variant="outline" size="sm">
                            <Link to="/forms">
                                All {slice.total} forms
                                <ArrowRight aria-hidden />
                            </Link>
                        </Button>
                    </div>
                )}
            </PageState>
        </section>
    )
}

/** One form, as the three facts that decide whether it is the one you want to open. */
function FormCard({ questionnaire }: { questionnaire: Questionnaire }) {
    const kind = formTypeOf(questionnaire)
    const questions = questionCount(questionnaire.item)
    const title = formTitle(questionnaire)

    return (
        <Link
            to={`/forms/${formIdentifier(questionnaire)}`}
            aria-label={`Open ${title}`}
            className="bg-card hover:bg-accent/40 focus-visible:ring-ring/50 flex h-full flex-col gap-3 rounded-lg border p-4 transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
        >
            <span className="text-sm font-medium">{title}</span>
            <span className="mt-auto flex flex-wrap items-center gap-2">
                {kind === null ? (
                    <Badge variant="outline" className="text-muted-foreground">
                        no form type
                    </Badge>
                ) : (
                    <Badge variant="secondary">{FORM_TYPE_LABELS[kind]}</Badge>
                )}
                <span className="text-muted-foreground font-mono text-xs">
                    {questions} questions
                </span>
            </span>
        </Link>
    )
}

/**
 * Who is answering, in one strip.
 *
 * The same facts the status menu holds behind a dropdown, laid out flat - because the question
 * "which guide is this, at which version, from which store" is the first one to ask when a capture
 * behaves unexpectedly, and a UI pointed at a stale `--live` process looks identical to one
 * pointed at a freshly compiled IG until somebody reads the conformance document.
 */
function ServerIdentity({
    capability,
    reachability,
    checking,
}: {
    capability: CapabilityStatement | null
    reachability: 'unknown' | 'ok' | 'unreachable'
    checking: boolean
}) {
    const igLabel = servedIgLabel(capability)
    const operations = operationNames(capability)
    const resourceTypes = capability?.rest?.[0]?.resource?.length ?? 0

    return (
        <section className="space-y-3">
            <SectionHeading
                title="This server"
                description="What /metadata says it is - the facade's only contract, since it publishes no OpenAPI document."
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
                <Card>
                    <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-3 py-4">
                        <span className="flex min-w-0 items-center gap-2">
                            <span
                                className={cn(
                                    'size-2 shrink-0 rounded-full',
                                    reachability === 'ok' ? 'bg-status-forwarded' : 'bg-muted-foreground',
                                )}
                                aria-hidden
                            />
                            <span className="truncate text-sm font-medium">
                                {igLabel ?? 'An unnamed guide'}
                            </span>
                            {capability?.software?.version !== undefined && (
                                <Badge variant="secondary" className="font-mono text-[0.7rem]">
                                    {capability.software.version}
                                </Badge>
                            )}
                        </span>

                        <span className="text-muted-foreground text-sm">
                            {resourceTypes} resource types
                        </span>

                        {operations.length > 0 && (
                            <span className="flex flex-wrap items-center gap-1.5">
                                {operations.map((operation) => (
                                    <Badge
                                        key={operation}
                                        variant="outline"
                                        className="font-mono text-[0.7rem]"
                                    >
                                        ${operation}
                                    </Badge>
                                ))}
                            </span>
                        )}

                        <div className="flex-1" />

                        <Button asChild variant="outline" size="sm">
                            <Link to="/server">
                                What /metadata declares
                                <ArrowRight aria-hidden />
                            </Link>
                        </Button>

                        {capability?.implementation?.description !== undefined && (
                            <p className="text-muted-foreground w-full text-xs">
                                {capability.implementation.description}
                            </p>
                        )}
                    </CardContent>
                </Card>
            </PageState>
        </section>
    )
}

/** A section's heading and the one line saying what it is answering. */
function SectionHeading({ title, description }: { title: string; description: string }) {
    return (
        <div className="space-y-0.5">
            <h3 className="text-base font-semibold">{title}</h3>
            <p className="text-muted-foreground text-sm">{description}</p>
        </div>
    )
}
