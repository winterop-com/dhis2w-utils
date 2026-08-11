import { createContext, use, type Dispatch, type ReactNode } from 'react'

import { AnswerControl } from '@/components/AnswerControl'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import {
    enabledLinkIds,
    type AnswerAction,
    type AnswerState,
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
 * ENABLEWHEN HIDES, IT DOES NOT DISCARD. A disabled item is not rendered, and its answers stay
 * in the reducer: re-enabling it brings back what was typed. `buildQuestionnaireResponse`
 * writes none of them, which is what makes the hidden state safe.
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
                        </CardHeader>
                        <CardContent className="grid gap-4">
                            {section.linkIds.map((linkId) => (
                                <QuestionnaireItemView
                                    key={linkId}
                                    spec={spec}
                                    linkId={linkId}
                                    answers={answers}
                                    enabled={enabled}
                                    dispatch={dispatch}
                                />
                            ))}
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

/** The DHIS2 uid a question carries, which is the string every other surface names it by. */
function CodeBadge({ code, className }: { code: string; className?: string }) {
    return (
        <Badge variant="outline" className={cn('text-muted-foreground font-mono text-[10px]', className)}>
            {code}
        </Badge>
    )
}

/** Whatever the form says about this question beyond its label: bounds, repetition, read-only. */
function QuestionHint({ node }: { node: QuestionnaireNode }) {
    const notes: string[] = []
    if (node.minimum !== null && node.maximum !== null) notes.push(`between ${node.minimum} and ${node.maximum}`)
    else if (node.minimum !== null) notes.push(`${node.minimum} or more`)
    else if (node.maximum !== null) notes.push(`${node.maximum} or less`)
    if (node.repeats) notes.push('takes more than one answer')
    if (node.readOnly) notes.push('read only')
    if (notes.length === 0) return null
    return <p className="text-muted-foreground text-xs">{notes.join(', ')}</p>
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
 */
function rootSections(spec: QuestionnaireSpec, enabled: ReadonlySet<string>): RootSection[] {
    const sections: RootSection[] = []
    let loose: string[] = []
    const flushLoose = () => {
        if (loose.length === 0) return
        sections.push({ key: `loose-${loose[0]}`, groupLinkId: null, linkIds: loose })
        loose = []
    }
    for (const linkId of spec.rootLinkIds) {
        if (!enabled.has(linkId)) continue
        if (spec.byLinkId.get(linkId)?.type === 'group') {
            flushLoose()
            sections.push({ key: linkId, groupLinkId: linkId, linkIds: spec.byLinkId.get(linkId)?.childLinkIds ?? [] })
            continue
        }
        loose.push(linkId)
    }
    flushLoose()
    return sections
}
