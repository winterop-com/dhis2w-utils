"""HEAD answers wherever GET does - the parity a FHIR liveness probe stands on.

RFC 9110 defines HEAD as GET without the body, and monitors lean on `HEAD /metadata` to ask
whether a server is up. The assertions here are about status and headers, not body emptiness:
stripping the body of a HEAD response is the HTTP server's job (verified against uvicorn), and
the in-process ASGI transport deliberately does not do it.
"""

from __future__ import annotations

import httpx

FHIR_JSON = "application/fhir+json"


async def test_head_metadata_answers_where_get_does(client: httpx.AsyncClient) -> None:
    head = await client.head("/metadata")
    get = await client.get("/metadata")

    assert head.status_code == 200
    assert get.status_code == 200
    assert head.headers["content-type"] == get.headers["content-type"] == FHIR_JSON


async def test_head_read_answers_where_get_does(client: httpx.AsyncClient) -> None:
    head = await client.head("/Questionnaire/d2-pr-anc-visit-q")

    assert head.status_code == 200
    assert head.headers["content-type"] == FHIR_JSON


async def test_head_search_answers_where_get_does(client: httpx.AsyncClient) -> None:
    head = await client.head("/Questionnaire")

    assert head.status_code == 200
    assert head.headers["content-type"] == FHIR_JSON


async def test_head_is_404_where_get_is(client: httpx.AsyncClient) -> None:
    head = await client.head("/Questionnaire/missing")

    assert head.status_code == 404
