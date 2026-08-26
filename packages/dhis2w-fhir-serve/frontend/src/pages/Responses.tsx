import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { ChevronRight, FileWarning, RefreshCw } from 'lucide-react'

import { ApiLink } from '@/components/ApiLink'
import { PageHeader, PageState } from '@/components/PageState'
import { ProseText } from '@/components/ProseText'
import { FormKindBadge, LifecycleBadge } from '@/components/ReceiptBadges'
import { NO_RECEIPT_OPENED, ReceiptSheet } from '@/components/ReceiptSheet'
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
import { useStatusLine } from '@/hooks/use-status-bar'
import { type Questionnaire } from '@/lib/fhir'
import { formLabel } from '@/lib/receipt'
import {
    LIFECYCLE_HINTS,
    LIFECYCLE_LABELS,
    LIFECYCLE_TINTS,
    RESPONSE_LIFECYCLES,
    formatInstant,
    type LifecycleHint,
    type QuarantinedFile,
    type ResponseLifecycle,
} from '@/lib/spool'
import { cn, countedNoun, formatCount } from '@/lib/utils'

/** The query parameter naming the lifecycle the listing is narrowed to. */
const LIFECYCLE_QUERY_PARAMETER = 'lifecycle'

/** The query parameter naming the receipt whose quick view is open over the listing. */
const OPENED_QUERY_PARAMETER = 'open'

/**
 * What came back: every capture this server stored, and what has become of it.
 *
 * A FILE THAT IS NOT A RECEIPT IS STATED FIRST. The spool also holds what it could not read, and
 * `counts.malformed` with the `malformed[]` reasons beside it is the whole of what is known about
 * those. They are in none of the four states and in none of the table's columns, so they are a
 * section above it - see `QuarantinedSection`.
 *
 * WHAT THIS PAGE IS ACTUALLY SHOWING. Not a view of DHIS2. A receipt is the
 * submission as it arrived, and the lifecycle beside it is which of the spool's
 * four directories the file currently sits in - `received` until
 * `d2w fhir forward` drains it, then `forwarded` or `rejected` depending on what
 * DHIS2 said. That is why the reload button matters: the forwarder is another
 * process moving files under a page that is already open, and the server
 * re-reads the directory to answer, so a reload is a real refresh rather than a
 * cache bust. `useSpool` also refetches when the window regains focus, which
 * catches the sequence this is actually used in - drain in the other terminal,
 * switch back to the browser.
 *
 * AND ON EVERY ARRIVAL AT THE ROUTE. Coming from another page mounts this one
 * and its first read is fresh by construction; arriving from this page - the
 * Responses nav item pressed while the table is already open, or a lifecycle
 * chosen - does not, so the effect below reads again for it. Between arrivals
 * nothing polls: a window left open and unfocused shows what it last read until
 * it regains focus, is arrived at again, or the Reload button is pressed.
 *
 * The form title comes from a second read. The spool states the canonical each
 * receipt answered but not the form's title, because a receipt is a fact about
 * a submission and the title is a fact about the guide - and the guide can be
 * rebuilt between the capture and the reading. So the Questionnaires are read
 * separately and joined by id, and a receipt whose form is no longer published
 * shows its canonical instead of pretending to a title.
 *
 * A ROW OPENS IN A SHEET OVER THE TABLE. The receipt in full - its answers joined
 * to the questions that were asked, the DHIS2 context it carries, and the import
 * report behind a rejection - arrives where the row is, and Esc gives the table
 * back with its filter and the reader's place in it untouched. `/responses/{id}`
 * is still a route of its own, which is what makes a particular receipt something
 * you can send someone a link to, and the sheet carries the way to it.
 *
 * THE LIFECYCLE FILTER LIVES IN THE URL, as `?lifecycle=received` on the hash
 * route. It is the one filter another page links into - the Overview's spool
 * tiles are counts you click to act on, and landing on an unfiltered table would
 * make the reader redo the narrowing they just asked for. A query parameter is
 * the smallest mechanism that does that: no shared store, no navigation state to
 * lose on a reload, and "responses that DHIS2 refused" becomes a link somebody
 * can be sent. The form filter stays local, because nothing links into it.
 * Selecting a state pushes, because it is a discrete choice a reader made and
 * Back is the way out of it.
 */
export function Responses() {
    const { listing, loading, error, refreshing, reload } = useSpool()
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const [searchParameters, setSearchParameters] = useSearchParams()
    const [formFilter, setFormFilter] = useState<string | null>(null)

    // The opened receipt lives in the URL as `?open={id}`, beside the lifecycle filter: the quick
    // view a reader has open is part of where they are, so a reload lands on the same receipt and
    // the address bar always says what is on screen.
    //
    // OPENING PUSHES, SHUTTING REPLACES. Opening a receipt is a place a reader went, so Back is
    // what shuts it - and because the whole state is in the address, shutting it that way restores
    // the filter and the search underneath for free. Shutting it by Escape or the close control
    // writes the parameter away in place instead, so the two ways out do not leave a history entry
    // per open-and-shut.
    const opened = searchParameters.get(OPENED_QUERY_PARAMETER) ?? NO_RECEIPT_OPENED
    const openReceipt = (responseId: string) => {
        const shutting = responseId === NO_RECEIPT_OPENED
        // A repeat is not a navigation: re-opening the receipt already open would stack an entry
        // Back has to step over before it shuts anything.
        if ((searchParameters.get(OPENED_QUERY_PARAMETER) ?? NO_RECEIPT_OPENED) === responseId) return
        setSearchParameters(
            (current) => {
                const written = new URLSearchParams(current)
                if (shutting) written.delete(OPENED_QUERY_PARAMETER)
                else written.set(OPENED_QUERY_PARAMETER, responseId)
                return written
            },
            { replace: shutting },
        )
    }

    // One read per arrival, and no more: the key changes on every navigation to this route, and the
    // one the page mounted on is the read already in flight - reloading for it would ask the same
    // question twice in a frame.
    const arrival = useLocation().key
    const arrivalRead = useRef(arrival)
    useEffect(() => {
        if (arrivalRead.current === arrival) return
        arrivalRead.current = arrival
        reload()
    }, [arrival, reload])

    const asked = searchParameters.get(LIFECYCLE_QUERY_PARAMETER)
    // Validated against the vocabulary rather than trusted: `?lifecycle=nonsense` filters
    // everything out silently, which reads as "this project has no receipts".
    const lifecycleFilter = RESPONSE_LIFECYCLES.find((candidate) => candidate === asked) ?? null
    // A chip is a discrete choice, so it pushes: Back walks off the filter and onto the listing
    // the reader was looking at before they narrowed it.
    const setLifecycleFilter = (next: ResponseLifecycle | null) => {
        if ((searchParameters.get(LIFECYCLE_QUERY_PARAMETER) ?? '') === (next ?? '')) return
        setSearchParameters((current) => {
            const written = new URLSearchParams(current)
            if (next === null) written.delete(LIFECYCLE_QUERY_PARAMETER)
            else written.set(LIFECYCLE_QUERY_PARAMETER, next)
            return written
        })
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

    // How much of the spool the table is showing. The state on the right is why the two numbers
    // differ, said in the same words the filter's own button carries - the form filter is not on it,
    // because a form's title is as long as DHIS2 made it and would push the count off the bar.
    useStatusLine(
        loading ? null : `Showing ${formatCount(rows.length)} of ${countedNoun(listing.total, 'receipt')}`,
        lifecycleFilter === null ? null : LIFECYCLE_LABELS[lifecycleFilter],
    )

    return (
        <>
            <PageHeader
                title="Responses"
                description="Every capture this server stored as a receipt, and where each receipt is now."
                aside={<ApiLink path="/QuestionnaireResponse" />}
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
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button variant="outline" size="sm" onClick={reload} disabled={refreshing}>
                            <RefreshCw className={cn('size-4', refreshing && 'animate-spin')} aria-hidden />
                            Reload
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">Read this list from the server again</TooltipContent>
                </Tooltip>
            </div>

            <QuarantinedSection count={listing.counts.malformed} files={listing.malformed} />

            <PageState
                loading={loading}
                error={error}
                empty={listing.total === 0}
                emptyMessage="Nothing has been captured into this project yet. A receipt arrives here when a client POSTs a QuestionnaireResponse - fill a form in from the Forms page, or ask the server for a synthetic one with GET /Questionnaire/{id}/$generate and post it back."
            >
                {rows.length === 0 ? (
                    <Card>
                        <CardContent className="text-muted-foreground py-8 text-sm">
                            No receipt matches this filter. {listing.total} stored in total.
                        </CardContent>
                    </Card>
                ) : (
                    <div className="show-scrollbars overflow-x-auto md:overflow-x-visible rounded-lg border">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    {/* "Captured", not "Received": the State column beside it
                                        already says Received, and when a capture arrived and where
                                        it sits now are two different facts. */}
                                    <TableHead>Captured</TableHead>
                                    <TableHead>Form</TableHead>
                                    <TableHead>Kind</TableHead>
                                    <TableHead>State</TableHead>
                                    <TableHead className="text-right">Answers</TableHead>
                                    <TableHead>Receipt</TableHead>
                                    <TableHead className="w-8" aria-hidden />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rows.map((summary) => {
                                    const label = formLabel(summary, formsByCanonical.get(summary.questionnaire))
                                    const open = () => {
                                        openReceipt(summary.response_id)
                                    }
                                    return (
                                        <TableRow
                                            key={summary.response_id}
                                            className="interactive"
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
                                            <TableCell>
                                                <span className="interactive-title">{label}</span>
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
                                            <TableCell className="machine-identifier text-xs">
                                                {summary.response_id}
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
                )}
            </PageState>

            <ReceiptSheet
                responseId={opened}
                onOpenChange={(next) => {
                    if (!next) openReceipt(NO_RECEIPT_OPENED)
                }}
            />
        </>
    )
}

/**
 * The files that reached the spool and could not be read as receipts.
 *
 * NOT A FIFTH STATE, AND ABOVE THE TABLE RATHER THAN IN IT. The four lifecycle states are where a
 * receipt's file sits; a quarantined file is one the facade could not read as a receipt at all, so
 * it has no form, no answers, no id to open, and nothing the table's columns could say about it. It
 * is also the one thing in the spool nobody can act on without being told: a capture that arrived
 * and could not be read is a capture that is not going to DHIS2 and is not going to appear anywhere
 * else. So it is stated above the table, with the server's own reason per file.
 *
 * THE COUNT AND THE LIST CAN DISAGREE, and the count is the one believed. `/spool` names the files
 * it moved aside on the page it answers; a listing walked over several pages, or a server that
 * counted more than it named, leaves a count with nothing under it - which is still worth saying.
 */
function QuarantinedSection({ count, files }: { count: number; files: QuarantinedFile[] }) {
    if (count === 0 && files.length === 0) return null
    const stated = Math.max(count, files.length)
    return (
        <section data-testid="spool-quarantined" className="mb-4 space-y-2 rounded-lg border p-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
                <FileWarning className="text-status-rejected size-4" aria-hidden />
                Quarantined
                <span className="machine-identifier text-xs">{stated}</span>
            </h3>
            <p className="text-muted-foreground text-sm">
                {stated === 1 ? 'One file reached' : `${formatCount(stated)} files reached`} this project's spool
                and could not be read as a receipt. {stated === 1 ? 'It is' : 'They are'} in no state, and{' '}
                {stated === 1 ? 'is' : 'are'} not in the table below.
            </p>
            {files.length > 0 && (
                <dl className="grid gap-2 text-sm">
                    {files.map((file) => (
                        <div key={file.file_name} className="grid gap-0.5">
                            <dt className="font-mono text-xs break-all">{file.file_name}</dt>
                            <dd className="text-muted-foreground text-xs">
                                <ProseText text={file.reason} />
                            </dd>
                        </div>
                    ))}
                </dl>
            )}
        </section>
    )
}

/**
 * The lifecycle filter, as a toggle group with the counts on it.
 *
 * The counts are the point. "Received 12" is the queue depth and the one number
 * that says whether a forward run is overdue; a filter that only narrowed the
 * table would make a person count rows to learn it.
 *
 * Each button states the state and its count as two facts, because they are two:
 * the count sits in its own element for the mono face it is set in, and a name
 * read off the elements alone would run them into the single word "Received12".
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
    // The group is named for the column the table heads with, because it filters that column.
    // "Lifecycle" is this project's word for the state and appears nowhere a reader can see.
    return (
        <div className="flex flex-wrap items-center gap-1 rounded-lg border p-1" role="group" aria-label="State">
            <Button
                variant={selected === null ? 'secondary' : 'ghost'}
                size="sm"
                aria-pressed={selected === null}
                aria-label={`All, ${String(total)}`}
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
                            aria-label={`${LIFECYCLE_LABELS[lifecycle]}, ${String(counts[lifecycle])}`}
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
                    <TooltipContent side="bottom">
                        <LifecycleHintLine hint={LIFECYCLE_HINTS[lifecycle]} />
                    </TooltipContent>
                </Tooltip>
            ))}
        </div>
    )
}

/** One state's line, with the command it names set in the mono face the rest of the app uses. */
function LifecycleHintLine({ hint }: { hint: LifecycleHint }) {
    if (hint.command === null) return <>{hint.lead}</>
    return (
        <>
            {hint.lead} <code className="font-mono">{hint.command}</code>
            {hint.tail}
        </>
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
