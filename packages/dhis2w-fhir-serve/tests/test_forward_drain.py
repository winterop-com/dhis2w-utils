"""The seam between the two processes: what `d2w fhir forward` writes is what the running facade reads.

Everywhere else the two halves are tested apart. The serve suite moves receipts with a rename of its
own and hand-writes the sidecars it then reads back, and the forwarder suite proves the renames and
sidecars it writes without a facade in the room. Both can be right about a convention they no longer
share, and neither test would notice.

So this one runs the real thing on both sides. A facade captures two submissions; the real
`forward_responses` drains that spool against a respx-mocked instance that takes one payload and
refuses the other with a body harvested off a live 2.42; then the same still-running facade is asked
for `/spool`, and what it answers has to be what the forwarder actually left on disk - the two
lifecycles, the rejection rolled up out of the report beside the refused receipt, and the import
counts off the report beside the accepted one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.service import forward_responses
from dhis2w_fhir_serve.spool import (
    FORWARDED_RESPONSES_RELATIVE_PATH,
    IMPORT_REPORT_SUFFIX,
    REJECTED_RESPONSES_RELATIVE_PATH,
)

#: The instance the drain is pointed at. Only respx answers on it.
_BASE_URL = "https://dhis2.example"

#: The harvested 409 the aggregate post is refused with, off the dhis2w-fhir suite that keeps the
#: bodies. Reused rather than re-typed: the point of this test is that the forwarder's real output
#: reaches the facade, and a hand-written 409 would be one more thing invented for the occasion.
_HARVESTED_409 = (
    Path(__file__).resolve().parents[2]
    / "dhis2w-fhir"
    / "tests"
    / "data"
    / "forward-409"
    / "data-value-set-value-type-v42.json"
)


def _profile() -> Profile:
    """A profile naming the mocked instance, which is all the forwarder needs to open a client."""
    return Profile(base_url=_BASE_URL, auth="pat", token="d2p_test")


def _accepted_tracker() -> httpx.Response:
    """What `/api/tracker` answers when it imported the event."""
    return httpx.Response(
        200,
        json={
            "status": "OK",
            "stats": {"created": 1, "updated": 0, "deleted": 0, "ignored": 0, "total": 1},
            "validationReport": {"errorReports": [], "warningReports": []},
        },
    )


def _rejected_aggregate() -> httpx.Response:
    """The harvested `/api/dataValueSets` 409, replayed field for field as DHIS2 wrote it."""
    assert _HARVESTED_409.is_file(), f"the harvested 409 body is missing: {_HARVESTED_409}"
    return httpx.Response(409, json=json.loads(_HARVESTED_409.read_text(encoding="utf-8")))


def _mock_instance() -> None:
    """Mock everything one drain touches: the version probe, the value-type reads, and both endpoints."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.6-SNAPSHOT"})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(side_effect=_value_types)
    respx.get(f"{_BASE_URL}/api/trackedEntityAttributes").mock(side_effect=_attribute_value_types)
    respx.post(f"{_BASE_URL}/api/dataValueSets").mock(return_value=_rejected_aggregate())
    respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=_accepted_tracker())


def _requested_uids(request: httpx.Request) -> list[str]:
    """The uids one id-only value-type read asked about, off its `id:in:[...]` filter."""
    raw = request.url.params.get("filter", "")
    inside = raw.partition("[")[2].rpartition("]")[0]
    return [uid for uid in inside.split(",") if uid]


def _value_types(request: httpx.Request) -> httpx.Response:
    """Answer the data-element read with a type for every uid it asked about."""
    return httpx.Response(
        200,
        json={"dataElements": [{"id": uid, "valueType": "TEXT"} for uid in _requested_uids(request)]},
    )


def _attribute_value_types(request: httpx.Request) -> httpx.Response:
    """Answer the tracked-entity-attribute read the same way, since a uid names exactly one object."""
    return httpx.Response(
        200,
        json={"trackedEntityAttributes": [{"id": uid, "valueType": "TEXT"} for uid in _requested_uids(request)]},
    )


async def _capture(client: httpx.AsyncClient, response: dict[str, Any]) -> str:
    """Post one submission through the facade and answer with the receipt id the server minted.

    The id is read off `Location` rather than off the body, because that is where the server states
    it - the body is the OperationOutcome carrying whatever it graded about the submission.
    """
    posted = await client.post(
        "/QuestionnaireResponse", json=response, headers={"Content-Type": "application/fhir+json"}
    )
    assert posted.status_code == 201, posted.text
    return posted.headers["Location"].rsplit("/", 1)[-1]


def _rows(listing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The listing's rows keyed by receipt id."""
    return {row["response_id"]: row for row in listing["responses"]}


@respx.mock
async def test_forward_drain_is_visible_to_the_running_facade(
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
    aggregate_response: dict[str, Any],
    event_response: dict[str, Any],
) -> None:
    """A real drain's renames and sidecars are what the still-running facade answers `/spool` with."""
    aggregate_id = await _capture(capture_client, aggregate_response)
    event_id = await _capture(capture_client, event_response)
    before = _rows((await capture_client.get("/spool")).json())
    assert {identifier: row["lifecycle"] for identifier, row in before.items()} == {
        aggregate_id: "received",
        event_id: "received",
    }

    _mock_instance()
    report = await forward_responses(_profile(), capture_project, import_responses=True)

    # The drain did what the mock told it to: the event was taken, the aggregate envelope was refused.
    assert [outcome.response_id for outcome in report.accepted] == [event_id]
    assert [outcome.response_id for outcome in report.rejected] == [aggregate_id]
    assert report.stopped is None

    listing = (await capture_client.get("/spool")).json()
    rows = _rows(listing)

    # The facade re-read the directory the forwarder moved the files into, without restarting.
    assert listing["counts"] == {"received": 0, "forwarded": 1, "rejected": 1, "withdrawn": 0, "malformed": 0}
    assert rows[event_id]["lifecycle"] == "forwarded"
    assert rows[aggregate_id]["lifecycle"] == "rejected"

    # Neither sidecar was listed as a receipt of its own, in either directory.
    assert listing["total"] == 2

    # The rejection rollup is read out of the report the forwarder really wrote, not one a test typed.
    rejection = rows[aggregate_id]["rejection"]
    assert rejection is not None
    assert rows[aggregate_id]["imported"] is None
    issues = rejection["issues"]
    assert issues, "the harvested 409 names at least one conflict"
    stored = json.loads(
        (
            capture_project.project_root / REJECTED_RESPONSES_RELATIVE_PATH / f"{aggregate_id}{IMPORT_REPORT_SUFFIX}"
        ).read_text(encoding="utf-8")
    )
    assert rejection["status"] == stored["status"]
    assert [issue["error_code"] for issue in issues] == [issue["error_code"] for issue in stored["issues"]]

    # And the accepted receipt's own sidecar - the one that says how much of it landed.
    imported = rows[event_id]["imported"]
    assert imported is not None
    assert rows[event_id]["rejection"] is None
    accepted_sidecar = json.loads(
        (
            capture_project.project_root / FORWARDED_RESPONSES_RELATIVE_PATH / f"{event_id}{IMPORT_REPORT_SUFFIX}"
        ).read_text(encoding="utf-8")
    )
    assert imported["created"] == accepted_sidecar["created"] == 1
    assert imported["status"] == accepted_sidecar["status"]


@respx.mock
async def test_a_receipt_the_drain_never_reached_is_still_offered_as_pending(
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
    aggregate_response: dict[str, Any],
    event_response: dict[str, Any],
) -> None:
    """A drain the instance broke off leaves the queue readable, so the facade still offers the retry."""
    aggregate_id = await _capture(capture_client, aggregate_response)
    event_id = await _capture(capture_client, event_response)

    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.6-SNAPSHOT"})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(side_effect=_value_types)
    respx.get(f"{_BASE_URL}/api/trackedEntityAttributes").mock(side_effect=_attribute_value_types)
    respx.post(f"{_BASE_URL}/api/dataValueSets").mock(
        return_value=httpx.Response(500, json={"status": "ERROR", "message": "the instance fell over"})
    )
    tracker = respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=_accepted_tracker())

    report = await forward_responses(_profile(), capture_project, import_responses=True)

    assert report.stopped is not None
    assert report.stopped.response_id == aggregate_id
    # The aggregate envelope posts first, so the tracker endpoint was never reached at all.
    assert tracker.call_count == 0

    listing = (await capture_client.get("/spool")).json()
    assert listing["counts"] == {"received": 2, "forwarded": 0, "rejected": 0, "withdrawn": 0, "malformed": 0}
    rows = _rows(listing)
    assert rows[aggregate_id]["lifecycle"] == "received"
    assert rows[event_id]["lifecycle"] == "received"
    assert rows[aggregate_id]["rejection"] is None
    assert rows[aggregate_id]["imported"] is None


@pytest.mark.parametrize("lifecycle_directory", [FORWARDED_RESPONSES_RELATIVE_PATH, REJECTED_RESPONSES_RELATIVE_PATH])
def test_an_import_report_is_never_listed_as_a_receipt(capture_project: FhirProject, lifecycle_directory: str) -> None:
    """The sidecar shares a directory and a `.json` tail with the receipt, in both drained states."""
    from dhis2w_fhir_serve.spool import ResponseSpool

    directory = capture_project.project_root / lifecycle_directory
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"stray{IMPORT_REPORT_SUFFIX}").write_text('{"status": "OK"}', encoding="utf-8")

    assert ResponseSpool.at(capture_project.project_root).receipts() == ()
