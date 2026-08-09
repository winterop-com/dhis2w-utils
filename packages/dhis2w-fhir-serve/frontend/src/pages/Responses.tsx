import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'

import { PageHeader, PageState } from '@/components/PageState'
import { FormKindBadge, LifecycleBadge } from '@/components/ReceiptBadges'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { type Questionnaire } from '@/lib/fhir'
import { formLabel } from '@/lib/receipt'
import {
    LIFECYCLE_HINTS,
    LIFECYCLE_LABELS,
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    formatInstant,
    type ResponseLifecycle,
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
 *
 * A ROW OPENS AT `/responses/{id}`. This is the index; the receipt in full - its
 * answers joined to the questions that were asked, the DHIS2 context it carries,
 * and the import report behind a rejection - is a route of its own, which is what
 * makes a particular receipt something you can send someone a link to.
 *
 * THE LIFECYCLE FILTER LIVES IN THE URL, as `?lifecycle=received` on the hash
 * route. It is the one filter another page links into - the Overview's spool
 * tiles are counts you click to act on, and landing on an unfiltered table would
 * make the reader redo the narrowing they just asked for. A query parameter is
 * the smallest mechanism that does that: no shared store, no navigation state to
 * lose on a reload, and "responses that DHIS2 refused" becomes a link somebody
 * can be sent. The form filter stays local, because nothing links into it.
 * Selecting writes with `replace`, so paging through states does not stack a
 * back-button entry per click.
 */
export function Responses() {
    const navigate = useNavigate()
    const { listing, loading, error, refreshing, reload } = useSpool()
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const [searchParameters, setSearchParameters] = useSearchParams()
    const [formFilter, setFormFilter] = useState<string | null>(null)

    const asked = searchParameters.get('lifecycle')
    // Validated against the vocabulary rather than trusted: `?lifecycle=nonsense` filters
    // everything out silently, which reads as "this project has no receipts".
    const lifecycleFilter = RESPONSE_LIFECYCLES.find((candidate) => candidate === asked) ?? null
    const setLifecycleFilter = (next: ResponseLifecycle | null) => {
        setSearchParameters(next === null ? {} : { lifecycle: next }, { replace: true })
    }

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
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rows.map((summary) => {
                                    const label = formLabel(summary, formsByCanonical.get(summary.questionnaire))
                                    const open = () => {
                                        navigate(`/responses/${summary.response_id}`)
                                    }
                                    return (
                                        <TableRow
                                            key={summary.response_id}
                                            className="hover:bg-accent cursor-pointer"
                                            tabIndex={0}
                                            aria-label={`Open the receipt for ${label}`}
                                            onClick={open}
                                            onKeyDown={(event) => {
                                                if (event.key === 'Enter' || event.key === ' ') {
                                                    event.preventDefault()
                                                    open()
                                                }
                                            }}
                                        >
                                            <TableCell className="whitespace-nowrap">
                                                {formatInstant(summary.received_at)}
                                            </TableCell>
                                            <TableCell className="font-medium">{label}</TableCell>
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
                                        </TableRow>
                                    )
                                })}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </PageState>
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
