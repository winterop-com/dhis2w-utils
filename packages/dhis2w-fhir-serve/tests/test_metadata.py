"""`GET /metadata`: the statement the running facade answers conformance requests with."""

from __future__ import annotations

from typing import Any

import httpx

CANONICAL = "http://example.org/fhir"
FHIR_JSON = "application/fhir+json"


async def _metadata(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/metadata")
    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON
    body: dict[str, Any] = response.json()
    return body


def _resource(body: dict[str, Any], resource_type: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        resource for resource in body["rest"][0]["resource"] if resource["type"] == resource_type
    ]
    assert len(matches) == 1
    return matches[0]


def _resource_types(body: dict[str, Any]) -> list[str]:
    return [resource["type"] for resource in body["rest"][0]["resource"]]


async def test_metadata_describes_this_instance(client: httpx.AsyncClient) -> None:
    body = await _metadata(client)

    assert body["resourceType"] == "CapabilityStatement"
    assert body["kind"] == "instance"
    assert body["status"] == "active"
    assert body["fhirVersion"] == "4.0.1"
    assert body["format"] == ["json"]


async def test_metadata_instantiates_the_ig_capture_server(client: httpx.AsyncClient) -> None:
    body = await _metadata(client)

    assert body["instantiates"] == [f"{CANONICAL}/CapabilityStatement/d2-capture-server"]


async def test_metadata_names_the_software_and_the_compiled_store(client: httpx.AsyncClient) -> None:
    body = await _metadata(client)

    assert body["software"]["name"] == "d2w fhir serve"
    assert body["implementation"]["description"].startswith(
        "A FHIR capture facade over a compiled implementation guide."
    )


async def test_metadata_says_stored_responses_are_receipts_not_live_data(client: httpx.AsyncClient) -> None:
    body = await _metadata(client)

    assert "receipts of submissions as they arrived" in body["implementation"]["description"]
    response_resource = _resource(body, "QuestionnaireResponse")
    assert response_resource["documentation"] == (
        "One response per request; stored responses are receipts of what was submitted"
    )


async def test_metadata_declares_capture_against_every_captured_response_profile(client: httpx.AsyncClient) -> None:
    response_resource = _resource(await _metadata(client), "QuestionnaireResponse")

    interactions = response_resource["interaction"]
    assert [interaction["code"] for interaction in interactions] == ["create", "read", "search-type"]
    assert response_resource["supportedProfile"] == [
        f"{CANONICAL}/StructureDefinition/d2-aggregate-response",
        f"{CANONICAL}/StructureDefinition/d2-event-response",
        f"{CANONICAL}/StructureDefinition/d2-tracker-registration-response",
        f"{CANONICAL}/StructureDefinition/d2-tracker-event-response",
        f"{CANONICAL}/StructureDefinition/d2-tracked-entity-response",
    ]


async def test_metadata_lists_only_the_read_types_the_store_holds(client: httpx.AsyncClient) -> None:
    types = _resource_types(await _metadata(client))

    assert types == [
        "QuestionnaireResponse",
        "Questionnaire",
        "CodeSystem",
        "Organization",
        "StructureDefinition",
        "ImplementationGuide",
        # Held by every run, whatever the guide publishes: the facade's own $evaluate definition.
        "OperationDefinition",
    ]
    assert "ValueSet" not in types
    assert "Location" not in types


async def test_metadata_declares_the_conformance_resources_the_guide_publishes(
    client: httpx.AsyncClient,
) -> None:
    """A served project hosts its own guide, and the statement says so where a client will read it."""
    body = await _metadata(client)

    for resource_type in ("StructureDefinition", "ImplementationGuide"):
        declared = _resource(body, resource_type)
        assert [interaction["code"] for interaction in declared["interaction"]] == ["read", "search-type"]
        assert [parameter["name"] for parameter in declared["searchParam"]] == ["_id", "url", "identifier"]
        assert "hosted here read-only" in declared["documentation"]
        assert "url={canonical}" in declared["documentation"]


async def test_metadata_declares_no_conformance_type_the_store_does_not_hold(
    client: httpx.AsyncClient,
) -> None:
    """A conformance type nothing holds is not declared - SearchParameter, which no run publishes.

    OperationDefinition stopped being the example: the facade's own $evaluate definition rides
    every store, so that type is now always held and always declared.
    """
    types = _resource_types(await _metadata(client))

    assert "SearchParameter" not in types


async def test_the_questionnaire_search_parameter_states_how_it_matches(client: httpx.AsyncClient) -> None:
    """A reference search parameter usually implies more than this one does, so the entry says what it is."""
    response = _resource(await _metadata(client), "QuestionnaireResponse")

    questionnaire = next(parameter for parameter in response["searchParam"] if parameter["name"] == "questionnaire")
    assert questionnaire["type"] == "reference"
    assert "exact canonical equality" in questionnaire["documentation"]
    assert "no version suffix is stripped" in questionnaire["documentation"]


async def test_read_types_declare_the_three_search_parameters(client: httpx.AsyncClient) -> None:
    questionnaire = _resource(await _metadata(client), "Questionnaire")

    parameters = questionnaire["searchParam"]
    assert [parameter["name"] for parameter in parameters] == ["_id", "url", "identifier"]
    identifier = parameters[2]
    assert "http://dhis2.org/fhir/id/program|<uid>" in identifier["documentation"]
