import { createContext, use, type Dispatch, type ReactNode } from 'react'

import { AnswerControl } from '@/components/AnswerControl'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import {
    disaggregationCells,
    enabledLinkIds,
    formBlocks,
    groupCategoryAxes,
    TRUE_ONLY_VALUE_TYPE,
    type AnswerAction,
    type AnswerState,
    type DisaggregationColumn,
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
                    <DisaggregationTable
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

/**
 * Several data elements cut the same way, as the table DHIS2 enters them in.
 *
 * ONE FACT, ONCE. Stacked, this run states its four category option combos fourteen times over,
 * each with its own label and its own uid chip - fifty-six labels for four facts. As a table the
 * combos are the header row, the data elements are the row labels, and every uid is still on screen
 * exactly once: the column's in its header, the element's beside its name. The categories the
 * columns cut along are named once above the table, because a combo's name is the corner of a grid
 * and never says which grid.
 *
 * THE CELLS ARE THE SAME QUESTIONS THEY WERE. Every input keeps its own linkId, its own answer slot
 * and its own reducer dispatch, so what a table produces and what a stack produced are the same
 * QuestionnaireResponse. Reading order is row by row, which is document order, so the keyboard walks
 * the form the way the form is written.
 *
 * WHAT EACH CELL IS NAMED. A cell's label is two words in a header row a screen reader has already
 * left, so each input carries the element and the combo as its own accessible name - "Malaria
 * (Deaths under 5 yrs) 0-11m" - which is the whole address of the value being typed.
 */
function DisaggregationTable({
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
    const locked = use(LockedQuestionsContext)
    const axes = groupCategoryAxes(spec, block.groupLinkIds[0])
    return (
        <div className="grid gap-2">
            {axes.length > 0 && (
                <p className="text-muted-foreground text-xs">Disaggregated by {joinNames(axes)}</p>
            )}
            <div className="overflow-x-auto rounded-lg border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            {/* The corner names what the rows are, because a table whose first
                                column has no heading asks the reader to work out what it holds. */}
                            <TableHead scope="col">Data element</TableHead>
                            {block.columns.map((column) => (
                                <TableHead key={columnKey(column)} scope="col">
                                    <span className="flex items-center gap-2">
                                        <span>{column.label}</span>
                                        {column.code !== null && <CodeBadge code={column.code} />}
                                    </span>
                                </TableHead>
                            ))}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {block.groupLinkIds.map((groupLinkId) => {
                            const group = spec.byLinkId.get(groupLinkId)
                            const description = group?.description ?? null
                            return (
                                <TableRow key={groupLinkId}>
                                    {/* The row label takes the slack, which is what keeps the
                                        answer columns the width of the answers: a table is as wide
                                        as its card, and with every column sharing the surplus a
                                        three-digit count sat in a box wide enough for a sentence. */}
                                    <TableHead
                                        scope="row"
                                        className="w-full min-w-48 py-2 align-top text-wrap whitespace-normal"
                                    >
                                        <span className="flex flex-wrap items-baseline gap-2">
                                            <span>{group?.text ?? groupLinkId}</span>
                                            {group?.code?.code !== undefined && (
                                                <CodeBadge code={group.code.code} />
                                            )}
                                        </span>
                                        {description !== null && (
                                            <span className="text-muted-foreground block text-xs font-normal">
                                                {description}
                                            </span>
                                        )}
                                    </TableHead>
                                    {disaggregationCells(spec, groupLinkId, enabled).map((cellLinkId) => {
                                        const cell = spec.byLinkId.get(cellLinkId)
                                        if (cell === undefined) return null
                                        const cellLocked = locked.linkIds.has(cellLinkId)
                                        return (
                                            <TableCell key={cellLinkId} className="align-top">
                                                <Label htmlFor={cellLinkId} className="sr-only">
                                                    {group?.text ?? groupLinkId} {cell.text ?? cellLinkId}
                                                </Label>
                                                <AnswerControl
                                                    node={cell}
                                                    slots={answers[cellLinkId] ?? []}
                                                    locked={cellLocked}
                                                    controlClassName="w-24"
                                                    dispatch={dispatch}
                                                />
                                                {cellLocked ? (
                                                    <p className="text-muted-foreground mt-1 text-xs">
                                                        {locked.note}
                                                    </p>
                                                ) : (
                                                    <QuestionHint node={cell} className="mt-1" />
                                                )}
                                            </TableCell>
                                        )
                                    })}
                                </TableRow>
                            )
                        })}
                    </TableBody>
                </Table>
            </div>
        </div>
    )
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
    if (notes.length === 0) return null
    return <p className={cn('text-muted-foreground text-xs', className)}>{notes.join(', ')}</p>
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
