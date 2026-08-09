import { useMemo, useState } from 'react'
import { AlertTriangle, Inbox, RefreshCw, TriangleAlert } from 'lucide-react'

import { PageHeader, PageState } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { useSpool } from '@/hooks/use-spool'
import { FORM_TYPE_LABELS, canonicalId, type Questionnaire } from '@/lib/fhir'
import {
    LIFECYCLE_HINTS,
    LIFECYCLE_LABELS,
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    captureContext,
    formatInstant,
    rejectionSummary,
    type ResponseLifecycle,
    type SpoolRejectionIssue,
    type SpoolResponseSummary,
} from '@/lib/spool'
import { cn } from '@/lib/utils'

/**
 * What came back: every capture this server stored, and what has become of it.
 *
 * WHAT THIS PAGE IS ACTUALLY SHOWING. Not a view of DHIS2. A receipt is the
 * submission as it arrived, and the lifecycle beside it is which of the spool's
 * three directories the file currently sits in - `received` until
 * `d2w fhir forward` drains it, then `forwarded` or `rejected` depending on what
 * DHIS2 said. That is why the reload button matters: the forwarder is another
 * process moving files under a page that is already open, and the server
 * re-reads the directory to answer, so a reload is a real refresh rather than a
 * cache bust. `useSpool` also refetches when the window regains focus, which
 * catches the sequence this is actually used in - drain in the other terminal,
 * switch back to the browser.
 *
 * The form title comes from a second read. The spool states the canonical each
 * receipt answered but not the form's title, because a receipt is a fact about
 * a submission and the title is a fact about the guide - and the guide can be
 * rebuilt between the capture and the reading. So the Questionnaires are read
 * separately and joined by id, and a receipt whose form is no longer published
 * shows its canonical instead of pretending to a title.
 */
export function Responses() {
    const { listing, loading, error, refreshing, reload } = useSpool()
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const [lifecycleFilter, setLifecycleFilter] = useState<ResponseLifecycle | null>(null)
    const [formFilter, setFormFilter] = useState<string | null>(null)
    const [opened, setOpened] = useState<SpoolResponseSummary | null>(null)

    const formsByCanonical = useMemo(() => {
        const index = new Map<string, Questionnaire>()
        for (const form of forms.resources) {
            if (form.url) index.set(form.url, form)
        }
        return index
    }, [forms.resources])

    const rows = listing.responses.filter(
        (summary) =>
            (lifecycleFilter === null || summary.lifecycle === lifecycleFilter) &&
            (formFilter === null || summary.questionnaire === formFilter),
    )

    const formOptions = useMemo(() => {
        const seen = new Map<string, string>()
        for (const summary of listing.responses) {
            if (seen.has(summary.questionnaire)) continue
            seen.set(summary.questionnaire, formLabel(summary, formsByCanonical.get(summary.questionnaire)))
        }
        return [...seen.entries()].toSorted((left, right) => left[1].localeCompare(right[1]))
    }, [listing.responses, formsByCanonical])

    return (
        <>
            <PageHeader
                title="Responses"
                description="Every capture this server stored, as the receipt it was stored as - and where that receipt is now."
            />

            <div className="mb-4 flex flex-wrap items-center gap-2">
                <LifecycleFilter
                    counts={listing.counts}
                    total={listing.total}
                    selected={lifecycleFilter}
                    onSelect={setLifecycleFilter}
                />
                <div className="flex-1" />
                {formOptions.length > 1 && (
                    <FormFilter options={formOptions} selected={formFilter} onSelect={setFormFilter} />
                )}
                <Button variant="outline" size="sm" onClick={reload} disabled={refreshing}>
                    <RefreshCw className={cn('size-4', refreshing && 'animate-spin')} aria-hidden />
                    Reload
                </Button>
            </div>

            <PageState
                loading={loading}
                error={error}
                empty={listing.total === 0}
                emptyMessage="Nothing has been captured into this project yet. A response arrives here when a client POSTs one to /QuestionnaireResponse - fill a form in from the Forms page, or ask the server for a synthetic one with GET /Questionnaire/{id}/$generate and post it back."
            >
                {rows.length === 0 ? (
                    <Card>
                        <CardContent className="text-muted-foreground py-8 text-sm">
                            No receipt matches this filter. {listing.total} stored in total.
                        </CardContent>
                    </Card>
                ) : (
                    <div className="show-scrollbars overflow-x-auto rounded-lg border">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Received</TableHead>
                                    <TableHead>Form</TableHead>
                                    <TableHead>Kind</TableHead>
                                    <TableHead>State</TableHead>
                                    <TableHead className="text-right">Answers</TableHead>
                                    <TableHead>Receipt</TableHead>
                                    <TableHead className="w-0" />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rows.map((summary) => {
                                    const form = formsByCanonical.get(summary.questionnaire)
                                    return (
                                        <TableRow key={summary.response_id}>
                                            <TableCell className="whitespace-nowrap">
                                                {formatInstant(summary.received_at)}
                                            </TableCell>
                                            <TableCell className="font-medium">
                                                {formLabel(summary, form)}
                                            </TableCell>
                                            <TableCell>
                                                <FormKindBadge kind={summary.form_kind} />
                                            </TableCell>
                                            <TableCell>
                                                <LifecycleBadge summary={summary} />
                                            </TableCell>
                                            <TableCell className="text-right font-mono text-xs">
                                                {summary.answer_count}
                                            </TableCell>
                                            <TableCell className="text-muted-foreground font-mono text-xs">
                                                {summary.response_id}
                                            </TableCell>
                                            <TableCell>
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => setOpened(summary)}
                                                >
                                                    Open
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    )
                                })}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </PageState>

            <ResponseDetail
                summary={opened}
                form={opened ? formsByCanonical.get(opened.questionnaire) : undefined}
                onClose={() => setOpened(null)}
            />
        </>
    )
}

/**
 * The lifecycle filter, as a toggle group with the counts on it.
 *
 * The counts are the point. "Received 12" is the queue depth and the one number
 * that says whether a forward run is overdue; a filter that only narrowed the
 * table would make a person count rows to learn it.
 */
function LifecycleFilter({
    counts,
    total,
    selected,
    onSelect,
}: {
    counts: Record<ResponseLifecycle, number>
    total: number
    selected: ResponseLifecycle | null
    onSelect: (lifecycle: ResponseLifecycle | null) => void
}) {
    return (
        <div className="flex flex-wrap items-center gap-1 rounded-lg border p-1" role="group" aria-label="Lifecycle">
            <Button
                variant={selected === null ? 'secondary' : 'ghost'}
                size="sm"
                aria-pressed={selected === null}
                onClick={() => onSelect(null)}
            >
                All
                <span className="text-muted-foreground ml-1 font-mono text-xs">{total}</span>
            </Button>
            {RESPONSE_LIFECYCLES.map((lifecycle) => (
                <Tooltip key={lifecycle}>
                    <TooltipTrigger asChild>
                        <Button
                            variant={selected === lifecycle ? 'secondary' : 'ghost'}
                            size="sm"
                            aria-pressed={selected === lifecycle}
                            onClick={() => onSelect(selected === lifecycle ? null : lifecycle)}
                        >
                            <span
                                className={cn(
                                    'size-2 shrink-0 rounded-full',
                                    LIFECYCLE_TINTS[lifecycle].dot,
                                )}
                                aria-hidden
                            />
                            {LIFECYCLE_LABELS[lifecycle]}
                            <span className="text-muted-foreground ml-1 font-mono text-xs">
                                {counts[lifecycle]}
                            </span>
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">{LIFECYCLE_HINTS[lifecycle]}</TooltipContent>
                </Tooltip>
            ))}
        </div>
    )
}

/**
 * The form filter.
 *
 * A plain `<select>` rather than a combobox: the option set is the forms this
 * project has receipts for, which is small, and a native control is the one that
 * behaves on a field device without any of this app's own keyboard handling.
 */
function FormFilter({
    options,
    selected,
    onSelect,
}: {
    options: [string, string][]
    selected: string | null
    onSelect: (canonical: string | null) => void
}) {
    return (
        <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Form</span>
            <select
                className="border-input bg-background focus-visible:ring-ring/50 h-8 rounded-md border px-2 text-sm focus-visible:ring-[3px] focus-visible:outline-none"
                value={selected ?? ''}
                onChange={(event) => onSelect(event.target.value || null)}
            >
                <option value="">All forms</option>
                {options.map(([canonical, label]) => (
                    <option key={canonical} value={canonical}>
                        {label}
                    </option>
                ))}
            </select>
        </label>
    )
}

/** Which spool directory the receipt is in, tinted by the shared lifecycle tokens. */
function LifecycleBadge({ summary }: { summary: SpoolResponseSummary }) {
    return (
        <span className="flex items-center gap-1.5">
            <Badge variant="outline" className={LIFECYCLE_TINTS[summary.lifecycle].badge}>
                {LIFECYCLE_LABELS[summary.lifecycle]}
            </Badge>
            {summary.warnings.length > 0 && (
                <Tooltip>
                    <TooltipTrigger asChild>
                        <TriangleAlert
                            className="text-status-refused size-3.5 shrink-0"
                            aria-label={`${summary.warnings.length} warning(s) recorded on capture`}
                        />
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                        {summary.warnings.length} warning(s) recorded when this was captured
                    </TooltipContent>
                </Tooltip>
            )}
        </span>
    )
}

/** The DHIS2 object kind the receipt was validated as, or a stated absence. */
function FormKindBadge({ kind }: { kind: string }) {
    const known = (FORM_TYPE_LABELS as Record<string, string | undefined>)[kind]
    if (!known) {
        return (
            <Badge variant="outline" className="text-muted-foreground">
                {kind || 'no form type'}
            </Badge>
        )
    }
    return <Badge variant="secondary">{known}</Badge>
}

/**
 * One receipt in full: what it answered, the DHIS2 context it carries, and - when
 * DHIS2 refused it - the import report saying why.
 *
 * The rejection block is the reason this dialog exists at all. A row that says
 * "rejected" and nothing else is the one state a person cannot act on, and the
 * report the forwarder wrote beside the receipt is exactly the missing sentence.
 */
function ResponseDetail({
    summary,
    form,
    onClose,
}: {
    summary: SpoolResponseSummary | null
    form: Questionnaire | undefined
    onClose: () => void
}) {
    return (
        <Dialog open={summary !== null} onOpenChange={(open) => !open && onClose()}>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
                {summary && (
                    <>
                        <DialogHeader>
                            <DialogTitle className="flex flex-wrap items-center gap-2">
                                {formLabel(summary, form)}
                                <LifecycleBadge summary={summary} />
                            </DialogTitle>
                            <DialogDescription>
                                Received {formatInstant(summary.received_at)} - the submission as it
                                arrived, not a view of what DHIS2 now holds.
                            </DialogDescription>
                        </DialogHeader>

                        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                            <Fact label="Receipt id" value={summary.response_id} mono />
                            <Fact label="Answers" value={String(summary.answer_count)} />
                            <Fact label="Form kind" value={summary.form_kind || 'not stated'} />
                            <Fact
                                label="Questionnaire"
                                value={summary.questionnaire_id ?? summary.questionnaire}
                                mono
                            />
                            {captureContext(summary).map((fact) => (
                                <Fact key={fact.label} label={fact.label} value={fact.value} mono />
                            ))}
                        </dl>

                        {summary.warnings.length > 0 && (
                            <>
                                <Separator />
                                <section className="space-y-2">
                                    <h3 className="flex items-center gap-2 text-sm font-medium">
                                        <TriangleAlert className="text-status-refused size-4" aria-hidden />
                                        Recorded on capture
                                    </h3>
                                    <ul className="text-muted-foreground space-y-1 text-xs">
                                        {summary.warnings.map((warning) => (
                                            <li key={warning}>{warning}</li>
                                        ))}
                                    </ul>
                                </section>
                            </>
                        )}

                        {summary.rejection && (
                            <>
                                <Separator />
                                <section className="space-y-3">
                                    <h3 className="flex items-center gap-2 text-sm font-medium">
                                        <AlertTriangle className="text-status-rejected size-4" aria-hidden />
                                        DHIS2 refused this import
                                    </h3>
                                    <p className="text-muted-foreground text-sm">
                                        {rejectionSummary(summary.rejection)}
                                    </p>
                                    <dl className="text-muted-foreground grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
                                        <Fact label="Status" value={summary.rejection.status ?? 'not stated'} />
                                        <Fact label="Created" value={String(summary.rejection.created)} />
                                        <Fact label="Updated" value={String(summary.rejection.updated)} />
                                        <Fact label="Ignored" value={String(summary.rejection.ignored)} />
                                    </dl>
                                    {summary.rejection.issues.length > 0 && (
                                        <div className="show-scrollbars overflow-x-auto rounded-lg border">
                                            <Table>
                                                <TableHeader>
                                                    <TableRow>
                                                        <TableHead>Code</TableHead>
                                                        <TableHead>Object</TableHead>
                                                        <TableHead>What DHIS2 said</TableHead>
                                                    </TableRow>
                                                </TableHeader>
                                                <TableBody>
                                                    {keyedIssues(summary.rejection.issues).map((row) => (
                                                        <TableRow key={row.key}>
                                                            <TableCell className="font-mono text-xs">
                                                                {row.issue.error_code ?? '-'}
                                                            </TableCell>
                                                            <TableCell className="font-mono text-xs">
                                                                {row.issue.subject ?? '-'}
                                                            </TableCell>
                                                            <TableCell className="text-xs">
                                                                {row.issue.message ?? 'no reason given'}
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                        </div>
                                    )}
                                </section>
                            </>
                        )}

                        <Separator />
                        <p className="text-muted-foreground flex items-start gap-2 text-xs">
                            <Inbox className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                            The full resource reads back verbatim at{' '}
                            <code className="font-mono">
                                GET /QuestionnaireResponse/{summary.response_id}
                            </code>
                        </p>
                    </>
                )}
            </DialogContent>
        </Dialog>
    )
}

/**
 * Give each issue row a stable key.
 *
 * DHIS2 states a rule once and names every object that broke it, so two rows
 * with the same code and the same message are ordinary rather than a mistake -
 * the position is part of the identity, and it is computed here so the JSX below
 * keys on data rather than on a loop counter.
 */
function keyedIssues(issues: SpoolRejectionIssue[]): { key: string; issue: SpoolRejectionIssue }[] {
    return issues.map((issue, position) => ({
        key: `${String(position)}:${issue.error_code ?? ''}:${issue.subject ?? ''}`,
        issue,
    }))
}

/** One labelled fact in a detail grid. */
function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
    return (
        <div className="min-w-0">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className={cn('break-words', mono && 'font-mono text-xs')}>{value}</dd>
        </div>
    )
}

/**
 * What to call the form a receipt answered.
 *
 * The published title when the form is still served, then the id off the
 * canonical, then the canonical itself. A receipt outlives the guide that
 * produced it, so "the form is gone" has to render as something readable rather
 * than as a blank cell.
 */
function formLabel(summary: SpoolResponseSummary, form: Questionnaire | undefined): string {
    return (
        form?.title ??
        form?.name ??
        summary.questionnaire_id ??
        canonicalId(summary.questionnaire) ??
        summary.questionnaire
    )
}
