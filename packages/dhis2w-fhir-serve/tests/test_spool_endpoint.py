"""`GET /spool`: the receipt envelopes with their lifecycle, re-read from disk on every request.

Two things are under test that nothing else covers. First, that the listing is a *live* view: the
forwarder moves files between the spool's three directories while this server runs, so a listing
answered from anything loaded at startup would keep reporting a queue that never empties. Second,
that a rejection carries the import report the forwarder left beside it - "rejected" with nothing
next to it is the one row a person cannot act on.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.service import ForwardImportIssue, ForwardImportOutcome
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import IMPORT_REPORT_SUFFIX, ResponseLifecycle, ResponseSpool
from fastapi import FastAPI

#: The service base the in-process client uses, matching every other serve test.
BASE_URL = "http://serve.test"

JSON_MEDIA_TYPE = "application/json"
FHIR_JSON_MEDIA_TYPE = "application/fhir+json"


def drain(project: FhirProject, response_id: str, lifecycle: ResponseLifecycle) -> Path:
    """Move one receipt the way `d2w fhir forward` moves it - a rename under a running server."""
    spool = ResponseSpool.at(project.project_root)
    destination = spool.directory_for(lifecycle)
    destination.mkdir(parents=True, exist_ok=True)
    moved = destination / f"{response_id}.json"
    (spool.directory_for(ResponseLifecycle.RECEIVED) / f"{response_id}.json").rename(moved)
    return moved


def write_report(project: FhirProject, response_id: str, report: ForwardImportOutcome) -> None:
    """Leave the sidecar import report beside a rejected receipt, as `move_to_rejected` does."""
    directory = ResponseSpool.at(project.project_root).directory_for(ResponseLifecycle.REJECTED)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{response_id}{IMPORT_REPORT_SUFFIX}").write_text(
        report.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
    )


@pytest.fixture
def bare_app(compiled_project: FhirProject) -> FastAPI:
    """The facade over a project nothing was ever captured into - the seeding `app` fixture is not used."""
    return create_app(ServeSettings(project_dir=compiled_project.project_root))


@pytest.fixture
async def bare_client(bare_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over a facade whose spool is empty."""
    async with bare_app.router.lifespan_context(bare_app):
        transport = httpx.ASGITransport(app=bare_app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


async def test_spool_lists_every_receipt_newest_first(client: httpx.AsyncClient) -> None:
    """The listing is the whole spool in received order, as plain JSON rather than a Bundle."""
    response = await client.get("/spool")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(JSON_MEDIA_TYPE)
    body = response.json()
    assert body["total"] == 3
    assert [row["response_id"] for row in body["responses"]] == ["receipt-newest", "receipt-middle", "receipt-oldest"]
    assert body["counts"] == {"received": 3, "forwarded": 0, "rejected": 0, "malformed": 0}


async def test_the_listing_states_the_form_the_receipt_answered(client: httpx.AsyncClient) -> None:
    """A row carries the canonical and the id it ends in, so a UI can join it to the form's title."""
    body = (await client.get("/spool")).json()

    row = next(row for row in body["responses"] if row["response_id"] == "receipt-newest")
    assert row["questionnaire"].endswith("/Questionnaire/d2-pr-anc-visit-q")
    assert row["questionnaire_id"] == "d2-pr-anc-visit-q"
    assert row["form_kind"] == "event"


async def test_the_listing_re_reads_the_directory_on_every_request(
    client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    """A drain that happens while the server is up shows up on the next request, with no restart.

    This is the whole reason the spool holds no index. `d2w fhir forward` is another process, and
    it renames files under this one.
    """
    before = (await client.get("/spool")).json()
    assert before["counts"] == {"received": 3, "forwarded": 0, "rejected": 0, "malformed": 0}

    drain(compiled_project, "receipt-oldest", ResponseLifecycle.FORWARDED)
    drain(compiled_project, "receipt-middle", ResponseLifecycle.REJECTED)

    after = (await client.get("/spool")).json()
    assert after["counts"] == {"received": 1, "forwarded": 1, "rejected": 1, "malformed": 0}
    assert {row["response_id"]: row["lifecycle"] for row in after["responses"]} == {
        "receipt-newest": "received",
        "receipt-oldest": "forwarded",
        "receipt-middle": "rejected",
    }


async def test_a_rejection_carries_what_dhis2_said(client: httpx.AsyncClient, compiled_project: FhirProject) -> None:
    """The sidecar report is rolled up onto the row: the status, the counts, and every issue named."""
    drain(compiled_project, "receipt-middle", ResponseLifecycle.REJECTED)
    write_report(
        compiled_project,
        "receipt-middle",
        ForwardImportOutcome(
            status="ERROR",
            message="Import process failed",
            ignored=2,
            issues=(
                ForwardImportIssue(error_code="E1120", subject="ImspTQPwCqd", message="Data element not found"),
                ForwardImportIssue(error_code="E1121", message="Period is not open"),
            ),
        ),
    )

    body = (await client.get("/spool")).json()

    row = next(row for row in body["responses"] if row["response_id"] == "receipt-middle")
    assert row["lifecycle"] == "rejected"
    assert row["rejection"]["status"] == "ERROR"
    assert row["rejection"]["message"] == "Import process failed"
    assert row["rejection"]["ignored"] == 2
    assert [issue["error_code"] for issue in row["rejection"]["issues"]] == ["E1120", "E1121"]
    assert row["rejection"]["issues"][0]["subject"] == "ImspTQPwCqd"


async def test_a_received_receipt_carries_no_rejection(client: httpx.AsyncClient) -> None:
    """Only a rejection has a report; every other row states none rather than an empty one."""
    body = (await client.get("/spool")).json()

    assert all(row["rejection"] is None for row in body["responses"])


async def test_a_rejection_with_an_unreadable_report_is_still_listed(
    client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    """A corrupt diagnostic is not a lost receipt: the row still says rejected, and says nothing more."""
    drain(compiled_project, "receipt-middle", ResponseLifecycle.REJECTED)
    directory = ResponseSpool.at(compiled_project.project_root).directory_for(ResponseLifecycle.REJECTED)
    (directory / f"receipt-middle{IMPORT_REPORT_SUFFIX}").write_text("{not json", encoding="utf-8")

    body = (await client.get("/spool")).json()

    row = next(row for row in body["responses"] if row["response_id"] == "receipt-middle")
    assert row["lifecycle"] == "rejected"
    assert row["rejection"] is None


async def test_an_empty_spool_lists_nothing(bare_client: httpx.AsyncClient) -> None:
    """A project nothing has been captured into answers an empty listing, not a refusal."""
    body = (await bare_client.get("/spool")).json()

    assert body == {
        "total": 0,
        "counts": {"received": 0, "forwarded": 0, "rejected": 0, "malformed": 0},
        "responses": [],
        "malformed": [],
        "self_url": "http://serve.test/spool?_count=50&page=bzBuMA",
        "previous_url": None,
        "next_url": None,
    }


async def test_the_read_catch_all_does_not_claim_the_listing(client: httpx.AsyncClient) -> None:
    """`/spool` is a fixed path mounted ahead of `/{resource_type}`, which would refuse it as a type."""
    response = await client.get("/spool")

    assert "resourceType" not in response.json()


async def test_a_forwarded_receipt_still_reads_back_as_fhir(
    client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    """Draining a receipt renames its file; the id a client was handed at capture time keeps resolving."""
    drain(compiled_project, "receipt-oldest", ResponseLifecycle.FORWARDED)

    read = await client.get("/QuestionnaireResponse/receipt-oldest")
    searched = await client.get("/QuestionnaireResponse")

    assert read.status_code == 200
    assert read.json()["id"] == "receipt-oldest"
    assert searched.json()["total"] == 3


async def test_the_capture_context_is_derived_from_the_stored_resource(
    capture_client: httpx.AsyncClient, tracker_response: dict[str, Any]
) -> None:
    """A tracker row states where it happened, whose it is, and how many answers it carries.

    The facts come out of the stored resource itself - the organisation-unit extension, the
    tracked-entity identifier on the subject, the enrollment - so the listing says them without a
    second read of anything.
    """
    posted = await capture_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(tracker_response),
        headers={"Content-Type": FHIR_JSON_MEDIA_TYPE},
    )
    assert posted.status_code == 201

    body = (await capture_client.get("/spool")).json()

    assert body["total"] == 1
    row = body["responses"][0]
    assert row["form_kind"] == "tracker-event"
    assert row["organisation_unit"] == "ImspTQPwCqd"
    assert row["tracked_entity"] == "tPpcmcRWO0g"
    assert row["tracker_enrollment"] == "gxMz7Qje7pk"
    assert row["status"] == "completed"
    assert row["answer_count"] > 0


async def test_an_aggregate_row_states_its_reporting_period(
    capture_client: httpx.AsyncClient, aggregate_response: dict[str, Any]
) -> None:
    """The ISO period and its type come off the D2Period extension, which is how an aggregate row is filed."""
    posted = await capture_client.post(
        "/QuestionnaireResponse",
        content=json.dumps(aggregate_response),
        headers={"Content-Type": FHIR_JSON_MEDIA_TYPE},
    )
    assert posted.status_code == 201

    row = (await capture_client.get("/spool")).json()["responses"][0]

    assert row["form_kind"] == "aggregate"
    assert row["period"] == "202607"
    assert row["period_type"] == "Monthly"
    assert row["organisation_unit"] == "ImspTQPwCqd"
