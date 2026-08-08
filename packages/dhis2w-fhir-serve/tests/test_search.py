"""`GET /{type}`: the search parameters the facade honors, and the Bundle it answers with."""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
from dhis2w_fhir_serve.spool import StoredResponseEnvelope

CANONICAL = "http://example.org/fhir"
QUESTIONNAIRE_URL = f"{CANONICAL}/Questionnaire/d2-pr-anc-visit-q"
PROGRAM_SYSTEM = "http://dhis2.org/fhir/id/program"
FHIR_JSON = "application/fhir+json"


async def test_search_without_parameters_returns_every_resource_of_the_type(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire")

    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON
    body = response.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] == 1
    assert body["entry"][0]["fullUrl"] == "http://serve.test/Questionnaire/d2-pr-anc-visit-q"
    assert body["entry"][0]["search"]["mode"] == "match"
    assert body["entry"][0]["resource"]["resourceType"] == "Questionnaire"


async def test_search_by_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire", params={"_id": "d2-pr-anc-visit-q"})

    assert response.json()["total"] == 1


async def test_search_by_id_ors_within_the_parameter(client: httpx.AsyncClient) -> None:
    hit = await client.get("/Questionnaire", params={"_id": "nope,d2-pr-anc-visit-q"})
    miss = await client.get("/Questionnaire", params={"_id": "nope,other"})

    assert hit.json()["total"] == 1
    assert miss.json()["total"] == 0


async def test_search_by_url(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire", params={"url": QUESTIONNAIRE_URL})

    assert response.json()["total"] == 1


async def test_search_by_system_qualified_identifier(client: httpx.AsyncClient) -> None:
    hit = await client.get("/Questionnaire", params={"identifier": f"{PROGRAM_SYSTEM}|ZzYYXq4fJie"})
    wrong_system = await client.get("/Questionnaire", params={"identifier": f"{CANONICAL}|ZzYYXq4fJie"})

    assert hit.json()["total"] == 1
    assert wrong_system.json()["total"] == 0


async def test_search_by_bare_identifier_matches_any_system(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire", params={"identifier": "ANC_VISIT"})

    assert response.json()["total"] == 1


async def test_search_ands_across_parameters(client: httpx.AsyncClient) -> None:
    both = await client.get("/Questionnaire", params={"_id": "d2-pr-anc-visit-q", "identifier": "ANC_VISIT"})
    conflicting = await client.get("/Questionnaire", params={"_id": "d2-pr-anc-visit-q", "identifier": "OTHER"})

    assert both.json()["total"] == 1
    assert conflicting.json()["total"] == 0


async def test_unknown_parameters_are_ignored_and_left_out_of_the_self_link(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire", params={"_id": "d2-pr-anc-visit-q", "_lastUpdated": "gt2020"})

    body = response.json()
    assert body["total"] == 1
    self_link = body["link"][0]
    assert self_link["relation"] == "self"
    assert self_link["url"] == "http://serve.test/Questionnaire?_id=d2-pr-anc-visit-q"


async def test_empty_result_carries_no_entry_key(client: httpx.AsyncClient) -> None:
    response = await client.get("/Questionnaire", params={"_id": "nothing-here"})

    body = response.json()
    assert body["total"] == 0
    assert "entry" not in body


async def test_search_of_an_unserved_type_is_not_supported(client: httpx.AsyncClient) -> None:
    response = await client.get("/StructureDefinition")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-supported"


async def test_receipt_search_answers_newest_first(
    client: httpx.AsyncClient, stored_responses: tuple[StoredResponseEnvelope, ...]
) -> None:
    response = await client.get("/QuestionnaireResponse")

    body = response.json()
    assert body["total"] == len(stored_responses)
    assert [entry["resource"]["id"] for entry in body["entry"]] == [
        "receipt-newest",
        "receipt-middle",
        "receipt-oldest",
    ]
    assert body["entry"][0]["fullUrl"] == "http://serve.test/QuestionnaireResponse/receipt-newest"


async def test_receipt_search_filters_by_questionnaire(client: httpx.AsyncClient) -> None:
    response = await client.get("/QuestionnaireResponse", params={"questionnaire": QUESTIONNAIRE_URL})

    body = response.json()
    assert [entry["resource"]["id"] for entry in body["entry"]] == ["receipt-newest", "receipt-oldest"]
    expected_query = urlencode({"questionnaire": QUESTIONNAIRE_URL})
    assert body["link"][0]["url"] == f"http://serve.test/QuestionnaireResponse?{expected_query}"


async def test_receipt_search_filters_by_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/QuestionnaireResponse", params={"_id": "receipt-oldest,receipt-middle"})

    body = response.json()
    assert [entry["resource"]["id"] for entry in body["entry"]] == ["receipt-middle", "receipt-oldest"]


async def test_receipt_search_ignores_unknown_parameters(client: httpx.AsyncClient) -> None:
    response = await client.get("/QuestionnaireResponse", params={"subject": "Patient/1"})

    body = response.json()
    assert body["total"] == 3
    assert body["link"][0]["url"] == "http://serve.test/QuestionnaireResponse"
