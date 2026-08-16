"""`Accept` on the FHIR surface: which headers are answered, which is refused, and where it applies."""

from __future__ import annotations

import httpx
import pytest
from dhis2w_fhir_serve.routes.negotiation import accepts_json

FHIR_JSON = "application/fhir+json"
FHIR_XML = "application/fhir+xml"

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


@pytest.mark.parametrize("path", ["/spool", "/uiconfig"])
async def test_the_non_fhir_endpoints_do_not_negotiate(client: httpx.AsyncClient, path: str) -> None:
    """These answer plain JSON about this facade rather than resources out of it, so there is nothing to refuse."""
    response = await client.get(path, headers={"Accept": FHIR_XML})

    assert response.status_code == 200
