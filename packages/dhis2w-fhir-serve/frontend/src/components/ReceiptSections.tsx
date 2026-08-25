import { useState, type ReactNode } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, Inbox, TriangleAlert, Undo2 } from 'lucide-react'

import { CodeBlock } from '@/components/CodeEditor'
import { PageState } from '@/components/PageState'
import { ProseText } from '@/components/ProseText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import type { ReceiptRecordState } from '@/hooks/use-receipt-record'
import type { QuestionnaireResponse } from '@/lib/fhir'
import type { OrgUnitChoice } from '@/lib/orgunits'
import type { ProgramRule } from '@/lib/questionnaire'
import {
    rejectionRuleName,
    type ReceiptAnswerRow,
    type ReceiptAnswerValue,
    type ReceiptContextFact,
} from '@/lib/receipt'
import {
    formatInstant,
    rejectionSummary,
    withdrawalSummary,
    type SpoolRefusal,
    type SpoolRejection,
    type SpoolRejectionIssue,
    type SpoolResponseSummary,
    type SpoolWithdrawal,
} from '@/lib/spool'

/**
 * One receipt in full: what it answered, the DHIS2 context it carries, and what became of it.
 *
 * WHY THE ANSWERS ARE THE HEADLINE. A spool row can say a receipt carries 128 answers; only this can
 * say what they were. The join is `joinAnswersToQuestions` in lib/receipt.ts - the form's own order,
 * the question text with its enclosing groups, and the value rendered as what it is, a coding keeping
 * both its display and the code DHIS2 will store. Unanswered questions are absent because the receipt
 * holds only the branches that were answered.
 *
 * AND A RAW VIEW UNDER ALL OF IT. Everything above is this UI's reading of the document. The
 * collapsible JSON is the document, so it can be checked against the bytes rather than believed.
 *
 * ONE BODY, TWO PLACES IT IS READ IN. The spool listing opens a row in a sheet over the table, and
 * the receipt's own route opens the same thing as a page for a link somebody was sent. A receipt that
 * read two ways would be two accounts of one submission, so it is written once and headed twice.
 */
export function ReceiptSections({ record }: { record: ReceiptRecordState }) {
    const { stored, summary } = record
    return (
        <PageState
            loading={stored.loading}
            error={stored.error}
            status={stored.status}
            empty={stored.resource === null && stored.error === null && !stored.loading}
            emptyMessage="This server holds no receipt under that id."
        >
            {stored.resource !== null && (
                <div className="space-y-6">
                    <ReceiptFacts
                        summary={summary}
                        stored={stored.resource}
                        seed={record.seed}
                        spoolLoading={record.spoolLoading}
                        spoolError={record.spoolError}
                    />

                    <CaptureContextSection facts={record.facts} />

                    <AnswersSection
                        rows={record.rows}
                        units={record.units}
                        formMissing={record.formMissing}
                        formLoading={record.formPending}
                    />

                    {summary !== null && summary.warnings.length > 0 && (
                        <section className="space-y-2">
                            <h3 className="flex items-center gap-2 text-base font-semibold">
                                <TriangleAlert className="text-status-refused size-4" aria-hidden />
                                Warnings recorded on capture
                            </h3>
                            {/* The validator quotes link ids and elements with backtick marks, and a
                                mark is a change of typeface rather than a character on the screen -
                                so every server-authored sentence here goes through ProseText. */}
                            <ul className="text-muted-foreground space-y-1 rounded-lg border p-4 text-sm">
                                {summary.warnings.map((warning) => (
                                    <li key={warning}>
                                        <ProseText text={warning} />
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {summary !== null && summary.rejection ? (
                        <RejectionSection rejection={summary.rejection} rules={record.rules} />
                    ) : null}

                    {summary !== null && summary.refusal ? (
                        <RefusalSection refusal={summary.refusal} />
                    ) : null}

                    {summary !== null && summary.withdrawal ? (
                        <WithdrawalSection withdrawal={summary.withdrawal} />
                    ) : null}

                    <RawResource resource={stored.resource} />

                    <p className="text-muted-foreground flex items-start gap-2 text-xs">
                        <Inbox className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                        The full resource reads back verbatim at{' '}
                        <code className="font-mono">GET /QuestionnaireResponse/{record.responseId}</code>
                    </p>
                </div>
            )}
        </PageState>
    )
}

/**
 * What the submission reports for and from, from both places those facts live.
 *
 * The spool derives the period, the unit, and the tracker handles when it indexes a receipt; the
 * attribute option combo is read straight off the stored resource, which is why this section
 * appears for a receipt the spool has no row for at all. Every fact is the receipt's own - nothing
 * here is looked up in DHIS2.
 */
function CaptureContextSection({ facts }: { facts: ReceiptContextFact[] }) {
    if (facts.length === 0) return null
    return (
        <section className="space-y-3">
            <div className="space-y-0.5">
                <h3 className="text-base font-semibold">Capture context</h3>
                <p className="text-muted-foreground text-sm">
                    What the submission reports for and from - read off the stored resource, not
                    looked up in DHIS2.
                </p>
            </div>
            <dl className="grid gap-x-6 gap-y-3 rounded-lg border p-4 text-sm sm:grid-cols-3">
                {facts.map((fact) => (
                    <Fact key={fact.label} label={fact.label} value={fact.value} mono={fact.mono} />
                ))}
            </dl>
        </section>
    )
}

/** The header block: when it arrived, what it is, and the handles it is found by again. */
function ReceiptFacts({
    summary,
    stored,
    seed,
    spoolLoading,
    spoolError,
}: {
    summary: SpoolResponseSummary | null
    stored: QuestionnaireResponse
    seed: string | null
    spoolLoading: boolean
    spoolError: string | null
}) {
    return (
        <div className="space-y-3 rounded-lg border p-4">
            <p className="text-sm">
                {summary === null
                    ? 'The submission as it arrived, not a view of what DHIS2 now holds.'
                    : `Received ${formatInstant(summary.received_at)} - the submission as it arrived, not a view of what DHIS2 now holds.`}
            </p>
            {stored.questionnaire !== undefined && (
                <p className="text-xs">
                    <span className="text-muted-foreground">Questionnaire </span>
                    <span className="machine-identifier break-all">
                        {stored.questionnaire}
                    </span>
                </p>
            )}
            <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
                <Fact label="Receipt id" value={stored.id ?? '-'} mono />
                <Fact
                    label="Answers"
                    value={summary === null ? '-' : String(summary.answer_count)}
                    mono
                />
                {seed !== null && <Fact label="Identifier" value={`generated from seed ${seed}`} />}
                {/* The response status is one of the capture-context facts below whenever the
                    spool answered; here it would be the same word twice on one screen. */}
                {summary === null && <Fact label="Response status" value={stored.status} />}
            </dl>
            {summary === null && !spoolLoading && (
                <p className="text-muted-foreground text-xs">
                    {spoolError === null
                        ? 'The spool lists no receipt under this id, so its lifecycle state and any import report are not here. The resource itself still reads back.'
                        : `The spool could not be read, so the lifecycle state is not here: ${spoolError}`}
                </p>
            )}
        </div>
    )
}

/**
 * The answers, joined to the questions that were asked.
 *
 * The link id is on every row and deliberately so: it is what the server's refusals, the spool,
 * and DHIS2 itself name a question by, and it is the only column that stays meaningful when the
 * form behind it has been rebuilt.
 */
function AnswersSection({
    rows,
    units,
    formMissing,
    formLoading,
}: {
    rows: ReceiptAnswerRow[]
    /** The registry, so an organisation-unit answer carrying no display still reads as a place. */
    units: ReadonlyMap<string, OrgUnitChoice>
    formMissing: boolean
    formLoading: boolean
}) {
    return (
        <section className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="space-y-0.5">
                    <h3 className="text-base font-semibold">Answers</h3>
                    <p className="text-muted-foreground text-sm">
                        Every question this receipt answers, in the order the form asks them. A
                        question the submission left unanswered is not in the receipt, so it is not
                        here.
                    </p>
                </div>
                <p className="text-muted-foreground text-xs">{rows.length} answered</p>
            </div>

            {formMissing && (
                <p className="text-muted-foreground rounded-lg border px-4 py-3 text-sm">
                    This server no longer serves the form this receipt answers, so there are no
                    question texts to show - an implementation guide recompiled since the capture
                    does this. The link ids and the values are the receipt's own, and they are
                    unchanged.
                </p>
            )}

            {rows.length === 0 ? (
                <p className="text-muted-foreground rounded-lg border px-4 py-8 text-sm">
                    {formLoading
                        ? 'Reading the form this receipt answers.'
                        : 'This receipt carries no answers at all - an empty submission the validator accepted for its context alone.'}
                </p>
            ) : (
                <div className="show-scrollbars overflow-x-auto rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Question</TableHead>
                                <TableHead>Link id</TableHead>
                                <TableHead>Answer</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {rows.map((row) => (
                                <TableRow key={row.linkId}>
                                    <TableCell className="min-w-48">
                                        {row.groupPath.length > 0 && (
                                            <span className="text-muted-foreground block text-xs">
                                                {row.groupPath.join(' / ')}
                                            </span>
                                        )}
                                        <span className={row.text === null ? 'text-muted-foreground' : 'font-medium'}>
                                            {row.text ?? 'no question text'}
                                        </span>
                                    </TableCell>
                                    <TableCell className="machine-identifier text-xs">
                                        {row.linkId}
                                    </TableCell>
                                    <TableCell>
                                        <div className="flex flex-col gap-1">
                                            {row.values.map((value, position) => (
                                                <AnswerValue
                                                    // Two identical answers to one repeating
                                                    // question are ordinary, so the position is
                                                    // part of the identity. Answers are never
                                                    // reordered in place.
                                                    // oxlint-disable-next-line react/no-array-index-key
                                                    key={`${String(position)}:${valueKey(value)}`}
                                                    value={value}
                                                    unitNames={units}
                                                />
                                            ))}
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </section>
    )
}

/**
 * One answer value: a coding and a reference keep both halves, everything else is the literal it was.
 *
 * THE NAME IS LOOKED UP WHEN THE ANSWER CARRIES NONE. This UI writes an organisation-unit answer
 * with its unit's name on the reference's `display`, so a receipt captured here reads as a place.
 * A `$generate` skeleton writes the bare `Location/<stem>`, and so does any client that sent the
 * reference alone - so the registry is asked, on the same argument the attribute option combo's
 * fact makes: the served resource is the authority on what a published unit is called now. When
 * neither answers, the reference itself is shown, which is exactly what the receipt holds.
 */
function AnswerValue({
    value,
    unitNames,
}: {
    value: ReceiptAnswerValue
    unitNames: ReadonlyMap<string, OrgUnitChoice>
}) {
    if (value.kind === 'text') return <span className="text-sm">{value.text}</span>
    if (value.kind === 'reference') {
        const named = value.display ?? (value.unitId === null ? null : (unitNames.get(value.unitId)?.name ?? null))
        return (
            <span className="flex flex-wrap items-center gap-2">
                <span className={named === null ? 'machine-identifier text-xs' : 'text-sm'}>
                    {named ?? value.reference}
                </span>
                {named !== null && value.unitId !== null && (
                    <Badge variant="outline" className="machine-identifier text-[10px]">
                        {value.unitId}
                    </Badge>
                )}
            </span>
        )
    }
    return (
        <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm">{value.display}</span>
            {value.code !== null && (
                <Badge variant="outline" className="machine-identifier text-[10px]">
                    {value.code}
                </Badge>
            )}
        </span>
    )
}

/** What one value is keyed by inside a repeating answer. */
function valueKey(value: ReceiptAnswerValue): string {
    if (value.kind === 'text') return value.text
    if (value.kind === 'reference') return value.reference
    return `${value.system ?? ''}|${value.code ?? ''}`
}

/**
 * What DHIS2 said when it refused this receipt.
 *
 * The reason this exists at all. A row that says "rejected" and nothing else is the one state a
 * person cannot act on, and the import report the forwarder wrote beside the receipt is exactly the
 * missing sentence - rendered in the same shape the forward report's rollup uses.
 */
function RejectionSection({ rejection, rules }: { rejection: SpoolRejection; rules: ProgramRule[] }) {
    return (
        <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-base font-semibold">
                <AlertTriangle className="text-status-rejected size-4" aria-hidden />
                DHIS2 refused this import
            </h3>
            <p className="text-muted-foreground text-sm">{rejectionSummary(rejection)}</p>
            <dl className="text-muted-foreground grid grid-cols-2 gap-x-6 gap-y-1 rounded-lg border p-4 text-xs sm:grid-cols-4">
                <Fact label="Status" value={rejection.status ?? 'not stated'} />
                <Fact label="Created" value={String(rejection.created)} />
                <Fact label="Updated" value={String(rejection.updated)} />
                <Fact label="Ignored" value={String(rejection.ignored)} />
            </dl>
            {rejection.issues.length > 0 && (
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
                            {keyedIssues(rejection.issues).map((row) => {
                                // The one join this table makes: DHIS2 names a program rule by uid,
                                // and the served form is where that uid has a name. It reads above
                                // what DHIS2 said rather than replacing it - the instance's own
                                // sentence is still the record of what happened.
                                const ruleName = rejectionRuleName(row.issue, rules)
                                return (
                                    <TableRow key={row.key}>
                                        <TableCell className="font-mono text-xs">
                                            {row.issue.error_code ?? '-'}
                                        </TableCell>
                                        <TableCell className="font-mono text-xs">
                                            {row.issue.subject ?? '-'}
                                        </TableCell>
                                        <TableCell className="text-xs">
                                            {ruleName !== null && (
                                                <span className="block font-medium">{ruleName}</span>
                                            )}
                                            {row.issue.message ?? 'no reason given'}
                                        </TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                    </Table>
                </div>
            )}
        </section>
    )
}

/**
 * What the last forward run said when it refused to send this still-queued receipt.
 *
 * Not a DHIS2 answer - the receipt never reached the instance - so the facts are the queue's own:
 * how many forward runs have refused it, when the last one looked, and the reasons it gave. The
 * reasons render in the rejection table's shape because a reader wants the same three things of
 * either: which rule, which object, what it said.
 */
function RefusalSection({ refusal }: { refusal: SpoolRefusal }) {
    return (
        <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-base font-semibold">
                <AlertTriangle className="text-status-received size-4" aria-hidden />
                A forward run refused this response
            </h3>
            <p className="text-muted-foreground text-sm">
                Still queued for DHIS2.{' '}
                {refusal.attempt_count === 1
                    ? 'One forward run has'
                    : `${String(refusal.attempt_count)} forward runs have`}{' '}
                refused to send it, most recently at {formatInstant(refusal.refused_at)}. The next
                forward run tries again.
            </p>
            {refusal.reasons.length > 0 && (
                <div className="show-scrollbars overflow-x-auto rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Category</TableHead>
                                <TableHead>Element</TableHead>
                                <TableHead>Why</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {keyedIssues(refusal.reasons).map((row) => (
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
    )
}

/**
 * What DHIS2 answered when it was asked to take this receipt's event back.
 *
 * WHY THE COPY IS SO CAREFUL. DHIS2 soft-deletes: the row stays in the instance carrying its value
 * and is gone from every ordinary read. "Deleted" would claim more than that, so the note is the
 * withdrawal record's own sentence rendered as written - one wording, in the package that posts the
 * delete, shown here and in the terminal alike.
 *
 * The receipt itself is untouched, and every answer above still renders: what a submitter asserted
 * is a fact about the submission, and retracting it from an instance does not unsay it.
 */
function WithdrawalSection({ withdrawal }: { withdrawal: SpoolWithdrawal }) {
    return (
        <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-base font-semibold">
                <Undo2 className="text-status-withdrawn size-4" aria-hidden />
                Withdrawn from DHIS2
            </h3>
            <p className="text-muted-foreground text-sm">{withdrawalSummary(withdrawal)}</p>
            {/* The instant is not in this grid: the line above it already states when the withdrawal
                happened, and a fact stated in prose and repeated in a cell is one fact twice. */}
            <dl className="text-muted-foreground grid grid-cols-2 gap-x-6 gap-y-1 rounded-lg border p-4 text-xs sm:grid-cols-3">
                <Fact label="Event" value={withdrawal.event_uid} mono />
                <Fact label="Status" value={withdrawal.status ?? 'not stated'} />
                <Fact label="Deleted" value={String(withdrawal.deleted)} />
            </dl>
        </section>
    )
}

/**
 * The stored resource itself, behind a toggle.
 *
 * The escape hatch that makes the rest honest: everything above is a reading of this document, and
 * a reading can be wrong in a way that is invisible until the bytes are on screen.
 */
function RawResource({ resource }: { resource: QuestionnaireResponse }) {
    const [shown, setShown] = useState(false)
    return (
        <section className="space-y-2">
            {/* The label names the document, because that is what opens; the tooltip says what the
                document is, for a reader who has never met the word. */}
            <Tooltip>
                <TooltipTrigger asChild>
                    <Button variant="outline" size="sm" aria-expanded={shown} onClick={() => setShown(!shown)}>
                        {shown ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
                        Raw QuestionnaireResponse
                    </Button>
                </TooltipTrigger>
                <TooltipContent>The receipt exactly as this server stored it</TooltipContent>
            </Tooltip>
            {shown && (
                <CodeBlock
                    value={JSON.stringify(resource, null, 2)}
                    testId="raw-questionnaire-response"
                    maxHeight="24rem"
                />
            )}
        </section>
    )
}

/**
 * Give each issue row a stable key.
 *
 * DHIS2 states a rule once and names every object that broke it, so two rows with the same code
 * and the same message are ordinary rather than a mistake - the position is part of the
 * identity, and it is computed here so the JSX above keys on data rather than on a loop counter.
 */
function keyedIssues(issues: SpoolRejectionIssue[]): { key: string; issue: SpoolRejectionIssue }[] {
    return issues.map((issue, position) => ({
        key: `${String(position)}:${issue.error_code ?? ''}:${issue.subject ?? ''}`,
        issue,
    }))
}

/** One labelled fact in a detail grid. */
function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }): ReactNode {
    return (
        <div className="min-w-0">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className={mono ? 'font-mono text-xs break-words' : 'break-words'}>{value}</dd>
        </div>
    )
}
