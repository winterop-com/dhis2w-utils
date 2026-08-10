"""The capture phase machine: what clears every phase, and what each phase refuses.

The three golden QuestionnaireResponses the dhis2w-fhir package publishes are the contract a
compliant client builds against, so every clean-path test posts one of them unaltered. Every other
test starts from a golden and breaks exactly one thing, which is what keeps the diagnostics honest:
the issue reported is the difference between the two documents and nothing else.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from dhis2w_fhir_serve.capture import (
    CaptureIndexCache,
    CaptureIssue,
    CaptureNaming,
    CaptureRejection,
    ValidatedCapture,
    validate_response,
)
from dhis2w_fhir_serve.store import ResourceStore

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"

AGGREGATE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/BfMAe6Itzgt"
TEMPORAL_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/PrTemporal1"
ANC_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/PsAncVisit1"
SYMPTOM_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-OsSymptom01-cs"
INFANT_FEEDING_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-x31y45jvIQL-cs"

TRACKED_ENTITY_SYSTEM = "http://dhis2.org/fhir/id/tracked-entity"
TRACKER_ENROLLMENT_SYSTEM = "http://dhis2.org/fhir/id/tracker-enrollment"


def _accept(
    body: dict[str, Any],
    indexes: CaptureIndexCache,
    naming: CaptureNaming,
    store: ResourceStore,
    strict_codes: bool = False,
) -> ValidatedCapture:
    """Validate one submission, failing the test when it is refused."""
    return validate_response(json.dumps(body).encode(), indexes, naming, store, strict_codes)


def _refuse(
    body: dict[str, Any],
    indexes: CaptureIndexCache,
    naming: CaptureNaming,
    store: ResourceStore,
    strict_codes: bool = False,
) -> CaptureRejection:
    """Validate one submission, failing the test when it is accepted."""
    with pytest.raises(CaptureRejection) as raised:
        validate_response(json.dumps(body).encode(), indexes, naming, store, strict_codes)
    return raised.value


def _errors(rejection: CaptureRejection) -> tuple[CaptureIssue, ...]:
    """Only the issues that refused the submission."""
    return tuple(issue for issue in rejection.issues if issue.is_error())


def _diagnostics(issues: tuple[CaptureIssue, ...]) -> str:
    """Every issue's diagnostics, joined, for one readable assertion."""
    return " | ".join(issue.diagnostics or "" for issue in issues)


def _temporal_response(**answers: dict[str, Any]) -> dict[str, Any]:
    """One submission against the temporal event form, answering only the questions named."""
    return {
        "resourceType": "QuestionnaireResponse",
        "extension": [{"url": f"{CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "event"}],
        "questionnaire": TEMPORAL_QUESTIONNAIRE,
        "status": "completed",
        "subject": {"reference": "Location/ImspTQPwCqd"},
        "authored": "2026-07-25T16:00:00Z",
        "item": [{"linkId": link_id, "answer": [answer]} for link_id, answer in answers.items()],
    }


def _anc_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """One submission against the ANC tracker stage, which carries a required and a bounded question."""
    return {
        "resourceType": "QuestionnaireResponse",
        "extension": [
            {
                "url": f"{CANONICAL}/StructureDefinition/d2-organisation-unit",
                "valueReference": {"reference": "Location/ImspTQPwCqd"},
            },
            {
                "url": f"{CANONICAL}/StructureDefinition/d2-tracker-enrollment",
                "valueIdentifier": {"system": TRACKER_ENROLLMENT_SYSTEM, "value": "gxMz7Qje7pk"},
            },
            {"url": f"{CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "tracker-event"},
        ],
        "questionnaire": ANC_QUESTIONNAIRE,
        "status": "completed",
        "subject": {"identifier": {"system": TRACKED_ENTITY_SYSTEM, "value": "tPpcmcRWO0g"}, "type": "Patient"},
        "authored": "2026-07-13T15:00:00Z",
        "item": items,
    }


def test_the_aggregate_golden_is_accepted_as_published(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    accepted = _accept(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert accepted.form_kind == "aggregate"
    assert accepted.canonical == AGGREGATE_QUESTIONNAIRE
    assert accepted.warnings == ()


def test_the_event_golden_is_accepted_on_the_shape_its_questionnaire_declares(
    event_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    accepted = _accept(event_response, capture_indexes, capture_naming, capture_store)

    assert accepted.form_kind == "event"
    assert accepted.warnings == ()


def test_the_published_event_example_answers_the_flat_shape_its_questionnaire_declares(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    load_golden: Any,
) -> None:
    """The example answers flat linkIds - an event data value carries no category option combo - and validates clean."""
    published = load_golden("QuestionnaireResponse-EVTsupVis01-example-1.json")

    accepted = _accept(published, capture_indexes, capture_naming, capture_store)

    assert accepted.form_kind == "event"
    assert all("." not in item["linkId"] for item in published["item"])


@pytest.mark.parametrize("strict_codes", [False, True])
def test_the_tracker_golden_is_accepted_however_strict_the_server_is(
    strict_codes: bool,
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    accepted = _accept(tracker_response, capture_indexes, capture_naming, capture_store, strict_codes)

    assert accepted.form_kind == "tracker-event"
    assert accepted.warnings == ()


def test_a_body_that_is_not_json_is_a_bad_request(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    with pytest.raises(CaptureRejection) as raised:
        validate_response(b"{not json", capture_indexes, capture_naming, capture_store, False)

    assert raised.value.http_status == 400
    assert "not valid JSON" in _diagnostics(raised.value.issues)


def test_a_body_that_is_not_an_object_is_a_bad_request(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    with pytest.raises(CaptureRejection) as raised:
        validate_response(b"[]", capture_indexes, capture_naming, capture_store, False)

    assert raised.value.http_status == 400
    assert "not a JSON object" in _diagnostics(raised.value.issues)


def test_a_bundle_is_refused_with_the_one_response_per_request_rule(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    rejection = _refuse(
        {"resourceType": "Bundle", "type": "transaction"}, capture_indexes, capture_naming, capture_store
    )

    assert rejection.http_status == 400
    assert "one QuestionnaireResponse per request" in _diagnostics(rejection.issues)


def test_another_resource_type_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    rejection = _refuse({"resourceType": "Patient"}, capture_indexes, capture_naming, capture_store)

    assert rejection.http_status == 400
    assert "not a `Patient`" in _diagnostics(rejection.issues)


def test_a_document_that_is_not_r4_shaped_names_the_elements_it_stumbled_on(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["status"] = "half-done"

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert rejection.http_status == 400
    assert [issue.expression for issue in rejection.issues] == ["status"]


def test_a_response_declaring_no_form_type_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["extension"] = [
        extension for extension in tracker_response["extension"] if not extension["url"].endswith("d2-form-type")
    ]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert rejection.http_status == 422
    assert "no DHIS2 form type" in _diagnostics(rejection.issues)


def test_a_response_declaring_two_form_types_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["extension"].append({"url": capture_naming.form_type_url, "valueCode": "event"})

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "more than one DHIS2 form type" in _diagnostics(rejection.issues)


def test_a_form_kind_no_generated_questionnaire_declares_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    for extension in tracker_response["extension"]:
        if extension["url"] == capture_naming.form_type_url:
            extension["valueCode"] = "dataset"

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "not a DHIS2 form kind this server captures" in _diagnostics(rejection.issues)


def test_a_response_naming_no_questionnaire_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    del tracker_response["questionnaire"]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "names no questionnaire" in _diagnostics(rejection.issues)


def test_an_aggregate_response_has_to_be_reported_as_completed(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    aggregate_response["status"] = "in-progress"

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "has to be `completed`" in _diagnostics(rejection.issues)


def test_an_aggregate_response_carries_a_reporting_period(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    aggregate_response["extension"] = [
        extension for extension in aggregate_response["extension"] if extension["url"] != capture_naming.period_url
    ]

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "exactly one" in _diagnostics(rejection.issues)
    assert capture_naming.period_url in _diagnostics(rejection.issues)


def test_an_aggregate_subject_is_the_organisation_unit_it_reports_for(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    aggregate_response["subject"] = {"reference": "Organization/ImspTQPwCqd"}

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "is not a `Location/<uid>` reference" in _diagnostics(rejection.issues)


def test_a_period_that_is_not_a_dhis2_iso_period_is_refused(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    _period(aggregate_response, capture_naming)["extension"][0]["valueString"] = "July-2026"

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "not a DHIS2 ISO period" in _diagnostics(rejection.issues)


def test_a_period_type_that_the_iso_period_does_not_read_as_is_refused(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    _period(aggregate_response, capture_naming)["extension"][1]["valueCode"] = "Weekly"

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "is a `Monthly` period, not a `Weekly` one" in _diagnostics(rejection.issues)


def test_a_date_range_disagreeing_with_the_iso_period_is_a_warning(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    _period(aggregate_response, capture_naming)["extension"][2]["valuePeriod"] = {
        "start": "2026-07-01",
        "end": "2026-07-15",
    }

    accepted = _accept(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "the ISO period is what is captured" in _diagnostics(accepted.warnings)


def test_an_event_response_records_when_it_was_captured(
    event_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    del event_response["authored"]

    rejection = _refuse(event_response, capture_indexes, capture_naming, capture_store)

    assert "records no `authored` instant" in _diagnostics(rejection.issues)


def test_an_authored_instant_without_a_zone_is_refused(
    event_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    event_response["authored"] = "2026-07-25T16:00:00"

    rejection = _refuse(event_response, capture_indexes, capture_naming, capture_store)

    assert "is not an R4 dateTime" in _diagnostics(rejection.issues)


def test_a_tracker_subject_named_under_another_system_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["subject"]["identifier"]["system"] = "http://example.org/patients"

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert capture_naming.tracked_entity_system in _diagnostics(rejection.issues)


def test_a_tracker_subject_reference_is_ignored_with_a_warning(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["subject"]["reference"] = "Patient/tPpcmcRWO0g"

    accepted = _accept(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "is ignored" in _diagnostics(accepted.warnings)


def test_a_tracker_event_names_the_organisation_unit_it_was_captured_at(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["extension"] = [
        extension
        for extension in tracker_response["extension"]
        if extension["url"] != capture_naming.organisation_unit_url
    ]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert capture_naming.organisation_unit_url in _diagnostics(rejection.issues)


def test_a_tracker_enrollment_named_under_another_system_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    for extension in tracker_response["extension"]:
        if extension["url"] == capture_naming.tracker_enrollment_url:
            extension["valueIdentifier"]["system"] = "http://example.org/enrollments"

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert capture_naming.tracker_enrollment_system in _diagnostics(rejection.issues)


def test_a_questionnaire_the_facade_does_not_serve_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["questionnaire"] = f"{CANONICAL}/Questionnaire/NeverPublish"

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert rejection.http_status == 422
    assert "no Questionnaire with canonical" in _diagnostics(rejection.issues)


def test_a_form_kind_that_the_questionnaire_does_not_declare_is_refused(
    event_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    event_response["questionnaire"] = ANC_QUESTIONNAIRE

    rejection = _refuse(event_response, capture_indexes, capture_naming, capture_store)

    assert "is a `tracker-event` form" in _diagnostics(rejection.issues)


def test_an_answer_on_a_group_is_refused(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    aggregate_response["item"][0]["answer"] = [{"valueInteger": 1}]

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert "is a group of the form" in _diagnostics(rejection.issues)


def test_a_link_id_the_form_does_not_ask_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["item"].append({"linkId": "DeMadeUp0001", "answer": [{"valueString": "x"}]})

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "is not a question of" in _diagnostics(rejection.issues)


def test_a_question_answered_twice_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["item"].append({"linkId": "GQY2lXrypjO", "answer": [{"valueDecimal": 6.2}]})

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "is answered more than once" in _diagnostics(rejection.issues)


def test_an_answer_on_the_wrong_value_element_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["item"][0]["answer"] = [{"valueString": "5.1"}]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "carries `valueDecimal`, not `valueString`" in _diagnostics(rejection.issues)


def test_an_answer_carrying_no_value_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["item"][0]["answer"] = [{}]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "carries no value" in _diagnostics(rejection.issues)


def test_an_answer_carrying_two_values_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["item"][0]["answer"] = [{"valueDecimal": 5.1, "valueString": "5.1"}]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "carries more than one value" in _diagnostics(rejection.issues)


def test_more_than_one_answer_to_a_single_answer_question_is_refused(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    tracker_response["item"][0]["answer"] = [{"valueDecimal": 5.1}, {"valueDecimal": 6.1}]

    rejection = _refuse(tracker_response, capture_indexes, capture_naming, capture_store)

    assert "takes one answer, and 2 were sent" in _diagnostics(rejection.issues)


@pytest.mark.parametrize(
    ("link_id", "answer", "expected"),
    [
        ("DeVisitDate1", {"valueDate": "2026-07"}, "not a full calendar date"),
        ("DeVisitDate1", {"valueDate": "2026-02-30"}, "not a full calendar date"),
        ("DeVisitStamp", {"valueDateTime": "2026-07-25T16:00:00"}, "not an R4 dateTime"),
        ("DeVisitTime1", {"valueTime": "25:00:00"}, "not an R4 time"),
    ],
)
def test_a_temporal_answer_is_checked_against_its_r4_primitive(
    link_id: str,
    answer: dict[str, Any],
    expected: str,
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    rejection = _refuse(_temporal_response(**{link_id: answer}), capture_indexes, capture_naming, capture_store)

    assert expected in _diagnostics(rejection.issues)


def test_a_full_calendar_date_and_a_zoned_stamp_are_accepted(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(
        DeVisitDate1={"valueDate": "2026-07-25"},
        DeVisitTime1={"valueTime": "16:00:00"},
        DeVisitStamp={"valueDateTime": "2026-07-25T16:00:00Z"},
        DeVisitLink1={"valueUri": "https://example.org/visit/1"},
    )

    assert _accept(body, capture_indexes, capture_naming, capture_store).warnings == ()


@pytest.mark.parametrize("value", [-0.5, 100.5])
def test_a_numeric_answer_outside_the_questions_bounds_is_refused(
    value: float,
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    body = _temporal_response(DeCoverage01={"valueDecimal": value})

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "minimum 0" in _diagnostics(rejection.issues) or "maximum 100" in _diagnostics(rejection.issues)


def test_selecting_the_same_option_twice_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response()
    body["item"] = [
        {
            "linkId": "DeSymptoms01",
            "answer": [
                {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "OpFever0001"}},
                {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "OpFever0001"}},
            ],
        }
    ]

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "selects OpFever0001 more than once" in _diagnostics(rejection.issues)


def test_a_repeating_question_takes_several_distinct_selections(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response()
    body["item"] = [
        {
            "linkId": "DeSymptoms01",
            "answer": [
                {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "OpFever0001"}},
                {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "OpCough0001"}},
            ],
        }
    ]

    assert _accept(body, capture_indexes, capture_naming, capture_store).warnings == ()


def test_a_code_sent_as_the_dhis2_option_code_is_accepted_with_a_warning(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(DeSymptoms01={"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "FEVER"}})

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert _diagnostics(accepted.warnings) == (
        "linkId DeSymptoms01: code 'FEVER' matched option OpFever0001 by dhis2-code; "
        "the contract expects concept code 'OpFever0001'"
    )


def test_a_strict_server_refuses_the_dhis2_option_code(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(DeSymptoms01={"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "FEVER"}})

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes=True)

    assert "not in the served terminology" in _diagnostics(rejection.issues)


def test_an_unknown_code_is_a_warning_by_default_and_an_error_when_strict(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(DeSymptoms01={"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "OpRash00001"}})

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)
    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes=True)

    assert "not in the served terminology" in _diagnostics(accepted.warnings)
    assert "not in the served terminology" in _diagnostics(_errors(rejection))


def test_a_coding_from_another_code_system_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(
        DeSymptoms01={"valueCoding": {"system": INFANT_FEEDING_CODE_SYSTEM, "code": "OpFever0001"}}
    )

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is answered from" in _diagnostics(rejection.issues)


def test_a_coding_with_no_code_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(DeSymptoms01={"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "display": "Fever"}})

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "a coding with no code" in _diagnostics(rejection.issues)


def test_a_question_bound_to_unpublished_terminology_is_stored_unchecked(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _temporal_response(DeOpenBind01={"valueCoding": {"code": "whatever"}})

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert "does not publish" in _diagnostics(accepted.warnings)


def test_a_required_question_left_unanswered_is_a_warning(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _anc_response([{"linkId": "DeAncBpSys1", "answer": [{"valueInteger": 120}]}])

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert "is required by the form and was not answered" in _diagnostics(accepted.warnings)


def test_a_required_question_below_its_minimum_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    body = _anc_response([{"linkId": "DeAncVisNo1", "answer": [{"valueInteger": 0}]}])

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is below the minimum 1" in _diagnostics(rejection.issues)


def _period(response: dict[str, Any], naming: CaptureNaming) -> dict[str, Any]:
    """The D2Period extension of one aggregate submission."""
    for extension in response["extension"]:
        if extension["url"] == naming.period_url:
            found: dict[str, Any] = extension
            return found
    raise AssertionError("the golden aggregate response carries no period extension")
