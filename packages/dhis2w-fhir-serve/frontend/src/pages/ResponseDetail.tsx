import { useMemo, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, ChevronDown, ChevronRight, Inbox, TriangleAlert } from 'lucide-react'

import { PageState } from '@/components/PageState'
import { FormKindBadge, LifecycleBadge } from '@/components/ReceiptBadges'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirResource } from '@/hooks/use-fhir-resource'
import { useOrgUnitRegistry } from '@/hooks/use-org-unit-scope'
import { useSpool } from '@/hooks/use-spool'
import {
    attributeOptionComboOf,
    canonicalId,
    generateSeedOf,
    type CodeSystem,
    type Questionnaire,
    type QuestionnaireResponse,
} from '@/lib/fhir'
import type { OrgUnitChoice } from '@/lib/orgunits'
import {
    dateLabelsOf,
    flattenQuestionnaire,
    programRulesOf,
    type DateLabels,
    type ProgramRule,
} from '@/lib/questionnaire'
import {
    attributeOptionComboFact,
    formLabel,
    joinAnswersToQuestions,
    mergeContextFacts,
    rejectionRuleName,
    trackerContextFacts,
    type ReceiptAnswerRow,
    type ReceiptAnswerValue,
    type ReceiptContextFact,
} from '@/lib/receipt'
import {
    captureContext,
    formatInstant,
    ORGANISATION_UNIT_FACT_LABEL,
    rejectionSummary,
    type SpoolRejection,
    type SpoolRejectionIssue,
    type SpoolResponseSummary,
} from '@/lib/spool'

/**
 * One receipt in full: what it answered, the DHIS2 context it carries, and what became of it.
 *
 * THREE READS, AND EACH ONE CAN BE THE MISSING ONE. The stored resource comes from
 * `GET /QuestionnaireResponse/{id}` - that is the receipt, and without it there is no page. The
 * lifecycle, the capture warnings, and DHIS2's import report come from `GET /spool`, because
 * none of the three are QuestionnaireResponse elements. And the *questions* come from a third
 * read of the served `Questionnaire`, which is the one that is allowed to fail: a receipt
 * outlives the guide that produced it, so a form recompiled since the capture degrades this page
 * to link ids and values with a line saying so, rather than blanking it.
 *
 * WHY THE ANSWERS ARE THE HEADLINE. A spool row can say a receipt carries 128 answers; only this
 * page can say what they were. The join is `joinAnswersToQuestions` in lib/receipt.ts - the
 * form's own order, the question text with its enclosing groups, and the value rendered as what
 * it is, a coding keeping both its display and the code DHIS2 will store. Unanswered questions
 * are absent because the receipt holds only the branches that were answered.
 *
 * AND A RAW VIEW UNDER ALL OF IT. Everything above is this UI's reading of the document. The
 * collapsible JSON is the document, so the page can be checked against the bytes rather than
 * believed.
 */
export function ResponseDetail() {
    const { responseId = '' } = useParams()
    const { listing, loading: spoolLoading, error: spoolError } = useSpool()
    const stored = useFhirResource<QuestionnaireResponse>('QuestionnaireResponse', responseId)

    const summary = listing.responses.find((candidate) => candidate.response_id === responseId) ?? null
    // The spool states the canonical; the stored resource states it too, and one of the two is
    // always there - so the form is still reachable when the spool read is the one that failed.
    const questionnaireId =
        summary?.questionnaire_id ??
        canonicalId(summary?.questionnaire) ??
        canonicalId(stored.resource?.questionnaire) ??
        ''
    const form = useFhirResource<Questionnaire>('Questionnaire', questionnaireId)
    // The form is gone when the read was refused or when the receipt names none at all; it is
    // pending for as long as neither has happened. Derived rather than read off `form.loading`,
    // so the frame between "the receipt arrived" and "the form read starts" does not flash the
    // rebuilt-guide notice at a page whose form is about to load.
    const formMissing = form.error !== null || questionnaireId === ''
    const formPending = !formMissing && form.resource === null

    // The combo the submission reports for is on the resource, not in the spool - so the vocabulary
    // it was chosen from is a fourth read, and one that is allowed to answer nothing: the fact
    // degrades to the system and code the receipt itself holds.
    const attributeOptionCombo = stored.resource === null ? null : attributeOptionComboOf(stored.resource)
    const attributeCodeSystem = useFhirResource<CodeSystem>(
        'CodeSystem',
        canonicalId(attributeOptionCombo?.system) ?? '',
    )

    // The registry, for the same reason the CodeSystem above is read: a receipt names organisation
    // units by uid, and the served Location is the authority on what each one is called. Cached
    // module-wide, so this is free for anyone who reached the receipt by filling a form.
    const registry = useOrgUnitRegistry()

    const rows = useMemo(() => {
        if (stored.resource === null) return []
        const spec = form.resource === null ? null : flattenQuestionnaire(form.resource)
        return joinAnswersToQuestions(spec, stored.resource)
    }, [form.resource, stored.resource])

    const title =
        summary === null
            ? ((form.resource?.title ?? form.resource?.name ?? questionnaireId) || responseId)
            : formLabel(summary, form.resource ?? undefined)
    const seed = stored.resource === null ? null : generateSeedOf(stored.resource)

    return (
        <>
            <div className="mb-6 space-y-2">
                <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                    <Link to="/responses">
                        <ArrowLeft className="size-4" />
                        All responses
                    </Link>
                </Button>
                <h2 className="text-xl font-semibold tracking-tight">
                    {questionnaireId === '' ? (
                        title
                    ) : (
                        <Link className="hover:underline" to={`/forms/${questionnaireId}`}>
                            {title}
                        </Link>
                    )}
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                    {summary !== null && <FormKindBadge kind={summary.form_kind} />}
                    {summary !== null && <LifecycleBadge summary={summary} showWarnings={false} />}
                    <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
                        {responseId}
                    </Badge>
                </div>
            </div>

            <PageState
                loading={stored.loading}
                error={stored.error}
                empty={stored.resource === null && stored.error === null && !stored.loading}
                emptyMessage="This server holds no receipt under that id."
            >
                {stored.resource !== null && (
                    <div className="space-y-6">
                        <ReceiptFacts
                            summary={summary}
                            stored={stored.resource}
                            seed={seed}
                            spoolLoading={spoolLoading}
                            spoolError={spoolError}
                        />

                        <CaptureContextSection
                            facts={contextFacts(
                                summary,
                                stored.resource,
                                attributeCodeSystem.resource,
                                registry.byId,
                                dateLabelsOf(form.resource),
                            )}
                        />

                        <AnswersSection
                            rows={rows}
                            units={registry.byId}
                            formMissing={formMissing}
                            formLoading={formPending}
                        />

                        {summary !== null && summary.warnings.length > 0 && (
                            <section className="space-y-2">
                                <h3 className="flex items-center gap-2 text-base font-semibold">
                                    <TriangleAlert className="text-status-refused size-4" aria-hidden />
                                    Warnings recorded on capture
                                </h3>
                                <ul className="text-muted-foreground space-y-1 rounded-lg border p-4 text-sm">
                                    {summary.warnings.map((warning) => (
                                        <li key={warning}>{warning}</li>
                                    ))}
                                </ul>
                            </section>
                        )}

                        {summary !== null && summary.rejection ? (
                            <RejectionSection
                                rejection={summary.rejection}
                                rules={programRulesOf(form.resource)}
                            />
                        ) : null}

                        <RawResource resource={stored.resource} />

                        <p className="text-muted-foreground flex items-start gap-2 text-xs">
                            <Inbox className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                            The full resource reads back verbatim at{' '}
                            <code className="font-mono">GET /QuestionnaireResponse/{responseId}</code>
                        </p>
                    </div>
                )}
            </PageState>
        </>
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

/**
 * The spool's derived facts and the resource's own, in one list for one grid.
 *
 * The organisation unit is the one derived fact this page can say more about than the spool did.
 * The spool has no registry and states the bare uid; the served Location names it, so the fact
 * becomes `Ngelehun CHC (DiszpKrYNg8)` in prose - the same shape the attribute option combo takes
 * once its CodeSystem has answered, and the same degradation to the mono uid when nothing does.
 *
 * THREE GROUPS, MERGED RATHER THAN CONCATENATED. The spool's derivations lead because they are
 * the ones this page has already resolved further. The tracker context follows and overlaps them
 * by two facts - the tracked entity and the enrollment, which the spool derives and the resource
 * also carries - so the merge keeps the spool's and adds the two enrollment dates, which live
 * nowhere but on the resource. The attribute option combo is last for the same reason it is read
 * separately: it comes off the stored document, so it is here for a receipt the spool never
 * indexed.
 *
 * THE DATES ARE LABELLED BY THE FORM the receipt answered, which is the same source the capture
 * screen labels its controls from. A programme that calls its enrollment date "Date first seen"
 * calls it that in both places; a receipt whose form is no longer served falls back to this
 * project's own words, which is what `dateLabelsOf` answers for a form that is not there.
 */
function contextFacts(
    summary: SpoolResponseSummary | null,
    stored: QuestionnaireResponse | null,
    attributeCodeSystem: CodeSystem | null,
    units: ReadonlyMap<string, OrgUnitChoice>,
    labels: DateLabels,
): ReceiptContextFact[] {
    // Everything else the spool derives is an identifier - a period, a uid - so all of it reads mono.
    const derived =
        summary === null
            ? []
            : captureContext(summary).map((fact) => {
                  const named = fact.label === ORGANISATION_UNIT_FACT_LABEL ? units.get(fact.value) : undefined
                  if (named === undefined) return { label: fact.label, value: fact.value, mono: true }
                  return { label: fact.label, value: `${named.name} (${fact.value})`, mono: false }
              })
    if (stored === null) return derived
    const combo = attributeOptionComboFact(stored, attributeCodeSystem)
    return mergeContextFacts(derived, trackerContextFacts(stored, labels), combo === null ? [] : [combo])
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
                    <span className="text-muted-foreground font-mono break-all">
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
                        ? 'The spool lists no receipt under this id, so its lifecycle state and any import report are not on this page. The resource itself still reads back.'
                        : `The spool could not be read, so the lifecycle state is not on this page: ${spoolError}`}
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
                                    <TableCell className="text-muted-foreground font-mono text-xs">
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
                <span className={named === null ? 'text-muted-foreground font-mono text-xs' : 'text-sm'}>
                    {named ?? value.reference}
                </span>
                {named !== null && value.unitId !== null && (
                    <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
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
                <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
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
 * The reason this page exists at all. A row that says "rejected" and nothing else is the one
 * state a person cannot act on, and the import report the forwarder wrote beside the receipt is
 * exactly the missing sentence - rendered in the same shape the forward report's rollup uses.
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
 * The stored resource itself, behind a toggle.
 *
 * The escape hatch that makes the rest of the page honest: everything above is a reading of this
 * document, and a reading can be wrong in a way that is invisible until the bytes are on screen.
 */
function RawResource({ resource }: { resource: QuestionnaireResponse }) {
    const [shown, setShown] = useState(false)
    return (
        <section className="space-y-2">
            <Button variant="outline" size="sm" aria-expanded={shown} onClick={() => setShown(!shown)}>
                {shown ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
                Raw QuestionnaireResponse
            </Button>
            {shown && (
                <pre className="show-scrollbars bg-muted/40 max-h-96 overflow-auto rounded-lg border p-4 font-mono text-xs">
                    {JSON.stringify(resource, null, 2)}
                </pre>
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
