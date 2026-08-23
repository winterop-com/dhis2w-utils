"""Projecting one recorded event onto the document its stage form describes.

The store here is hand-written rather than harvested, because what these tests are about is the
typing rule: one stage form asking a question of every shape DHIS2 stores a value in, and one
recorded event answering all of them. The form declares its subject as `Device`, so the record of a
cold chain fridge is what the projection is exercised on - the surface is not about people, and a
test that only ever projected a person would not say so.
"""

from __future__ import annotations

from typing import Any

import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.capture import CaptureIndexCache, CaptureNaming
from dhis2w_fhir_serve.history.projection import RecordProjection
from dhis2w_fhir_serve.history.wire import RecordedEvent, RecordedValue, TrackedEntityRecord
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, StoreEntry

CANONICAL = "http://example.org/fhir"
IDENTIFIER_BASE = "http://dhis2.org/fhir"

FRIDGE_UID = "geghdTobFoE"
FRIDGE_TYPE_UID = "oWMH7vxiPpZ"
STAGE_UID = "PsTempRead1"
ENROLLMENT_UID = "IsEmT1d3S4X"
ORG_UNIT_UID = "DiszpKrYNg8"

DATA_ELEMENT_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-de-cs"
ALARM_VALUE_SET = f"{CANONICAL}/ValueSet/d2-os-alarm-vs"
ALARM_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-alarm-cs"
STAGE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{STAGE_UID}"

TEMPERATURE = "DeTempRead1"
READING_COUNT = "DeReadCount"
TAKEN_AT = "DeTakenAt01"
FAULTS = "DeFaults001"
ALARM = "DeAlarmSt01"
INSPECTOR = "DeInspect01"


def _concept(code: str, display: str, value_type: str) -> dict[str, Any]:
    """One data-dictionary concept, carrying the DHIS2 value type its question is graded on."""
    return {"code": code, "display": display, "property": [{"code": "value-type", "valueCode": value_type}]}


DATA_ELEMENT_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": "d2-de-cs",
    "url": DATA_ELEMENT_CODE_SYSTEM,
    "status": "active",
    "content": "complete",
    "property": [{"code": "value-type", "type": "code"}],
    "concept": [
        _concept(TEMPERATURE, "Fridge temperature", "NUMBER"),
        _concept(READING_COUNT, "Readings since last check", "INTEGER"),
        _concept(TAKEN_AT, "Reading taken at", "DATETIME"),
        _concept(FAULTS, "Faults observed", "MULTI_TEXT"),
        _concept(ALARM, "Alarm state", "TEXT"),
        _concept(INSPECTOR, "Inspector", "TEXT"),
    ],
}

ALARM_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": "d2-os-alarm-cs",
    "url": ALARM_CODE_SYSTEM,
    "status": "active",
    "content": "complete",
    "concept": [
        {
            "code": "OpAlarmHigh",
            "display": "Above range",
            "property": [{"code": "dhis2-code", "valueString": "ALARM_HIGH"}],
        }
    ],
}

ALARM_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": "d2-os-alarm-vs",
    "url": ALARM_VALUE_SET,
    "status": "active",
    "compose": {"include": [{"system": ALARM_CODE_SYSTEM}]},
}


def _item(link_id: str, item_type: str, **extra: Any) -> dict[str, Any]:
    """One question of the stage form, coded from the data dictionary the way the emitter writes it."""
    return {
        "linkId": link_id,
        "type": item_type,
        "text": link_id,
        "code": [{"system": DATA_ELEMENT_CODE_SYSTEM, "code": link_id}],
        **extra,
    }


STAGE_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": STAGE_UID,
    "url": STAGE_QUESTIONNAIRE,
    "status": "active",
    "title": "Cold chain monitoring - Temperature reading",
    "subjectType": ["Device"],
    "extension": [{"url": f"{CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "tracker-event"}],
    "identifier": [
        {"system": f"{IDENTIFIER_BASE}/id/program-stage", "value": STAGE_UID},
        {"system": f"{IDENTIFIER_BASE}/id/program", "value": "PrColdCh001"},
    ],
    "item": [
        {
            "linkId": "reading",
            "type": "group",
            "text": "Reading",
            "item": [_item(TEMPERATURE, "decimal"), _item(READING_COUNT, "integer")],
        },
        _item(TAKEN_AT, "dateTime"),
        _item(FAULTS, "choice", answerValueSet=ALARM_VALUE_SET, repeats=True),
        _item(ALARM, "choice", answerValueSet=ALARM_VALUE_SET),
        _item(INSPECTOR, "string"),
    ],
}


def _entry(body: dict[str, Any]) -> StoreEntry:
    """One store entry over a hand-written resource, indexed by the identifiers it carries."""
    return StoreEntry(
        resource_type=str(body["resourceType"]),
        resource_id=str(body["id"]),
        canonical_url=str(body["url"]),
        identifiers=tuple(
            IdentifierToken(system=identifier["system"], value=identifier["value"])
            for identifier in body.get("identifier", [])
        ),
        source="test",
        body=body,
    )


@pytest.fixture
def record_store() -> ResourceStore:
    """The stage form a fridge's readings are projected through, and the terminology it binds."""
    return ResourceStore(
        entries=(
            _entry(STAGE_QUESTIONNAIRE_BODY),
            _entry(DATA_ELEMENT_CODE_SYSTEM_BODY),
            _entry(ALARM_CODE_SYSTEM_BODY),
            _entry(ALARM_VALUE_SET_BODY),
        )
    )


@pytest.fixture
def projection(compiled_project: FhirProject, record_store: ResourceStore) -> RecordProjection:
    """The projection one record read runs through, over that store and this project's own names."""
    return RecordProjection(
        naming=CaptureNaming.from_project(compiled_project),
        store=record_store,
        indexes=CaptureIndexCache(),
        timezone="Asia/Vientiane",
    )


def _record() -> TrackedEntityRecord:
    """The fridge whose record is being projected."""
    return TrackedEntityRecord(tracked_entity_uid=FRIDGE_UID, tracked_entity_type_uid=FRIDGE_TYPE_UID)


def _event(*values: tuple[str, str], stage_uid: str = STAGE_UID) -> RecordedEvent:
    """One temperature reading of that fridge, carrying the values it was recorded with."""
    return RecordedEvent(
        event_uid="EvTempRead1",
        program_uid="PrColdCh001",
        program_stage_uid=stage_uid,
        enrollment_uid=ENROLLMENT_UID,
        status="COMPLETED",
        occurred_at="2026-08-22T07:00:00.000",
        organisation_unit_uid=ORG_UNIT_UID,
        values=tuple(RecordedValue(data_element_uid=uid, value=value) for uid, value in values),
    )


def test_a_subject_that_is_not_a_person_is_served_as_what_its_form_says_it_is(
    projection: RecordProjection,
) -> None:
    """The subject's `type` is the form's own `subjectType`, so a fridge is never served as a patient."""
    projected = projection.project_event(_record(), _event((TEMPERATURE, "4.4")))

    assert projected.response is not None
    assert projected.response.subject is not None
    assert projected.response.subject.type == "Device"
    assert projected.response.subject.identifier is not None
    assert projected.response.subject.identifier.value == FRIDGE_UID


def test_each_value_lands_on_the_element_its_question_asks_it_on(projection: RecordProjection) -> None:
    """The item type decides the `value[x]` element, and the stored value decides what it carries."""
    projected = projection.project_event(
        _record(),
        _event((TEMPERATURE, "4.4"), (READING_COUNT, "2"), (INSPECTOR, "  M Kamara  ")),
    )

    assert projected.response is not None
    assert projected.response.item is not None
    [reading, inspector] = projected.response.item
    assert reading.linkId == "reading"
    assert reading.item is not None
    assert [answered.linkId for answered in reading.item] == [TEMPERATURE, READING_COUNT]
    assert reading.item[0].answer is not None
    assert reading.item[0].answer[0].valueDecimal == 4.4
    assert reading.item[1].answer is not None
    assert reading.item[1].answer[0].valueInteger == 2
    assert inspector.answer is not None
    assert inspector.answer[0].valueString == "M Kamara"


def test_the_items_mirror_the_form_and_carry_nothing_it_does_not_ask(projection: RecordProjection) -> None:
    """A value of a data element outside the form answers a question this guide never published."""
    projected = projection.project_event(_record(), _event((TEMPERATURE, "4.4"), ("DeElsewher1", "9")))

    assert projected.response is not None
    assert projected.response.item is not None
    assert [item.linkId for item in projected.response.item] == ["reading"]


def test_a_zone_less_timestamp_takes_the_offset_the_project_states(projection: RecordProjection) -> None:
    """DHIS2 writes a DATETIME with no zone (BUGS.md 62), and an R4 dateTime carrying a time needs one."""
    projected = projection.project_event(_record(), _event((TAKEN_AT, "2026-08-22T06:30:00.000")))

    assert projected.response is not None
    assert projected.response.item is not None
    assert projected.response.item[0].answer is not None
    assert projected.response.item[0].answer[0].valueDateTime == "2026-08-22T06:30:00.000+07:00"
    assert projected.response.authored == "2026-08-22T07:00:00.000+07:00"


def test_a_coded_value_is_carried_as_the_concept_the_published_code_system_states(
    projection: RecordProjection,
) -> None:
    """DHIS2 stores the option's own code, and the guide publishes it beside the concept code."""
    projected = projection.project_event(_record(), _event((ALARM, "ALARM_HIGH")))

    assert projected.response is not None
    assert projected.response.item is not None
    assert projected.response.item[0].answer is not None
    coding = projected.response.item[0].answer[0].valueCoding
    assert coding is not None
    assert coding.system == ALARM_CODE_SYSTEM
    assert coding.code == "OpAlarmHigh"
    assert coding.display == "Above range"


def test_a_multi_text_value_is_one_answer_per_option_it_names(projection: RecordProjection) -> None:
    """A `MULTI_TEXT` data element stores several option codes in one value, and each is one answer."""
    projected = projection.project_event(_record(), _event((FAULTS, "ALARM_HIGH,OpAlarmHigh")))

    assert projected.response is not None
    assert projected.response.item is not None
    answers = projected.response.item[0].answer
    assert answers is not None
    assert [answer.valueCoding.code for answer in answers if answer.valueCoding is not None] == [
        "OpAlarmHigh",
        "OpAlarmHigh",
    ]


def test_a_value_the_terminology_cannot_code_is_carried_as_the_instance_stored_it(
    projection: RecordProjection,
) -> None:
    """Dropping it would hide a value DHIS2 holds; recoding it would be this server deciding what it means."""
    projected = projection.project_event(_record(), _event((ALARM, "ALARM_UNKNOWN")))

    assert projected.response is not None
    assert projected.response.item is not None
    assert projected.response.item[0].answer is not None
    assert projected.response.item[0].answer[0].valueString == "ALARM_UNKNOWN"


def test_a_number_the_instance_holds_as_text_is_carried_as_text(projection: RecordProjection) -> None:
    """The same rule the example corpus follows: a value that is not the number its type promises stays as it is."""
    projected = projection.project_event(_record(), _event((READING_COUNT, "two")))

    assert projected.response is not None
    assert projected.response.item is not None
    assert projected.response.item[0].item is not None
    assert projected.response.item[0].item[0].answer is not None
    assert projected.response.item[0].item[0].answer[0].valueString == "two"


def test_an_event_of_a_stage_this_project_publishes_no_form_for_is_named(projection: RecordProjection) -> None:
    """There is no questionnaire to name, so there is no document - and the stage is stated instead."""
    projected = projection.project_event(_record(), _event((TEMPERATURE, "4.4"), stage_uid="PsUnknown01"))

    assert projected.response is None
    assert projected.unpublished_stage_uid == "PsUnknown01"


def test_two_projections_of_an_unchanged_record_are_the_same_document(projection: RecordProjection) -> None:
    """Nothing is minted per request: every id and every order comes from what DHIS2 holds."""
    event = _event((TEMPERATURE, "4.4"), (ALARM, "ALARM_HIGH"))

    first = projection.project_event(_record(), event)
    second = projection.project_event(_record(), event)

    assert first.response is not None
    assert second.response is not None
    assert first.response.model_dump_json() == second.response.model_dump_json()
