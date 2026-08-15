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
import { useEnrollmentOptions } from '@/hooks/use-enrollment-options'
import { useFormOrgUnitScope } from '@/hooks/use-org-unit-scope'
import { usePatientSearchSupport } from '@/hooks/use-patient-search-support'
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
    buildQuestionnaireResponse,
    clearedEntityLevelAnswers,
    collectsIncidentDate,
    dateTimeInputValue,
    entityLevelLinkIds,
    flattenQuestionnaire,
    initialAnswers,
    normaliseDateTime,
    NO_VALUE_TYPES,
    openedAttributeOptionCombo,
    openedReportingUnit,
    questionCodeSystemIds,
    refilledAttributeOptionCombo,
    refilledEnrollment,
    refilledReportingUnit,
    reportingPeriodOf,
    unansweredRequiredLinkIds,
    valueTypesByConcept,
    type AnswerState,
    type ExistingSubject,
    type ReportingPeriod,
} from '@/lib/questionnaire'
import { INCIDENT_AT_FACT_LABEL } from '@/lib/receipt'
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
 * TWO PIECES OF CONTEXT ARE THE USER'S, AND ONE OF THEM IS THE ONLY DISABLED BUTTON HERE. A data
 * set on a non-default category combo declares its attribute option combos as a vocabulary, and a
 * response to it has to name one - it is the third key of every value it carries, beside the
 * organisation unit and the period. Nothing derives it, not even the server, so it is picked above
 * the form and Submit refuses until it is. That is the one place a stated-reason disabled control
 * beats posting and rendering the refusal: the answer is a fact about the submission the person
 * came here with, not something they could read off the form and correct.
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
 * `GET /Patient?identifier=`, so the person can be found instead - and a registration answering for
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
 * THE PERIOD IS THE ONE THIS SCREEN CANNOT CHECK. The server grades an aggregate submission's ISO
 * period against the type its data set reports for, and against the date range the period resolves
 * to. Resolving `202607` into July 2026 is DHIS2 period arithmetic, which this UI does not have and
 * will not grow - so an edited period is written as the identifier alone, with the drafted type kept
 * and the drafted range dropped rather than recomputed. The range is optional and the ISO period is
 * what is captured, so what leaves here is a claim about exactly what a person typed; a period of
 * the wrong type is refused by the server, naming both types, which is better than a client guess.
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
    const [valueTypes, setValueTypes] = useState<ReadonlyMap<string, string>>(NO_VALUE_TYPES)
    const orgUnitScope = useFormOrgUnitScope(questionnaire)
    const enrollmentOffer = useEnrollmentOptions(questionnaire)
    const patientSearchSupport = usePatientSearchSupport()

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
        () => flattenQuestionnaire(questionnaire ?? { resourceType: 'Questionnaire', status: 'unknown' }, valueTypes),
        [questionnaire, valueTypes],
    )

    // The data dictionaries this form's own questions are coded in, and nothing else. R4 spells
    // `BOOLEAN` and `TRUE_ONLY` as one item type, so the value type behind a tick is a fact only the
    // served CodeSystem holds - and reading the two or three systems the form names is what keeps
    // that from becoming a read of the whole terminology. The list is joined into one string so the
    // read runs when the form changes rather than every time the spec is rebuilt around its answer.
    const codeSystemKey = useMemo(() => questionCodeSystemIds(spec).join(' '), [spec])
    useEffect(() => {
        const ids = codeSystemKey === '' ? [] : codeSystemKey.split(' ')
        if (ids.length === 0) {
            setValueTypes(NO_VALUE_TYPES)
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
            setValueTypes(valueTypesByConcept(read.filter((codeSystem) => codeSystem !== null)))
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
                    setAttributeOptionCombo((current) => openedAttributeOptionCombo(current, skeleton))
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
    const draftedPeriod = reportingPeriodOf(envelope)
    // Declared and unchosen is the one state Submit refuses in. A form that declares no vocabulary
    // reports for the default combo, which is what absence means, and nothing is asked.
    const missingAttributeOptionCombo = attributeOptionCombos !== null && attributeOptionCombo === null

    const submit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        if (busy || missingAttributeOptionCombo) return
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
                            draftedPeriod !== null) &&
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
                    {draftedPeriod !== null && (
                        <ReportingPeriodControl
                            drafted={draftedPeriod}
                            iso={reportingPeriodIso ?? draftedPeriod.iso}
                            onChange={setReportingPeriodIso}
                        />
                    )}
                    {draftedVisitDate !== null && (
                        <div className="grid gap-2 rounded-lg border p-4">
                            <InstantField
                                controlId={VISIT_DATE_CONTROL_ID}
                                label="Visit date"
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
                            support={patientSearchSupport}
                            source={personSource}
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
                            support={patientSearchSupport}
                            programUid={programOf(questionnaire)}
                            onChange={(source, option) => {
                                setEnrollmentSource(source)
                                setEnrollment(option)
                            }}
                        />
                    )}
                    {enrolledAt !== null && envelope !== null && (
                        <EnrollmentContext
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
                <Button type="submit" disabled={busy || missingAttributeOptionCombo}>
                    <Send className="size-4" />
                    {busy ? 'Submitting' : 'Submit'}
                </Button>
                <Button type="button" variant="outline" disabled={filling} onClick={fillWithTestData}>
                    <Sparkles className="size-4" />
                    {filling ? 'Filling' : 'Fill with test data'}
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                        // Everything the person entered goes, the combo included: it is their input
                        // rather than the server's context, and it is the only control here a Radix
                        // select cannot be returned to unchosen any other way. The reporting unit
                        // stays, because clearing it would empty a control the form cannot be
                        // submitted well without and that nothing on this page would refill. The
                        // enrollment stays for the harder version of the same reason: clearing it
                        // would silently return the submission to a synthetic pair that cannot
                        // import.
                        dispatch({ kind: 'replace', answers: initialAnswers(spec) })
                        setAttributeOptionCombo(null)
                        setIssues([])
                    }}
                >
                    <Eraser className="size-4" />
                    Clear
                </Button>
                <div className="flex-1" />
                {/* The reason a disabled button always states, because a control that refuses
                    without saying why is worse than one that posts and is refused. */}
                {missingAttributeOptionCombo && (
                    <p className="text-muted-foreground text-xs">
                        Choose what this submission reports for before submitting
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
 * so what a person edits is which period of that type, and the drafted identifier in the box is the
 * worked example of how to spell one.
 *
 * WHAT HAPPENS TO A PERIOD OF THE WRONG TYPE. It is posted and refused, and the refusal names the
 * type the identifier parses as and the type the data set reports for. This screen has no DHIS2
 * period arithmetic to catch it earlier, and inventing one here would be a second implementation of
 * the rule the server already holds.
 */
function ReportingPeriodControl({
    drafted,
    iso,
    onChange,
}: {
    drafted: ReportingPeriod
    iso: string
    onChange: (iso: string) => void
}) {
    return (
        <div className="grid gap-2 rounded-lg border p-4">
            <Label htmlFor={REPORTING_PERIOD_CONTROL_ID}>Reporting period</Label>
            <p className="text-muted-foreground text-sm">
                {drafted.periodType === null
                    ? 'The period this submission reports for. DHIS2 keys the whole submission by it, beside the organisation unit.'
                    : `${drafted.periodType} period, as the data set reports. DHIS2 keys the whole submission by it, beside the organisation unit.`}
            </p>
            <Input
                id={REPORTING_PERIOD_CONTROL_ID}
                className="max-w-xs font-mono"
                value={iso}
                onChange={(event) => onChange(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">
                A period of another type is refused when this submission is sent, and the refusal
                names both types.
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
    enrollmentDate,
    incidentDate,
    enrollment,
    onEnrollmentDateChange,
    onIncidentDateChange,
}: {
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
                label="Enrollment date"
                hint="The date this enrollment begins. DHIS2 files it under this date."
                value={enrollmentDate}
                onChange={onEnrollmentDateChange}
            />
            {incidentDate !== null && (
                <InstantField
                    controlId={INCIDENT_DATE_CONTROL_ID}
                    label={INCIDENT_AT_FACT_LABEL}
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

/** The form's identity: what it is, which DHIS2 object it came from, and how much it asks. */
function FormFillHeader({
    questionnaire,
    questionnaireId,
}: {
    questionnaire: Questionnaire | null
    questionnaireId: string
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
        </div>
    )
}
