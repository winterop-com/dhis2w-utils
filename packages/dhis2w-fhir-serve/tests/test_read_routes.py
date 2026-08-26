"""`GET /{type}/{id}`: what the facade serves, what it refuses, and what it holds back."""

from __future__ import annotations

import json

import httpx
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.spool import StoredResponseEnvelope

FHIR_JSON = "application/fhir+json"


async def test_read_returns_the_compiled_file_verbatim(
    client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    compiled = compiled_project.ig_directory / "fsh-generated" / "resources" / "Questionnaire-d2-pr-anc-visit-q.json"

    response = await client.get("/Questionnaire/d2-pr-anc-visit-q")

    assert response.status_code == 200
    assert response.json() == json.loads(compiled.read_text(encoding="utf-8"))


async def test_read_answers_as_fhir_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire/d2-pr-anc-visit-q")

    assert response.headers["content-type"] == FHIR_JSON


async def test_read_serves_the_predefined_tree_too(client: httpx.AsyncClient) -> None:
    response = await client.get("/Organization/X")

    assert response.status_code == 200
    assert response.json()["name"] == "Sierra Leone"


async def test_read_of_an_unknown_id_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == FHIR_JSON
    body = response.json()
    assert body["resourceType"] == "OperationOutcome"
    assert body["issue"][0]["code"] == "not-found"
    assert "nope" in body["issue"][0]["diagnostics"]


async def test_read_of_an_unserved_type_is_not_supported(client: httpx.AsyncClient) -> None:
    response = await client.get("/Patient/anything")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-supported"


async def test_a_profile_the_guide_publishes_is_read_like_every_other_resource(
    client: httpx.AsyncClient,
) -> None:
    """A served project hosts its own guide, so a profile it published is answered at its own address."""
    response = await client.get("/StructureDefinition/d2-aggregate-response")

    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON
    body = response.json()
    assert body["resourceType"] == "StructureDefinition"
    assert body["url"] == "http://example.org/fhir/StructureDefinition/d2-aggregate-response"
    assert body["type"] == "QuestionnaireResponse"


async def test_reading_a_receipt_returns_the_submission_as_received(
    client: httpx.AsyncClient, stored_responses: tuple[StoredResponseEnvelope, ...]
) -> None:
    envelope = stored_responses[1]

    response = await client.get(f"/QuestionnaireResponse/{envelope.response_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON
    assert response.json() == envelope.response


async def test_reading_an_unknown_receipt_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/QuestionnaireResponse/receipt-missing")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-found"
