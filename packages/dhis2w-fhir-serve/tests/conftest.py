"""Shared fixtures for dhis2w-fhir-serve tests: a compiled IG project on disk."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir.config import FhirProject, load_fhir_config

CANONICAL = "http://example.org/fhir"

MINIMAL_FHIR_TOML = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"

[generate.organisation_units]
root = ""
max_level = 0
"""

QUESTIONNAIRE = {
    "resourceType": "Questionnaire",
    "id": "d2-pr-anc-visit-q",
    "url": f"{CANONICAL}/Questionnaire/d2-pr-anc-visit-q",
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/program", "value": "ZzYYXq4fJie"},
        {"system": "http://dhis2.org/fhir/code/program", "value": "ANC_VISIT"},
    ],
    "status": "active",
    "title": "ANC Visit",
}

STRUCTURE_DEFINITION = {
    "resourceType": "StructureDefinition",
    "id": "d2-aggregate-response",
    "url": f"{CANONICAL}/StructureDefinition/d2-aggregate-response",
    "status": "active",
    "kind": "resource",
    "type": "QuestionnaireResponse",
}

IMPLEMENTATION_GUIDE = {
    "resourceType": "ImplementationGuide",
    "id": "dhis2.fhir.example",
    "url": f"{CANONICAL}/ImplementationGuide/dhis2.fhir.example",
    "status": "draft",
    "packageId": "dhis2.fhir.example",
}

ORGANIZATION = {
    "resourceType": "Organization",
    "id": "X",
    "identifier": [{"system": "http://dhis2.org/fhir/id/organisationUnit", "value": "ImspTQPwCqd"}],
    "name": "Sierra Leone",
}

CODE_SYSTEM = {
    "resourceType": "CodeSystem",
    "id": "Y",
    "url": f"{CANONICAL}/CodeSystem/Y",
    "identifier": [{"value": "bare-token-no-system"}],
    "status": "active",
    "content": "complete",
}


def _write_resource(path: Path, resource: dict[str, Any]) -> None:
    """Write one resource file, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resource, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def write_resource() -> Callable[[Path, dict[str, Any]], None]:
    """Return a helper that writes one resource file into a project tree."""
    return _write_resource


@pytest.fixture
def compiled_project(tmp_path: Path) -> FhirProject:
    """A project tree with a compiled IG plus a predefined registry and terminology tree."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(MINIMAL_FHIR_TOML, encoding="utf-8")

    compiled = tmp_path / "ig" / "fsh-generated" / "resources"
    _write_resource(compiled / "Questionnaire-d2-pr-anc-visit-q.json", QUESTIONNAIRE)
    _write_resource(compiled / "StructureDefinition-d2-aggregate-response.json", STRUCTURE_DEFINITION)
    _write_resource(compiled / "ImplementationGuide-dhis2.fhir.example.json", IMPLEMENTATION_GUIDE)

    predefined = tmp_path / "ig" / "input" / "resources"
    _write_resource(predefined / "registry" / "Organization-X.json", ORGANIZATION)
    _write_resource(predefined / "terminology" / "CodeSystem-Y.json", CODE_SYSTEM)

    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


@pytest.fixture
def empty_project(tmp_path: Path) -> FhirProject:
    """A project tree with a fhir.toml but nothing compiled yet."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(MINIMAL_FHIR_TOML, encoding="utf-8")
    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())
