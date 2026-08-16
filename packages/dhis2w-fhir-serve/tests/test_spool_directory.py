"""`[serve] spool_dir`: where this server writes its receipts, and who else has to agree about it.

The key belongs to `[serve]` because the server is what writes the tree, and `d2w fhir forward`
follows the project's declaration rather than carrying one of its own. Both sides resolve it through
`dhis2w_fhir.spool.resolve_spool_root`, so the agreement is a shared function rather than two
implementations that happen to match today - which is what the last test here holds.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.spool import SPOOL_RELATIVE_PATH, SpoolLayout, SpoolState
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseLifecycle, ResponseSpool
from fastapi import FastAPI

FHIR_JSON = "application/fhir+json"

BASE_URL = "http://serve.test"


def _serving(project: FhirProject, spool_dir: str) -> FastAPI:
    """The facade over one project, writing its receipts wherever the key points."""
    return create_app(ServeSettings(project_dir=project.project_root, spool_dir=spool_dir))


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """An in-process client over one built app, with the lifespan run around the caller."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


async def _capture(app: FastAPI, response: dict[str, Any]) -> str:
    """Post one submission and answer with the receipt id the server minted for it."""
    async with _client(app) as http:
        posted = await http.post("/QuestionnaireResponse", json=response, headers={"content-type": FHIR_JSON})
        assert posted.status_code == 201, posted.text
        return posted.headers["Location"].rsplit("/", 1)[-1]


def _received_files(root: Path) -> list[str]:
    """Every receipt file name sitting in one spool root's `received/`, in name order."""
    directory = root / "received"
    return sorted(path.name for path in directory.glob("*.json")) if directory.is_dir() else []


async def test_a_relative_directory_is_resolved_against_the_project(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """The ordinary case: a tree inside the project the receipts belong to, under a name of its own."""
    response_id = await _capture(_serving(capture_project, "receipts"), aggregate_response)

    assert _received_files(capture_project.project_root / "receipts") == [f"{response_id}.json"]
    # And nothing at all in the directory this project is not using.
    assert _received_files(capture_project.project_root / SPOOL_RELATIVE_PATH) == []


async def test_an_absolute_directory_is_taken_as_written(
    capture_project: FhirProject, aggregate_response: dict[str, Any], tmp_path: Path
) -> None:
    """A spool on a volume the operator chose, which is the reason absolute paths are allowed at all."""
    elsewhere = tmp_path / "volume" / "receipts"
    response_id = await _capture(_serving(capture_project, str(elsewhere)), aggregate_response)

    assert _received_files(elsewhere) == [f"{response_id}.json"]
    assert _received_files(capture_project.project_root / SPOOL_RELATIVE_PATH) == []


async def test_the_default_is_the_tree_inside_the_project(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """A project that states no directory writes where it always did, which is what the scaffold ignores."""
    response_id = await _capture(
        create_app(ServeSettings(project_dir=capture_project.project_root)), aggregate_response
    )

    assert _received_files(capture_project.project_root / SPOOL_RELATIVE_PATH) == [f"{response_id}.json"]


async def test_the_spool_listing_reads_the_directory_the_project_named(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """One process, one answer: what a run writes is what the same run counts."""
    app = _serving(capture_project, "receipts")

    async with _client(app) as http:
        posted = await http.post("/QuestionnaireResponse", json=aggregate_response, headers={"content-type": FHIR_JSON})
        assert posted.status_code == 201, posted.text
        body = (await http.get("/spool")).json()

    assert body["total"] == 1
    assert body["counts"]["received"] == 1


async def test_a_receipt_is_a_whole_envelope_wherever_it_lands(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """The tree moved, not the format: a relocated receipt reads back as the same document."""
    response_id = await _capture(_serving(capture_project, "receipts"), aggregate_response)

    written = json.loads(
        (capture_project.project_root / "receipts" / "received" / f"{response_id}.json").read_text(encoding="utf-8")
    )

    assert written["response_id"] == response_id
    assert written["form_kind"] == "aggregate"
    assert written["response"]["resourceType"] == "QuestionnaireResponse"


@pytest.mark.parametrize("spool_dir", [SPOOL_RELATIVE_PATH, "receipts", "/tmp/dhis2w-spool", "nested/deep/tree"])
def test_the_server_and_the_forwarder_resolve_one_directory(tmp_path: Path, spool_dir: str) -> None:
    """The invariant the whole key rests on: a receipt this server writes is one that drain finds.

    Two packages hold the layout under the root - the duplication `dhis2w_fhir.spool` explains - so
    the one thing that cannot be duplicated is where the root is. A disagreement here is a receipt
    nothing ever forwards, which is the failure a capture surface must not have.
    """
    served = ResponseSpool.at(tmp_path, spool_dir)
    drained = SpoolLayout.resolve(tmp_path, spool_dir)

    assert served.directory == drained.root
    # And every directory under it, since each state is a rename between the two sides.
    assert served.directory_for(ResponseLifecycle.RECEIVED) == drained.directory_for(SpoolState.RECEIVED)
    assert served.directory_for(ResponseLifecycle.FORWARDED) == drained.directory_for(SpoolState.FORWARDED)
    assert served.directory_for(ResponseLifecycle.REJECTED) == drained.directory_for(SpoolState.REJECTED)
    assert served.malformed_directory == drained.malformed_directory
