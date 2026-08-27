"""Paging and quarantine over the two spool reads: `GET /facade/spool` and `GET /QuestionnaireResponse`.

A facade that has taken ten thousand submissions must not answer either read with all of them, and
must not answer either with a 500 because one file on disk is no longer a receipt. Both properties
are about what a client sees, so both are tested through the wire rather than through the spool.

The cursor is opaque on purpose: every walk below follows the `next` link the server handed out,
which is exactly what a client does and the only thing this server promises.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseLifecycle, ResponseSpool, StoredResponseEnvelope
from fastapi import FastAPI

BASE_URL = "http://serve.test"

#: How many receipts the paging fixtures seed - enough that a small page leaves several behind.
SEEDED_RECEIPTS = 7

QUESTIONNAIRE_URL = "http://example.org/fhir/Questionnaire/d2-ds-anc-q"


def _envelope(index: int) -> StoredResponseEnvelope:
    """One seeded receipt, its instant ordered by its index so newest-first is a known order."""
    response_id = f"receipt-{index:02d}"
    return StoredResponseEnvelope(
        response_id=response_id,
        received_at=f"2026-08-07T{9 + index:02d}:00:00Z",
        form_kind="aggregate",
        questionnaire=QUESTIONNAIRE_URL,
        response={
            "resourceType": "QuestionnaireResponse",
            "id": response_id,
            "questionnaire": QUESTIONNAIRE_URL,
            "status": "completed",
        },
    )


@pytest.fixture
def paged_app(compiled_project: FhirProject) -> FastAPI:
    """A facade whose spool holds several receipts, so a small page leaves a `next` link behind."""
    spool = ResponseSpool.at(compiled_project.project_root)
    for index in range(SEEDED_RECEIPTS):
        spool.save(_envelope(index))
    return create_app(ServeSettings(project_dir=compiled_project.project_root))


@pytest.fixture
async def paged_client(paged_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over the seeded facade."""
    async with paged_app.router.lifespan_context(paged_app):
        transport = httpx.ASGITransport(app=paged_app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


def _path_and_query(url: str) -> str:
    """One absolute link as the in-process client asks for it again."""
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def _link(body: dict[str, object], relation: str) -> str | None:
    """The url of one Bundle link, or None when the Bundle names no such neighbour."""
    links = body.get("link")
    assert isinstance(links, list)
    for link in links:
        if link["relation"] == relation:
            return str(link["url"])
    return None


async def test_the_spool_listing_pages_and_states_one_total_throughout(paged_client: httpx.AsyncClient) -> None:
    """A walk reads every receipt once, newest first, and every page states the whole listing's total."""
    walked: list[str] = []
    totals: list[int] = []
    next_url: str | None = "/facade/spool?_count=3"
    while next_url is not None:
        body = (await paged_client.get(next_url)).json()
        walked.extend(row["response_id"] for row in body["responses"])
        totals.append(body["total"])
        next_url = None if body["next_url"] is None else _path_and_query(body["next_url"])

    assert walked == [f"receipt-{index:02d}" for index in reversed(range(SEEDED_RECEIPTS))]
    assert totals == [SEEDED_RECEIPTS] * 3


async def test_a_spool_page_links_back_to_the_one_before_it(paged_client: httpx.AsyncClient) -> None:
    """`previous` returns a client to the page it came from, which is what makes a walk reversible."""
    first = (await paged_client.get("/facade/spool?_count=3")).json()
    second = (await paged_client.get(_path_and_query(first["next_url"]))).json()

    assert first["previous_url"] is None
    back = (await paged_client.get(_path_and_query(second["previous_url"]))).json()

    assert [row["response_id"] for row in back["responses"]] == [row["response_id"] for row in first["responses"]]


async def test_the_spool_counts_are_the_whole_spool_rather_than_the_page(paged_client: httpx.AsyncClient) -> None:
    """A queue depth that changed with the page you were looking at would be no queue depth at all."""
    body = (await paged_client.get("/facade/spool?_count=2")).json()

    assert len(body["responses"]) == 2
    assert body["counts"] == {
        "received": SEEDED_RECEIPTS,
        "forwarded": 0,
        "rejected": 0,
        "withdrawn": 0,
        "malformed": 0,
    }


async def test_a_page_this_server_did_not_mint_is_refused(paged_client: httpx.AsyncClient) -> None:
    """`page` is a link to follow, not a number a client composes."""
    response = await paged_client.get("/facade/spool?page=17")

    assert response.status_code == 400
    assert "is not a page of this listing" in response.json()["issue"][0]["diagnostics"]


async def test_a_count_that_is_not_a_number_of_rows_is_refused(paged_client: httpx.AsyncClient) -> None:
    """A malformed query is refused; an ambitious one is served the limit."""
    response = await paged_client.get("/facade/spool?_count=none")

    assert response.status_code == 400
    assert "not a number of rows" in response.json()["issue"][0]["diagnostics"]


async def test_the_receipt_search_pages_over_the_same_order(paged_client: httpx.AsyncClient) -> None:
    """The FHIR search walks the same receipts, in the same order, by following the same kind of link."""
    walked: list[str] = []
    totals: list[int] = []
    next_url: str | None = "/QuestionnaireResponse?_count=4"
    while next_url is not None:
        body = (await paged_client.get(next_url)).json()
        walked.extend(entry["resource"]["id"] for entry in body.get("entry", []))
        totals.append(body["total"])
        next_url = None if _link(body, "next") is None else _path_and_query(str(_link(body, "next")))

    assert walked == [f"receipt-{index:02d}" for index in reversed(range(SEEDED_RECEIPTS))]
    assert totals == [SEEDED_RECEIPTS, SEEDED_RECEIPTS]


async def test_a_receipt_search_page_carries_the_filters_that_were_applied(paged_client: httpx.AsyncClient) -> None:
    """Following a link must not silently widen the search it came from."""
    body = (await paged_client.get(f"/QuestionnaireResponse?questionnaire={QUESTIONNAIRE_URL}&_count=3")).json()

    following = _link(body, "next")

    assert following is not None
    assert "questionnaire=" in following
    followed = (await paged_client.get(_path_and_query(following))).json()
    assert followed["total"] == SEEDED_RECEIPTS


async def test_a_corrupt_file_costs_one_row_and_is_named_rather_than_failing_the_listing(
    paged_client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    """One unreadable byte on disk must not take the whole listing down with it - the loud part is the naming."""
    spool = ResponseSpool.at(compiled_project.project_root)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "receipt-03.json").write_text("{not json", encoding="utf-8")

    body = (await paged_client.get("/facade/spool?_count=50")).json()

    assert body["total"] == SEEDED_RECEIPTS - 1
    assert body["counts"]["malformed"] == 1
    assert [entry["file_name"] for entry in body["malformed"]] == ["receipt-03.json"]
    assert "not readable as JSON" in body["malformed"][0]["reason"]
    assert "receipt-03" not in [row["response_id"] for row in body["responses"]]


async def test_a_corrupt_file_does_not_fail_the_receipt_search_either(
    paged_client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    """The FHIR search answers the receipts that are readable rather than refusing the query."""
    spool = ResponseSpool.at(compiled_project.project_root)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "receipt-03.json").write_text("{not json", encoding="utf-8")

    body = (await paged_client.get("/QuestionnaireResponse?_count=50")).json()

    assert body["total"] == SEEDED_RECEIPTS - 1
    assert "receipt-03" not in [entry["resource"]["id"] for entry in body["entry"]]


async def test_a_corrupt_receipt_read_by_id_answers_not_found_and_is_quarantined(
    paged_client: httpx.AsyncClient, compiled_project: FhirProject
) -> None:
    """A file that no longer reads as a receipt is not a receipt, and is moved aside rather than served."""
    spool = ResponseSpool.at(compiled_project.project_root)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "receipt-03.json").write_text("{not json", encoding="utf-8")

    response = await paged_client.get("/QuestionnaireResponse/receipt-03")

    assert response.status_code == 404
    assert (spool.malformed_directory / "receipt-03.json").is_file()
