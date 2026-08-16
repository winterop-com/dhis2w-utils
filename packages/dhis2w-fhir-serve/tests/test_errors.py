"""Every failure the facade can answer: the status, the issue code, and what a 500 refuses to say."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import Response

FHIR_JSON = "application/fhir+json"
LEAKED_SECRET = "connection string postgres://user:hunter2@db"

BASE_URL = "http://serve.test"


async def _explode() -> Response:
    raise RuntimeError(LEAKED_SECRET)


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """The facade plus one route that raises, mounted ahead of the read catch-alls."""
    app.add_api_route("/boom", _explode, methods=["GET"])
    app.router.routes.insert(0, app.router.routes.pop())
    return app


@pytest.fixture
async def tolerant_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A client that reads the 500 the handler wrote instead of re-raising the route's exception."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


async def test_unknown_resource_type_is_not_supported(client: httpx.AsyncClient) -> None:
    response = await client.get("/Patient")

    assert response.status_code == 404
    assert response.headers["content-type"] == FHIR_JSON
    assert response.json()["issue"][0]["code"] == "not-supported"


async def test_unknown_id_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire/missing")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-found"


async def test_unroutable_path_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire/one/two")

    assert response.status_code == 404
    assert response.headers["content-type"] == FHIR_JSON
    assert response.json()["issue"][0]["code"] == "not-found"


async def test_an_unreadable_search_parameter_is_invalid(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire?_id=")

    assert response.status_code == 400
    assert response.headers["content-type"] == FHIR_JSON
    assert response.json()["issue"][0]["code"] == "invalid"


async def test_an_identifier_token_without_a_value_is_invalid(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire", params={"identifier": "http://dhis2.org/fhir/id/program|"})

    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "invalid"


async def test_a_method_the_path_does_not_take_is_not_supported(client: httpx.AsyncClient) -> None:
    response = await client.delete("/Questionnaire/d2-pr-anc-visit-q")

    assert response.status_code == 405
    assert response.headers["content-type"] == FHIR_JSON
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert "DELETE" in issue["diagnostics"]


async def test_posting_to_the_service_base_says_batch_is_not_supported(client: httpx.AsyncClient) -> None:
    """`POST [base]` is FHIR's batch endpoint, and a client that finds it deserves the reason it is not here."""
    response = await client.post("/", json={"resourceType": "Bundle", "type": "batch"})

    assert response.status_code == 405
    assert response.headers["content-type"] == FHIR_JSON
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert issue["diagnostics"] == (
        "`POST /` is not served here: this server runs no batch and no transaction. Post one "
        "QuestionnaireResponse per request to `/QuestionnaireResponse`."
    )


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
async def test_every_other_method_on_the_service_base_refuses_the_same_way(
    client: httpx.AsyncClient, method: str
) -> None:
    """FHIR defines none of these at the base, so each is one fact stated about a different verb."""
    response = await client.request(method, "/")

    assert response.status_code == 405
    assert response.json()["issue"][0]["code"] == "not-supported"
    assert f"`{method} /`" in response.json()["issue"][0]["diagnostics"]


async def test_reading_the_service_base_without_a_ui_is_still_not_an_endpoint(client: httpx.AsyncClient) -> None:
    """Refusing the write does not invent a read: without `--ui` nothing serves the base."""
    response = await client.get("/")

    assert response.status_code == 404
    assert response.json()["issue"][0]["diagnostics"] == "`/` is not an endpoint this server serves"


async def test_an_unexpected_failure_leaks_nothing(
    tolerant_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="dhis2w_fhir_serve"):
        response = await tolerant_client.get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == FHIR_JSON
    issue = response.json()["issue"][0]
    assert issue["severity"] == "fatal"
    assert issue["code"] == "exception"
    assert issue["diagnostics"] == "the server failed to process this request"
    assert LEAKED_SECRET not in response.text
    assert "RuntimeError" not in response.text
    assert LEAKED_SECRET in caplog.text
