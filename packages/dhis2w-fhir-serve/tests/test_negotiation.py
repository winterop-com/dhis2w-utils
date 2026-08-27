"""`Accept` on the FHIR surface: which headers are answered, which is refused, and where it applies.

`_format` is here too, because it is the same negotiation asked a second way: R4's query parameter
overrides the header, which is what makes a FHIR query a URL a browser can open.
"""

from __future__ import annotations

import httpx
import pytest
from dhis2w_fhir_serve.routes.negotiation import accepts_json, format_asks_for_json

FHIR_JSON = "application/fhir+json"
FHIR_XML = "application/fhir+xml"

#: A header naming markup and no JSON at all - the one `_format` has to win over.
HOSTILE_ACCEPT = "text/html,application/xhtml+xml,application/fhir+xml;q=0.9"

#: The three spellings of `_format` that name the format this server answers in.
JSON_FORMATS = ("json", "application/json", FHIR_JSON, "JSON", "Application/FHIR+JSON")

#: The paths one refusal has to cover: a read, a search, the conformance document, and an operation.
FHIR_PATHS = (
    "/Questionnaire/d2-pr-anc-visit-q",
    "/Questionnaire",
    "/metadata",
    "/ConceptMap/$translate?system=x&code=y",
)


@pytest.mark.parametrize(
    "accept",
    [None, "", "*/*", "application/*", "application/json", FHIR_JSON, "application/xml, */*;q=0.1", "text/html, */*"],
)
def test_a_header_that_admits_json_is_answered(accept: str | None) -> None:
    """An absent header, a wildcard, and every JSON media type this server could answer under."""
    assert accepts_json(accept)


@pytest.mark.parametrize("accept", [FHIR_XML, "application/xml", "text/html", "application/fhir+xml, text/plain"])
def test_a_header_that_admits_no_json_is_not(accept: str) -> None:
    """The one case a refusal falls on: a client that named formats and named no JSON among them."""
    assert not accepts_json(accept)


@pytest.mark.parametrize("path", FHIR_PATHS)
async def test_a_request_accepting_no_json_is_refused(client: httpx.AsyncClient, path: str) -> None:
    """Every FHIR interaction answers `application/fhir+json`, and says so rather than sending it anyway."""
    response = await client.get(path, headers={"Accept": FHIR_XML})

    assert response.status_code == 406
    assert response.headers["content-type"] == FHIR_JSON
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert issue["diagnostics"] == (
        f"`{FHIR_XML}` accepts no JSON, and this server answers `{FHIR_JSON}` only; "
        "ask for that, for `application/json`, or for `*/*`"
    )


@pytest.mark.parametrize("path", FHIR_PATHS)
@pytest.mark.parametrize("accept", [None, "*/*", FHIR_JSON])
async def test_a_request_that_takes_json_is_answered(client: httpx.AsyncClient, path: str, accept: str | None) -> None:
    """Absent, wildcard, and explicit are all unchanged - the negotiation never falls on a plain client."""
    response = await client.get(path, headers=None if accept is None else {"Accept": accept})

    assert response.status_code == 200


async def test_the_capture_endpoint_negotiates_too(client: httpx.AsyncClient) -> None:
    """A capture answers an OperationOutcome whatever it decides, and that is JSON like everything else."""
    response = await client.post(
        "/QuestionnaireResponse",
        headers={"Accept": FHIR_XML, "Content-Type": FHIR_JSON},
        content=b'{"resourceType":"QuestionnaireResponse","status":"completed"}',
    )

    assert response.status_code == 406


async def test_the_service_base_refusal_negotiates_too(client: httpx.AsyncClient) -> None:
    """The batch refusal is an OperationOutcome, so a client that cannot read one is told first."""
    response = await client.post("/", headers={"Accept": FHIR_XML}, json={"resourceType": "Bundle"})

    assert response.status_code == 406


@pytest.mark.parametrize("path", ["/facade/spool", "/facade/uiconfig"])
async def test_the_non_fhir_endpoints_do_not_negotiate(client: httpx.AsyncClient, path: str) -> None:
    """These answer plain JSON about this facade rather than resources out of it, so there is nothing to refuse."""
    response = await client.get(path, headers={"Accept": FHIR_XML})

    assert response.status_code == 200


@pytest.mark.parametrize("stated_format", JSON_FORMATS)
def test_every_spelling_of_the_served_format_is_read(stated_format: str) -> None:
    """The three R4 spellings, in any casing, all name the one format this server answers in."""
    assert format_asks_for_json(stated_format)


@pytest.mark.parametrize("stated_format", ["xml", "application/fhir+xml", "text/html", "turtle", "ttl"])
def test_a_format_this_server_does_not_serve_is_not(stated_format: str) -> None:
    """A client naming any other format named something this server has none of."""
    assert not format_asks_for_json(stated_format)


@pytest.mark.parametrize("path", FHIR_PATHS)
@pytest.mark.parametrize("stated_format", JSON_FORMATS)
async def test_a_format_naming_json_wins_over_a_header_that_does_not(
    client: httpx.AsyncClient, path: str, stated_format: str
) -> None:
    """The case the parameter exists for: a link opened where the client's header rules JSON out."""
    separator = "&" if "?" in path else "?"
    response = await client.get(f"{path}{separator}_format={stated_format}", headers={"Accept": HOSTILE_ACCEPT})

    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON


@pytest.mark.parametrize("path", FHIR_PATHS)
async def test_a_format_this_server_does_not_serve_is_refused_however_welcoming_the_header(
    client: httpx.AsyncClient, path: str
) -> None:
    """`_format` is the client's own word about what it wants, so it is answered rather than read past."""
    separator = "&" if "?" in path else "?"
    response = await client.get(f"{path}{separator}_format=xml", headers={"Accept": "application/json"})

    assert response.status_code == 406
    assert response.headers["content-type"] == FHIR_JSON
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert issue["diagnostics"] == (
        f"`_format=xml` names a format this server does not serve, and this server answers `{FHIR_JSON}` only; "
        "ask for `_format=json`, for `_format=application/json`, or for `_format=application/fhir+json`"
    )


async def test_the_media_type_spelled_with_a_plus_is_read_as_written(client: httpx.AsyncClient) -> None:
    """A query string decodes an unescaped `+` to a space, and that is how the media type gets typed."""
    response = await client.get("/metadata?_format=application/fhir+json", headers={"Accept": HOSTILE_ACCEPT})

    assert response.status_code == 200


async def test_a_blank_format_leaves_the_header_to_decide(client: httpx.AsyncClient) -> None:
    """`_format=` names nothing, so it is the absent case and the header still rules JSON out."""
    response = await client.get("/Questionnaire?_format=", headers={"Accept": FHIR_XML})

    assert response.status_code == 406
    assert response.json()["issue"][0]["diagnostics"].startswith(f"`{FHIR_XML}` accepts no JSON")


@pytest.mark.parametrize("path", ["/Questionnaire", "/QuestionnaireResponse", "/CodeSystem", "/ValueSet"])
async def test_a_format_narrows_no_search(client: httpx.AsyncClient, path: str) -> None:
    """It names the format the answer comes back in, so the answer is the same set either way."""
    plain = await client.get(path)
    formatted = await client.get(f"{path}?_format=json")

    assert plain.status_code == formatted.status_code == 200
    assert formatted.json()["total"] == plain.json()["total"]
    assert [entry["resource"]["id"] for entry in formatted.json().get("entry", [])] == [
        entry["resource"]["id"] for entry in plain.json().get("entry", [])
    ]
