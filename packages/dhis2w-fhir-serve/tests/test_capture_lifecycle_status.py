"""A correction and a withdrawal at capture time: refused where the project's dial is off, stored where it is on.

R4 spells both on the response itself - `amended` corrects a receipt this project already forwarded,
`entered-in-error` retracts one - and `[forward] corrections` / `[forward] withdrawals` in `fhir.toml`
say whether this deployment receives them. Both default to off.

What is under test is the pair of answers that follow. With the dial off the submission is refused at
capture with a 422 naming the key, rather than spooled for a drain that would never act on it - a
receipt accepted and never forwarded tells a client "kept" about a fact that never reaches DHIS2.
With the dial on the submission is stored like any other receipt, its status preserved on disk, which
is what the later slices of `docs/fhir/design/data-lifecycle.md` read.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capture.validate import (
    AMENDED_STATUS,
    CORRECTIONS_CONFIG_KEY,
    ENTERED_IN_ERROR_STATUS,
    WITHDRAWALS_CONFIG_KEY,
)
from dhis2w_fhir_serve.settings import ServeSettings
from fastapi import FastAPI

BASE_URL = "http://serve.test"

FHIR_JSON = "application/fhir+json"

#: The `[forward]` table a project states to receive both kinds of marked submission.
BOTH_DIALS_ON = """
[forward]
corrections = "amend"
withdrawals = "retract"
"""


def _with_status(response: dict[str, Any], status: str) -> dict[str, Any]:
    """One golden submission, declaring the lifecycle status under test."""
    return {**response, "status": status}


def _dial_project(project: FhirProject, table: str) -> FhirProject:
    """The same project with a `[forward]` table appended to its `fhir.toml`.

    The file is what the facade reads: `create_app` loads the project at startup, so a table written
    before the lifespan runs is the one the capture path validates against.
    """
    config_path = project.config_path
    config_path.write_text(config_path.read_text(encoding="utf-8") + table, encoding="utf-8")
    return project


async def _client(project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over one project, with the lifespan run around the caller."""
    app: FastAPI = create_app(ServeSettings(project_dir=project.project_root))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


@pytest.fixture
async def dialled_client(capture_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """A facade over a project that receives both corrections and withdrawals."""
    async for http in _client(_dial_project(capture_project, BOTH_DIALS_ON)):
        yield http


def _receipt(project: FhirProject, response_id: str) -> dict[str, Any]:
    """The receipt one accepted capture wrote into `received/`."""
    path = project.project_root / ".serve" / "responses" / "received" / f"{response_id}.json"
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def _diagnostics(body: dict[str, Any]) -> str:
    """Every diagnostic of one OperationOutcome, joined so a test can read the whole answer at once."""
    return " ".join(issue.get("diagnostics", "") for issue in body["issue"])


@pytest.mark.parametrize(
    ("status", "config_key", "posture"),
    [
        (AMENDED_STATUS, CORRECTIONS_CONFIG_KEY, "amend"),
        (ENTERED_IN_ERROR_STATUS, WITHDRAWALS_CONFIG_KEY, "retract"),
    ],
)
async def test_a_marked_submission_is_refused_with_the_key_that_would_receive_it(
    capture_client: httpx.AsyncClient,
    event_response: dict[str, Any],
    status: str,
    config_key: str,
    posture: str,
) -> None:
    """422, and the refusal names the `fhir.toml` key and the value that would accept the submission."""
    posted = await capture_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(_with_status(event_response, status)),
        headers={"content-type": FHIR_JSON},
    )

    assert posted.status_code == 422
    body = posted.json()
    assert body["resourceType"] == "OperationOutcome"
    assert body["issue"][0]["expression"] == ["QuestionnaireResponse.status"]
    diagnostics = _diagnostics(body)
    assert status in diagnostics
    assert config_key in diagnostics
    assert f"`{posture}`" in diagnostics


@pytest.mark.parametrize("status", [AMENDED_STATUS, ENTERED_IN_ERROR_STATUS])
async def test_nothing_is_spooled_when_the_dial_is_off(
    capture_client: httpx.AsyncClient, capture_project: FhirProject, event_response: dict[str, Any], status: str
) -> None:
    """A refusal writes no receipt: the queue holds what will be forwarded, not what was turned away."""
    await capture_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(_with_status(event_response, status)),
        headers={"content-type": FHIR_JSON},
    )

    listing = (await capture_client.get("/facade/spool")).json()

    assert listing["total"] == 0
    assert list((capture_project.project_root / ".serve" / "responses" / "received").glob("*.json")) == []


@pytest.mark.parametrize("status", [AMENDED_STATUS, ENTERED_IN_ERROR_STATUS])
async def test_a_marked_submission_is_stored_with_its_status_where_the_dial_is_on(
    dialled_client: httpx.AsyncClient, capture_project: FhirProject, event_response: dict[str, Any], status: str
) -> None:
    """201, and the stored receipt is the submission as it arrived - the status included."""
    posted = await dialled_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(_with_status(event_response, status)),
        headers={"content-type": FHIR_JSON},
    )

    assert posted.status_code == 201, posted.text
    response_id = posted.headers["Location"].rsplit("/", 1)[-1]
    stored = _receipt(capture_project, response_id)
    assert stored["response"]["status"] == status
    assert stored["form_kind"] == "event"
    assert stored["response"]["item"] == event_response["item"]


@pytest.mark.parametrize("status", [AMENDED_STATUS, ENTERED_IN_ERROR_STATUS])
async def test_a_stored_marked_submission_is_a_queued_receipt_like_any_other(
    dialled_client: httpx.AsyncClient, event_response: dict[str, Any], status: str
) -> None:
    """The spool row states the status and nothing else about it: what a drain does with it is a later slice."""
    await dialled_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(_with_status(event_response, status)),
        headers={"content-type": FHIR_JSON},
    )

    listing = (await dialled_client.get("/facade/spool")).json()

    assert listing["counts"]["received"] == 1
    row = listing["responses"][0]
    assert row["lifecycle"] == "received"
    assert row["status"] == status


async def test_one_dial_receives_only_its_own_status(
    capture_project: FhirProject, event_response: dict[str, Any]
) -> None:
    """`corrections = "amend"` says nothing about withdrawals: the other status is still refused, by its own key."""
    dialled = _dial_project(capture_project, '\n[forward]\ncorrections = "amend"\n')

    async for http in _client(dialled):
        amended = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(_with_status(event_response, AMENDED_STATUS)),
            headers={"content-type": FHIR_JSON},
        )
        withdrawn = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(_with_status(event_response, ENTERED_IN_ERROR_STATUS)),
            headers={"content-type": FHIR_JSON},
        )

        assert amended.status_code == 201, amended.text
        assert withdrawn.status_code == 422
        assert WITHDRAWALS_CONFIG_KEY in _diagnostics(withdrawn.json())


async def test_an_amended_aggregate_response_is_still_refused_by_its_own_profile(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """The dial says this project receives corrections; the aggregate contract still pins `completed`.

    Widening `AGGREGATE_REQUIRED_STATUS` to admit `amended` is a later slice of
    `docs/fhir/design/data-lifecycle.md`, and until it lands the aggregate profile is what refuses -
    by its own rule, naming its own reason, rather than by the dial.
    """
    dialled = _dial_project(capture_project, BOTH_DIALS_ON)

    async for http in _client(dialled):
        posted = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(_with_status(aggregate_response, AMENDED_STATUS)),
            headers={"content-type": FHIR_JSON},
        )

        assert posted.status_code == 422
        diagnostics = _diagnostics(posted.json())
        assert "stored as reported" in diagnostics
        assert CORRECTIONS_CONFIG_KEY not in diagnostics


async def test_an_unmarked_submission_is_untouched_by_either_dial(
    capture_client: httpx.AsyncClient, event_response: dict[str, Any]
) -> None:
    """The dials govern a marked submission; an ordinary `completed` capture is received as it always was."""
    posted = await capture_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(event_response),
        headers={"content-type": FHIR_JSON},
    )

    assert posted.status_code == 201, posted.text
    assert event_response["status"] == "completed"


async def test_the_refusal_is_the_only_thing_said_about_a_correction(
    capture_client: httpx.AsyncClient, event_response: dict[str, Any]
) -> None:
    """A submission this project does not receive is answered with that, not with the form's own rules.

    The phase runs before the profile invariants, so a client that also left out the `authored` instant
    is told the one thing that decides the request rather than a list it cannot act on.
    """
    incomplete = {key: value for key, value in event_response.items() if key != "authored"}

    posted = await capture_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(_with_status(incomplete, AMENDED_STATUS)),
        headers={"content-type": FHIR_JSON},
    )

    assert posted.status_code == 422
    body = posted.json()
    assert len(body["issue"]) == 1
    assert CORRECTIONS_CONFIG_KEY in _diagnostics(body)
