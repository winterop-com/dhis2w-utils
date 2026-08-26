import { createContext, use, useState, type Dispatch, type ReactNode } from 'react'
import { Columns3, Rows3 } from 'lucide-react'

import { AnswerControl } from '@/components/AnswerControl'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, formatCount } from '@/lib/utils'
import {
    comboFilterPlaceholder,
    comboRows,
    disaggregationCells,
    enabledLinkIds,
    facetColumns,
    formBlocks,
    groupCategoryAxes,
    isAnswered,
    liveTotal,
    offersComboFilter,
    offersOrientationSwitch,
    openedDisaggregationOrientation,
    otherOrientation,
    rememberDisaggregationOrientation,
    rowAxisName,
    TRUE_ONLY_VALUE_TYPE,
    visibleComboRows,
    type AnswerAction,
    type AnswerState,
    type ComboRow,
    type DisaggregationColumn,
    type DisaggregationFacet,
    type DisaggregationOrientation,
    type FormBlock,
    type QuestionnaireNode,
    type QuestionnaireSpec,
} from '@/lib/questionnaire'

/** The questions this form is not asking after all, and the one line each of them states instead. */
export interface LockedQuestions {
    linkIds: ReadonlySet<string>
    /** The short reason shown under each locked control - the full reason belongs to whatever locked them. */
    note: string
}

/** Nothing locked, which is every form until something above it says otherwise. */
export const NO_LOCKED_QUESTIONS: LockedQuestions = { linkIds: new Set(), note: '' }

/**
 * Which questions are read-only for a reason that is not the form's own.
 *
 * A CONTEXT, ON THE PRECEDENT `OrgUnitScopeProvider` SET. `item.readOnly` is a fact about the
 * question and is read off the node; this is a fact about the *submission* - a registration
 * answering for a person this DHIS2 instance already holds asks none of the questions that write
 * onto the person - and it is decided by the page. Threading it through `QuestionnaireForm` and
 * every level of the recursion would put a patient-linking concern into code whose whole job is not
 * to know what a question is about, so the page that knows publishes it once.
 */
const LockedQuestionsContext = createContext<LockedQuestions>(NO_LOCKED_QUESTIONS)

/** Publish the locked set to every control rendered under it. */
export function LockedQuestionsProvider({ locked, children }: { locked: LockedQuestions; children: ReactNode }) {
    return <LockedQuestionsContext value={locked}>{children}</LockedQuestionsContext>
}

/**
 * A Questionnaire, rendered as something a person can fill in.
 *
 * THE SHAPE OF A DHIS2 FORM. An aggregate data set nests three deep - a section group, a data
 * element group, and one disaggregated cell per category option combo - while an event or
 * tracker form is a flat list of questions. Both are handled by the same recursion: a top-level
 * group is a Card, a nested group is a bordered section inside it, and a run of loose questions
 * at the root gets a Card of its own so nothing floats without a surface. That last rule is
 * what stops an aggregate form (which mixes sections with ungrouped data elements) from
 * rendering half its questions inside a card and half beside one.
 *
 * THE CODE IS THE IDENTITY. Every question carries its DHIS2 uid as a mono badge next to the
 * label. The people who run these servers navigate by uid - it is what appears in the capture
 * validator's refusals, in the spool, and in DHIS2 itself - so hiding it behind a tooltip would
 * hide the one string that connects this screen to everything else.
 *
 * ENABLEWHEN HIDES, AND WHAT IS HIDDEN IS CLEARED. A disabled item is not rendered and carries no
 * answer: a value typed under a question the form then stopped asking describes nothing, and
 * forwarded it becomes a real DHIS2 data value about a real person - the very thing DHIS2's program
 * rules exist to prevent. The clearing itself is `clearedHiddenAnswers` in lib/questionnaire.ts;
 * this component only declines to render what the form is not asking.
 *
 * WHAT DHIS2 SAYS ABOUT A QUESTION IS SAID BESIDE IT. A data element's description is help text a
 * form designer wrote, so it reads under the label and above the control - the same place the
 * capture context's own controls put theirs. A section's description reads under its heading. And a
 * group of disaggregated cells names the categories its cells are cut by, because "Fixed, <1y" is
 * the name of one corner of a grid and says nothing about which grid it is a corner of.
 *
 * THE SHAPE OF A RUN IS DECIDED BEFORE ANY ITEM IS DRAWN. `formBlocks` reads each level of the form
 * as a sequence of runs - a disaggregation table, a flow of scalar questions, or a single item - and
 * this component draws each run as what it is. The two wide shapes never meet: a run is a table or a
 * flow, never a table flowed into columns, because a table already uses the width it needs and
 * halving it would put two grids side by side for a reader to tell apart.
 */
export function QuestionnaireForm({
    spec,
    answers,
    dispatch,
}: {
    spec: QuestionnaireSpec
    answers: AnswerState
    dispatch: Dispatch<AnswerAction>
}) {
    const enabled = enabledLinkIds(spec, answers)
    const sections = rootSections(spec, enabled)

    return (
        <div className="grid gap-4">
            {sections.map((section) => {
                const heading = spec.byLinkId.get(section.groupLinkId ?? '')
                return (
                    <Card key={section.key}>
                        <CardHeader>
                            <CardTitle className="flex flex-wrap items-center gap-2">
                                <span>{heading?.text ?? heading?.linkId ?? 'Questions'}</span>
                                {heading?.code?.code !== undefined && <CodeBadge code={heading.code.code} />}
                            </CardTitle>
                            {section.groupLinkId !== null && (
                                <GroupNotes spec={spec} groupLinkId={section.groupLinkId} />
                            )}
                        </CardHeader>
                        <CardContent className="grid gap-4">
                            <FormBlocks
                                spec={spec}
                                linkIds={section.linkIds}
                                answers={answers}
                                enabled={enabled}
                                dispatch={dispatch}
                            />
                        </CardContent>
                    </Card>
                )
            })}
        </div>
    )
}

/** One item and everything under it: a nested group, a display, or a question with its control. */
export function QuestionnaireItemView({
    spec,
    linkId,
    answers,
    enabled,
    dispatch,
}: {
    spec: QuestionnaireSpec
    linkId: string
    answers: AnswerState
    enabled: ReadonlySet<string>
    dispatch: Dispatch<AnswerAction>
}) {
    const locked = use(LockedQuestionsContext)
    const node = spec.byLinkId.get(linkId)
    if (node === undefined || !enabled.has(linkId)) return null

    if (node.type === 'display') {
        return <p className="text-muted-foreground text-sm">{node.text ?? node.linkId}</p>
    }

    if (node.type === 'group') {
        return (
            <fieldset className="border-border grid gap-4 rounded-lg border p-4">
                <legend className="flex flex-wrap items-center gap-2 px-1 text-sm font-medium">
                    <span>{node.text ?? node.linkId}</span>
                    {node.code?.code !== undefined && <CodeBadge code={node.code.code} />}
                </legend>
                <GroupNotes spec={spec} groupLinkId={node.linkId} />
                <FormBlocks
                    spec={spec}
                    linkIds={node.childLinkIds}
                    answers={answers}
                    enabled={enabled}
                    dispatch={dispatch}
                />
            </fieldset>
        )
    }

    return (
        <div className="grid gap-2">
            <Label htmlFor={node.linkId} className="flex-wrap items-baseline gap-2">
                <span>{node.text ?? node.linkId}</span>
                {node.required && (
                    <span className="text-destructive" aria-hidden>
                        *
                    </span>
                )}
                {node.required && <span className="sr-only">(required)</span>}
                {node.code?.code !== undefined && <CodeBadge code={node.code.code} />}
            </Label>
            {/* Between the label and the control, which is where help text belongs and where the
                capture context's own controls already put theirs: it is what the question means,
                read before it is answered, rather than a note about what the answer may hold. */}
            {node.description !== null && (
                <p className="text-muted-foreground text-sm">{node.description}</p>
            )}
            <AnswerControl
                node={node}
                slots={answers[node.linkId] ?? []}
                locked={locked.linkIds.has(node.linkId)}
                dispatch={dispatch}
            />
            {locked.linkIds.has(node.linkId) ? (
                <p className="text-muted-foreground text-xs">{locked.note}</p>
            ) : (
                <QuestionHint node={node} />
            )}
            {node.childLinkIds.map((childLinkId) => (
                <QuestionnaireItemView
                    key={childLinkId}
                    spec={spec}
                    linkId={childLinkId}
                    answers={answers}
                    enabled={enabled}
                    dispatch={dispatch}
                />
            ))}
        </div>
    )
}

/** One level of a form, drawn run by run: a table, a flow of scalar questions, or a single item. */
function FormBlocks({
    spec,
    linkIds,
    answers,
    enabled,
    dispatch,
}: {
    spec: QuestionnaireSpec
    /** The sibling items of this level, in document order. */
    linkIds: readonly string[]
    answers: AnswerState
    enabled: ReadonlySet<string>
    dispatch: Dispatch<AnswerAction>
}) {
    return (
        <>
            {formBlocks(spec, linkIds, enabled).map((block) =>
                block.kind === 'disaggregation' ? (
                    <DisaggregationRun
                        key={block.key}
                        spec={spec}
                        block={block}
                        answers={answers}
                        enabled={enabled}
                        dispatch={dispatch}
                    />
                ) : block.kind === 'scalars' ? (
                    // AS MANY COLUMNS AS THE SCREEN HAS ROOM FOR, AND NO BREAKPOINT SAYING HOW MANY.
                    // A question needs about twenty rems to hold its label, its uid and its control,
                    // so that is what is asked for and the browser decides how many fit - which
                    // makes the same form read as one column on a laptop split in two and as four
                    // on a wide screen, without this file knowing either width.
                    <div key={block.key} className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(20rem,1fr))]">
                        {block.linkIds.map((linkId) => (
                            <QuestionnaireItemView
                                key={linkId}
                                spec={spec}
                                linkId={linkId}
                                answers={answers}
                                enabled={enabled}
                                dispatch={dispatch}
                            />
                        ))}
                    </div>
                ) : (
                    <QuestionnaireItemView
                        key={block.key}
                        spec={spec}
                        linkId={block.linkId}
                        answers={answers}
                        enabled={enabled}
                        dispatch={dispatch}
                    />
                ),
            )}
        </>
    )
}

/** What the switch says it will do next, which is the shape it is not in now. */
export const SHOW_AS_ROWS_LABEL = 'Show as rows'
export const SHOW_AS_COLUMNS_LABEL = 'Show as columns'

/** What the tick beside the filter box asks for: the rows still waiting for a value. */
export const UNFILLED_ONLY_LABEL = 'Unfilled only'

/**
 * Several data elements cut the same way, in whichever of the two shapes the run is drawn in.
 *
 * ONE FACT, ONCE. Stacked one question per combo, this run states its four category option combos
 * fourteen times over - fifty-six labels for four facts. Both shapes here spend those labels once:
 * the grid puts the combos in a header row and the elements down the side, and the vertical form puts
 * the element in a band and the combos down the page under it. The categories the cut runs along are
 * named once for the whole run, because a combo's name is the corner of a grid and never says which
 * grid, and so is anything every cell of the run states about what it accepts.
 *
 * THE LADDER DECIDES THE SHAPE AND A PERSON OVERRIDES IT. `defaultDisaggregationOrientation` reads
 * the width of the cut - four combos or fewer is a grid, wider is rows - and the switch on the band
 * is how somebody who wants the other one says so, kept per run in this browser. A cut with no grid
 * form at all offers no switch: see `offersOrientationSwitch`.
 *
 * THE CELLS ARE THE SAME QUESTIONS IN EITHER SHAPE. Every input keeps its own linkId, its own answer
 * slot and its own reducer dispatch, so the submission a grid produces and the submission a list of
 * rows produces are the same QuestionnaireResponse - and so is the one produced under a filter, which
 * hides rows from the screen and nothing else. Reading order is document order in both.
 *
 * WHAT EACH CELL IS NAMED. A cell's label is two words in a header row a screen reader has already
 * left, so each input carries the element and the combo as its own accessible name - "Malaria
 * (Deaths under 5 yrs) 0-11m" - which is the whole address of the value being typed.
 */
function DisaggregationRun({
    spec,
    block,
    answers,
    enabled,
    dispatch,
}: {
    spec: QuestionnaireSpec
    block: Extract<FormBlock, { kind: 'disaggregation' }>
    answers: AnswerState
    enabled: ReadonlySet<string>
    dispatch: Dispatch<AnswerAction>
}) {
    const axes = groupCategoryAxes(spec, block.groupLinkIds[0])
    // A cut over two categories is wider than any screen as one table, so the category with fewest
    // options becomes a band apiece: Female's ages, then Male's. Read from the decomposition the
    // served vocabulary publishes rather than from the combo's name, which is why reordering the
    // categories inside a combo does not redraw the form - see `facetColumns`. Banding is structure
    // rather than shape: it holds in both orientations, and what changes is what is drawn inside a band.
    const facets = facetColumns(block.columns)
    // The run's first group uid is the run's name in storage. It is stable for as long as the form is:
    // the run begins at that element because the elements before it are cut differently.
    const runKey = block.groupLinkIds[0]
    // WHAT IS HELD IS THE OVERRIDE, NOT THE SHAPE. The ladder reads the served combo vocabulary, and
    // that arrives one render after the form does - so a shape decided at mount would be decided
    // before anything is known about the cut, and a run that bands into two fours would be latched as
    // rows for as long as the page is open. The ladder is asked again every render instead, and only
    // a person's own choice is state.
    const [override, setOverride] = useState<DisaggregationOrientation | null>(null)
    const [query, setQuery] = useState('')
    const [unfilledOnly, setUnfilledOnly] = useState(false)
    const switchable = offersOrientationSwitch(block.columns)
    const orientation = switchable ? (override ?? openedDisaggregationOrientation(runKey, block.columns)) : 'vertical'
    const rows = comboRows(block.columns, facets?.[0] ?? null)
    const filtering = orientation === 'vertical' && offersComboFilter(rows)
    const filterPlaceholder = comboFilterPlaceholder(rows, rowAxisName(axes, facets?.[0] ?? null))
    const flip = () => {
        const next = otherOrientation(orientation)
        setOverride(next)
        rememberDisaggregationOrientation(runKey, next)
    }

    return (
        <div className="grid gap-2">
            {/* The run's own strip: what the cut is, on the left, and the one control that decides
                the whole run's shape on the right. The two ways of narrowing a long band belong to
                the band they narrow and sit there instead. */}
            <div className="flex flex-wrap items-center justify-between gap-2">
                <RunNotes spec={spec} block={block} axes={axes} enabled={enabled} />
                {switchable && (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon-sm"
                                onClick={flip}
                                aria-label={orientation === 'grid' ? SHOW_AS_ROWS_LABEL : SHOW_AS_COLUMNS_LABEL}
                            >
                                {orientation === 'grid' ? <Rows3 /> : <Columns3 />}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                            {orientation === 'grid' ? SHOW_AS_ROWS_LABEL : SHOW_AS_COLUMNS_LABEL}
                        </TooltipContent>
                    </Tooltip>
                )}
            </div>
            {facets === null ? (
                <RunBody
                    spec={spec}
                    block={block}
                    facet={null}
                    facetKey=""
                    orientation={orientation}
                    answers={answers}
                    enabled={enabled}
                    filtering={filtering}
                    filterPlaceholder={filterPlaceholder}
                    query={query}
                    unfilledOnly={unfilledOnly}
                    onQuery={setQuery}
                    onUnfilledOnly={setUnfilledOnly}
                    dispatch={dispatch}
                />
            ) : (
                facets.map((facet, position) => (
                    <RunBody
                        key={facet.heading}
                        spec={spec}
                        block={block}
                        facet={facet}
                        facetKey={String(position)}
                        orientation={orientation}
                        answers={answers}
                        enabled={enabled}
                        filtering={filtering}
                        filterPlaceholder={filterPlaceholder}
                        query={query}
                        unfilledOnly={unfilledOnly}
                        onQuery={setQuery}
                        onUnfilledOnly={setUnfilledOnly}
                        dispatch={dispatch}
                    />
                ))
            )}
        </div>
    )
}

/**
 * One run's worth of cells - the whole cut, or one facet of it - drawn as a grid or as rows.
 *
 * THE BOX IS THE UNIT AND THE BAND IS ITS NAME. Everything a run draws lands in a bordered box, and
 * the box is headed by an accent band carrying what it holds: the facet's own value where the ladder
 * banded the cut, the data element where the run is drawn as rows. A grid over a cut nothing banded
 * has no such name - the elements are its rows and the combos are its columns, both already headed -
 * so it takes the box without a band rather than a band with nothing to say in it.
 */
function RunBody({
    spec,
    block,
    facet,
    facetKey,
    orientation,
    answers,
    enabled,
    filtering,
    filterPlaceholder,
    query,
    unfilledOnly,
    onQuery,
    onUnfilledOnly,
    dispatch,
}: {
    spec: QuestionnaireSpec
    block: Extract<FormBlock, { kind: 'disaggregation' }>
    /** The facet this body draws, or null when the cut has no facet form and is drawn whole. */
    facet: DisaggregationFacet | null
    /** This facet's position in the run, which is what keeps one band's tick apart from the next's. */
    facetKey: string
    orientation: DisaggregationOrientation
    answers: AnswerState
    enabled: ReadonlySet<string>
    /** Whether these bands offer the two ways of narrowing their lines. */
    filtering: boolean
    filterPlaceholder: string
    query: string
    unfilledOnly: boolean
    onQuery: (query: string) => void
    onUnfilledOnly: (unfilledOnly: boolean) => void
    dispatch: Dispatch<AnswerAction>
}) {
    const rows = comboRows(block.columns, facet)
    const totalled = addsUpToATotal(block.columns)
    if (orientation === 'grid') {
        return (
            <div className="bg-card overflow-hidden rounded-lg border">
                {facet !== null && <BandHeading>{facet.heading}</BandHeading>}
                <DisaggregationTable
                    spec={spec}
                    block={block}
                    rows={rows}
                    totalled={totalled}
                    answers={answers}
                    enabled={enabled}
                    dispatch={dispatch}
                />
            </div>
        )
    }
    return (
        <div className="grid gap-2">
            {/* The same band the grid draws its facet in. A facet is what the box under it holds
                whichever shape the run is in, and a quiet paragraph over a stack of banded elements
                read as a caption rather than as the heading of everything below it - which is the
                one thing a reader has to know before they read a single number. */}
            {facet !== null && (
                <BandHeading className="rounded-lg border">{facet.heading}</BandHeading>
            )}
            {block.groupLinkIds.map((groupLinkId) => (
                <ElementRows
                    key={groupLinkId}
                    spec={spec}
                    groupLinkId={groupLinkId}
                    bandKey={`${groupLinkId}-${facetKey}`}
                    rows={rows}
                    totalled={totalled}
                    answers={answers}
                    enabled={enabled}
                    filtering={filtering}
                    filterPlaceholder={filterPlaceholder}
                    query={filtering ? query : ''}
                    unfilledOnly={filtering && unfilledOnly}
                    onQuery={onQuery}
                    onUnfilledOnly={onUnfilledOnly}
                    dispatch={dispatch}
                />
            ))}
        </div>
    )
}

/**
 * The accent strip a band-box is headed with, and whatever belongs beside the name on it.
 *
 * One component for both shapes, because a reader should not have to work out whether *Female* over a
 * table and *BCG doses given* over a list of lines are the same kind of heading. They are: each names
 * what the box under it holds.
 */
function BandHeading({ children, className }: { children: ReactNode; className?: string }) {
    return (
        <div
            className={cn(
                'bg-accent text-accent-foreground flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-3 py-1.5 text-sm font-semibold',
                className,
            )}
        >
            {children}
        </div>
    )
}

/**
 * One table: the elements of the run down the side, the combos it was handed across the top.
 *
 * The rows it is handed are the whole cut or one facet's slice of it, which is what lets the same
 * table serve a cut of four combos and one facet of a cut of eight.
 *
 * THE COLUMN OF TOTALS IS THE ARITHMETIC SOMEBODY WAS GOING TO DO ANYWAY. A row of counts is read
 * against its own total - it is how a 1370 typed where 137 was meant is caught, at the desk rather
 * than in a DHIS2 validation rule a fortnight later - so the table closes every row with what it
 * currently adds to, recomputed as the boxes are typed in. Nothing of it is submitted: see
 * `liveTotal` for what a blank counts as and what an unreadable box does to the figure.
 *
 * NO UIDS IN HERE. Every cell of this table belongs to a data element and a category option combo
 * that both have one, and a chip on each would put fifty-six identifiers on a screen whose whole
 * purpose is fifty-six numbers. The uids stay a click away, on the form's own heading and in the
 * API and raw views, which is where somebody looking for one goes.
 */
function DisaggregationTable({
    spec,
    block,
    rows,
    totalled,
    answers,
    enabled,
    dispatch,
}: {
    spec: QuestionnaireSpec
    block: Extract<FormBlock, { kind: 'disaggregation' }>
    rows: ComboRow[]
    /** Whether these cells are one element cut several ways, which is what a total may add. */
    totalled: boolean
    answers: AnswerState
    enabled: ReadonlySet<string>
    dispatch: Dispatch<AnswerAction>
}) {
    const locked = use(LockedQuestionsContext)
    return (
        <div className="overflow-x-auto">
            <Table>
                <TableHeader>
                    <TableRow>
                        {/* The corner names what the rows are, because a table whose first column
                            has no heading asks the reader to work out what it holds. It is also the
                            column that takes the slack: the answer columns are the width of an
                            answer, and a three-digit count in a box wide enough for a sentence is a
                            box that was never about the count. */}
                        <TableHead scope="col" className="w-full">
                            Data element
                        </TableHead>
                        {rows.map((row) => {
                            const column = block.columns[row.index]
                            return (
                                <TableHead key={columnKey(column)} scope="col" className="h-9 w-28 text-right">
                                    {row.label}
                                </TableHead>
                            )
                        })}
                        {totalled && (
                            <TableHead scope="col" className="text-muted-foreground h-9 w-16 text-right">
                                Total
                            </TableHead>
                        )}
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {block.groupLinkIds.map((groupLinkId) => {
                        const group = spec.byLinkId.get(groupLinkId)
                        const description = group?.description ?? null
                        const cells = disaggregationCells(spec, groupLinkId, enabled)
                        const total = totalled
                            ? liveTotal(rows.map((row) => cellLiteral(answers, cells[row.index])))
                            : null
                        return (
                            <TableRow key={groupLinkId}>
                                {/* The row label takes the slack, which is what keeps the answer
                                    columns the width of the answers: a table is as wide as its card,
                                    and with every column sharing the surplus a three-digit count sat
                                    in a box wide enough for a sentence. */}
                                <TableHead scope="row" className="min-w-48 py-1.5 align-top text-wrap whitespace-normal">
                                    <span>{group?.text ?? groupLinkId}</span>
                                    {description !== null && (
                                        <span className="text-muted-foreground block text-xs font-normal">
                                            {description}
                                        </span>
                                    )}
                                </TableHead>
                                {rows.map((row) => {
                                    const cellLinkId = cells[row.index]
                                    const cell = cellLinkId === undefined ? undefined : spec.byLinkId.get(cellLinkId)
                                    if (cellLinkId === undefined || cell === undefined) {
                                        return <TableCell key={`${groupLinkId}-${String(row.index)}`} />
                                    }
                                    const cellLocked = locked.linkIds.has(cellLinkId)
                                    return (
                                        <TableCell key={cellLinkId} className="px-1.5 py-1 align-top">
                                            <Label htmlFor={cellLinkId} className="sr-only">
                                                {group?.text ?? groupLinkId} {cell.text ?? cellLinkId}
                                            </Label>
                                            <AnswerControl
                                                node={cell}
                                                slots={answers[cellLinkId] ?? []}
                                                locked={cellLocked}
                                                controlClassName="w-full min-w-20"
                                                dispatch={dispatch}
                                            />
                                            {cellLocked && (
                                                <p className="text-muted-foreground mt-1 text-xs">{locked.note}</p>
                                            )}
                                        </TableCell>
                                    )
                                })}
                                {totalled && (
                                    <TableCell className="text-muted-foreground px-3 py-1 text-right align-middle tabular-nums">
                                        {total === null ? '' : formatCount(total)}
                                    </TableCell>
                                )}
                            </TableRow>
                        )
                    })}
                </TableBody>
            </Table>
        </div>
    )
}

/**
 * One data element of a run, drawn as rows: its name as a band, and a line per combo under it.
 *
 * WHY THE ROWS WRAP INTO COLUMN GROUPS RATHER THAN RUNNING ON. A cut of ninety-six options is a
 * ninety-six-line column with a screen of white beside it, and the eye that has to travel that far
 * loses the band the rows belong to. Flowing them into as many groups as the width holds keeps the
 * whole element in view without a single row leaving its own reading order - the flow runs down a
 * group and on to the next, which is the order the form states its combos in. Nothing scrolls
 * sideways here at any width, which is the whole reason this shape exists.
 *
 * A SHORT ELEMENT DOES NOT FLOW. Four rows split into three groups is a grid nobody asked for, so the
 * flow starts where a single column starts being long.
 */
function ElementRows({
    spec,
    groupLinkId,
    bandKey,
    rows,
    totalled,
    answers,
    enabled,
    filtering,
    filterPlaceholder,
    query,
    unfilledOnly,
    onQuery,
    onUnfilledOnly,
    dispatch,
}: {
    spec: QuestionnaireSpec
    groupLinkId: string
    /** This band's own name, which is what keeps its tick's id apart from every other band's. */
    bandKey: string
    rows: ComboRow[]
    /** Whether these lines are one element cut several ways, which is what a total may add. */
    totalled: boolean
    answers: AnswerState
    enabled: ReadonlySet<string>
    filtering: boolean
    filterPlaceholder: string
    query: string
    unfilledOnly: boolean
    onQuery: (query: string) => void
    onUnfilledOnly: (unfilledOnly: boolean) => void
    dispatch: Dispatch<AnswerAction>
}) {
    const locked = use(LockedQuestionsContext)
    const group = spec.byLinkId.get(groupLinkId)
    const cells = disaggregationCells(spec, groupLinkId, enabled)
    const visible = visibleComboRows(rows, query, unfilledOnly, (index) => {
        const cellLinkId = cells[index]
        const cell = cellLinkId === undefined ? undefined : spec.byLinkId.get(cellLinkId)
        return cell !== undefined && isAnswered(cell, answers)
    })
    // Over every line the element has, never over the ones a filter left on screen: the total is
    // what this element currently reports, and a figure that changed because somebody typed three
    // letters into a filter box would be a figure about the filter.
    const total = totalled ? liveTotal(rows.map((row) => cellLiteral(answers, cells[row.index]))) : null
    return (
        <div className="bg-card overflow-hidden rounded-lg border">
            <BandHeading>
                <span>{group?.text ?? groupLinkId}</span>
                {filtering && (
                    <ComboFilter
                        placeholder={filterPlaceholder}
                        query={query}
                        unfilledOnly={unfilledOnly}
                        bandKey={bandKey}
                        onQuery={onQuery}
                        onUnfilledOnly={onUnfilledOnly}
                    />
                )}
                {total !== null && (
                    <span className="ml-auto font-normal tabular-nums">Total {formatCount(total)}</span>
                )}
            </BandHeading>
            {group?.description !== null && group?.description !== undefined && (
                <p className="text-muted-foreground border-b px-3 py-1.5 text-xs">{group.description}</p>
            )}
            {visible.length === 0 ? (
                <p className="text-muted-foreground px-3 py-2 text-xs">No option matches what is asked for</p>
            ) : (
                <div className={cn('px-3 py-2', COLUMN_GROUP_CLASSES[columnGroups(visible.length)])}>
                    {visible.map((row) => {
                        const cellLinkId = cells[row.index]
                        const cell = cellLinkId === undefined ? undefined : spec.byLinkId.get(cellLinkId)
                        if (cellLinkId === undefined || cell === undefined) return null
                        const cellLocked = locked.linkIds.has(cellLinkId)
                        return (
                            <div
                                key={cellLinkId}
                                className="flex break-inside-avoid items-center justify-between gap-3 py-0.5"
                            >
                                <Label htmlFor={cellLinkId} className="min-w-0 flex-wrap items-baseline gap-2">
                                    {/* The element first and the combo second, which is the order a
                                        table cell names itself in - so one address finds a value
                                        whichever shape the run is drawn in, for a screen reader and
                                        for anything else that goes looking by name. The band carries
                                        the element on screen, so only a screen reader hears it here. */}
                                    <span className="sr-only">{`${group?.text ?? groupLinkId} `}</span>
                                    <span className="truncate">{row.label}</span>
                                </Label>
                                <AnswerControl
                                    node={cell}
                                    slots={answers[cellLinkId] ?? []}
                                    locked={cellLocked}
                                    controlClassName="w-[4.5rem] shrink-0 text-right tabular-nums"
                                    dispatch={dispatch}
                                />
                            </div>
                        )
                    })}
                </div>
            )}
            {locked.linkIds.has(cells[0] ?? '') && (
                <p className="text-muted-foreground px-3 pb-2 text-xs">{locked.note}</p>
            )}
        </div>
    )
}

/**
 * How many groups the lines of one band wrap into, read off how many lines there are.
 *
 * A count rather than a width, because the point is the height: four lines split into three groups
 * is a grid nobody asked for, and ninety-six in one column is a band whose heading has left the
 * screen by the time the last box is reached. The steps are where a single column stops being a list
 * and starts being a scroll. What each group is *worth* in pixels is the browser's - CSS columns
 * divide whatever width the card gives them.
 */
function columnGroups(lineCount: number): 1 | 2 | 3 {
    if (lineCount < 10) return 1
    return lineCount <= 24 ? 2 : 3
}

/**
 * The three column counts as classes, spelled out so the stylesheet's scanner can see them.
 *
 * The width cap is what keeps a group a column of lines rather than a line of two halves: a label on
 * the far left and its box on the far right, a screen apart, is a pairing the eye has to travel to
 * make. About twenty-six rems is as wide as one of these lines reads, so one group is held to it and
 * two are held to twice it; three fill whatever the card has, which lands at about the same width.
 */
const COLUMN_GROUP_CLASSES: Record<1 | 2 | 3, string> = {
    1: 'columns-1 max-w-[26rem]',
    2: 'columns-2 max-w-[54rem] gap-x-7',
    3: 'columns-3 gap-x-7',
}

/** What one cell's box currently holds, verbatim - the literal a total is computed from. */
function cellLiteral(answers: AnswerState, cellLinkId: string | undefined): string {
    if (cellLinkId === undefined) return ''
    return answers[cellLinkId]?.[0]?.text ?? ''
}

/**
 * Whether the cells of this run are one data element cut several ways, which is what adds up.
 *
 * THE RUN IS NOT ALWAYS A CUT. A section of plain numeric data elements - deliveries in a facility,
 * deliveries in the community, low birth weights - is a group of numeric questions and reaches this
 * renderer as one, which is what lets it read as a block rather than as seven stacked controls. What
 * it is not is one quantity measured seven ways, so a total under it would add live births to bed
 * nets and call the answer a figure. The decomposition the served combo vocabulary publishes is what
 * tells the two apart: a real cut states which category option each cell stands for, and a column
 * that states none is a data element in its own right. A vocabulary this server has not published
 * leaves every column stating none, so nothing is totalled until it lands - which is the right way
 * round, because a total nobody can account for is worse than no total.
 */
function addsUpToATotal(columns: readonly DisaggregationColumn[]): boolean {
    return columns.every((column) => column.decomposition.length > 0)
}

/**
 * The two ways of getting to one row of a wide cut: name part of it, or ask for the ones still empty.
 *
 * ON THE BAND OF THE ELEMENT IT NARROWS. A run of fifteen elements cut ninety-six ways is fifteen
 * screens of lines, so a filter stated once at the top of the run is a control that has scrolled away
 * by the time anybody wants it. Every band carries its own, and all of them ask the same question -
 * what is typed into one narrows every band of the run, because the lines they hold are the same
 * ninety-six options and somebody looking for Bombali is looking for it in all of them.
 */
function ComboFilter({
    placeholder,
    query,
    unfilledOnly,
    bandKey,
    onQuery,
    onUnfilledOnly,
}: {
    placeholder: string
    query: string
    unfilledOnly: boolean
    /** The band's own name, which is what keeps the tick's id unique on a form with several bands. */
    bandKey: string
    onQuery: (query: string) => void
    onUnfilledOnly: (unfilledOnly: boolean) => void
}) {
    const tickId = `${bandKey}-unfilled-only`
    return (
        <div className="flex flex-wrap items-center gap-2">
            <Input
                type="search"
                value={query}
                aria-label={placeholder}
                placeholder={placeholder}
                onChange={(event) => {
                    onQuery(event.target.value)
                }}
                className="bg-card h-7 w-52 text-sm font-normal"
            />
            <Label htmlFor={tickId} className="gap-1.5 text-xs font-normal">
                <input
                    id={tickId}
                    type="checkbox"
                    checked={unfilledOnly}
                    onChange={(event) => {
                        onUnfilledOnly(event.target.checked)
                    }}
                    className="accent-primary size-3.5"
                />
                {UNFILLED_ONLY_LABEL}
            </Label>
        </div>
    )
}

/**
 * What a whole run states about itself: what its cells are cut by, and what every one of them accepts.
 *
 * ONE FACT ONCE, AND THE CELLS ARE WHERE IT WAS SAID FIFTY-SIX TIMES. Every cell of a run is the same
 * data element cut a different way, so "0 or more" under each of them is one fact wearing fifty-six
 * costumes. When every cell of the run says the same thing, it is said here instead and the cells say
 * nothing; when they differ - a run whose elements carry different bounds - each cell keeps its own,
 * because a single line could then only be wrong.
 */
function RunNotes({
    spec,
    block,
    axes,
    enabled,
}: {
    spec: QuestionnaireSpec
    block: Extract<FormBlock, { kind: 'disaggregation' }>
    axes: string[]
    enabled: ReadonlySet<string>
}) {
    const shared = sharedCellNote(spec, block, enabled)
    if (axes.length === 0 && shared === null) return null
    return (
        <p className="text-muted-foreground text-xs">
            {axes.length > 0 && <span>Disaggregated by {joinNames(axes)}</span>}
            {axes.length > 0 && shared !== null && <span aria-hidden> - </span>}
            {shared !== null && <span>{shared}</span>}
        </p>
    )
}

/** What every cell of a run says about what it accepts, or null when they do not all say the same. */
function sharedCellNote(
    spec: QuestionnaireSpec,
    block: Extract<FormBlock, { kind: 'disaggregation' }>,
    enabled: ReadonlySet<string>,
): string | null {
    const notes = block.groupLinkIds.flatMap((groupLinkId) =>
        disaggregationCells(spec, groupLinkId, enabled).map((cellLinkId) => {
            const cell = spec.byLinkId.get(cellLinkId)
            return cell === undefined ? '' : questionNotes(cell).join(', ')
        }),
    )
    const first = notes[0]
    if (first === undefined || first === '') return null
    return notes.every((note) => note === first) ? first : null
}

/** A column's own key: the combo uid when it has one, and its label when the form codes it with none. */
function columnKey(column: DisaggregationColumn): string {
    return column.code ?? column.label
}

/** The DHIS2 uid a question carries, which is the string every other surface names it by. */
function CodeBadge({ code, className }: { code: string; className?: string }) {
    return (
        <Badge variant="outline" className={cn('machine-identifier text-[10px]', className)}>
            {code}
        </Badge>
    )
}

/**
 * What one group states about the questions under it: its description, then what its cells are cut by.
 *
 * THE AXES ARE THE FACT THE CELL LABELS DO NOT CARRY. A data element group holds one question per
 * category option combo and each is labelled with the combo's own name - "Fixed, <1y" - which names a
 * corner of a grid and never says which grid. The categories are the same for every cell of one
 * group, so they are named once, here, from the decomposition the served combo vocabulary publishes.
 */
function GroupNotes({ spec, groupLinkId }: { spec: QuestionnaireSpec; groupLinkId: string }) {
    const node = spec.byLinkId.get(groupLinkId)
    const axes = groupCategoryAxes(spec, groupLinkId)
    if (node === undefined) return null
    if (node.description === null && axes.length === 0) return null
    return (
        <div className="grid gap-1">
            {node.description !== null && (
                <p className="text-muted-foreground text-sm">{node.description}</p>
            )}
            {axes.length > 0 && (
                <p className="text-muted-foreground text-xs">Disaggregated by {joinNames(axes)}</p>
            )}
        </div>
    )
}

/** Several names as one phrase, so a reader gets prose rather than a comma-separated list. */
function joinNames(names: string[]): string {
    if (names.length <= 1) return names.join('')
    return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** What this question takes beyond its label: bounds, the two answers a tick has, repetition, read-only. */
function QuestionHint({ node, className }: { node: QuestionnaireNode; className?: string }) {
    const notes = questionNotes(node)
    if (notes.length === 0) return null
    return <p className={cn('text-muted-foreground text-xs', className)}>{notes.join(', ')}</p>
}

/**
 * Everything one question states about what it accepts, as the phrases a reader is shown.
 *
 * A list rather than a sentence because two callers need it in two shapes: the hint under one control
 * reads it as a sentence, and a run of disaggregated cells compares it cell against cell to find out
 * whether the whole run has one thing to say.
 */
function questionNotes(node: QuestionnaireNode): string[] {
    const notes: string[] = []
    if (node.minimum !== null && node.maximum !== null) notes.push(`between ${node.minimum} and ${node.maximum}`)
    else if (node.minimum !== null) notes.push(`${node.minimum} or more`)
    else if (node.maximum !== null) notes.push(`${node.maximum} or less`)
    // The same fact one element over: a bounded day reads as days rather than as numbers, because
    // "between 2026-01-01 and 2026-12-31" is a range of dates and nothing about it is a quantity.
    if (node.minimumDate !== null && node.maximumDate !== null) {
        notes.push(`between ${node.minimumDate} and ${node.maximumDate}`)
    } else if (node.minimumDate !== null) notes.push(`${node.minimumDate} or later`)
    else if (node.maximumDate !== null) notes.push(`${node.maximumDate} or earlier`)
    // The one note that comes from the data dictionary rather than from the form: a TRUE_ONLY data
    // element holds `true` or nothing, so the two answers the control offers are the two DHIS2 keeps.
    if (node.valueType === TRUE_ONLY_VALUE_TYPE) {
        notes.push('yes or not answered - DHIS2 stores no No for this question')
    }
    if (node.repeats) notes.push('takes more than one answer')
    // A read-only question is one nothing here can answer, and the dictionary is what says why:
    // DHIS2 mints a generated attribute's value on import. Saying "read only" alone would leave a
    // person looking for the way to type in it; naming the shape is what tells them what will arrive.
    if (node.readOnly && node.generated) {
        notes.push(
            node.pattern === null
                ? 'DHIS2 fills this in when the submission is imported'
                : `DHIS2 fills this in when the submission is imported, shaped ${node.pattern}`,
        )
    } else if (node.readOnly) {
        notes.push('read only')
    }
    return notes
}

/** One Card's worth of the form: a top-level group, or a run of questions that sit outside one. */
interface RootSection {
    key: string
    /** The group this Card renders, or null when the Card is a run of ungrouped questions. */
    groupLinkId: string | null
    linkIds: string[]
}

/**
 * Partition the top level into Cards.
 *
 * A top-level group becomes its own Card. Consecutive top-level items that are *not* groups are
 * collected into one Card between them, which preserves document order - a data set that states
 * two sections and then three loose totals reads as section, section, totals, not as three
 * cards of one question each.
 *
 * A DATA ELEMENT GROUP THAT IS A TABLE ROW IS NOT A SECTION. A data set with no sections states its
 * disaggregated elements at the top level, so fourteen elements would be fourteen Cards of four
 * questions each - the same run that reads as one table one level down. The partition runs first,
 * and a run that became a table is carried into the Card beside it rather than opening one per row.
 */
function rootSections(spec: QuestionnaireSpec, enabled: ReadonlySet<string>): RootSection[] {
    const sections: RootSection[] = []
    let loose: string[] = []
    const flushLoose = () => {
        if (loose.length === 0) return
        sections.push({ key: `loose-${loose[0]}`, groupLinkId: null, linkIds: loose })
        loose = []
    }
    for (const block of formBlocks(spec, spec.rootLinkIds, enabled)) {
        if (block.kind === 'item' && spec.byLinkId.get(block.linkId)?.type === 'group') {
            flushLoose()
            sections.push({
                key: block.linkId,
                groupLinkId: block.linkId,
                linkIds: spec.byLinkId.get(block.linkId)?.childLinkIds ?? [],
            })
            continue
        }
        loose.push(...blockLinkIds(block))
    }
    flushLoose()
    return sections
}

/** The items one run is made of, in document order - what a Card holding the run is drawn from. */
function blockLinkIds(block: FormBlock): string[] {
    if (block.kind === 'disaggregation') return block.groupLinkIds
    if (block.kind === 'scalars') return block.linkIds
    return [block.linkId]
}
