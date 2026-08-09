import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Eraser, Send, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { PageState } from '@/components/PageState'
import { QuestionnaireForm } from '@/components/QuestionnaireItem'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FhirRequestError, generateResponse, postQuestionnaireResponse, readResource } from '@/lib/api'
import {
    FORM_TYPE_LABELS,
    formTypeOf,
    generateSeedOf,
    questionCount,
    type OperationOutcomeIssue,
    type Questionnaire,
    type QuestionnaireResponse, unescapeMarkup } from '@/lib/fhir'
import {
    answersFromResponse,
    answersReducer,
    buildQuestionnaireResponse,
    flattenQuestionnaire,
    initialAnswers,
    unansweredRequiredLinkIds,
    type AnswerState,
} from '@/lib/questionnaire'

/**
 * One form, filled in and posted back.
 *
 * THE ENVELOPE IS THE SERVER'S, THE ANSWERS ARE THE USER'S. A capture-valid
 * QuestionnaireResponse carries context this screen has no business deriving - the D2Period an
 * aggregate submission reports for, the Location it reports from, the tracked entity and
 * enrollment a tracker event hangs off. All of it comes from one
 * `GET /Questionnaire/{id}/$generate` read when the page opens: the skeleton's envelope is
 * kept, its answers are thrown away, and the user's answers go in their place. That call is
 * pinned postable by the Python suite, so what leaves this page is valid context by
 * construction. If `$generate` fails the form still opens and still submits - and the server's
 * refusal naming exactly which context is missing is a better answer than a disabled button.
 *
 * FILL WITH TEST DATA EDITS, IT DOES NOT POST. The button reads a fresh `$generate` and pours
 * its answers into the reducer, so what appears is a filled-in form a person can change one
 * field of before submitting. The seed is shown, because the same seed reproduces the same
 * answers and that is what makes a reported bug repeatable.
 *
 * REFUSALS ARE RENDERED WHERE THEY WERE CAUSED. The capture validator refuses in phases and
 * names the item each issue is about (`QuestionnaireResponse.item.where(linkId='...')`), so its
 * OperationOutcome is shown issue by issue above the action bar rather than flattened into a
 * toast that loses everything after the first line.
 */
export function FormFill() {
    const { questionnaireId = '' } = useParams()
    const navigate = useNavigate()

    const [questionnaire, setQuestionnaire] = useState<Questionnaire | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [envelope, setEnvelope] = useState<QuestionnaireResponse | null>(null)
    const [answers, dispatch] = useReducer(answersReducer, {} as AnswerState)
    const [issues, setIssues] = useState<OperationOutcomeIssue[]>([])
    const [busy, setBusy] = useState(false)
    const [filling, setFilling] = useState(false)

    const spec = useMemo(
        () => flattenQuestionnaire(questionnaire ?? { resourceType: 'Questionnaire', status: 'unknown' }),
        [questionnaire],
    )

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        setQuestionnaire(null)
        setEnvelope(null)
        setIssues([])
        readResource<Questionnaire>('Questionnaire', questionnaireId)
            .then((resource) => {
                if (cancelled) return
                setQuestionnaire(resource)
                dispatch({ kind: 'replace', answers: initialAnswers(flattenQuestionnaire(resource)) })
                setLoading(false)
                // The skeleton is read after the form is on screen rather than blocking it:
                // reading a form and being able to submit one are different capabilities, and a
                // slow or refused `$generate` should not keep the questions off the page.
                return generateResponse(questionnaireId).then((skeleton) => {
                    if (!cancelled) setEnvelope(skeleton)
                })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                // A refused `$generate` leaves the form usable, so it is only fatal before the
                // Questionnaire itself has been read.
                setLoading(false)
                setError((current) =>
                    current ?? (failure instanceof Error ? failure.message : String(failure)),
                )
            })
        return () => {
            cancelled = true
        }
    }, [questionnaireId])

    const fillWithTestData = useCallback(() => {
        // The button only exists once the form is on screen, so a null questionnaire here
        // would be a routing bug rather than a state a person can reach.
        if (filling || questionnaire === null) return
        setFilling(true)
        generateResponse(questionnaireId)
            .then((generated) => {
                setEnvelope(generated)
                dispatch({
                    kind: 'replace',
                    answers: answersFromResponse(flattenQuestionnaire(questionnaire), generated),
                })
                setIssues([])
                const seed = generateSeedOf(generated)
                toast.success(
                    seed === null ? 'Filled with generated answers' : `Filled with generated answers, seed ${seed}`,
                    { description: 'Change anything you like before submitting.' },
                )
            })
            .catch((failure: unknown) => {
                toast.error('The server would not generate answers to this form', {
                    description: failure instanceof Error ? failure.message : String(failure),
                })
            })
            .finally(() => setFilling(false))
    }, [filling, questionnaire, questionnaireId])

    if (questionnaire === null) {
        return (
            <>
                <FormFillHeader questionnaire={null} questionnaireId={questionnaireId} />
                <PageState
                    loading={loading}
                    error={error}
                    empty={!loading && error === null}
                    emptyMessage="This server holds no form under that id. It may have been published under a different one - the form list names every id it serves."
                >
                    {null}
                </PageState>
            </>
        )
    }

    const missingRequired = unansweredRequiredLinkIds(spec, answers)

    const submit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        if (busy) return
        setBusy(true)
        setIssues([])
        try {
            const receipt = await postQuestionnaireResponse(
                buildQuestionnaireResponse(spec, answers, questionnaire, envelope),
            )
            toast.success('The server accepted this submission', {
                description: `Stored as ${receipt.id ?? 'a new receipt'}.`,
            })
            navigate('/responses')
        } catch (failure: unknown) {
            if (failure instanceof FhirRequestError && failure.outcome !== null) {
                setIssues(failure.outcome.issue)
                toast.error(`The server refused this submission (${failure.outcome.issue.length} issues)`)
            } else {
                toast.error('This submission could not be sent', {
                    description: failure instanceof Error ? failure.message : String(failure),
                })
            }
        } finally {
            setBusy(false)
        }
    }

    return (
        <form onSubmit={submit}>
            <FormFillHeader questionnaire={questionnaire} questionnaireId={questionnaireId} />

            {envelope === null && (
                <Alert className="mb-4">
                    <AlertTitle>No submission context yet</AlertTitle>
                    <AlertDescription>
                        This form's context - the period, the organisation unit, the tracked entity - comes from
                        the server's <code className="font-mono">$generate</code> operation, which has not answered
                        here. The answers below can still be sent, and the server will name whatever it needs.
                    </AlertDescription>
                </Alert>
            )}

            <QuestionnaireForm spec={spec} answers={answers} dispatch={dispatch} />

            {issues.length > 0 && (
                <div className="mt-4 grid gap-2">
                    {issues.map((issue, index) => (
                        // An OperationOutcome issue carries no id, and one submission can be
                        // refused twice on the same code and expression, so position is the only
                        // thing that tells two issues apart. The list is replaced wholesale on
                        // every submit and never reordered in place.
                        // oxlint-disable-next-line react/no-array-index-key
                        <CaptureIssueAlert key={`${index}-${issue.code}`} issue={issue} />
                    ))}
                </div>
            )}

            {/* Sticky rather than fixed: it belongs to the form, so it scrolls with it on a
                short one and pins itself over a long one. */}
            <div className="bg-sidebar sticky bottom-0 z-10 mt-6 -mx-4 flex flex-wrap items-center gap-2 border-t px-4 py-3 md:-mx-8 md:px-8">
                <Button type="submit" disabled={busy}>
                    <Send className="size-4" />
                    {busy ? 'Submitting' : 'Submit'}
                </Button>
                <Button type="button" variant="outline" disabled={filling} onClick={fillWithTestData}>
                    <Sparkles className="size-4" />
                    {filling ? 'Generating' : 'Fill with test data'}
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                        dispatch({ kind: 'replace', answers: initialAnswers(spec) })
                        setIssues([])
                    }}
                >
                    <Eraser className="size-4" />
                    Clear
                </Button>
                <div className="flex-1" />
                {missingRequired.length > 0 && (
                    <p className="text-muted-foreground text-xs">
                        {missingRequired.length} required{' '}
                        {missingRequired.length === 1 ? 'question is' : 'questions are'} unanswered
                    </p>
                )}
            </div>
        </form>
    )
}

/**
 * One thing the capture validator said, as it said it.
 *
 * Severity, code, and the FHIRPath expression naming the item are all shown: the validator
 * refuses in phases and its expressions point at exactly one question
 * (`QuestionnaireResponse.item.where(linkId='GQY2lXrypjO')`), which is the difference between
 * "the submission was refused" and "this question carries the wrong kind of value".
 */
function CaptureIssueAlert({ issue }: { issue: OperationOutcomeIssue }) {
    const fatal = issue.severity === 'error' || issue.severity === 'fatal'
    return (
        <Alert variant={fatal ? 'destructive' : 'default'}>
            <AlertTitle className="flex flex-wrap items-center gap-2">
                <Badge variant={fatal ? 'outline' : 'secondary'}>{issue.severity}</Badge>
                <span className="font-mono text-xs">{issue.code}</span>
                {issue.expression?.[0] !== undefined && (
                    <span className="text-muted-foreground font-mono text-xs">{issue.expression[0]}</span>
                )}
            </AlertTitle>
            <AlertDescription>{issue.diagnostics ?? issue.details?.text ?? ''}</AlertDescription>
        </Alert>
    )
}

/** The form's identity: what it is, which DHIS2 object it came from, and how much it asks. */
function FormFillHeader({
    questionnaire,
    questionnaireId,
}: {
    questionnaire: Questionnaire | null
    questionnaireId: string
}) {
    const kind = questionnaire === null ? null : formTypeOf(questionnaire)
    return (
        <div className="mb-6 space-y-2">
            <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                <Link to="/">
                    <ArrowLeft className="size-4" />
                    All forms
                </Link>
            </Button>
            <h2 className="text-xl font-semibold tracking-tight">
                {unescapeMarkup(questionnaire?.title ?? questionnaire?.name ?? questionnaireId)}
            </h2>
            <div className="flex flex-wrap items-center gap-2">
                {kind !== null && <Badge variant="secondary">{FORM_TYPE_LABELS[kind]}</Badge>}
                {kind === null && questionnaire !== null && (
                    <Badge variant="outline" className="text-muted-foreground">
                        no form type
                    </Badge>
                )}
                <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
                    {questionnaire?.id ?? questionnaireId}
                </Badge>
                {questionnaire !== null && (
                    <span className="text-muted-foreground text-sm">
                        {questionCount(questionnaire.item)} questions
                    </span>
                )}
            </div>
            {questionnaire?.description !== undefined && (
                <p className="text-muted-foreground text-sm">{questionnaire.description}</p>
            )}
        </div>
    )
}
