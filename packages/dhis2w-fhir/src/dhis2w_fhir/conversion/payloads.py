"""The three payload translators: one per DHIS2 form kind, each writing the import shape DHIS2 reads.

    aggregate      -> a `/api/dataValueSets` envelope: data set, ISO period, organisation unit,
                      and one data value per answered cell, each carrying its category option combo.
    event          -> one `/api/tracker` event of an event program: program, organisation unit,
                      occurrence, status, and one data value per answered question.
    tracker-event  -> the same event, plus the program stage it belongs to, the tracked entity it
                      was captured for, and the enrollment it sits on.

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
from typing import TYPE_CHECKING

from dhis2w_client.generated.v42.oas import (
    DataValue,
    DataValueSet,
    EventStatus,
    TrackerDataValue,
    TrackerEvent,
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
    resolve_organisation_unit,
    wall_clock_notes,
    wall_clock_reading,
)
from dhis2w_fhir.period import parse_period

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
    "TranslatedAnswer",
    "TranslatedAnswers",
    "translate_aggregate_response",
    "translate_event_response",
    "translate_tracker_event_response",
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


def _tracker_data_values(translated: TranslatedAnswers) -> list[TrackerDataValue]:
    """The event data values one translated item tree produced - flat, because an event value carries no combo."""
    return [
        TrackerDataValue(dataElement=answer.question.data_element_uid, value=answer.value)
        for answer in translated.answers
    ]


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
    """The organisation unit a tracker event was captured at, off its D2OrganisationUnit extension.

    A tracker-event response's subject is the tracked entity, so the capture unit rides on an
    extension of its own rather than on `subject`.
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
    """The tracked entity a tracker event was captured for, off the response's subject identifier."""
    subject = response.subject
    identifier = subject.identifier if subject is not None else None
    if subject is not None and subject.reference:
        notes.append(
            ConversionNote(
                category=ConversionNoteCategory.SUBJECT_REFERENCE_IGNORED,
                message=f"the subject reference `{subject.reference}` is not read: a tracker event names its "
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
    """The enrollment a tracker event sits on, off its D2TrackerEnrollment extension."""
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
