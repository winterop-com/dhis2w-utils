"""The aggregate round trip: a form captured through the guide is read back through the guide, unchanged.

This is the claim the data set read-back exists to make, and the only test in the suite that runs both
legs against each other. Nothing here is hand-written between them:

1. The golden aggregate submission is posted to `POST /QuestionnaireResponse`, which is the document
   the IG publishes as what a compliant client sends.
2. The real `forward_responses` drains the spool against a respx-mocked instance, and the envelope it
   posts to `/api/dataValueSets` is captured off the wire - so what DHIS2 is told is what the
   forwarder really says, not a payload this file typed.
3. That same envelope is served back as the export `GET /facade/data-sets/{uid}/responses` reads, and
   the document it answers is compared with the one that was submitted.

The comparison is the link ids and the typed answers, cell for cell. Those two are the contract: a
form is described once, and the same question carries the same value whichever direction it travelled.
The envelope around them is deliberately not compared - a submission carries the id the server minted
for the receipt and a served form carries its reporting key, and they are two different documents
about one reported form.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.service import forward_responses
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from fastapi import FastAPI

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"

#: The data set the golden aggregate submission answers, and the keys it reports under.
_DATA_SET_UID = "BfMAe6Itzgt"
_ORG_UNIT_UID = "ImspTQPwCqd"
_PERIOD = "202607"


def _profile() -> Profile:
    """A profile naming the mocked instance, which is all the forwarder needs to open a client."""
    return Profile(base_url=_HOST, auth="pat", token="d2p_test")


def _accepted_aggregate() -> httpx.Response:
    """What `/api/dataValueSets` answers when it took the whole envelope."""
    return httpx.Response(
        200,
        json={
            "status": "SUCCESS",
            "importCount": {"imported": 0, "updated": 12, "ignored": 0, "deleted": 0},
            "conflicts": [],
        },
    )


def _requested_uids(request: httpx.Request) -> list[str]:
    """The uids one id-only value-type read asked about, off its `id:in:[...]` filter."""
    raw = request.url.params.get("filter", "")
    inside = raw.partition("[")[2].rpartition("]")[0]
    return [uid for uid in inside.split(",") if uid]


def _value_types(request: httpx.Request) -> httpx.Response:
    """Answer the data-element read with a type for every uid it asked about."""
    return httpx.Response(
        200, json={"dataElements": [{"id": uid, "valueType": "NUMBER"} for uid in _requested_uids(request)]}
    )


def _attribute_value_types(request: httpx.Request) -> httpx.Response:
    """Answer the tracked-entity-attribute read the same way, since a uid names exactly one object."""
    return httpx.Response(
        200,
        json={"trackedEntityAttributes": [{"id": uid, "valueType": "TEXT"} for uid in _requested_uids(request)]},
    )


@pytest.fixture
async def round_trip_client(capture_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """One facade that both receives the submission and reads the values back, over the same guide.

    One process rather than two, deliberately: the whole claim is that the form a submission is
    validated against is the form a served value is projected through, and two facades over one
    project would be the same claim made twice with a chance of disagreeing.

    The instance behind it is a plain connection standing in for the live client a `--live` run holds,
    which is the same stand-in `test_data_set_responses.py` builds.
    """
    app: FastAPI = create_app(ServeSettings(project_dir=capture_project.project_root))
    async with app.router.lifespan_context(app), httpx.AsyncClient(base_url=_HOST) as instance:
        app.state.live_client = _Reader(instance)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
            yield http


def _answers(response: dict[str, Any]) -> dict[str, Any]:
    """Every answered cell of one document, keyed by link id - the shape both directions are pinned on."""
    found: dict[str, Any] = {}

    def _walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("answer"):
                found[item["linkId"]] = item["answer"]
            _walk(item.get("item", []))

    _walk(response.get("item", []))
    return found


@respx.mock
async def test_an_aggregate_form_reads_back_as_the_form_that_was_captured(
    round_trip_client: httpx.AsyncClient,
    capture_project: FhirProject,
    aggregate_response: dict[str, Any],
) -> None:
    """Capture, forward, read back: the same link ids carrying the same typed answers, both directions."""
    respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.6"}))
    respx.get(f"{_HOST}/api/dataElements").mock(side_effect=_value_types)
    respx.get(f"{_HOST}/api/trackedEntityAttributes").mock(side_effect=_attribute_value_types)
    posted = respx.post(f"{_HOST}/api/dataValueSets").mock(return_value=_accepted_aggregate())
    # A `completed` aggregate response registers the data set complete beside the values it lands, and
    # the served document carries that same status - which is what makes this a round trip rather than
    # a comparison of two shapes that happen to overlap.
    respx.post(f"{_HOST}/api/completeDataSetRegistrations").mock(
        return_value=httpx.Response(200, json={"status": "SUCCESS", "importCount": {"imported": 1}})
    )

    captured = await round_trip_client.post(
        "/QuestionnaireResponse", json=aggregate_response, headers={"Content-Type": "application/fhir+json"}
    )
    assert captured.status_code == 201, captured.text

    report = await forward_responses(_profile(), capture_project, import_responses=True)
    assert [outcome.response_id for outcome in report.rejected] == []
    assert len(report.accepted) == 1

    # What the forwarder really told DHIS2 is what the instance is now made to answer with.
    envelope = json.loads(posted.calls.last.request.content)
    assert envelope["dataSet"] == _DATA_SET_UID
    respx.get(f"{_HOST}/api/dataValueSets").mock(return_value=httpx.Response(200, json=envelope))

    read = await round_trip_client.get(
        f"/facade/data-sets/{_DATA_SET_UID}/responses?orgUnit={_ORG_UNIT_UID}&period={_PERIOD}"
    )

    assert read.status_code == 200, read.text
    body = read.json()
    [served] = [entry["resource"] for entry in body["entry"] if entry["search"]["mode"] == "match"]

    assert body["total"] == 1
    assert served["questionnaire"] == aggregate_response["questionnaire"]
    assert served["subject"] == aggregate_response["subject"]
    assert _answers(served) == _answers(aggregate_response)


class _Reader:
    """The instance as a `RegisterReader`, over the plain client this test opened against the mock."""

    def __init__(self, connection: httpx.AsyncClient) -> None:
        """Hold the connection every read of this test's instance runs over."""
        self.connection = connection

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one DHIS2 path, answering the parsed JSON body."""
        answer = await self.connection.get(path, params=params)
        body: dict[str, Any] = answer.json()
        return body
