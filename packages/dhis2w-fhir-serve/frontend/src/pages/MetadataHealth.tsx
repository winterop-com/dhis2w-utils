import { useMemo, useState } from 'react'
import { Languages, RefreshCw, ShieldCheck } from 'lucide-react'

import { PageHeader, PageState } from '@/components/PageState'
import { Unfoldable } from '@/components/Unfoldable'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useMetadataHealth } from '@/hooks/use-metadata-health'
import { useStatusLine } from '@/hooks/use-status-bar'
import {
    coveragePercent,
    countOf,
    findingMessage,
    FINDING_SEVERITIES,
    isClean,
    listedCount,
    matchingFindings,
    matchingRatios,
    SEVERITY_LABELS,
    SEVERITY_TINTS,
    shelveFindings,
    type CoverageRatio,
    type FindingCounts,
    type FindingSeverity,
    type MetadataFinding,
    type MetadataHealth as MetadataHealthReport,
} from '@/lib/health'
import { cn, countedNoun, formatCount } from '@/lib/utils'

/** What this page is for, said as a fact about the page rather than about this particular run. */
export const METADATA_HEALTH_DESCRIPTION =
    'What the DHIS2 instance this guide was generated from holds that FHIR cannot carry cleanly, and how far the selection is translated.'

/** What the page says when the instance is clean and nobody has translated anything in it. */
export const NOTHING_TO_REPORT =
    'Every name and code in this selection is one the guide can carry as it stands.'

/** What the page says on a run with no instance behind it, when the server stated no reason of its own. */
export const NO_INSTANCE_BEHIND_THIS_SERVER =
    'This server is reading a compiled implementation guide from disk, so there is no DHIS2 instance behind it to check.'

/** What the filter box asks for, and what it looks in. */
const FILTER_PLACEHOLDER = 'Filter by object name or UID'

/**
 * Metadata health: what the DHIS2 instance behind this guide holds that the guide cannot carry cleanly.
 *
 * WHAT IS ON IT. Two analyses under one heading. The first is `d2w fhir validate` run over the
 * instance this process is connected to - a name carrying a character the implementation guide
 * publisher cannot survive, a code no FHIR system will take, an object carrying no code at all - and
 * every finding arrives at the severity it graded. The second is the translation coverage: which
 * locales this instance carries translations in, and how much of the selection each one covers.
 *
 * IT OPENS AS A SUMMARY. The counts and the coverage meters are the whole of what a reader meets:
 * every table under them is closed, and each closed heading states what is inside it - which
 * severity, which DHIS2 collection, how many rows. Opening one is the drill-down, and a page that
 * opened with three thousand rows on it was a page nobody could read the first line of.
 *
 * REPORTING ONLY. Nothing here changes anything in DHIS2, and nothing here offers to. A reader who
 * wants to act on a row goes to the instance and changes it; making that a control on this page is
 * the next slice, and the FHIR roadmap is where it is stated.
 *
 * SEVERITY LEADS THE ARRANGEMENT, object kind is the second cut. An error stops the build whichever
 * kind of object it sits on, so the errors are what a reader meets first; inside a severity the rows
 * are shelved by DHIS2 collection, because somebody fixing names fixes a run of data elements at
 * once. `lib/health.shelveFindings` is that arrangement, and it is a pure function so the shape of
 * the page is testable without rendering it.
 *
 * ONE FILTER BOX OVER THE WHOLE PAGE, AND IT OPENS WHAT IT MATCHES. A reader looking for an object is
 * looking for it wherever it is, so the box narrows the findings and the translation lists alike -
 * and while anything is typed every section stands open, because a match hidden behind a closed
 * heading is a match the reader has to be told about twice.
 *
 * A COMPILED RUN IS TOLD, NOT SHOWN A BLANK PAGE. The server answers this address on every run and
 * says in words when there is no instance behind it, so a bookmark kept from a live run lands on an
 * explanation rather than on an empty table.
 */
export function MetadataHealth() {
    const { health, loading, error, refreshing, reload } = useMetadataHealth()
    const [filter, setFilter] = useState('')
    const filtering = filter.trim() !== ''

    const findings = useMemo(() => matchingFindings(health.findings, filter), [health.findings, filter])
    const shelves = useMemo(() => shelveFindings(findings), [findings])
    const ratios = useMemo(() => matchingRatios(health.translations, filter), [health.translations, filter])

    // The count only; the posture the severities were graded under is a whole sentence and belongs
    // where there is room to read it, which is under the tiles the severities are counted on.
    useStatusLine(
        loading || !health.available
            ? null
            : `Showing ${formatCount(findings.length)} of ${countedNoun(health.findings.length, 'finding')}`,
    )

    const nothingMatched = filtering && shelves.length === 0 && ratios.every((ratio) => listedCount(ratio) === 0)

    return (
        <>
            <PageHeader
                title="Metadata health"
                description={METADATA_HEALTH_DESCRIPTION}
                aside={
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button variant="outline" size="sm" onClick={reload} disabled={refreshing || loading}>
                                <RefreshCw className={cn('size-4', refreshing && 'animate-spin')} aria-hidden />
                                Reload
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                            Read this DHIS2 instance again
                        </TooltipContent>
                    </Tooltip>
                }
            />

            <PageState loading={loading} error={error} empty={false}>
                {!health.available ? (
                    <NoInstanceBehindThisServer reason={health.reason} />
                ) : isClean(health) ? (
                    <NothingToReport swept={health.object_count} />
                ) : (
                    <div className="space-y-6">
                        <SummaryStrip health={health} ratios={ratios} unfolded={filtering} />
                        <FilterBox value={filter} onChange={setFilter} />
                        {nothingMatched ? (
                            <Card>
                                <CardContent className="text-muted-foreground py-8 text-sm">
                                    No object matches this filter.{' '}
                                    {countedNoun(health.findings.length, 'finding')} in total.
                                </CardContent>
                            </Card>
                        ) : (
                            shelves.map((shelf) => (
                                <SeveritySection
                                    key={shelf.severity}
                                    severity={shelf.severity}
                                    total={shelf.total}
                                    groups={shelf.groups}
                                    unfolded={filtering}
                                />
                            ))
                        )}
                    </div>
                )}
            </PageState>
        </>
    )
}

/** The card a compiled run gets, carrying the server's own sentence about why there is nothing here. */
function NoInstanceBehindThisServer({ reason }: { reason: string | null }) {
    return (
        <Card>
            <CardContent className="text-muted-foreground py-8 text-sm">
                <p data-testid="metadata-health-unavailable">{reason ?? NO_INSTANCE_BEHIND_THIS_SERVER}</p>
            </CardContent>
        </Card>
    )
}

/** The empty state: the names and codes all pass and nothing carries a translation, said as the fact it is. */
function NothingToReport({ swept }: { swept: number }) {
    return (
        <Card>
            <CardContent className="flex items-start gap-3 py-8">
                <ShieldCheck className="text-status-forwarded-ink mt-0.5 size-4 shrink-0" aria-hidden />
                <div className="space-y-1">
                    <p className="text-sm font-medium" data-testid="metadata-health-clean">
                        {NOTHING_TO_REPORT}
                    </p>
                    <p className="text-muted-foreground text-sm">
                        {countedNoun(swept, 'metadata object')} read from this DHIS2 instance, none of them
                        carrying a translation.
                    </p>
                </div>
            </CardContent>
        </Card>
    )
}

/**
 * The strip: how many findings of each severity, and how far each locale covers the selection.
 *
 * Counts are the whole report rather than what the filter left, because they are what the page was
 * opened to learn - a filter narrows what is read, not what is true.
 */
function SummaryStrip({
    health,
    ratios,
    unfolded,
}: {
    health: MetadataHealthReport
    ratios: CoverageRatio[]
    unfolded: boolean
}) {
    return (
        <section className="space-y-4" data-testid="metadata-health-summary">
            <div className="grid gap-3 sm:grid-cols-3">
                {FINDING_SEVERITIES.map((severity) => (
                    <SeverityTile key={severity} severity={severity} counts={health.counts} />
                ))}
            </div>
            {/* A severity is unreadable without the posture behind it: the same DHIS2 name is a
                blocker under one `[generate] hostile_names` setting and a note under the other, so
                the run states which reading produced these counts. */}
            <p className="text-muted-foreground text-sm">
                {countedNoun(health.object_count, 'metadata object')} read from this DHIS2 instance
                {health.graded_under === null ? '.' : `, graded under hostile names ${health.graded_under}.`}
            </p>
            <CoverageStrip ratios={ratios} unfolded={unfolded} />
        </section>
    )
}

/** One severity's count, with the hue that severity wears everywhere else on the page. */
function SeverityTile({ severity, counts }: { severity: FindingSeverity; counts: FindingCounts }) {
    const count = countOf(counts, severity)
    return (
        <div className="bg-card rounded-lg border p-4" data-testid={`metadata-health-${severity}-count`}>
            <span className="flex items-center gap-2">
                <span className={cn('size-2 shrink-0 rounded-full', SEVERITY_TINTS[severity].dot)} aria-hidden />
                <span className="text-sm font-medium">{SEVERITY_LABELS[severity]}</span>
            </span>
            <span className="mt-2 block text-3xl font-semibold tracking-tight">{formatCount(count)}</span>
        </div>
    )
}

/** What the coverage strip says when nobody has translated anything in the selection. */
const NO_LOCALES_IN_USE =
    'Nothing in this selection carries a translation, so this instance is being maintained in one language.'

/**
 * Translation coverage, one row per locale the selection carries a translation in.
 *
 * COVERAGE IS A FACT, NOT A GRADE. Nothing here is tinted like a defect and nothing here is counted
 * on the tiles above: an instance whose main language is English and which holds three Spanish
 * translations is an instance with three Spanish translations, not an instance three thousand
 * Spanish translations short. That reading is the server's - each locale arrives told through
 * whichever side of it is the shorter list - and this renders the side it was told through.
 *
 * WEAKEST FIRST. The language somebody stopped translating halfway is the one worth acting on, and a
 * strip sorted alphabetically would bury it under whichever tag sorts first.
 *
 * THE DENOMINATOR IS EVERY TRANSLATABLE STRING, not every object: a data element carries a name and
 * a form name, and a locale that has the first and not the second has done half of that object. The
 * count says so in words beside the bar rather than leaving a reader to work out what the share is
 * of.
 */
function CoverageStrip({ ratios, unfolded }: { ratios: CoverageRatio[]; unfolded: boolean }) {
    return (
        <div className="rounded-lg border p-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Languages className="text-muted-foreground size-4" aria-hidden />
                Translations
            </h3>
            {ratios.length === 0 ? (
                <p className="text-muted-foreground mt-2 text-sm">{NO_LOCALES_IN_USE}</p>
            ) : (
                <div className="mt-3 grid gap-3" data-testid="metadata-health-coverage">
                    {ratios.map((ratio) => (
                        <CoverageRow key={ratio.locale} ratio={ratio} unfolded={unfolded} />
                    ))}
                </div>
            )}
        </div>
    )
}

/**
 * What the table under one locale's meter lists, said in the words of whichever side it was told through.
 *
 * The numbers are on the meter row above and are not said again here - this line names the list, and
 * for a sparse locale it names it as the thing it is: objects somebody wrote a translation on.
 */
function coverageSentence(ratio: CoverageRatio): string {
    if (ratio.standing === 'sparse') return `Objects carrying a translation in ${ratio.locale}.`
    return `Objects with no translation yet written in ${ratio.locale}.`
}

/** One locale's meter and counts, with the objects behind it under a heading that opens. */
function CoverageRow({ ratio, unfolded }: { ratio: CoverageRatio; unfolded: boolean }) {
    const percent = coveragePercent(ratio)
    return (
        <Unfoldable
            forced={unfolded}
            testId={`metadata-health-locale-${ratio.locale}`}
            heading={
                <span className="grid flex-1 grid-cols-[4rem_1fr_auto] items-center gap-3">
                    {/* The tag is a machine string - `pt-BR`, `lo` - and is read character by character. */}
                    <span className="machine-identifier text-xs">{ratio.locale}</span>
                    {/* The bar is the counts beside it drawn, and it sits inside the heading's own
                        button - so it carries no role and no label of its own, and the sentence a
                        screen reader hears is the one on the right, spelled out. */}
                    <span className="bg-muted h-2 overflow-hidden rounded-full" aria-hidden>
                        <span className="bg-primary block h-full" style={{ width: `${String(percent)}%` }} />
                    </span>
                    <span className="text-muted-foreground text-xs tabular-nums">
                        {formatCount(ratio.covered)} of {formatCount(ratio.total)} translatable strings
                    </span>
                </span>
            }
        >
            <div className="space-y-2 pl-[1.375rem]">
                <p className="text-muted-foreground text-sm">{coverageSentence(ratio)}</p>
                {ratio.standing === 'sparse' ? (
                    <CarriersTable ratio={ratio} />
                ) : (
                    <UntranslatedTable ratio={ratio} />
                )}
            </div>
        </Unfoldable>
    )
}

/** The objects that carry a locale little of the selection carries - the short list, in neutral words. */
function CarriersTable({ ratio }: { ratio: CoverageRatio }) {
    if (ratio.carriers.length === 0) {
        return <p className="text-muted-foreground text-sm">No object here matches this filter.</p>
    }
    return (
        <div className="rounded-lg border">
            <Table className="table-fixed">
                <TableHeader>
                    <TableRow>
                        <TableHead className="break-words whitespace-normal w-[52%]">Object</TableHead>
                        <TableHead className="break-words whitespace-normal w-[24%]">Kind</TableHead>
                        <TableHead className="break-words whitespace-normal w-[24%]">Written in {ratio.locale}</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {ratio.carriers.map((carrier) => (
                        <TableRow key={`${carrier.resource_type}-${carrier.uid}`}>
                            <ObjectCell name={carrier.name} uid={carrier.uid} />
                            <TableCell className="machine-identifier align-top text-xs break-words whitespace-normal">
                                {carrier.resource_type}
                            </TableCell>
                            <TableCell className="align-top text-sm break-words whitespace-normal">
                                {spellings(carrier.carries_name, carrier.carries_form_name)}
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    )
}

/** The objects short of a locale most of the selection is translated into. */
function UntranslatedTable({ ratio }: { ratio: CoverageRatio }) {
    if (ratio.missing.length === 0) {
        return <p className="text-muted-foreground text-sm">No object here matches this filter.</p>
    }
    return (
        <div className="rounded-lg border">
            <Table className="table-fixed">
                <TableHeader>
                    <TableRow>
                        <TableHead className="break-words whitespace-normal w-[52%]">Object</TableHead>
                        <TableHead className="break-words whitespace-normal w-[24%]">Kind</TableHead>
                        <TableHead className="break-words whitespace-normal w-[24%]">Not yet written in {ratio.locale}</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {ratio.missing.map((row) => (
                        <TableRow key={`${row.resource_type}-${row.uid}`}>
                            <ObjectCell name={row.name} uid={row.uid} />
                            <TableCell className="machine-identifier align-top text-xs break-words whitespace-normal">
                                {row.resource_type}
                            </TableCell>
                            <TableCell className="align-top text-sm break-words whitespace-normal">
                                {spellings(row.name_untranslated, row.form_name_untranslated)}
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    )
}

/** Which of an object's two spellings a translation row is about, in the words DHIS2 uses for them. */
function spellings(name: boolean, formName: boolean): string {
    if (name && formName) return 'Name and form name'
    if (formName) return 'Form name'
    return 'Name'
}

/** The object cell every table on this page opens with: what it is called, and its DHIS2 uid under it. */
function ObjectCell({ name, uid }: { name: string; uid: string }) {
    return (
        <TableCell className="align-top break-words whitespace-normal">
            <span className="grid gap-0.5">
                <span className="font-medium">{name}</span>
                <span className="machine-identifier text-xs">{uid}</span>
            </span>
        </TableCell>
    )
}

/** The filter box, over the findings and the translation lists alike. */
function FilterBox({ value, onChange }: { value: string; onChange: (next: string) => void }) {
    return (
        <Input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={FILTER_PLACEHOLDER}
            aria-label={FILTER_PLACEHOLDER}
            data-testid="metadata-health-filter"
            className="max-w-sm"
        />
    )
}

/** One severity's findings, shelved by the DHIS2 collection each object belongs to, each shelf closed. */
function SeveritySection({
    severity,
    total,
    groups,
    unfolded,
}: {
    severity: FindingSeverity
    total: number
    groups: { resourceType: string; findings: MetadataFinding[] }[]
    unfolded: boolean
}) {
    return (
        <section data-testid={`metadata-health-${severity}-section`}>
            <Unfoldable
                forced={unfolded}
                heading={
                    <span className="flex items-center gap-2 text-sm font-semibold">
                        <span
                            className={cn('size-2 shrink-0 rounded-full', SEVERITY_TINTS[severity].dot)}
                            aria-hidden
                        />
                        {SEVERITY_LABELS[severity]}
                        <span className="text-muted-foreground text-xs font-normal tabular-nums">
                            {countedNoun(total, 'finding')}
                        </span>
                    </span>
                }
            >
                <div className="space-y-2 pl-[1.375rem]">
                    {groups.map((group) => (
                        <Unfoldable
                            key={group.resourceType}
                            forced={unfolded}
                            heading={
                                <span className="flex items-center gap-2">
                                    <span
                                        className={cn(
                                            'size-2 shrink-0 rounded-full',
                                            SEVERITY_TINTS[severity].dot,
                                        )}
                                        aria-hidden
                                    />
                                    {/* DHIS2's own spelling of the collection - `dataElements`,
                                        `organisationUnits` - which is the word a reader will meet
                                        again in the instance and in a build log. */}
                                    <span className="machine-identifier text-xs">{group.resourceType}</span>
                                    <span className="text-muted-foreground text-xs tabular-nums">
                                        {countedNoun(group.findings.length, 'finding')}
                                    </span>
                                </span>
                            }
                        >
                            <FindingsTable findings={group.findings} />
                        </Unfoldable>
                    ))}
                </div>
            </Unfoldable>
        </section>
    )
}

/**
 * One shelf's findings, in a table that wraps rather than one that scrolls.
 *
 * THE COLUMNS ARE FIXED AND THE PROSE WRAPS. Two of these four columns are whole sentences and the
 * other two are short - so the widths are declared, `table-fixed` holds them, and the sentences
 * break inside their cells. Left to size itself the Problem column pushed the cost column off the
 * side of the screen, and a column a reader has to scroll sideways to find is a column that is not
 * there.
 */
function FindingsTable({ findings }: { findings: MetadataFinding[] }) {
    return (
        <div className="rounded-lg border">
            <Table className="table-fixed">
                <TableHeader>
                    <TableRow>
                        <TableHead className="w-[22%] break-words whitespace-normal">Object</TableHead>
                        <TableHead className="w-[14%] break-words whitespace-normal">Field</TableHead>
                        <TableHead className="w-[40%] break-words whitespace-normal">Problem</TableHead>
                        <TableHead className="w-[24%] break-words whitespace-normal">What it costs</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {findings.map((finding) => (
                        <FindingRow
                            key={`${finding.uid}-${finding.category}-${finding.field ?? ''}`}
                            finding={finding}
                        />
                    ))}
                </TableBody>
            </Table>
        </div>
    )
}

/** One finding: the object, the field at fault, what is wrong with it, and what the grade costs. */
function FindingRow({ finding }: { finding: MetadataFinding }) {
    return (
        <TableRow>
            <ObjectCell name={finding.name} uid={finding.uid} />
            {/* Wraps between words and never inside one: `form name` is two words and `name` is a
                word a column this narrow can still hold whole. */}
            <TableCell className="text-muted-foreground align-top text-sm whitespace-normal">
                {finding.field ?? '-'}
            </TableCell>
            {/* The object and the field are the two cells to the left of this one, so the head the
                validator writes for a terminal line comes off - see `lib/health.findingMessage`. */}
            <TableCell className="align-top text-sm break-words whitespace-normal">
                {findingMessage(finding)}
            </TableCell>
            <TableCell className="text-muted-foreground align-top text-sm break-words whitespace-normal">
                {finding.cost}
            </TableCell>
        </TableRow>
    )
}
