"""The viewer posture: what a server serving `[serve] capture = false` answers, and what it still answers.

The dial removes exactly one interaction. A submission is refused in FHIR's own terms, naming the key,
and `/metadata` stops declaring `create` - while every receipt the project already holds is read,
searched, and counted at the same addresses, and `$generate` keeps answering, being a read of a
published form. That split is the whole decision, so it is asserted from both sides here: what goes,
and what pointedly does not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool, StoredResponseEnvelope
from fastapi import FastAPI

FHIR_JSON = "application/fhir+json"

BASE_URL = "http://serve.test"

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"

#: The form the read-shaped operation is invoked on, which every posture answers.
AGGREGATE_FORM = "BfMAe6Itzgt"


def _receipt(response_id: str) -> StoredResponseEnvelope:
    """One receipt already on disk when the viewer-posture process starts - a capture from before."""
    return StoredResponseEnvelope(
        response_id=response_id,
        received_at="2026-08-01T09:00:00Z",
        form_kind="aggregate",
        questionnaire=f"{CANONICAL}/Questionnaire/{AGGREGATE_FORM}",
        response={
            "resourceType": "QuestionnaireResponse",
            "id": response_id,
            "questionnaire": f"{CANONICAL}/Questionnaire/{AGGREGATE_FORM}",
            "status": "completed",
        },
    )


@pytest.fixture
def viewer_app(capture_project: FhirProject) -> FastAPI:
    """The golden project served as a viewer, over a spool that already holds one receipt."""
    ResponseSpool.at(capture_project.project_root).save(_receipt("receipt-from-before"))
    return create_app(ServeSettings(project_dir=capture_project.project_root, capture=False))


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over the viewer-posture facade, with the lifespan run around the test."""
    async with viewer_app.router.lifespan_context(viewer_app):
        transport = httpx.ASGITransport(app=viewer_app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


def _response_entry(body: dict[str, Any]) -> dict[str, Any]:
    """The QuestionnaireResponse entry of one CapabilityStatement."""
    entries = body["rest"][0]["resource"]
    return next(entry for entry in entries if entry["type"] == "QuestionnaireResponse")


async def test_a_submission_is_refused_in_fhirs_own_terms_naming_the_key(
    viewer_client: httpx.AsyncClient, aggregate_response: dict[str, Any]
) -> None:
    """405 with an OperationOutcome: the address is served, and the create interaction is what is gone."""
    posted = await viewer_client.post(
        "/QuestionnaireResponse", json=aggregate_response, headers={"content-type": FHIR_JSON}
    )

    assert posted.status_code == 405
    assert posted.headers["content-type"].startswith(FHIR_JSON)
    issue = posted.json()["issue"][0]
    assert issue["severity"] == "error"
    assert issue["code"] == "not-supported"
    # The operator has to read this as a decision their project wrote down, not a missing feature.
    assert "[serve] capture" in issue["diagnostics"]


async def test_the_statement_declares_no_create_and_keeps_every_read(viewer_client: httpx.AsyncClient) -> None:
    """A statement declaring `create` here would advertise the one interaction every request to it refuses."""
    entry = _response_entry((await viewer_client.get("/metadata")).json())

    assert [interaction["code"] for interaction in entry["interaction"]] == ["read", "search-type"]
    # The profiles stay: they are what the receipts on disk conform to, and a reader still resolves them.
    assert entry["supportedProfile"]


async def test_a_capturing_server_declares_create_beside_the_reads(capture_client: httpx.AsyncClient) -> None:
    """The other half of the same claim, so the difference is the dial rather than the fixture."""
    entry = _response_entry((await capture_client.get("/metadata")).json())

    assert [interaction["code"] for interaction in entry["interaction"]] == ["create", "read", "search-type"]


async def test_the_receipts_this_project_already_holds_are_still_served(viewer_client: httpx.AsyncClient) -> None:
    """An id handed out at capture time must not expire on the day somebody edited one line of fhir.toml."""
    read = await viewer_client.get("/QuestionnaireResponse/receipt-from-before")

    assert read.status_code == 200
    assert read.json()["id"] == "receipt-from-before"

    searched = await viewer_client.get("/QuestionnaireResponse")

    assert searched.status_code == 200
    assert [entry["resource"]["id"] for entry in searched.json()["entry"]] == ["receipt-from-before"]


async def test_the_spool_still_counts_what_it_holds(viewer_client: httpx.AsyncClient) -> None:
    """The queue is a fact about receipts already taken, and a drain of them is still ahead."""
    body = (await viewer_client.get("/spool")).json()

    assert body["total"] == 1


async def test_the_read_shaped_operation_still_answers(viewer_client: httpx.AsyncClient) -> None:
    """`$generate` reads a published form and answers with a draft; it writes nothing, so it stays."""
    generated = await viewer_client.get(f"/Questionnaire/{AGGREGATE_FORM}/$generate")

    assert generated.status_code == 200
    assert generated.json()["resourceType"] == "QuestionnaireResponse"


async def test_the_settings_the_screens_read_carry_the_posture(viewer_client: httpx.AsyncClient) -> None:
    """The screens gate their Submit on this, so a form says the fact rather than posting into a refusal."""
    assert (await viewer_client.get("/uiconfig")).json()["capture"] is False


async def test_a_capturing_server_states_the_same_flag_the_other_way(capture_client: httpx.AsyncClient) -> None:
    """Always stated, never inferred from absence - the screens read one field either way."""
    assert (await capture_client.get("/uiconfig")).json()["capture"] is True
