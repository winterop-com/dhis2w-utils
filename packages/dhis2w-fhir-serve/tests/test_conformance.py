"""The guide's own definitions, served: read by id, resolved by canonical, and hosted in both modes.

A served project self-hosts the conformance resources its compiled guide holds, because a canonical
has to resolve somewhere and until the guide is published under its own canonical this server is the
only address it has. What these cases hold to is that the new types are ordinary read types - the
same route, the same search grammar, the same negotiation - rather than a surface of their own.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir_serve.store import GUIDE_CONFORMANCE_RESOURCE_TYPES, load_compiled_conformance_entries

WriteResource = Callable[[Path, dict[str, Any]], None]

CANONICAL = "http://example.org/fhir"
PROFILE_CANONICAL = f"{CANONICAL}/StructureDefinition/d2-aggregate-response"
GUIDE_CANONICAL = f"{CANONICAL}/ImplementationGuide/dhis2.fhir.example"
FHIR_JSON = "application/fhir+json"

OPERATION_DEFINITION: dict[str, Any] = {
    "resourceType": "OperationDefinition",
    "id": "d2-generate",
    "url": f"{CANONICAL}/OperationDefinition/d2-generate",
    "name": "D2GenerateOperation",
    "status": "active",
    "kind": "operation",
    "code": "generate",
    "system": False,
    "type": False,
    "instance": True,
}


async def test_a_profile_is_read_at_its_own_address(client: httpx.AsyncClient) -> None:
    response = await client.get("/StructureDefinition/d2-aggregate-response")

    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON
    assert response.json()["url"] == PROFILE_CANONICAL


async def test_the_guide_resource_is_read_at_its_own_address(client: httpx.AsyncClient) -> None:
    response = await client.get("/ImplementationGuide/dhis2.fhir.example")

    assert response.status_code == 200
    assert response.json()["packageId"] == "dhis2.fhir.example"


@pytest.mark.parametrize(
    ("path", "canonical"),
    [
        ("/StructureDefinition", PROFILE_CANONICAL),
        ("/ImplementationGuide", GUIDE_CANONICAL),
    ],
)
async def test_a_canonical_found_on_a_resource_is_resolved_by_searching_url(
    client: httpx.AsyncClient, path: str, canonical: str
) -> None:
    """The search a client actually runs: it holds a canonical it read off a response, and no id."""
    response = await client.get(path, params={"url": canonical})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "searchset"
    assert body["total"] == 1
    assert body["entry"][0]["resource"]["url"] == canonical
    assert body["link"][0]["url"] == f"http://serve.test{path}?{urlencode({'url': canonical})}"


async def test_a_canonical_this_guide_never_published_matches_nothing(client: httpx.AsyncClient) -> None:
    response = await client.get("/StructureDefinition", params={"url": f"{CANONICAL}/StructureDefinition/d2-nothing"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert "entry" not in body


async def test_a_search_naming_no_parameter_answers_every_profile_the_guide_holds(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/StructureDefinition")

    body = response.json()
    assert body["total"] == 1
    assert body["entry"][0]["fullUrl"] == "http://serve.test/StructureDefinition/d2-aggregate-response"


async def test_a_profile_id_the_guide_never_published_is_not_found(client: httpx.AsyncClient) -> None:
    """Not-found rather than not-supported: the type is served, and this id is not one of its resources."""
    response = await client.get("/StructureDefinition/d2-nothing")

    assert response.status_code == 404
    body = response.json()
    assert body["resourceType"] == "OperationOutcome"
    assert body["issue"][0]["code"] == "not-found"
    assert "d2-nothing" in body["issue"][0]["diagnostics"]


@pytest.mark.parametrize(
    "path",
    [
        "/StructureDefinition/d2-aggregate-response",
        "/StructureDefinition",
        "/ImplementationGuide/dhis2.fhir.example",
        "/ImplementationGuide",
    ],
)
async def test_format_overrides_a_header_naming_no_json_on_the_new_reads_too(
    client: httpx.AsyncClient, path: str
) -> None:
    """The conformance reads ride the same router as every other read, so they negotiate identically."""
    separator = "&" if "?" in path else "?"

    response = await client.get(f"{path}{separator}_format=json", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert response.headers["content-type"] == FHIR_JSON


@pytest.mark.parametrize("path", ["/StructureDefinition/d2-aggregate-response", "/StructureDefinition"])
async def test_a_format_this_server_does_not_serve_is_refused_on_the_new_reads_too(
    client: httpx.AsyncClient, path: str
) -> None:
    separator = "&" if "?" in path else "?"

    response = await client.get(f"{path}{separator}_format=xml")

    assert response.status_code == 406
    assert response.json()["resourceType"] == "OperationOutcome"
    assert "`_format=xml`" in response.json()["issue"][0]["diagnostics"]


def test_the_conformance_types_are_read_out_of_the_compiled_tree_alone(compiled_project: FhirProject) -> None:
    """What a live store hosts: the guide's definitions, and none of the artifacts it builds itself."""
    entries = load_compiled_conformance_entries(compiled_project)

    assert sorted(entry.resource_type for entry in entries) == ["ImplementationGuide", "StructureDefinition"]
    assert [entry.source for entry in entries] == [
        "ig/fsh-generated/resources/ImplementationGuide-dhis2.fhir.example.json",
        "ig/fsh-generated/resources/StructureDefinition-d2-aggregate-response.json",
    ]


def test_an_operation_definition_beside_them_is_read_as_well(
    compiled_project: FhirProject, write_resource: WriteResource
) -> None:
    """A generated guide publishes one, and it is the definition `/metadata` names for `$generate`."""
    compiled = compiled_project.ig_directory / "fsh-generated" / "resources"
    write_resource(compiled / "OperationDefinition-d2-generate.json", OPERATION_DEFINITION)

    entries = load_compiled_conformance_entries(compiled_project)

    assert "OperationDefinition" in {entry.resource_type for entry in entries}
    assert "OperationDefinition" in GUIDE_CONFORMANCE_RESOURCE_TYPES


def test_a_project_with_nothing_compiled_beside_it_hosts_none(empty_project: FhirProject) -> None:
    """A live run over a project that was never compiled has nothing on disk to host, and says so."""
    assert load_compiled_conformance_entries(empty_project) == ()


def test_a_compiled_tree_holding_no_conformance_resource_hosts_none(
    tmp_path: Path, write_resource: WriteResource
) -> None:
    """A build that wrote only instances leaves nothing to resolve a canonical against."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(
        '[ig]\nid = "dhis2.fhir.example"\ncanonical = "http://example.org/fhir"\n'
        'name = "Dhis2FhirExample"\ntitle = "DHIS2 FHIR Example IG"\npublisher = "Example Organisation"\n'
        '\n[generate.organisation_units]\nroot = ""\nmax_level = 0\n',
        encoding="utf-8",
    )
    compiled = tmp_path / "ig" / "fsh-generated" / "resources"
    write_resource(
        compiled / "Questionnaire-only.json",
        {"resourceType": "Questionnaire", "id": "only", "status": "active"},
    )
    project = FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())

    assert load_compiled_conformance_entries(project) == ()
