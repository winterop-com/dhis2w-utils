import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Eraser, Send, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { AttributeOptionComboPicker } from '@/components/AttributeOptionComboPicker'
import { EnrollmentPicker, type EnrollmentSource } from '@/components/EnrollmentPicker'
import { OrgUnitScopeProvider } from '@/components/OrgUnitPicker'
import { PageState } from '@/components/PageState'
import {
    LockedQuestionsProvider,
    NO_LOCKED_QUESTIONS,
    QuestionnaireForm,
    type LockedQuestions,
} from '@/components/QuestionnaireItem'
import { EXISTING_PERSON_QUESTION_NOTE, PersonPicker, type PersonSource } from '@/components/PersonPicker'
import { ReportingUnitPicker } from '@/components/ReportingUnitPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useEnrollmentOptions } from '@/hooks/use-enrollment-options'
import { useFormOrgUnitScope } from '@/hooks/use-org-unit-scope'
import { useRegisterSearchSupport } from '@/hooks/use-register-search-support'
import { useUiConfig } from '@/hooks/use-ui-config'
import { CAPTURE_OFF_NOTICE, capturesSubmissions, PEOPLE_RESOURCE_TYPE } from '@/lib/uiconfig'
import { FhirRequestError, generateResponse, postQuestionnaireResponse, readResource } from '@/lib/api'
import { reloadedEnrollment, type EnrollmentOption } from '@/lib/enrollments'
import {
    attributeOptionCombosOf,
    enrolledAtOf,
    FORM_TYPE_LABELS,
    formTypeOf,
    generateSeedOf,
    incidentAtOf,
    programOf,
    questionCount,
    registersAPerson,
    trackerEnrollmentOf,
    type CodeSystem,
    type Coding,
    type OperationOutcomeIssue,
    type Questionnaire,
    type QuestionnaireResponse,
    type Reference } from '@/lib/fhir'
import { orgUnitReference, referencedUnitId } from '@/lib/orgunits'
import type { PatientProjection } from '@/lib/patients'
import {
    answersFromResponse,
    answersReducer,
    boundBreaches,
    buildQuestionnaireResponse,
    clearedEntityLevelAnswers,
    clearedHiddenAnswers,
    collectsIncidentDate,
    dateLabelsOf,
    dateTimeInputValue,
    dictionaryOfCodeSystems,
    entityLevelLinkIds,
    flattenQuestionnaire,
    initialAnswers,
    isWellShapedPeriod,
    normaliseDateTime,
    NO_DICTIONARY,
    openedReportingUnit,
    periodShape,
    programRulesOf,
    questionCodeSystemIds,
    refilledAttributeOptionCombo,
    refilledEnrollment,
    refilledReportingUnit,
    repeatsPerEnrollment,
    reportingPeriodOf,
    reportingPeriodTypeOf,
    unansweredRequiredLinkIds,
    type AnswerState,
    type DateLabels,
    type ExistingSubject,
    type ProgramRule,
    type QuestionDictionary,
} from '@/lib/questionnaire'
import { TRACKER_ENROLLMENT_FACT_LABEL } from '@/lib/spool'
import { cn } from '@/lib/utils'

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
 *
 * TWO PIECES OF CONTEXT ARE THE USER'S, AND THEY ARE WHY SUBMIT IS EVER DISABLED. A data set on a
 * non-default category combo declares its attribute option combos as a vocabulary, and a response to
 * it has to name one - it is the third key of every value it carries, beside the organisation unit
 * and the period. Nothing derives it, not even the server, so it is picked above the form, the
 * control opens unanswered however the draft was drawn, and Submit refuses until somebody chooses.
 * The period is the same fact one key over: an aggregate submission is filed for a period of the type
 * its data set declares, so an empty box and a mis-shaped identifier are both refused here. That is
 * the one place a stated-reason disabled control beats posting and rendering the refusal: the answer
 * is a fact about the submission the person came here with, not something they could read off the
 * form and correct.
 *
 * WHY THE COMBO IS NOT PRE-SELECTED FROM THE DRAW. `$generate` picks one so its skeleton is postable,
 * and adopting that pick would make the common case one click - but it would also make every
 * submission nobody looked at claim to be filed under whichever combo the draw landed on. DHIS2's own
 * capture app refuses to render the form at all until the combo is chosen; the same refusal in this
 * app's idiom is a control that is empty, required, and says which submissions it keys. The draw is
 * still adopted by "fill with test data", because that is the server proposing a whole submission
 * rather than a form waiting to be filled in.
 *
 * The organisation unit sits beside it and behaves differently on exactly one point. `$generate`
 * draws a unit the form's assignment admits, so the picker arrives answered and Submit is never
 * blocked on it - but which unit is a choice rather than a fact about the form, so the draw is a
 * proposal and changing it rewrites the built response. Both pickers are fed by one read of the
 * registry, published to the form through `OrgUnitScopeProvider` so the `ORGANISATION_UNIT`
 * questions inside it pick from the same set. That choice is kept for the browser tab, because a
 * person filing six forms reports them all from the same place: the next form opens on the kept
 * unit whenever its own assignment admits it, and says so either way.
 *
 * A THIRD PIECE OF CONTEXT IS THE USER'S ON A STAGE FORM, AND IT IS THE ONE THE SKELETON GETS
 * WRONG. `$generate` mints synthetic tracked-entity and enrollment uids, which is what makes the
 * skeleton postable *here* - but they name nothing in any DHIS2, so an unassisted stage
 * submission is refused at forward time. The real enrollments are the ones this server's own
 * registration receipts minted, so a stage form gets a picker over exactly those, each option
 * stating whether DHIS2 has it yet, and the choice is written over the envelope the same
 * replace-in-place way the combo and the unit are. The default is the newest forwarded
 * registration's pair - a submission that lands - and with nothing to offer the synthetic draw
 * stands, said out loud rather than discovered in a rejection.
 *
 * A FOURTH IS WHO A REGISTRATION IS ABOUT, AND IT IS THE ONLY ONE THAT REACHES THE DHIS2 INSTANCE.
 * A registration form mints a new person by default, which is the whole of what this screen could
 * do while the facade answered only from what a project published. A live facade also answers
 * `GET /{resourceType}?identifier=`, so the person can be found instead - and a registration answering for
 * someone the instance already holds is a different submission: its subject is a real
 * tracked-entity uid, it carries the `D2SubjectExists` marker, and it writes no entity-level
 * answer at all, because the instance holds those values and `d2w fhir forward` refuses a
 * submission that states its subject exists and carries one anyway. So those questions go
 * read-only and cleared with the reason stated, which is the only place in this app where the
 * capture context takes questions off the form.
 *
 * A FIFTH IS THE DATE THE SUBMISSION IS ABOUT, AND IT WEARS A DIFFERENT ELEMENT ON EVERY KIND.
 * An event happened on a day and the forwarder reads `TrackerEvent.occurredAt` off `authored`; a
 * registration files an enrollment that begins on a day, on `D2EnrolledAt`, with `D2IncidentAt`
 * beside it on a program that collects one; an aggregate submission reports for one DHIS2 period,
 * on `D2Period`. The server draws all of them so the draft is postable, and a capture of last
 * Tuesday's visit is a capture of last Tuesday - so each is a control above the questions, opening
 * on the drafted value and riding the envelope in the slot the draft put it in.
 *
 * THE PERIOD IS THE ONE THIS SCREEN CHECKS THE SHAPE OF AND NOTHING MORE. The form declares the DHIS2
 * period type its data set reports for, so the control asks for a period of that type from the moment
 * the form is on screen - placeholder, example, and a refusal to submit something that is not shaped
 * like one. Resolving `202607` into July 2026 is DHIS2 period arithmetic, which this UI does not have
 * and will not grow: the server grades the identifier against the type and against the range it
 * resolves to, so an edited period is written as the identifier alone, with the drafted type kept and
 * the drafted range dropped rather than recomputed. The range is optional and the ISO period is what
 * is captured, so what leaves here is a claim about exactly what a person typed; a period of the
 * wrong type is refused by the server, naming both types, which is better than a client guess.
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
    const [attributeOptionCombo, setAttributeOptionCombo] = useState<Coding | null>(null)
    const [reportingUnit, setReportingUnit] = useState<Reference | null>(null)
    const [keptUnitNotAdmitted, setKeptUnitNotAdmitted] = useState(false)
    const [enrollment, setEnrollment] = useState<EnrollmentOption | null>(null)
    const [enrollmentSource, setEnrollmentSource] = useState<EnrollmentSource>('spool')
    const [personSource, setPersonSource] = useState<PersonSource>('new')
    const [existingPerson, setExistingPerson] = useState<PatientProjection | null>(null)
    // The four dates and periods a person may state for themselves. Null is "the draft's value
    // stands", which is what every form opens on; a string is the literal its control holds.
    const [visitDate, setVisitDate] = useState<string | null>(null)
    const [enrollmentDate, setEnrollmentDate] = useState<string | null>(null)
    const [incidentDate, setIncidentDate] = useState<string | null>(null)
    const [reportingPeriodIso, setReportingPeriodIso] = useState<string | null>(null)
    const [dictionary, setDictionary] = useState<QuestionDictionary>(NO_DICTIONARY)
    // Whether this server takes what is filled in here. A form on a server that receives nothing is
    // still worth opening and reading, so the page is the page it always was and only the Submit goes.
    const receivesSubmissions = capturesSubmissions(useUiConfig().config)
    const orgUnitScope = useFormOrgUnitScope(questionnaire)
    const enrollmentOffer = useEnrollmentOptions(questionnaire)
    // The register this form's subject lives in - the form's own subjectType, with the guide's
    // unnamed-type default. The search gate and the search itself both read it, so a deployment
    // whose registrations land in Specimen or Device asks about that register rather than Patient.
    const registerResource = questionnaire?.subjectType?.[0] ?? PEOPLE_RESOURCE_TYPE
    const registerSearchSupport = useRegisterSearchSupport(registerResource)

    // Applied whenever the offer lands or reloads: a person's choice is re-read so its lifecycle
    // badge catches up with a forwarder run, and before anyone chose, the default rule picks the
    // newest forwarded registration - the one pair a submission is known to land against. It runs
    // for the spool source alone: the default rule is about receipts, and applying it while the
    // instance source is open would answer a submission with a pair nobody picked.
    const { loading: offerLoading, options: offerOptions } = enrollmentOffer
    useEffect(() => {
        if (offerLoading || enrollmentSource !== 'spool') return
        setEnrollment((current) => reloadedEnrollment(current, offerOptions))
    }, [offerLoading, offerOptions, enrollmentSource])

    const spec = useMemo(
        () => flattenQuestionnaire(questionnaire ?? { resourceType: 'Questionnaire', status: 'unknown' }, dictionary),
        [questionnaire, dictionary],
    )

    // The data dictionaries this form's own questions are coded in, and nothing else. Four facts
    // live there and nowhere else: R4 spells `BOOLEAN` and `TRUE_ONLY` as one item type, so the value
    // type behind a tick is the dictionary's to state; a generated attribute's minting and the shape
    // it is minted to are the dictionary's; and a disaggregated cell's categories are published by
    // the combo vocabulary the cells are coded in. Reading the two or three systems the form names is
    // what keeps that from becoming a read of the whole terminology. The list is joined into one
    // string so the read runs when the form changes rather than every time the spec is rebuilt.
    const codeSystemKey = useMemo(() => questionCodeSystemIds(spec).join(' '), [spec])
    useEffect(() => {
        const ids = codeSystemKey === '' ? [] : codeSystemKey.split(' ')
        if (ids.length === 0) {
            setDictionary(NO_DICTIONARY)
            return
        }
        let cancelled = false
        // A dictionary this server does not publish is a form whose value types are unknown, which
        // is the state every boolean question renders as a plain BOOLEAN in - so a refused read is
        // caught per system rather than losing the systems that did answer.
        Promise.all(
            ids.map((id) => readResource<CodeSystem>('CodeSystem', id).catch(() => null)),
        ).then((read) => {
            if (cancelled) return
            setDictionary(dictionaryOfCodeSystems(read.filter((codeSystem) => codeSystem !== null)))
        })
        return () => {
            cancelled = true
        }
    }, [codeSystemKey])

    const existingSubject: ExistingSubject | null =
        existingPerson === null ? null : { trackedEntity: existingPerson.trackedEntityUid }
    const lockedQuestions: LockedQuestions =
        existingSubject === null
            ? NO_LOCKED_QUESTIONS
            : { linkIds: entityLevelLinkIds(spec), note: EXISTING_PERSON_QUESTION_NOTE }

    // The one rule that has to hold however the answers got there - typed, poured in by a refill,
    // or declared as an item's `initial`: a submission about a person this instance already holds
    // carries no entity-level answer. Clearing here rather than at each of those three places is
    // what keeps the screen and the wire agreeing with one rule instead of three.
    useEffect(() => {
        if (existingPerson === null) return
        const cleared = clearedEntityLevelAnswers(spec, answers)
        if (cleared !== answers) dispatch({ kind: 'replace', answers: cleared })
    }, [existingPerson, spec, answers])

    // The same shape of rule one condition over, and for a sharper reason: an answer to a question
    // the form has stopped asking describes nothing, and forwarded it becomes a real DHIS2 data
    // value about a real person. It runs on every answer change rather than at Submit, so what is
    // on screen and what would be sent never disagree - and it cascades, because clearing one
    // answer can close the question the next condition depended on.
    useEffect(() => {
        const cleared = clearedHiddenAnswers(spec, answers)
        if (cleared !== answers) dispatch({ kind: 'replace', answers: cleared })
    }, [spec, answers])

    // Every stated date and period back to "the draft's value stands". Run wherever a fresh draft
    // lands, because a redrawn envelope is a fresh set of defaults for these controls to open on.
    const clearStatedDates = useCallback(() => {
        setVisitDate(null)
        setEnrollmentDate(null)
        setIncidentDate(null)
        setReportingPeriodIso(null)
    }, [])

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        setQuestionnaire(null)
        setEnvelope(null)
        setIssues([])
        setAttributeOptionCombo(null)
        setReportingUnit(null)
        setKeptUnitNotAdmitted(false)
        setEnrollment(null)
        setEnrollmentSource('spool')
        setPersonSource('new')
        setExistingPerson(null)
        clearStatedDates()
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
                    if (cancelled) return
                    setEnvelope(skeleton)
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
    }, [questionnaireId, clearStatedDates])

    // Which organisation unit the form opens reporting from, decided once the draft and the offer
    // are both in hand. Both halves are needed: the draft carries the drawn unit, and the offer is
    // what says whether the unit this browser tab keeps is one this form may be reported from at
    // all. A unit already in the picker ends this - a person's choice is never overwritten.
    useEffect(() => {
        if (reportingUnit !== null || envelope === null || questionnaire === null) return
        if (orgUnitScope.loading || orgUnitScope.byId.size === 0) return
        const opened = openedReportingUnit(null, envelope, questionnaire, keptReportingUnitId(), orgUnitScope.byId)
        setReportingUnit(opened.unit)
        setKeptUnitNotAdmitted(opened.keptUnitNotAdmitted)
    }, [reportingUnit, envelope, questionnaire, orgUnitScope])

    const fillWithTestData = useCallback(() => {
        // The button only exists once the form is on screen, so a null questionnaire here
        // would be a routing bug rather than a state a person can reach.
        if (filling || questionnaire === null) return
        setFilling(true)
        generateResponse(questionnaireId)
            .then((generated) => {
                setEnvelope(generated)
                setAttributeOptionCombo((current) => refilledAttributeOptionCombo(current, generated))
                setReportingUnit((current) => refilledReportingUnit(current, generated, questionnaire))
                // The one refill rule that runs the other way: the fresh draw's pair is synthetic,
                // so the answers refill and the chosen identity stands.
                setEnrollment((current) => refilledEnrollment(current))
                // A refill is the server proposing a whole submission, dates included, so the
                // controls over them open on the fresh draft rather than holding the last draft's.
                clearStatedDates()
                dispatch({
                    kind: 'replace',
                    answers: answersFromResponse(flattenQuestionnaire(questionnaire), generated),
                })
                setIssues([])
                const seed = generateSeedOf(generated)
                toast.success(
                    seed === null ? 'Filled with test data' : `Filled with test data, seed ${seed}`,
                    { description: 'Change anything you like before submitting.' },
                )
            })
            .catch((failure: unknown) => {
                toast.error('The server could not fill this form with test data', {
                    description: failure instanceof Error ? failure.message : String(failure),
                })
            })
            .finally(() => setFilling(false))
    }, [filling, questionnaire, questionnaireId, clearStatedDates])

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

    const missingRequired = unansweredRequiredLinkIds(spec, answers, lockedQuestions.linkIds)
    const attributeOptionCombos = attributeOptionCombosOf(questionnaire)
    const formKind = formTypeOf(questionnaire)
    // The two kinds whose submission is about a person, and therefore the two the Person control
    // belongs on. A stage form is about a person too, but the person is already named by the
    // enrollment it answers for, which is the control it gets instead.
    const registersAPersonHere = registersAPerson(formKind)
    // Read off the envelope rather than off the form kind: a registration response is the only one
    // that carries an enrollment date, so the presence of the fact is what decides the block is
    // shown, and a `$generate` that never answered simply has nothing to state.
    const enrolledAt = envelope === null ? null : enrolledAtOf(envelope)
    const incidentAt = envelope === null ? null : incidentAtOf(envelope)
    // Both halves are required, and each says something the other does not: the form declares
    // whether its program collects an incident date, and the draft is where an edited one is
    // written. A control over a date the draft never drew would have no slot to ride in.
    const asksIncidentDate = collectsIncidentDate(questionnaire) && incidentAt !== null
    // The visit date of an event: the same read off the envelope the enrollment dates get, on the
    // one element the forwarder derives `TrackerEvent.occurredAt` from.
    const recordsAnEvent = formKind === 'event' || formKind === 'tracker-event'
    const draftedVisitDate = (recordsAnEvent ? envelope?.authored : undefined) ?? null
    // What the form says about its dates, which is what its controls are labelled with: a DHIS2
    // programme renames the dates it collects, and a screen using its own words for them would be
    // asking a different question from the one the clerk was trained on.
    const dateLabels = dateLabelsOf(questionnaire)
    // Whether one enrollment may answer this stage more than once, as the form declares it. Null is
    // a form that says nothing, and nothing is stated for one.
    const repeatsPerEnrollmentHere = repeatsPerEnrollment(questionnaire)
    // The period an aggregate submission reports for. The form declares the type its data set
    // reports for, so the control knows what to ask for before any draft lands - and the draft
    // proposes an identifier of that type. Either one is enough for the control to exist.
    const draftedPeriod = reportingPeriodOf(envelope)
    const declaredPeriodType = reportingPeriodTypeOf(questionnaire)
    const reportsForAPeriod = formKind === 'aggregate' && (declaredPeriodType !== null || draftedPeriod !== null)
    const periodType = declaredPeriodType ?? draftedPeriod?.periodType ?? null
    const reportingPeriod = reportingPeriodIso ?? draftedPeriod?.iso ?? ''
    // Declared and unchosen is the one state Submit refuses in. A form that declares no vocabulary
    // reports for the default combo, which is what absence means, and nothing is asked.
    const missingAttributeOptionCombo = attributeOptionCombos !== null && attributeOptionCombo === null
    // The other. An aggregate submission is keyed by its period, and neither an empty box nor an
    // identifier of the wrong shape is one - so both are refused here rather than at the server.
    const unfitReportingPeriod = reportsForAPeriod && !isWellShapedPeriod(reportingPeriod, periodType)
    // The third, and the one that is about an answer rather than about the submission. A value the
    // form itself publishes as outside what it accepts is a mistake the person who typed it can fix
    // under the cursor, and a round trip spent being told what the form already says is a round trip
    // wasted. The fact is stated per question; nothing here instructs anyone what to type instead.
    const breaches = boundBreaches(spec, answers)

    const submit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        if (!receivesSubmissions) return
        if (busy || missingAttributeOptionCombo || unfitReportingPeriod || breaches.length > 0) return
        setBusy(true)
        setIssues([])
        try {
            const receipt = await postQuestionnaireResponse(
                buildQuestionnaireResponse(spec, answers, questionnaire, envelope, {
                    attributeOptionCombo,
                    reportingUnit,
                    enrollment,
                    // An untouched control states nothing and the draft's own value rides, which is
                    // also what an emptied one means: a submission of any of these kinds carries a
                    // date whether or not a person restated it.
                    authored: normaliseDateTime(visitDate ?? ''),
                    enrolledAt: normaliseDateTime(enrollmentDate ?? ''),
                    incidentAt: normaliseDateTime(incidentDate ?? ''),
                    reportingPeriodIso,
                    existingSubject,
                }),
            )
            toast.success('The server accepted this submission', {
                description: `Stored as ${receipt.id ?? 'a new receipt'}.`,
            })
            navigate('/responses')
        } catch (failure: unknown) {
            if (failure instanceof FhirRequestError && failure.outcome !== null) {
                setIssues(failure.outcome.issue)
                toast.error(
                    `The server refused this submission (${failure.outcome.issue.length} ${
                        failure.outcome.issue.length === 1 ? 'issue' : 'issues'
                    })`,
                )
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
            <FormFillHeader
                questionnaire={questionnaire}
                questionnaireId={questionnaireId}
                stageRepeats={repeatsPerEnrollmentHere}
            />

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

            <OrgUnitScopeProvider scope={orgUnitScope}>
                {/* Side by side on a wide screen, because they are two facts about one submission
                    and reading them together is how a person checks they are filing the right
                    thing. Stacked below that, in the order DHIS2 keys a value by. */}
                <div
                    className={cn(
                        'mb-4 grid gap-4',
                        (attributeOptionCombos !== null ||
                            enrolledAt !== null ||
                            enrollmentOffer.active ||
                            registersAPersonHere ||
                            draftedVisitDate !== null ||
                            reportsForAPeriod) &&
                            'lg:grid-cols-2',
                    )}
                >
                    <ReportingUnitPicker
                        formKind={formKind}
                        declaresAttributeOptionCombo={attributeOptionCombos !== null}
                        selectedUnitId={referencedUnitId(reportingUnit)}
                        keptUnitNotAdmitted={keptUnitNotAdmitted}
                        onChange={(choice) => {
                            setReportingUnit(orgUnitReference(choice))
                            // Kept from here on, so the next form this tab opens reports from it -
                            // and the mismatch this form may have stated is answered by the choice.
                            keepReportingUnitId(choice.id)
                            setKeptUnitNotAdmitted(false)
                        }}
                    />
                    {reportsForAPeriod && (
                        <ReportingPeriodControl
                            periodType={periodType}
                            iso={reportingPeriod}
                            unfit={unfitReportingPeriod}
                            onChange={setReportingPeriodIso}
                        />
                    )}
                    {draftedVisitDate !== null && (
                        <div className="grid gap-2 rounded-lg border p-4">
                            <InstantField
                                controlId={VISIT_DATE_CONTROL_ID}
                                label={dateLabels.eventDate}
                                hint="The date this event happened. It is context, not an answer - DHIS2 records the event under it."
                                value={visitDate ?? dateTimeInputValue(draftedVisitDate)}
                                onChange={setVisitDate}
                            />
                        </div>
                    )}
                    {attributeOptionCombos !== null && (
                        <AttributeOptionComboPicker
                            canonical={attributeOptionCombos}
                            selected={attributeOptionCombo}
                            onChange={setAttributeOptionCombo}
                        />
                    )}
                    {registersAPersonHere && (
                        <PersonPicker
                            support={registerSearchSupport}
                            source={personSource}
                            resource={registerResource}
                            chosen={existingPerson}
                            onChange={(source, patient) => {
                                setPersonSource(source)
                                setExistingPerson(patient)
                            }}
                        />
                    )}
                    {enrollmentOffer.active && (
                        <EnrollmentPicker
                            offer={enrollmentOffer}
                            selected={enrollment}
                            source={enrollmentSource}
                            support={registerSearchSupport}
                            resource={registerResource}
                            programUid={programOf(questionnaire)}
                            onChange={(source, option) => {
                                setEnrollmentSource(source)
                                setEnrollment(option)
                            }}
                        />
                    )}
                    {enrolledAt !== null && envelope !== null && (
                        <EnrollmentContext
                            labels={dateLabels}
                            enrollmentDate={enrollmentDate ?? dateTimeInputValue(enrolledAt)}
                            incidentDate={
                                asksIncidentDate && incidentAt !== null
                                    ? (incidentDate ?? dateTimeInputValue(incidentAt))
                                    : null
                            }
                            enrollment={trackerEnrollmentOf(envelope)}
                            onEnrollmentDateChange={setEnrollmentDate}
                            onIncidentDateChange={setIncidentDate}
                        />
                    )}
                </div>

                <LockedQuestionsProvider locked={lockedQuestions}>
                    <QuestionnaireForm spec={spec} answers={answers} dispatch={dispatch} />
                </LockedQuestionsProvider>
            </OrgUnitScopeProvider>

            {breaches.length > 0 && (
                <div className="mt-4 grid gap-2">
                    {breaches.map((breach) => (
                        <Alert key={`${breach.linkId}-${String(breach.index)}`} variant="destructive">
                            <AlertTitle className="flex flex-wrap items-center gap-2">
                                <span>{breach.text}</span>
                                <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
                                    {breach.linkId}
                                </Badge>
                            </AlertTitle>
                            <AlertDescription>{breach.fact}</AlertDescription>
                        </Alert>
                    ))}
                </div>
            )}

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
                <Button
                    type="submit"
                    disabled={
                        !receivesSubmissions ||
                        busy ||
                        missingAttributeOptionCombo ||
                        unfitReportingPeriod ||
                        breaches.length > 0
                    }
                >
                    <Send className="size-4" />
                    {busy ? 'Submitting' : 'Submit'}
                </Button>
                <Button type="button" variant="outline" disabled={filling} onClick={fillWithTestData}>
                    <Sparkles className="size-4" />
                    {filling ? 'Filling' : 'Fill with test data'}
                </Button>
                {/* The one control here whose reach is not obvious from its name: it empties what
                    was filled in and deliberately leaves two pieces of context standing, so the
                    tooltip states both halves rather than letting a person discover the second. */}
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            type="button"
                            variant="ghost"
                            onClick={() => {
                                // Everything the person entered goes, the combo included: it is
                                // their input rather than the server's context, and it is the only
                                // control here a Radix select cannot be returned to unchosen any
                                // other way. The reporting unit stays, because clearing it would
                                // empty a control the form cannot be submitted well without and
                                // that nothing on this page would refill. The enrollment stays for
                                // the harder version of the same reason: clearing it would silently
                                // return the submission to a synthetic pair that cannot import.
                                dispatch({ kind: 'replace', answers: initialAnswers(spec) })
                                setAttributeOptionCombo(null)
                                setIssues([])
                            }}
                        >
                            <Eraser className="size-4" />
                            Clear
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                        Empties what you filled in. The organisation unit and the enrollment stay.
                    </TooltipContent>
                </Tooltip>
                <div className="flex-1" />
                {/* The reason a disabled button always states, because a control that refuses
                    without saying why is worse than one that posts and is refused. This one is
                    about the server rather than about the form, so it stands ahead of the rest. */}
                {!receivesSubmissions && <p className="text-muted-foreground text-xs">{CAPTURE_OFF_NOTICE}</p>}
                {missingAttributeOptionCombo && (
                    <p className="text-muted-foreground text-xs">
                        Choose what this submission reports for before submitting
                    </p>
                )}
                {unfitReportingPeriod && (
                    <p className="text-muted-foreground text-xs">
                        {reportingPeriod.trim() === ''
                            ? 'This submission reports for a period, and none is stated'
                            : `${reportingPeriod} is not a ${periodType ?? 'DHIS2'} period`}
                    </p>
                )}
                {breaches.length > 0 && (
                    <p className="text-muted-foreground text-xs">
                        {breaches.length === 1
                            ? '1 answer is outside what this form accepts'
                            : `${String(breaches.length)} answers are outside what this form accepts`}
                    </p>
                )}
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

/** The capture-context controls with a fixed id, so each label and its input find each other. */
const VISIT_DATE_CONTROL_ID = 'capture-visit-date'
const ENROLLMENT_DATE_CONTROL_ID = 'capture-enrollment-date'
const INCIDENT_DATE_CONTROL_ID = 'capture-incident-date'
const REPORTING_PERIOD_CONTROL_ID = 'capture-reporting-period'

/** Where a chosen reporting organisation unit is kept: one browser tab, and no longer. */
const KEPT_REPORTING_UNIT_KEY = 'dhis2w-capture-reporting-organisation-unit'

/**
 * The organisation unit this browser tab last reported from, or null when it has reported from none.
 *
 * SESSION-SCOPED ON PURPOSE. A kept unit is a fact about what someone is doing right now - a morning
 * spent filing for one facility - not a preference they set once. A fresh tab starts fresh, which is
 * also what makes two tabs open on two facilities a thing a person can do. A storage a browser
 * refuses to hand over (a private mode, a blocked origin) reads as nothing kept, which is exactly
 * the state the app was in before anything was chosen.
 */
function keptReportingUnitId(): string | null {
    try {
        return window.sessionStorage.getItem(KEPT_REPORTING_UNIT_KEY)
    } catch {
        return null
    }
}

/** Keep the organisation unit this tab reports from, so the next form opens on it. */
function keepReportingUnitId(unitId: string): void {
    try {
        window.sessionStorage.setItem(KEPT_REPORTING_UNIT_KEY, unitId)
    } catch {
        // A browser that refuses storage keeps nothing, and the next form opens on the server's
        // draw - the behaviour of this screen with nothing kept, rather than a failure to report.
    }
}

/**
 * One instant of the capture context, as a control over what the draft drew.
 *
 * WHAT AN EMPTY CONTROL MEANS. The value is the literal the browser's own `datetime-local` holds,
 * kept verbatim the way every answer control keeps its literal, and turned into an R4 `dateTime` at
 * submit by the same normaliser the form's own date questions use - which stamps the wall time as
 * stated rather than shifting it by whichever zone the operator's laptop is in. An emptied control
 * states nothing, and the submission carries the date the draft drew: every profile that has one of
 * these requires it, so "no date" is not a submission this server would take.
 */
function InstantField({
    controlId,
    label,
    hint,
    value,
    onChange,
}: {
    controlId: string
    label: string
    hint: string
    /** What the control shows: the stated literal, or the drafted instant it opens on. */
    value: string
    onChange: (value: string) => void
}) {
    return (
        <div className="grid gap-2">
            <Label htmlFor={controlId}>{label}</Label>
            <p className="text-muted-foreground text-sm">{hint}</p>
            <Input
                id={controlId}
                type="datetime-local"
                step={1}
                className="max-w-xs"
                value={value}
                onChange={(event) => onChange(event.target.value)}
            />
        </div>
    )
}

/**
 * The DHIS2 period an aggregate submission reports for.
 *
 * A TEXT BOX AND NOT A CALENDAR, because a DHIS2 period is an identifier rather than a date:
 * `202607` is July 2026, `2026W30` is a week, `2026April` is a financial year opening in April. The
 * type is the data set's own and is stated rather than asked - a monthly data set reports monthly -
 * so what a person edits is which period of that type, and the placeholder is the worked example of
 * how to spell one.
 *
 * REQUIRED, BECAUSE AN AGGREGATE SUBMISSION IS KEYED BY IT. The organisation unit, the period and the
 * attribute option combo are the three keys of every value a data set carries, and no period is not
 * one of them. Submit refuses an empty box for the same reason it refuses an unchosen combo: nothing
 * derives the answer, and posting a submission that cannot be keyed would be spending a round trip to
 * be told what the form already knows.
 *
 * THE SHAPE IS CHECKED HERE, THE PERIOD IS NOT. `isWellShapedPeriod` knows what a monthly identifier
 * looks like and refuses `july` under the cursor; it knows nothing about which months exist or what
 * range one resolves to, and the types whose identifiers carry an offset (`2026WedW30`, `2026April`)
 * are accepted as typed rather than half-checked. A period of the wrong type still reaches the
 * server, whose refusal names the type the identifier parses as and the type the data set reports
 * for - which is a better answer than a client guess at what the operator meant.
 */
function ReportingPeriodControl({
    periodType,
    iso,
    unfit,
    onChange,
}: {
    /** The DHIS2 period type the data set reports for, or null when nothing states one. */
    periodType: string | null
    iso: string
    /** True when what the box holds is not a period this submission could be keyed by. */
    unfit: boolean
    onChange: (iso: string) => void
}) {
    const shape = periodShape(periodType)
    return (
        <div className="grid gap-2 rounded-lg border p-4">
            <Label htmlFor={REPORTING_PERIOD_CONTROL_ID}>
                Reporting period
                <span className="text-destructive" aria-hidden>
                    *
                </span>
            </Label>
            <p className="text-muted-foreground text-sm">
                {periodType === null
                    ? 'The period this submission reports for. DHIS2 keys the whole submission by it, beside the organisation unit.'
                    : `${periodType} period, as the data set reports. DHIS2 keys the whole submission by it, beside the organisation unit.`}
            </p>
            <Input
                id={REPORTING_PERIOD_CONTROL_ID}
                className="max-w-xs font-mono"
                value={iso}
                required
                aria-invalid={unfit}
                placeholder={shape?.placeholder}
                onChange={(event) => onChange(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">
                {shape === null
                    ? 'A period of another type is refused when this submission is sent, and the refusal names both types.'
                    : `A ${periodType ?? ''} period is spelled like ${shape.example}. One of another type is refused when this submission is sent, and the refusal names both types.`}
            </p>
        </div>
    )
}

/**
 * When the enrollment a registration files begins, and when the incident it follows occurred.
 *
 * TWO DATES A PERSON CAME HERE WITH. A registration is filed days after the visit it records as
 * often as not, and DHIS2 files the enrollment under the date this states - so these are choices in
 * exactly the way the organisation unit is a choice, and the server's draw is the default rather
 * than the answer. The incident date is asked only on a program that collects one, which the form
 * declares on `D2CollectsIncidentDate`: a program that collects none generates responses that carry
 * none, and a control over an absent fact would have no slot to write into.
 *
 * THE ENROLLMENT UID IS THE ONE FACT HERE THAT IS STILL ONLY SHOWN. `$generate` mints it, DHIS2
 * creates the enrollment under it, and nothing about it is a choice - so it is stated in the words
 * the receipt uses, and reads identically before and after the capture.
 */
function EnrollmentContext({
    labels,
    enrollmentDate,
    incidentDate,
    enrollment,
    onEnrollmentDateChange,
    onIncidentDateChange,
}: {
    /** What this form's own programme calls each of its dates, falling back to this project's words. */
    labels: DateLabels
    /** What the enrollment date control shows: the stated literal, or the drafted instant. */
    enrollmentDate: string
    /** The same for the incident date, or null on a program that collects none. */
    incidentDate: string | null
    /** The DHIS2 enrollment uid the draft minted, or null when it minted none. */
    enrollment: string | null
    onEnrollmentDateChange: (value: string) => void
    onIncidentDateChange: (value: string) => void
}) {
    return (
        <div className="grid gap-4 rounded-lg border p-4">
            <h3 className="text-sm font-medium">Enrollment</h3>
            <InstantField
                controlId={ENROLLMENT_DATE_CONTROL_ID}
                label={labels.enrollmentDate}
                hint="The date this enrollment begins. DHIS2 files it under this date."
                value={enrollmentDate}
                onChange={onEnrollmentDateChange}
            />
            {incidentDate !== null && (
                <InstantField
                    controlId={INCIDENT_DATE_CONTROL_ID}
                    label={labels.incidentDate}
                    hint="The date of the incident this enrollment follows, as this program collects one."
                    value={incidentDate}
                    onChange={onIncidentDateChange}
                />
            )}
            {enrollment !== null && (
                <dl className="text-sm">
                    <dt className="text-muted-foreground text-xs">{TRACKER_ENROLLMENT_FACT_LABEL}</dt>
                    <dd className="font-mono text-xs break-words">{enrollment}</dd>
                </dl>
            )}
        </div>
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

/**
 * The form's identity: what it is, which DHIS2 object it came from, how much it asks, and how often.
 *
 * REPETITION IS PART OF WHAT THE FORM IS. A DHIS2 programme stage is either answered once per
 * enrollment or once per visit, and that changes what filling this form in means - so a repeatable
 * stage says so where the form describes itself, beside its kind and its question count. A stage that
 * declares nothing states nothing: silence is a form compiled before the declaration was published,
 * not a claim that the programme allows one answer.
 */
function FormFillHeader({
    questionnaire,
    questionnaireId,
    stageRepeats = null,
}: {
    questionnaire: Questionnaire | null
    questionnaireId: string
    /** True when one enrollment may answer this stage more than once, null when the form is silent. */
    stageRepeats?: boolean | null
}) {
    const kind = questionnaire === null ? null : formTypeOf(questionnaire)
    const questions = questionnaire === null ? 0 : questionCount(questionnaire.item)
    return (
        <div className="mb-6 space-y-2">
            <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                <Link to="/forms">
                    <ArrowLeft className="size-4" />
                    All forms
                </Link>
            </Button>
            <h2 className="text-xl font-semibold tracking-tight">
                {questionnaire?.title ?? questionnaire?.name ?? questionnaireId}
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
                        {questions} question{questions === 1 ? '' : 's'}
                    </span>
                )}
            </div>
            {questionnaire?.description !== undefined && (
                <p className="text-muted-foreground text-sm">{questionnaire.description}</p>
            )}
            {stageRepeats === true && (
                <p className="text-muted-foreground text-sm">Repeats: each visit is its own record</p>
            )}
            <ProgramRules rules={programRulesOf(questionnaire)} />
        </div>
    )
}

/**
 * The DHIS2 program rules this form's instance enforces once the submission is imported.
 *
 * WHERE THE FORM DESCRIBES ITSELF, because that is what this is: a fact about the form, alongside
 * its kind, its question count, and whether its stage repeats. It is not a warning about anything a
 * person has done - it reads identically on a blank form and a filled one - and it belongs before
 * the questions rather than after a refusal, because the whole point is that it is knowable in
 * advance. A form its instance holds no rules for says nothing at all.
 *
 * "N MORE RULES" IS DELIBERATE. The form has already stated the rules it enforces itself - the
 * bounds on its own questions, which Submit refuses - so these are the ones beyond it: evaluated
 * somewhere else, after the submission leaves, by the system that has the data to evaluate them.
 *
 * THE CONDITION IS BEHIND THE EXPAND. `#{DeAncVisNo1} > 99` is the instance's own spelling and the
 * only exact statement of what the rule does, so it is here rather than paraphrased - and it is mono
 * and folded away, on the rule this app follows everywhere: the machine spelling of a fact is kept
 * for whoever needs it and never put in front of a reader who does not.
 */
function ProgramRules({ rules }: { rules: ProgramRule[] }) {
    if (rules.length === 0) return null
    return (
        <details className="rounded-lg border px-4 py-3">
            <summary className="cursor-pointer text-sm">
                This DHIS2 instance enforces {rules.length} more {rules.length === 1 ? 'rule' : 'rules'} when the
                submission is imported
            </summary>
            <dl className="mt-3 grid gap-3">
                {rules.map((rule) => (
                    <div key={rule.ruleUid} className="grid gap-1">
                        <dt className="text-sm font-medium">{rule.name}</dt>
                        {rule.description !== null && (
                            <dd className="text-muted-foreground text-sm">{rule.description}</dd>
                        )}
                        <dd className="text-muted-foreground font-mono text-xs break-words">
                            {rule.ruleUid} {rule.condition}
                        </dd>
                    </div>
                ))}
            </dl>
        </details>
    )
}
