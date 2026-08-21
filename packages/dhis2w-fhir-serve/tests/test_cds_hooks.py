"""CDS Hooks: the discovery document, and the one service that runs a CQL library over a prefetch.

The claims are what the surface promises and what it refuses. Discovery names one service and its
prefetch templates. An invocation evaluates the caller's own library over what the EHR prefetched -
never over anything the hook merely pointed at - and turns the defines that said something into
cards. A library that will not parse is a card an EHR can render, not a 500 it can only log. And a
service with no rules to run refuses rather than answering an empty list, because a caller who sent
no library learns nothing from silence.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.routes.cds import CQL_LIBRARY_SERVICE_HOOK, CQL_LIBRARY_SERVICE_ID

LIBRARY = """
library Advice version '1.0'
using FHIR version '4.0.1'

define IsOverdueForAVisit: exists [Condition]
define QuietDefine: false
define WhatToDo: 'Book a follow-up visit'
"""

PATIENT: dict[str, Any] = {"resourceType": "Patient", "id": "ada", "birthDate": "1815-12-10"}
CONDITION: dict[str, Any] = {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/ada"}}


def _invocation(**context: object) -> dict[str, Any]:
    """One `patient-view` invocation with the prefetch an EHR would have filled."""
    return {
        "hook": CQL_LIBRARY_SERVICE_HOOK,
        "hookInstance": "6d0b0c0e-0f2a-4a2e-9f4a-6f4a0a1b2c3d",
        "context": {"patientId": "ada", **context},
        "prefetch": {
            "patient": PATIENT,
            "conditions": {
                "resourceType": "Bundle",
                "type": "searchset",
                "entry": [{"resource": CONDITION}],
            },
        },
    }


async def test_discovery_names_one_service_and_what_it_wants_prefetched(client: httpx.AsyncClient) -> None:
    """One service, honestly described, with the prefetch templates an EHR fills before invoking."""
    answered = await client.get("/cds-services")

    assert answered.status_code == 200
    services = answered.json()["services"]
    assert len(services) == 1
    assert services[0]["id"] == CQL_LIBRARY_SERVICE_ID
    assert services[0]["hook"] == CQL_LIBRARY_SERVICE_HOOK
    assert services[0]["prefetch"]["patient"] == "Patient/{{context.patientId}}"
    assert "context.library" in services[0]["usageRequirements"]


async def test_an_invocation_answers_a_card_per_define_that_said_something(client: httpx.AsyncClient) -> None:
    """A define answering true becomes its own name; one answering a message becomes that message."""
    answered = await client.post(f"/cds-services/{CQL_LIBRARY_SERVICE_ID}", json=_invocation(library=LIBRARY))

    assert answered.status_code == 200
    summaries = [card["summary"] for card in answered.json()["cards"]]
    assert summaries == ["IsOverdueForAVisit", "Book a follow-up visit"]
    assert {card["indicator"] for card in answered.json()["cards"]} == {"info"}


async def test_the_prefetch_is_the_only_data_the_library_sees(client: httpx.AsyncClient) -> None:
    """The retrieves read what the EHR sent and nothing else - `fhirServer` is read and never followed."""
    invocation = _invocation(library=LIBRARY)
    invocation["prefetch"] = {"patient": PATIENT}
    invocation["fhirServer"] = "https://someone-elses-ehr.example/fhir"

    answered = await client.post(f"/cds-services/{CQL_LIBRARY_SERVICE_ID}", json=invocation)

    # No Condition was prefetched, so the define that needs one has nothing to say.
    assert [card["summary"] for card in answered.json()["cards"]] == ["Book a follow-up visit"]


async def test_one_define_can_be_asked_for_by_name(client: httpx.AsyncClient) -> None:
    """`expressionName` narrows the invocation to the one rule a caller wanted run."""
    answered = await client.post(
        f"/cds-services/{CQL_LIBRARY_SERVICE_ID}",
        json=_invocation(library=LIBRARY, expressionName="WhatToDo"),
    )

    assert [card["summary"] for card in answered.json()["cards"]] == ["Book a follow-up visit"]


async def test_a_library_that_will_not_parse_is_a_card_rather_than_a_failure(client: httpx.AsyncClient) -> None:
    """An EHR gets an answer it can render, carrying the parser's own message and where it stopped."""
    answered = await client.post(
        f"/cds-services/{CQL_LIBRARY_SERVICE_ID}",
        json=_invocation(library="library Broken version '1.0'\ndefine X: 1 +\n"),
    )

    assert answered.status_code == 200
    card = answered.json()["cards"][0]
    assert card["indicator"] == "warning"
    assert card["summary"].startswith("The CQL library did not parse at line")
    assert card["detail"]


async def test_an_invocation_with_no_rules_is_refused_rather_than_answered_with_nothing(
    client: httpx.AsyncClient,
) -> None:
    """Silence would teach nobody why; the refusal names both ways to send the rules."""
    answered = await client.post(f"/cds-services/{CQL_LIBRARY_SERVICE_ID}", json=_invocation())

    assert answered.status_code == 400
    assert "context.libraryId" in answered.json()["issue"][0]["diagnostics"]


async def test_a_service_this_facade_does_not_offer_is_not_found(client: httpx.AsyncClient) -> None:
    """One service is one service: an id nothing answers is a 404 OperationOutcome, not an empty card list."""
    answered = await client.post("/cds-services/some-other-service", json=_invocation(library=LIBRARY))

    assert answered.status_code == 404
    assert answered.json()["resourceType"] == "OperationOutcome"


@pytest.fixture
def library_project(
    compiled_project: FhirProject, write_resource: Callable[[Path, dict[str, Any]], None]
) -> FhirProject:
    """The compiled project with one Library resource in it, embedding its CQL inline."""
    write_resource(
        compiled_project.ig_directory / "fsh-generated" / "resources" / "Library-advice.json",
        {
            "resourceType": "Library",
            "id": "advice",
            "status": "active",
            "type": {"coding": [{"code": "logic-library"}]},
            "content": [
                {
                    "contentType": "text/cql",
                    "data": base64.b64encode(LIBRARY.encode("utf-8")).decode("ascii"),
                }
            ],
        },
    )
    return compiled_project


async def test_a_library_this_guide_publishes_is_run_by_id(
    library_project: FhirProject, client: httpx.AsyncClient
) -> None:
    """The other way to name the rules: a Library the guide publishes, whose inline content is decoded here."""
    answered = await client.post(f"/cds-services/{CQL_LIBRARY_SERVICE_ID}", json=_invocation(libraryId="advice"))

    assert answered.status_code == 200
    assert "Book a follow-up visit" in [card["summary"] for card in answered.json()["cards"]]


async def test_a_library_id_this_guide_does_not_publish_is_not_found(client: httpx.AsyncClient) -> None:
    """A named Library the store does not hold is a 404 about that Library, not a silent empty answer."""
    answered = await client.post(f"/cds-services/{CQL_LIBRARY_SERVICE_ID}", json=_invocation(libraryId="nothing-here"))

    assert answered.status_code == 404
    assert "Library" in answered.json()["issue"][0]["diagnostics"]


def test_the_discovery_document_is_the_shape_cds_hooks_defines() -> None:
    """The wire keys are the specification's, camelCase and all, whatever the fields are named here."""
    from dhis2w_fhir_serve.routes.cds import CdsDiscovery, CdsService

    document = CdsDiscovery(services=(CdsService(id="x", hook="patient-view", title="X", description="x"),)).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )

    assert json.loads(json.dumps(document))["services"][0]["hook"] == "patient-view"
