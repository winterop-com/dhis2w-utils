"""The five payload translators: one per DHIS2 form kind, each writing the import shape DHIS2 reads.

    aggregate      -> a `/api/dataValueSets` envelope: data set, ISO period, organisation unit, the
                      attribute option combo the whole report is filed under where the form declares
                      a vocabulary for one, and one data value per answered cell, each carrying its
                      category option combo.
    event          -> one `/api/tracker` event of an event program: the UID derived from the
                      receipt's own logical id, program, organisation unit, occurrence, status,
                      and one data value per answered question.
    tracker        -> one `/api/tracker` tracked entity: its client-minted UID, the tracked entity
                      type the form names, the organisation unit that owns it, one attribute per
                      answered entity-level question, and the single enrollment the response
                      creates - minted UID, program, organisation unit, enrolment date, incident
                      date where one was stated, `ACTIVE` status, and one attribute per answered
                      program-only question. A response stating `D2SubjectExists` names a person
                      the instance already holds, and produces that enrollment alone - naming the
                      existing tracked entity, with no tracked entity beside it to rewrite.
    tracker-event  -> the same event as `event`, plus the program stage it belongs to, the tracked
                      entity it was captured for, and the enrollment it sits on.

Every DHIS2 object a tracker payload creates is named before it is posted. A registration reads its
tracked entity and enrollment UIDs off the response, where the client that filled the form minted
them; both event kinds derive theirs from the receipt's own logical id, so one receipt always names
one event. A dry run and the import behind it therefore report the same UID, and forwarding a
receipt twice is refused by the instance as an object it already holds rather than filing a second
copy of one visit.

Every fact a payload carries is read out of the response through an identifier or an extension,
never out of a URL. A Questionnaire's canonical segment is an identity stem, and a Location's id
is one too, so a data set UID comes off the form's `.../id/data-set` identifier and an
organisation unit UID off the registry's `.../id/org-unit` slice - which under code-or-id naming
are not what the ids spell.

A response the translator cannot read whole produces refusals and no payload at all. There is no
partial envelope: a data value set missing the third of its forty cells would import as a complete
report of a period, which is worse than not importing.
"""

from __future__ import annotations

import datetime
import random
from typing import TYPE_CHECKING

from dhis2w_client.generated.v42.oas import (
    DataValue,
    DataValueSet,
    EnrollmentStatus,
    EventStatus,
    TrackerAttribute,
    TrackerDataValue,
    TrackerEnrollment,
    TrackerEvent,
    TrackerTrackedEntity,
)
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.conversion.schemas import (
    ConversionNote,
    ConversionNoteCategory,
    ConversionRefusal,
    ConversionRefusalCategory,
    ConversionTargetKind,
    QuestionSpec,
)
from dhis2w_fhir.conversion.values import (
    LOCATION_REFERENCE_PREFIX,
    answer_wire_value,
    resolve_option,
    resolve_organisation_unit,
    wall_clock_notes,
    wall_clock_reading,
)
from dhis2w_fhir.period import parse_period
from dhis2w_fhir.resources.examples import derived_seed, synthetic_uid

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_fhir.conversion.schemas import ConversionContext, FormSpec
    from dhis2w_fhir.r4 import Extension, QuestionnaireResponse, QuestionnaireResponseItem

__all__ = [
    "COMPLETED_EVENT_STATUSES",
    "EVENT_STATUSES_BY_RESPONSE_STATUS",
    "PERIOD_ISO_SUB_EXTENSION",
    "PERIOD_RANGE_SUB_EXTENSION",
    "PERIOD_TYPE_SUB_EXTENSION",
    "REGISTERED_ENROLLMENT_STATUS",
    "TranslatedAnswer",
    "TranslatedAnswers",
    "receipt_event_uid",
    "translate_aggregate_response",
    "translate_event_response",
    "translate_tracked_entity_response",
    "translate_tracker_event_response",
    "translate_tracker_registration_response",
]

#: The sub-extension urls D2Period slices its three facts under, as `d2-period.fsh.jinja` names them.
PERIOD_ISO_SUB_EXTENSION = "iso"
PERIOD_TYPE_SUB_EXTENSION = "type"
PERIOD_RANGE_SUB_EXTENSION = "period"

#: The DHIS2 event status each `QuestionnaireResponse.status` reports as.
#:
#: The forward mapping is not injective - `COMPLETED`, `SCHEDULE`, `OVERDUE`, and `VISITED` all
#: read as `completed`, because every one of them has been captured against the form - so the
#: inverse cannot recover which of the four an event stood at and answers `COMPLETED` for all of
#: them. `amended` is an R4 lifecycle state DHIS2 has no event status for at all, and collapses
#: onto `COMPLETED` as well. Both collapses raise a note; `entered-in-error` raises a refusal,
#: because retracting an event is a deletion rather than an import.
EVENT_STATUSES_BY_RESPONSE_STATUS = {
    "completed": EventStatus.COMPLETED,
    "in-progress": EventStatus.ACTIVE,
    "stopped": EventStatus.SKIPPED,
    "amended": EventStatus.COMPLETED,
}

#: The DHIS2 event statuses that all read forward as `completed` - what the inverse cannot undo.
COMPLETED_EVENT_STATUSES = (
    EventStatus.COMPLETED,
    EventStatus.SCHEDULE,
    EventStatus.OVERDUE,
    EventStatus.VISITED,
)

#: The response statuses whose DHIS2 event status several response statuses would have produced.
_COLLAPSING_RESPONSE_STATUSES = frozenset({"completed", "amended"})

#: How many dash-separated parts a full calendar date carries, which is what a `completeDate` is.
_DATE_PART_SEPARATOR = "T"

#: The status the enrollment a registration creates is imported under. A registration form is
#: answered when a person is enrolled, and DHIS2 spells a live enrollment `ACTIVE` - completing or
#: cancelling one is a later act against an enrollment that already exists.
REGISTERED_ENROLLMENT_STATUS = EnrollmentStatus.ACTIVE

#: What the event-identity material names itself, so the UID a receipt's event is imported under
#: cannot collide with any other identity minted off the same receipt id.
_EVENT_IDENTITY_TOKEN = "event"

#: The ordinal slot of the event-identity material. A receipt reports exactly one event, so the
#: discriminator a receipt naming several would move stays at the first.
_SOLE_EVENT_ORDINAL = 0


class TranslatedAnswer(BaseModel):
    """One answered question and the DHIS2 wire value it produced."""

    model_config = ConfigDict(frozen=True)

    question: QuestionSpec
    value: str


class TranslatedAnswers(BaseModel):
    """Every data value one response's item tree produced, in the order the response carries them."""

    model_config = ConfigDict(frozen=True)

    answers: tuple[TranslatedAnswer, ...] = ()
    notes: tuple[ConversionNote, ...] = ()
    refusals: tuple[ConversionRefusal, ...] = ()


class _Outcome(BaseModel):
    """One payload under construction: what it has resolved so far, and what resolving it raised."""

    model_config = ConfigDict(frozen=True)

    notes: tuple[ConversionNote, ...] = ()
    refusals: tuple[ConversionRefusal, ...] = ()


class AggregateTranslation(_Outcome):
    """One aggregate response translated: its data value set, or the reasons it produced none."""

    data_value_set: DataValueSet | None = None


class EventTranslation(_Outcome):
    """One event or tracker-event response translated: its event, or the reasons it produced none."""

    event: TrackerEvent | None = None
    target_kind: ConversionTargetKind = ConversionTargetKind.EVENT


class RegistrationTranslation(_Outcome):
    """One registration response translated: what it creates in DHIS2, or the reasons it produced none.

    `tracked_entity` and `enrollment` are alternatives, and `target_kind` says which one the
    response produced: a registration creating the person it enrols carries the tracked entity with
    the enrollment nested inside it, and one whose subject the instance already holds carries the
    enrollment alone.
    """

    tracked_entity: TrackerTrackedEntity | None = None
    enrollment: TrackerEnrollment | None = None
    target_kind: ConversionTargetKind = ConversionTargetKind.TRACKER


def translate_aggregate_response(
    response: QuestionnaireResponse, form: FormSpec, context: ConversionContext
) -> AggregateTranslation:
    """Translate one aggregate response into the `/api/dataValueSets` envelope DHIS2 imports it as."""
    notes: list[ConversionNote] = []
    refusals: list[ConversionRefusal] = []
    data_set = form.data_set_uid
    if data_set is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_TARGET_IDENTIFIER,
                element="Questionnaire.identifier",
                reason=f"`{form.canonical}` carries no `{context.naming.data_set_system}` identifier, so the "
                f"data set its responses report for is unknown",
            )
        )
    period = _period(response, context, notes, refusals)
    organisation_unit = _subject_organisation_unit(response, context, notes, refusals)
    attribute_option_combo = _attribute_option_combo(response, form, context, notes, refusals)
    complete_date = _complete_date(response, context, notes)
    translated = translate_answers(response, form, context)
    notes.extend(translated.notes)
    refusals.extend(translated.refusals)
    if refusals or data_set is None or period is None or organisation_unit is None:
        return AggregateTranslation(notes=tuple(notes), refusals=tuple(refusals))
    return AggregateTranslation(
        notes=tuple(notes),
        data_value_set=DataValueSet(
            dataSet=data_set,
            period=period,
            orgUnit=organisation_unit,
            attributeOptionCombo=attribute_option_combo,
            completeDate=complete_date,
            dataValues=[
                DataValue(
                    dataElement=answer.question.data_element_uid,
                    categoryOptionCombo=answer.question.category_option_combo_uid,
                    value=answer.value,
                )
                for answer in translated.answers
            ],
        ),
    )


def receipt_event_uid(response_id: str) -> str:
    """The DHIS2 UID one receipt's event is imported under, derived from the receipt's own logical id.

    The same receipt names the same event UID - on the dry run and on the import that follows it,
    on this machine and on the next. That property is the whole point: an event travels to
    `/api/tracker` under `importStrategy=CREATE`, so forwarding a receipt DHIS2 already holds the
    event of is refused as an object that exists, rather than filing a second copy of one visit.
    It is the identity a registration already has - the tracked entity UID its subject identifier
    carries - given to the one payload kind that carried none, and it is what lets a dry run's
    diagnostics be read against the objects the import then creates, because both name this UID.

    The material is `<response id>:event:0`, hashed with SHA-256 - never Python's per-process
    salted `hash` - and shaped into `[A-Za-z][A-Za-z0-9]{10}` by the same drawer the synthesis
    path mints tracked entity and enrollment UIDs with. The trailing ordinal is the discriminator
    a receipt naming more than one event would move; a receipt reports exactly one.
    """
    material = f"{response_id}:{_EVENT_IDENTITY_TOKEN}"
    generator = random.Random(derived_seed(material, _SOLE_EVENT_ORDINAL))  # noqa: S311 - an identity, not a secret
    return synthetic_uid(generator)


def translate_event_response(
    response: QuestionnaireResponse, form: FormSpec, context: ConversionContext
) -> EventTranslation:
    """Translate one event-program response into the single `/api/tracker` event DHIS2 imports it as."""
    notes: list[ConversionNote] = []
    refusals: list[ConversionRefusal] = []
    program = _program(form, context, refusals)
    organisation_unit = _subject_organisation_unit(response, context, notes, refusals)
    occurred_at = _occurred_at(response, context, notes, refusals)
    status = _event_status(response, notes, refusals)
    translated = translate_answers(response, form, context)
    notes.extend(translated.notes)
    refusals.extend(translated.refusals)
    if refusals or program is None or organisation_unit is None or occurred_at is None or status is None:
        return EventTranslation(notes=tuple(notes), refusals=tuple(refusals))
    return EventTranslation(
        notes=tuple(notes),
        event=TrackerEvent(
            event=_event_identity(response),
            program=program,
            programStage=form.program_stage_uid,
            orgUnit=organisation_unit,
            occurredAt=occurred_at,
            status=status,
            dataValues=_tracker_data_values(translated),
        ),
    )


def translate_tracker_event_response(
    response: QuestionnaireResponse, form: FormSpec, context: ConversionContext
) -> EventTranslation:
    """Translate one tracker program stage response into the enrolled `/api/tracker` event it reports."""
    notes: list[ConversionNote] = []
    refusals: list[ConversionRefusal] = []
    program = _program(form, context, refusals)
    stage = _program_stage(form, context, refusals)
    organisation_unit = _extension_organisation_unit(response, context, notes, refusals)
    occurred_at = _occurred_at(response, context, notes, refusals)
    status = _event_status(response, notes, refusals)
    tracked_entity = _tracked_entity(response, context, notes, refusals)
    enrollment = _enrollment(response, context, refusals)
    translated = translate_answers(response, form, context)
    notes.extend(translated.notes)
    refusals.extend(translated.refusals)
    if refusals or program is None or stage is None or organisation_unit is None or occurred_at is None:
        return EventTranslation(
            notes=tuple(notes), refusals=tuple(refusals), target_kind=ConversionTargetKind.TRACKER_EVENT
        )
    if status is None or tracked_entity is None or enrollment is None:
        return EventTranslation(
            notes=tuple(notes), refusals=tuple(refusals), target_kind=ConversionTargetKind.TRACKER_EVENT
        )
    return EventTranslation(
        notes=tuple(notes),
        target_kind=ConversionTargetKind.TRACKER_EVENT,
        event=TrackerEvent(
            event=_event_identity(response),
            program=program,
            programStage=stage,
            orgUnit=organisation_unit,
            trackedEntity=tracked_entity,
            enrollment=enrollment,
            occurredAt=occurred_at,
            status=status,
            dataValues=_tracker_data_values(translated),
        ),
    )


def translate_tracker_registration_response(
    response: QuestionnaireResponse, form: FormSpec, context: ConversionContext
) -> RegistrationTranslation:
    """Translate one registration response into the `/api/tracker` tracked entity and enrollment it creates.

    Both DHIS2 identities are the client's: the tracked entity UID the subject identifier carries
    and the enrollment UID the `D2TrackerEnrollment` extension carries are minted by whoever filled
    the form, and they travel to DHIS2 as sent. That is what lets the stage events of the same
    enrollment be captured before either identity exists, and it is why a registration is posted
    before them.

    The attributes are the form's own answers, serialised through the value-type machinery a data
    element's answers go through - a tracked entity attribute has the same DHIS2 value types, binds
    option sets the same way, and its coded answers resolve against the published ValueSets on the
    same strict/lenient dial.

    DHIS2 imports those answers at two levels, and the form says which is which: a question whose
    `D2EntityLevel` extension is true asks a tracked entity attribute of the program's tracked
    entity type, and its value is stated on the tracked entity; a question stating false asks an
    attribute only the program collects, and its value is stated on the enrollment. A question
    stating no level at all - a guide compiled before the extension was published - is written on
    the tracked entity, which is where every registration answer went before the split.

    A response carrying `D2SubjectExists` as true states that its subject identifier names a person
    the instance already holds, and what it creates is then the enrollment alone - a top-level
    `enrollments` array naming that existing tracked entity, posted under the same plain
    `importStrategy=CREATE` every other payload goes under. No `trackedEntities` wrapper goes round
    it: an enrollment that rides inside one has to be posted `CREATE_AND_UPDATE`, which silently
    rewrites the person's owning organisation unit (BUGS.md 73), and the person is not this
    response's to move. The program's own attributes ride the enrollment, because DHIS2 answers
    `E1018` to a mandatory program attribute that arrives on nothing.
    """
    notes: list[ConversionNote] = []
    refusals: list[ConversionRefusal] = []
    program = _program(form, context, refusals)
    tracked_entity_type = _tracked_entity_type(form, context, refusals)
    organisation_unit = _extension_organisation_unit(response, context, notes, refusals)
    tracked_entity = _tracked_entity(response, context, notes, refusals)
    enrollment = _enrollment(response, context, refusals)
    enrolled_at = _enrollment_date(response, context.naming.enrolled_at_url, context, notes, refusals, required=True)
    incident_at = _enrollment_date(response, context.naming.incident_at_url, context, notes, refusals, required=False)
    subject_exists = _subject_exists(response, context)
    translated = translate_answers(response, form, context)
    notes.extend(translated.notes)
    refusals.extend(translated.refusals)
    if subject_exists:
        refusals.extend(_existing_subject_refusals(translated, form))
    target_kind = ConversionTargetKind.TRACKER_ENROLLMENT if subject_exists else ConversionTargetKind.TRACKER
    if refusals or program is None or tracked_entity_type is None or organisation_unit is None:
        return RegistrationTranslation(notes=tuple(notes), refusals=tuple(refusals), target_kind=target_kind)
    if tracked_entity is None or enrollment is None or enrolled_at is None:
        return RegistrationTranslation(notes=tuple(notes), refusals=tuple(refusals), target_kind=target_kind)
    created = TrackerEnrollment(
        enrollment=enrollment,
        trackedEntity=tracked_entity if subject_exists else None,
        program=program,
        orgUnit=organisation_unit,
        enrolledAt=enrolled_at,
        occurredAt=incident_at,
        status=REGISTERED_ENROLLMENT_STATUS,
        attributes=_registration_attributes(translated, entity_level=False) or None,
    )
    if subject_exists:
        return RegistrationTranslation(notes=tuple(notes), enrollment=created, target_kind=target_kind)
    return RegistrationTranslation(
        notes=tuple(notes),
        target_kind=target_kind,
        tracked_entity=TrackerTrackedEntity(
            trackedEntity=tracked_entity,
            trackedEntityType=tracked_entity_type,
            orgUnit=organisation_unit,
            attributes=_registration_attributes(translated, entity_level=True),
            enrollments=[created],
        ),
    )


def translate_tracked_entity_response(
    response: QuestionnaireResponse, form: FormSpec, context: ConversionContext
) -> RegistrationTranslation:
    """Translate one person-only response into the `/api/tracker` tracked entity it creates.

    The registration translator without its enrollment half. DHIS2 accepts a bare `trackedEntities`
    import under plain CREATE, so the payload is one tracked entity carrying the type off
    `$DHIS2-TET`, the organisation unit it is owned at, and its answers - every one of them on the
    entity, because the form asks only attributes the type itself collects and there is no
    enrollment for an answer to land on.
    """
    notes: list[ConversionNote] = []
    refusals: list[ConversionRefusal] = []
    tracked_entity_type = _tracked_entity_type(form, context, refusals)
    organisation_unit = _extension_organisation_unit(response, context, notes, refusals)
    tracked_entity = _tracked_entity(response, context, notes, refusals)
    translated = translate_answers(response, form, context)
    notes.extend(translated.notes)
    refusals.extend(translated.refusals)
    if refusals or tracked_entity_type is None or organisation_unit is None or tracked_entity is None:
        return RegistrationTranslation(
            notes=tuple(notes), refusals=tuple(refusals), target_kind=ConversionTargetKind.TRACKED_ENTITY
        )
    return RegistrationTranslation(
        notes=tuple(notes),
        target_kind=ConversionTargetKind.TRACKED_ENTITY,
        tracked_entity=TrackerTrackedEntity(
            trackedEntity=tracked_entity,
            trackedEntityType=tracked_entity_type,
            orgUnit=organisation_unit,
            attributes=[
                TrackerAttribute(attribute=answer.question.data_element_uid, value=answer.value)
                for answer in translated.answers
            ],
        ),
    )


def translate_answers(response: QuestionnaireResponse, form: FormSpec, context: ConversionContext) -> TranslatedAnswers:
    """Walk one response's item tree and serialise every answered question, in document order."""
    answers: list[TranslatedAnswer] = []
    notes: list[ConversionNote] = []
    refusals: list[ConversionRefusal] = []
    _walk(response.item or [], form, context, answers, notes, refusals)
    return TranslatedAnswers(answers=tuple(answers), notes=tuple(notes), refusals=tuple(refusals))


def _walk(
    items: Sequence[QuestionnaireResponseItem],
    form: FormSpec,
    context: ConversionContext,
    answers: list[TranslatedAnswer],
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> None:
    """Read one level of the response's item tree, then the level below it."""
    for item in items:
        _item(item, form, context, answers, notes, refusals)
        _walk(item.item or [], form, context, answers, notes, refusals)


def _item(
    item: QuestionnaireResponseItem,
    form: FormSpec,
    context: ConversionContext,
    answers: list[TranslatedAnswer],
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> None:
    """Serialise one answered item against the question the form says its link id is."""
    link_id = item.linkId
    if not link_id:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNKNOWN_LINK_ID,
                element="QuestionnaireResponse.item.linkId",
                reason="an answered item carries no `linkId`",
            )
        )
        return
    if link_id in form.group_link_ids:
        if item.answer:
            notes.append(
                ConversionNote(
                    category=ConversionNoteCategory.GROUP_ITEM_IGNORED,
                    link_id=link_id,
                    message=f"`{link_id}` is a group of `{form.canonical}` and stores no DHIS2 data value of its own",
                )
            )
        return
    question = form.questions.get(link_id)
    if question is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNKNOWN_LINK_ID,
                link_id=link_id,
                reason=f"`{link_id}` is not a question of `{form.canonical}`",
            )
        )
        return
    wire = answer_wire_value(question, item.answer or [], context)
    notes.extend(wire.notes)
    refusals.extend(wire.refusals)
    if wire.value is not None:
        answers.append(TranslatedAnswer(question=question, value=wire.value))


def _subject_exists(response: QuestionnaireResponse, context: ConversionContext) -> bool:
    """Whether the response states that the person it is subject to is already held by the instance.

    Absent is false, which is what makes an unmarked registration the create it has always been:
    the client minted the subject identifier and DHIS2 has never seen it. Only an explicit `true`
    switches the payload to the enrollment-only shape.
    """
    return any(extension.valueBoolean is True for extension in _extensions(response, context.naming.subject_exists_url))


def _existing_subject_refusals(translated: TranslatedAnswers, form: FormSpec) -> tuple[ConversionRefusal, ...]:
    """Refuse every answer belonging to the person's own record when the instance already holds that person.

    An enrollment-only import carries the program's attributes and nothing else, so an entity-level
    answer has nowhere on the payload to go. The alternative - wrapping the enrollment in a
    `trackedEntities` entry so the attribute has a home - rewrites the owning organisation unit of a
    person this response did not create (BUGS.md 73). Dropping the answer silently is the third
    option and the worst: a captured value that reaches no instance is data loss nobody is told
    about. So the whole response is refused, each answer named, and the fix stated.

    OWNER REVIEW: refusal is the strict reading of all-or-nothing. The looser reading - import the
    enrollment and report the dropped answers as notes - is a policy decision, not a technical one.
    """
    return tuple(
        ConversionRefusal(
            category=ConversionRefusalCategory.ENTITY_LEVEL_ANSWER_ON_EXISTING_SUBJECT,
            link_id=answer.question.link_id,
            element="QuestionnaireResponse.item.answer",
            reason=f"`{answer.question.link_id}` is a question of the person's own record, and this response "
            f"enrols a person the instance already holds - so it imports as an enrollment alone, which "
            f"carries no answer of that kind. Answer it on that person's own record, or capture a new "
            f"person through `{form.canonical}` without stating that the subject already exists",
        )
        for answer in translated.answers
        if _is_entity_level(answer)
    )


def _registration_attributes(translated: TranslatedAnswers, *, entity_level: bool) -> list[TrackerAttribute]:
    """The answers of one registration belonging to a single DHIS2 level, in the response's own order.

    A question stating no level counts as entity-level, so a guide compiled before `D2EntityLevel`
    was published writes every answer where it wrote them before: on the tracked entity.
    """
    return [
        TrackerAttribute(attribute=answer.question.data_element_uid, value=answer.value)
        for answer in translated.answers
        if _is_entity_level(answer) is entity_level
    ]


def _is_entity_level(answer: TranslatedAnswer) -> bool:
    """Whether one answered question's value is stated on the tracked entity rather than the enrollment."""
    return answer.question.entity_level is not False


def _tracker_data_values(translated: TranslatedAnswers) -> list[TrackerDataValue]:
    """The event data values one translated item tree produced - flat, because an event value carries no combo."""
    return [
        TrackerDataValue(dataElement=answer.question.data_element_uid, value=answer.value)
        for answer in translated.answers
    ]


def _event_identity(response: QuestionnaireResponse) -> str | None:
    """The event UID one response names, or None for a response carrying no logical id to name it with.

    A receipt off the capture spool is a file named after its own id and a resource carrying that
    id, so the None branch is a response handed straight to the translator by a caller who minted
    no identity for it - and a payload nothing can name is one DHIS2 mints the UID of, exactly as
    it does for every other identity such a response does not state.
    """
    return receipt_event_uid(response.id) if response.id else None


def _period(
    response: QuestionnaireResponse,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> str | None:
    """The DHIS2 ISO period an aggregate response reports for, read off its D2Period extension.

    The ISO identifier is what DHIS2 imports against, so it is parsed here rather than trusted:
    a period the parser cannot read would import against a period that does not exist. The date
    range riding beside it is derived data and is only checked, never used.
    """
    periods = _extensions(response, context.naming.period_url)
    if len(periods) != 1:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_PERIOD,
                element="QuestionnaireResponse.extension",
                reason=f"an aggregate response carries exactly one `{context.naming.period_url}` extension, "
                f"not {len(periods)}",
            )
        )
        return None
    iso_extensions = _sub_extensions(periods[0], PERIOD_ISO_SUB_EXTENSION)
    iso = iso_extensions[0].valueString if iso_extensions else None
    if not iso:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_PERIOD,
                element="QuestionnaireResponse.extension",
                reason="the D2Period extension carries no `iso` sub-extension",
            )
        )
        return None
    try:
        parsed = parse_period(iso)
    except ValueError as error:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MALFORMED_PERIOD,
                element="QuestionnaireResponse.extension",
                reason=str(error),
            )
        )
        return None
    ranges = _sub_extensions(periods[0], PERIOD_RANGE_SUB_EXTENSION)
    claimed = ranges[0].valuePeriod if ranges else None
    if claimed is not None and (
        claimed.start != parsed.start_date.isoformat() or claimed.end != parsed.end_date.isoformat()
    ):
        notes.append(
            ConversionNote(
                category=ConversionNoteCategory.PERIOD_RANGE_IGNORED,
                message=f"the D2Period date range {claimed.start} to {claimed.end} is not what the ISO period "
                f"`{iso}` covers; the ISO period is what DHIS2 imports against",
            )
        )
    return parsed.iso


def _attribute_option_combo(
    response: QuestionnaireResponse,
    form: FormSpec,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> str | None:
    """The third key of a data value set, resolved off the response's D2AttributeOptionCombo extension.

    Whether the response has to carry one is a fact about the form: a data set on the default
    category combo declares no vocabulary, its values are keyed under the one attribute option
    combo it has, and DHIS2 fills the field itself - so a form declaring none writes nothing here
    and a response carrying the extension anyway is noted rather than written. A form that does
    declare one and a response that does not name it is refused, because DHIS2 refuses that write
    with `E8023` and a payload we know it will not take is worse than a named refusal.

    Resolution is the coded answer's, against the very option table a coded answer resolves
    through: the concept code first (which is the DHIS2 UID under `concept_code_source = "id"`),
    then - leniently - the UID the CodeSystem's `dhis2-id` property carries and the DHIS2 code, both
    of them refined by whatever the combo's own ConceptMap maps onto
    `{base}/id/category-option-combo`.
    """
    extensions = _extensions(response, context.naming.attribute_option_combo_url)
    declared = form.attribute_option_combo_value_set
    if declared is None:
        if extensions:
            notes.append(
                ConversionNote(
                    category=ConversionNoteCategory.ATTRIBUTE_OPTION_COMBO_IGNORED,
                    message=f"`{form.canonical}` declares no attribute-option-combo vocabulary, so the "
                    f"response's `{context.naming.attribute_option_combo_url}` extension is not written; its "
                    f"data set rides the default category combo",
                )
            )
        return None
    if len(extensions) != 1:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_ATTRIBUTE_OPTION_COMBO,
                element="QuestionnaireResponse.extension",
                reason=f"`{form.canonical}` keys its values from `{declared}`, and the response carries "
                f"{len(extensions)} `{context.naming.attribute_option_combo_url}` extensions rather than "
                f"exactly one; DHIS2 refuses a write naming no attribute option combo with E8023",
            )
        )
        return None
    coding = extensions[0].valueCoding
    code = coding.code if coding is not None else None
    if not code:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_ATTRIBUTE_OPTION_COMBO,
                element="QuestionnaireResponse.extension",
                reason="the D2AttributeOptionCombo extension carries a coding with no code, so which "
                "attribute option combo the values are keyed under is unknown",
            )
        )
        return None
    table = context.option_tables.get(form.attribute_option_combo_system or "")
    if table is None:
        notes.append(
            ConversionNote(
                category=ConversionNoteCategory.CODED_ANSWER_UNCHECKED,
                message=f"the context carries no CodeSystem behind `{declared}`, so `{code}` goes to DHIS2 as "
                f'the attribute option combo UID it is under `concept_code_source = "id"`',
            )
        )
        return code
    lookup = resolve_option(table, code, context.coded_answer_mode)
    if lookup.ambiguous_option_uids:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNRESOLVABLE_ATTRIBUTE_OPTION_COMBO,
                element="QuestionnaireResponse.extension",
                reason=f"`{code}` names more than one attribute option combo of `{table.system}` "
                f"({', '.join(lookup.ambiguous_option_uids)})",
            )
        )
        return None
    if lookup.option is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNRESOLVABLE_ATTRIBUTE_OPTION_COMBO,
                element="QuestionnaireResponse.extension",
                reason=f"`{table.system}` holds no attribute option combo `{code}` under the "
                f"`{context.coded_answer_mode}` coded-answer dial; DHIS2 refuses a write keyed to a combo "
                f"its data set does not carry with E8023",
            )
        )
        return None
    if not lookup.option.matched_contract_spelling:
        notes.append(
            ConversionNote(
                category=ConversionNoteCategory.CODED_ANSWER_FALLBACK,
                message=f"the attribute option combo `{code}` matched {lookup.option.entry.option_uid} by "
                f"{lookup.option.matched_by}; the contract asks for concept code "
                f"`{lookup.option.entry.concept_code}`",
            )
        )
    return lookup.option.entry.option_uid


def _subject_organisation_unit(
    response: QuestionnaireResponse,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> str | None:
    """The organisation unit an aggregate or event response reports for, off its Location subject."""
    subject = response.subject
    reference = subject.reference if subject is not None else None
    return _organisation_unit(reference, "QuestionnaireResponse.subject.reference", context, notes, refusals)


def _extension_organisation_unit(
    response: QuestionnaireResponse,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> str | None:
    """The organisation unit a tracker response names, off its D2OrganisationUnit extension.

    A tracker response's subject is the tracked entity, so the unit rides on an extension of its
    own rather than on `subject`: for a stage event it is where the event happened, and for a
    registration it is the unit that owns the person and the enrollment being created.
    """
    extensions = _extensions(response, context.naming.organisation_unit_url)
    if len(extensions) != 1:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_ORGANISATION_UNIT,
                element="QuestionnaireResponse.extension",
                reason=f"a tracker event carries exactly one `{context.naming.organisation_unit_url}` "
                f"extension, not {len(extensions)}",
            )
        )
        return None
    carried = extensions[0].valueReference
    reference = carried.reference if carried is not None else None
    return _organisation_unit(reference, "QuestionnaireResponse.extension", context, notes, refusals)


def _organisation_unit(
    reference: str | None,
    element: str,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> str | None:
    """Resolve one `Location/<id>` reference to the DHIS2 organisation unit UID it names."""
    if not reference or not reference.startswith(LOCATION_REFERENCE_PREFIX):
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_ORGANISATION_UNIT,
                element=element,
                reason=f"the response names no `{LOCATION_REFERENCE_PREFIX}<id>` organisation unit",
            )
        )
        return None
    resolution = resolve_organisation_unit(reference, context)
    if resolution.uid is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNRESOLVABLE_ORGANISATION_UNIT,
                element=element,
                reason=f"`{reference}` is no published Location, so it identifies no DHIS2 organisation unit",
            )
        )
        return None
    if resolution.note is not None:
        notes.append(resolution.note)
    return resolution.uid


def _complete_date(
    response: QuestionnaireResponse, context: ConversionContext, notes: list[ConversionNote]
) -> str | None:
    """The day an aggregate report was completed, taken from the response's `authored` instant.

    A data value set is reported as complete for a period, and the moment the response records
    itself as authored is the only statement of when that happened it carries.
    """
    if not response.authored:
        return None
    reading = wall_clock_reading(response.authored, context.timezone)
    complete_date = reading.value.partition(_DATE_PART_SEPARATOR)[0]
    notes.append(
        ConversionNote(
            category=ConversionNoteCategory.COMPLETE_DATE_DERIVED,
            message=f"the data value set is reported complete on `{complete_date}`, the day the response "
            f"records itself as authored",
        )
    )
    return complete_date


def _program(form: FormSpec, context: ConversionContext, refusals: list[ConversionRefusal]) -> str | None:
    """The DHIS2 program an event belongs to, off the form's program identifier."""
    if form.program_uid is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_TARGET_IDENTIFIER,
                element="Questionnaire.identifier",
                reason=f"`{form.canonical}` carries no `{context.naming.program_system}` identifier, so the "
                f"program its events belong to is unknown",
            )
        )
    return form.program_uid


def _program_stage(form: FormSpec, context: ConversionContext, refusals: list[ConversionRefusal]) -> str | None:
    """The DHIS2 program stage a tracker event reports, off the form's program-stage identifier."""
    if form.program_stage_uid is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_TARGET_IDENTIFIER,
                element="Questionnaire.identifier",
                reason=f"`{form.canonical}` carries no `{context.naming.program_stage_system}` identifier, so "
                f"the stage its events report is unknown",
            )
        )
    return form.program_stage_uid


def _tracked_entity_type(form: FormSpec, context: ConversionContext, refusals: list[ConversionRefusal]) -> str | None:
    """The DHIS2 type a registration enrols a person as, off the form's tracked-entity-type identifier.

    A tracker program without a tracked entity type cannot register anybody, so a form carrying no
    such identifier is refused by name rather than posted for DHIS2 to reject: the gap is in the
    guide - or in the instance the guide was generated from - and naming it here says which.
    """
    if form.tracked_entity_type_uid is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_TRACKED_ENTITY_TYPE,
                element="Questionnaire.identifier",
                reason=f"`{form.canonical}` carries no `{context.naming.tracked_entity_type_system}` identifier, "
                f"so the tracked entity type it enrols a person as is unknown",
            )
        )
    return form.tracked_entity_type_uid


def _enrollment_date(
    response: QuestionnaireResponse,
    url: str,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
    *,
    required: bool,
) -> datetime.datetime | None:
    """One date the enrollment carries, as the zone-less wall clock DHIS2 stores it in (BUGS.md #62).

    `enrolledAt` is required because DHIS2 requires every enrollment to say when it began;
    `occurredAt` - the incident date - is written only where the response states one, because the
    registration profile slices it 0..1 and a program that displays no incident date has none.
    """
    extensions = _extensions(response, url)
    if not extensions:
        if required:
            refusals.append(
                ConversionRefusal(
                    category=ConversionRefusalCategory.MISSING_ENROLLMENT_DATE,
                    element="QuestionnaireResponse.extension",
                    reason=f"the response carries no `{url}` extension, so when the enrollment began is unknown",
                )
            )
        return None
    value = extensions[0].valueDateTime
    reading = wall_clock_reading(value or "", context.timezone)
    if not value or reading.moment is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MALFORMED_ENROLLMENT_DATE,
                element="QuestionnaireResponse.extension",
                reason=f"`{value}` does not read as an instant, so the enrollment date `{url}` states is unknown",
            )
        )
        return None
    notes.extend(wall_clock_notes(reading, context, link_id=None))
    return reading.moment


def _occurred_at(
    response: QuestionnaireResponse,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> datetime.datetime | None:
    """The moment an event occurred, as the zone-less wall clock DHIS2 stores (BUGS.md #62).

    `TrackerEvent.occurredAt` is typed `Instant`, which the generated model reads as a `datetime`
    - and a zone-less `datetime` is exactly what DHIS2 both serves and accepts on that field, so
    the offset the R4 `dateTime` carries is read off through the project's zone and the naive
    instant behind it is what travels.
    """
    if not response.authored:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_OCCURRENCE,
                element="QuestionnaireResponse.authored",
                reason="the response records no `authored` instant, which is when the event occurred",
            )
        )
        return None
    reading = wall_clock_reading(response.authored, context.timezone)
    if reading.moment is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_OCCURRENCE,
                element="QuestionnaireResponse.authored",
                reason=f"`{response.authored}` does not read as an instant, so when the event occurred is unknown",
            )
        )
        return None
    notes.extend(wall_clock_notes(reading, context, link_id=None))
    return reading.moment


def _event_status(
    response: QuestionnaireResponse, notes: list[ConversionNote], refusals: list[ConversionRefusal]
) -> EventStatus | None:
    """The DHIS2 event status one response status reports, noting the collapse where there is one."""
    status = response.status
    if status is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNMAPPABLE_STATUS,
                element="QuestionnaireResponse.status",
                reason="the response carries no status, so the event's DHIS2 status is unknown",
            )
        )
        return None
    event_status = EVENT_STATUSES_BY_RESPONSE_STATUS.get(status)
    if event_status is None:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNMAPPABLE_STATUS,
                element="QuestionnaireResponse.status",
                reason=f"`{status}` names no DHIS2 event status; retracting an event is a deletion rather "
                f"than an import",
            )
        )
        return None
    if status in _COLLAPSING_RESPONSE_STATUSES:
        collapsed = ", ".join(sorted(member.value for member in COMPLETED_EVENT_STATUSES))
        notes.append(
            ConversionNote(
                category=ConversionNoteCategory.STATUS_COLLAPSED,
                message=f"`{status}` is written as `{event_status.value}`; DHIS2 reads {collapsed} all as "
                f"`completed`, so which of them the event stood at is not recoverable",
            )
        )
    return event_status


def _tracked_entity(
    response: QuestionnaireResponse,
    context: ConversionContext,
    notes: list[ConversionNote],
    refusals: list[ConversionRefusal],
) -> str | None:
    """The tracked entity a tracker response is about, off its subject identifier - minted by a registration."""
    subject = response.subject
    identifier = subject.identifier if subject is not None else None
    if subject is not None and subject.reference:
        notes.append(
            ConversionNote(
                category=ConversionNoteCategory.SUBJECT_REFERENCE_IGNORED,
                message=f"the subject reference `{subject.reference}` is not read: a tracker response names its "
                f"tracked entity by identifier under `{context.naming.tracked_entity_system}`",
            )
        )
    if identifier is None or not identifier.value or identifier.system != context.naming.tracked_entity_system:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_SUBJECT,
                element="QuestionnaireResponse.subject.identifier",
                reason=f"the response names no tracked entity under `{context.naming.tracked_entity_system}`",
            )
        )
        return None
    return identifier.value


def _enrollment(
    response: QuestionnaireResponse, context: ConversionContext, refusals: list[ConversionRefusal]
) -> str | None:
    """The enrollment a tracker response names, off its D2TrackerEnrollment extension - minted by a registration."""
    extensions = _extensions(response, context.naming.tracker_enrollment_url)
    identifier = extensions[0].valueIdentifier if len(extensions) == 1 else None
    if identifier is None or not identifier.value or identifier.system != context.naming.tracker_enrollment_system:
        refusals.append(
            ConversionRefusal(
                category=ConversionRefusalCategory.MISSING_ENROLLMENT,
                element="QuestionnaireResponse.extension",
                reason=f"the response names no enrollment under `{context.naming.tracker_enrollment_system}`",
            )
        )
        return None
    return identifier.value


def _extensions(response: QuestionnaireResponse, url: str) -> tuple[Extension, ...]:
    """Every extension the response carries under one url."""
    return tuple(extension for extension in response.extension or [] if extension.url == url)


def _sub_extensions(extension: Extension, url: str) -> tuple[Extension, ...]:
    """Every sub-extension one complex extension carries under one slice url."""
    return tuple(nested for nested in extension.extension or [] if nested.url == url)
