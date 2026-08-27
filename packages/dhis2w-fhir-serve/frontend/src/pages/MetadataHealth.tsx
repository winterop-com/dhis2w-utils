import { useMemo, useState } from 'react'
import { Languages, RefreshCw, ShieldCheck } from 'lucide-react'

import { PageHeader, PageState } from '@/components/PageState'
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
    coverageRatios,
    countOf,
    FINDING_SEVERITIES,
    isClean,
    matchingFindings,
    matchingGaps,
    SEVERITY_LABELS,
    SEVERITY_TINTS,
    shelveFindings,
    type CoverageRatio,
    type FindingCounts,
    type FindingSeverity,
    type MetadataFinding,
    type MetadataHealth as MetadataHealthReport,
    type TranslationCoverage,
    type TranslationGap,
} from '@/lib/health'
import { cn, countedNoun, formatCount } from '@/lib/utils'

/** What this page is for, said as a fact about the page rather than about this particular run. */
export const METADATA_HEALTH_DESCRIPTION =
    'What the DHIS2 instance this guide was generated from holds that FHIR cannot carry cleanly, and how far the selection is translated.'

/** What the page says when the instance is clean and every locale in use is complete. */
export const NOTHING_TO_REPORT =
    'Every name, code, and translation in this selection is one the guide can carry as it stands.'

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
 * every finding arrives in the validator's own words, at the severity it graded. The second is the
 * translation coverage: which locales this instance is being maintained in, how much of the
 * selection each one covers, and which objects are short of a translation the rest already have.
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
 * ONE FILTER BOX OVER THE WHOLE PAGE. A reader looking for an object is looking for it wherever it
 * is, so the box narrows the findings and the translation gaps alike - a name that matched one and
 * not the other would hide half of what is known about the object.
 *
 * A COMPILED RUN IS TOLD, NOT SHOWN A BLANK PAGE. The server answers this address on every run and
 * says in words when there is no instance behind it, so a bookmark kept from a live run lands on an
 * explanation rather than on an empty table.
 */
export function MetadataHealth() {
    const { health, loading, error, refreshing, reload } = useMetadataHealth()
    const [filter, setFilter] = useState('')

    const findings = useMemo(() => matchingFindings(health.findings, filter), [health.findings, filter])
    const gaps = useMemo(() => matchingGaps(health.translations.gaps, filter), [health.translations.gaps, filter])
    const shelves = useMemo(() => shelveFindings(findings), [findings])

    // The count only; the posture the severities were graded under is a whole sentence and belongs
    // where there is room to read it, which is under the tiles the severities are counted on.
    useStatusLine(
        loading || !health.available
            ? null
            : `Showing ${formatCount(findings.length)} of ${countedNoun(health.findings.length, 'finding')}`,
    )

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
                        <SummaryStrip health={health} />
                        <FilterBox value={filter} onChange={setFilter} />
                        {shelves.length === 0 && gaps.length === 0 ? (
                            <Card>
                                <CardContent className="text-muted-foreground py-8 text-sm">
                                    No object matches this filter.{' '}
                                    {countedNoun(health.findings.length, 'finding')} in total.
                                </CardContent>
                            </Card>
                        ) : (
                            <>
                                {shelves.map((shelf) => (
                                    <SeveritySection
                                        key={shelf.severity}
                                        severity={shelf.severity}
                                        total={shelf.total}
                                        groups={shelf.groups}
                                    />
                                ))}
                                <TranslationGaps gaps={gaps} locales={health.translations.locales} />
                            </>
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

/** The empty state: the selection is clean, said as the fact it is. */
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
                        {countedNoun(swept, 'metadata object')} read from this DHIS2 instance.
                    </p>
                </div>
            </CardContent>
        </Card>
    )
}

/**
 * The strip: how many findings of each severity, and how far each locale in use covers the selection.
 *
 * Counts are the whole report rather than what the filter left, because they are what the page was
 * opened to learn - a filter narrows what is read, not what is true.
 */
function SummaryStrip({ health }: { health: MetadataHealthReport }) {
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
            <CoverageStrip coverage={health.translations} />
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

/** What the coverage strip is headed, and what it says when nobody has translated anything. */
const NO_LOCALES_IN_USE = 'Nothing in this selection carries a translation, so this instance is being maintained in one language.'

/**
 * Translation coverage, one row per locale in use.
 *
 * WEAKEST FIRST. The language somebody stopped translating halfway is the one worth acting on, and
 * a strip sorted alphabetically would bury it under whichever tag sorts first.
 *
 * THE DENOMINATOR IS EVERY TRANSLATABLE STRING, not every object: a data element carries a name and
 * a form name, and a locale that has the first and not the second has done half of that object. The
 * count says so in words beside the bar rather than leaving a reader to work out what the share is
 * of.
 */
function CoverageStrip({ coverage }: { coverage: TranslationCoverage }) {
    const ratios = coverageRatios(coverage)
    return (
        <div className="rounded-lg border p-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Languages className="text-muted-foreground size-4" aria-hidden />
                Translations
            </h3>
            {ratios.length === 0 ? (
                <p className="text-muted-foreground mt-2 text-sm">{NO_LOCALES_IN_USE}</p>
            ) : (
                <dl className="mt-3 grid gap-2" data-testid="metadata-health-coverage">
                    {ratios.map((ratio) => (
                        <CoverageRow key={ratio.locale} ratio={ratio} />
                    ))}
                </dl>
            )}
        </div>
    )
}

/** One locale's coverage: the tag, a bar, and the two numbers the bar is drawn from. */
function CoverageRow({ ratio }: { ratio: CoverageRatio }) {
    const percent = coveragePercent(ratio)
    return (
        <div className="grid grid-cols-[4rem_1fr_auto] items-center gap-3">
            {/* The tag is a machine string - `pt-BR`, `lo` - and is read character by character. */}
            <dt className="machine-identifier text-xs">{ratio.locale}</dt>
            <dd
                className="bg-muted h-2 overflow-hidden rounded-full"
                role="meter"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${ratio.locale}: ${String(ratio.covered)} of ${String(ratio.total)} translatable strings`}
            >
                <span className="bg-primary block h-full" style={{ width: `${String(percent)}%` }} />
            </dd>
            <dd className="text-muted-foreground text-xs tabular-nums">
                {formatCount(ratio.covered)} of {formatCount(ratio.total)}
            </dd>
        </div>
    )
}

/** The filter box, over the findings and the translation gaps alike. */
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

/** One severity's findings, shelved by the DHIS2 collection each object belongs to. */
function SeveritySection({
    severity,
    total,
    groups,
}: {
    severity: FindingSeverity
    total: number
    groups: { resourceType: string; findings: MetadataFinding[] }[]
}) {
    return (
        <section className="space-y-3" data-testid={`metadata-health-${severity}-section`}>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
                <span className={cn('size-2 shrink-0 rounded-full', SEVERITY_TINTS[severity].dot)} aria-hidden />
                {SEVERITY_LABELS[severity]}
                <span className="text-muted-foreground text-xs font-normal tabular-nums">
                    {formatCount(total)}
                </span>
            </h3>
            {groups.map((group) => (
                <div key={group.resourceType} className="space-y-2">
                    {/* DHIS2's own spelling of the collection - `dataElements`, `organisationUnits` -
                        which is the word a reader will meet again in the instance and in a build log. */}
                    <h4 className="machine-identifier text-xs">{group.resourceType}</h4>
                    <div className="show-scrollbars overflow-x-auto rounded-lg border md:overflow-x-visible">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Object</TableHead>
                                    <TableHead>Field</TableHead>
                                    <TableHead>Problem</TableHead>
                                    <TableHead>What it costs</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {group.findings.map((finding) => (
                                    <FindingRow
                                        key={`${finding.uid}-${finding.category}-${finding.field ?? ''}`}
                                        finding={finding}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </div>
            ))}
        </section>
    )
}

/** One finding: the object, the field at fault, the validator's own sentence, and what the grade costs. */
function FindingRow({ finding }: { finding: MetadataFinding }) {
    return (
        <TableRow>
            <TableCell className="align-top">
                <span className="grid gap-0.5">
                    <span className="font-medium">{finding.name}</span>
                    <span className="machine-identifier text-xs">{finding.uid}</span>
                </span>
            </TableCell>
            <TableCell className="text-muted-foreground align-top text-sm whitespace-nowrap">
                {finding.field ?? '-'}
            </TableCell>
            <TableCell className="align-top text-sm">{finding.message}</TableCell>
            <TableCell className="text-muted-foreground align-top text-sm">{finding.cost}</TableCell>
        </TableRow>
    )
}

/** What the gap table is headed and what it says under the heading. */
const TRANSLATION_GAPS_HEADING = 'Translations not written'

/**
 * The objects short of a translation the rest of the selection already has.
 *
 * A GAP IS AN ABSENCE AGAINST WHAT IS IN USE, which is why this section exists at all and why it is
 * empty on an instance nobody has translated: a locale nobody uses is not a locale anybody is short
 * of. The name and the form name are listed apart because they are two different strings somebody
 * has to go and write, and an object with no form name can never be short of one.
 */
function TranslationGaps({ gaps, locales }: { gaps: TranslationGap[]; locales: string[] }) {
    if (gaps.length === 0) return null
    return (
        <section className="space-y-3" data-testid="metadata-health-gaps">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Languages className="text-muted-foreground size-4" aria-hidden />
                {TRANSLATION_GAPS_HEADING}
                <span className="text-muted-foreground text-xs font-normal tabular-nums">
                    {formatCount(gaps.length)}
                </span>
            </h3>
            <p className="text-muted-foreground text-sm">
                These objects hold no translation in a locale the rest of this selection is
                translated into: {locales.join(', ')}.
            </p>
            <div className="show-scrollbars overflow-x-auto rounded-lg border md:overflow-x-visible">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Object</TableHead>
                            <TableHead>Kind</TableHead>
                            <TableHead>Name not written in</TableHead>
                            <TableHead>Form name not written in</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {gaps.map((gap) => (
                            <TableRow key={`${gap.resource_type}-${gap.uid}`}>
                                <TableCell className="align-top">
                                    <span className="grid gap-0.5">
                                        <span className="font-medium">{gap.name}</span>
                                        <span className="machine-identifier text-xs">{gap.uid}</span>
                                    </span>
                                </TableCell>
                                <TableCell className="machine-identifier align-top text-xs">
                                    {gap.resource_type}
                                </TableCell>
                                <TableCell className="align-top text-sm">
                                    {gap.missing_name_locales.join(', ') || '-'}
                                </TableCell>
                                <TableCell className="align-top text-sm">
                                    {gap.missing_form_name_locales.join(', ') || '-'}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </section>
    )
}
