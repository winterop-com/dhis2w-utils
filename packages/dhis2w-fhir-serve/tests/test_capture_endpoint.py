"""`POST /QuestionnaireResponse` end to end: what a client gets back, and what the facade then serves."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings

FHIR_JSON = "application/fhir+json"

BASE_URL = "http://serve.test"

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"

TRACKER_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/ZzYYXq4fJie"
SYMPTOM_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-OsSymptom01-cs"
TEMPORAL_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/PrTemporal1"

#: Committed OperationOutcome bodies, so a change to what a client is told is a change to a file.
OUTCOME_GOLDEN_DIRECTORY = Path(__file__).resolve().parent / "golden"


def _outcome_golden(name: str) -> dict[str, Any]:
    """One committed rejection body."""
    parsed: dict[str, Any] = json.loads((OUTCOME_GOLDEN_DIRECTORY / name).read_text(encoding="utf-8"))
    return parsed


def _spooled(project: FhirProject, response_id: str) -> dict[str, Any]:
    """The receipt one accepted capture wrote to the spool directory."""
    path = project.project_root / ".serve" / "responses" / "received" / f"{response_id}.json"
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def _temporal_response(link_id: str, answer: dict[str, Any]) -> dict[str, Any]:
    """One submission against the temporal event form, answering a single question."""
    return {
        "resourceType": "QuestionnaireResponse",
        "extension": [{"url": f"{CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "event"}],
        "questionnaire": TEMPORAL_QUESTIONNAIRE,
        "status": "completed",
        "subject": {"reference": "Location/ImspTQPwCqd"},
        "authored": "2026-07-25T16:00:00Z",
        "item": [{"linkId": link_id, "answer": [answer]}],
    }


@pytest.mark.parametrize(
    ("fixture_name", "form_kind"),
    [
        ("aggregate_response", "aggregate"),
        ("event_response", "event"),
        ("tracker_response", "tracker-event"),
    ],
)
async def test_each_form_kind_is_created_and_then_served_from_its_location(
    fixture_name: str,
    form_kind: str,
    request: pytest.FixtureRequest,
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
) -> None:
    body: dict[str, Any] = request.getfixturevalue(fixture_name)

    created = await capture_client.post("/QuestionnaireResponse", json=body)

    assert created.status_code == 201
    assert created.headers["content-type"] == FHIR_JSON
    location = created.headers["Location"]
    assert location.startswith(f"{BASE_URL}/QuestionnaireResponse/")
    response_id = location.rsplit("/", 1)[-1]

    read = await capture_client.get(f"/QuestionnaireResponse/{response_id}")

    assert read.status_code == 200
    assert read.json() == {**body, "id": response_id}
    assert created.json()["issue"][0]["diagnostics"] == (
        f"stored response {response_id}; a stored response is the submission as received - "
        "a receipt, not a live view of DHIS2 data"
    )
    assert _spooled(capture_project, response_id)["form_kind"] == form_kind


async def test_a_created_response_is_found_by_the_questionnaire_it_answers(
    capture_client: httpx.AsyncClient, tracker_response: dict[str, Any]
) -> None:
    created = await capture_client.post("/QuestionnaireResponse", json=tracker_response)
    response_id = created.headers["Location"].rsplit("/", 1)[-1]

    found = await capture_client.get("/QuestionnaireResponse", params={"questionnaire": TRACKER_QUESTIONNAIRE})

    body = found.json()
    assert body["total"] == 1
    assert body["entry"][0]["fullUrl"] == f"{BASE_URL}/QuestionnaireResponse/{response_id}"


async def test_a_warning_rides_back_on_the_created_outcome(capture_client: httpx.AsyncClient) -> None:
    submission = _temporal_response("DeSymptoms01", {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "FEVER"}})

    created = await capture_client.post("/QuestionnaireResponse", json=submission)

    issues = created.json()["issue"]
    assert created.status_code == 201
    assert issues[1]["severity"] == "warning"
    assert issues[1]["code"] == "code-invalid"
    assert "the contract expects concept code 'OpFever0001'" in issues[1]["diagnostics"]


async def test_a_stored_warning_is_kept_on_the_receipt(
    capture_client: httpx.AsyncClient, capture_project: FhirProject
) -> None:
    submission = _temporal_response("DeSymptoms01", {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "FEVER"}})

    created = await capture_client.post("/QuestionnaireResponse", json=submission)
    response_id = created.headers["Location"].rsplit("/", 1)[-1]

    spooled = _spooled(capture_project, response_id)
    assert spooled["form_kind"] == "event"
    assert spooled["questionnaire"] == TEMPORAL_QUESTIONNAIRE
    assert "matched option OpFever0001 by dhis2-code" in spooled["warnings"][0]


@pytest.mark.parametrize("strict_codes", [True])
async def test_a_strict_facade_refuses_the_code_a_lenient_one_warns_about(
    strict_codes: bool, capture_client: httpx.AsyncClient
) -> None:
    submission = _temporal_response("DeSymptoms01", {"valueCoding": {"system": SYMPTOM_CODE_SYSTEM, "code": "FEVER"}})

    refused = await capture_client.post("/QuestionnaireResponse", json=submission)

    assert refused.status_code == 422
    assert refused.headers["content-type"] == FHIR_JSON
    assert refused.json()["issue"][0]["code"] == "code-invalid"


async def test_a_body_declared_in_a_media_type_this_server_does_not_read_is_415(
    capture_client: httpx.AsyncClient, aggregate_response: dict[str, Any]
) -> None:
    refused = await capture_client.post(
        "/QuestionnaireResponse", content=json.dumps(aggregate_response), headers={"Content-Type": "text/plain"}
    )
    found = await capture_client.get("/QuestionnaireResponse")

    assert refused.status_code == 415
    assert refused.headers["content-type"] == FHIR_JSON
    issue = refused.json()["issue"][0]
    assert refused.json()["resourceType"] == "OperationOutcome"
    assert issue["code"] == "not-supported"
    assert "text/plain" in issue["diagnostics"]
    assert found.json()["total"] == 0


@pytest.mark.parametrize(
    "content_type",
    [FHIR_JSON, "application/json", f"{FHIR_JSON}; charset=utf-8", "application/scim+json"],
)
async def test_every_json_spelling_of_the_content_type_is_accepted(
    content_type: str, capture_client: httpx.AsyncClient, aggregate_response: dict[str, Any]
) -> None:
    created = await capture_client.post(
        "/QuestionnaireResponse", content=json.dumps(aggregate_response), headers={"Content-Type": content_type}
    )

    assert created.status_code == 201


async def test_a_body_declaring_no_content_type_is_read_as_the_json_it_has_to_be(
    capture_client: httpx.AsyncClient, aggregate_response: dict[str, Any]
) -> None:
    created = await capture_client.post("/QuestionnaireResponse", content=json.dumps(aggregate_response))

    assert created.status_code == 201


async def test_a_bundle_is_refused_with_the_one_response_per_request_rule(
    capture_client: httpx.AsyncClient,
) -> None:
    refused = await capture_client.post("/QuestionnaireResponse", json={"resourceType": "Bundle", "type": "batch"})

    assert refused.status_code == 400
    assert refused.json() == _outcome_golden("outcome-bundle-posted.json")


async def test_a_response_declaring_no_form_type_is_refused(
    capture_client: httpx.AsyncClient, tracker_response: dict[str, Any]
) -> None:
    tracker_response["extension"] = [
        extension for extension in tracker_response["extension"] if not extension["url"].endswith("d2-form-type")
    ]

    refused = await capture_client.post("/QuestionnaireResponse", json=tracker_response)

    assert refused.status_code == 422
    assert refused.json() == _outcome_golden("outcome-no-form-type.json")


async def test_every_problem_with_the_answers_is_reported_at_once(
    capture_client: httpx.AsyncClient, tracker_response: dict[str, Any]
) -> None:
    tracker_response["item"][0]["answer"] = [{"valueString": "5.1"}]
    tracker_response["item"].append({"linkId": "DeMadeUp0001", "answer": [{"valueString": "x"}]})

    refused = await capture_client.post("/QuestionnaireResponse", json=tracker_response)

    assert refused.status_code == 422
    assert refused.json() == _outcome_golden("outcome-answers-refused.json")


async def test_nothing_is_stored_when_a_submission_is_refused(
    capture_client: httpx.AsyncClient, tracker_response: dict[str, Any]
) -> None:
    del tracker_response["questionnaire"]

    refused = await capture_client.post("/QuestionnaireResponse", json=tracker_response)
    found = await capture_client.get("/QuestionnaireResponse")

    assert refused.status_code == 422
    assert found.json()["total"] == 0


async def test_a_receipt_survives_a_restart_over_the_same_project(
    capture_client: httpx.AsyncClient, capture_project: FhirProject, tracker_response: dict[str, Any]
) -> None:
    created = await capture_client.post("/QuestionnaireResponse", json=tracker_response)
    response_id = created.headers["Location"].rsplit("/", 1)[-1]

    restarted = create_app(ServeSettings(project_dir=capture_project.project_root))
    async with restarted.router.lifespan_context(restarted):
        transport = httpx.ASGITransport(app=restarted)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            read = await http.get(f"/QuestionnaireResponse/{response_id}")

    assert read.status_code == 200
    assert read.json()["id"] == response_id


async def test_the_read_routes_still_answer_for_every_other_type(capture_client: httpx.AsyncClient) -> None:
    read = await capture_client.get("/Questionnaire/ZzYYXq4fJie")

    assert read.status_code == 200
    assert read.json()["url"] == TRACKER_QUESTIONNAIRE


async def test_creating_any_other_resource_type_is_not_allowed(capture_client: httpx.AsyncClient) -> None:
    refused = await capture_client.post("/Questionnaire", json={"resourceType": "Questionnaire"})

    assert refused.status_code == 405
    assert refused.json()["issue"][0]["code"] == "not-supported"
