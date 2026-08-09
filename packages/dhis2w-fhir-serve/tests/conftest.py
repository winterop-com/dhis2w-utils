"""Shared fixtures for dhis2w-fhir-serve tests: a compiled IG project on disk, and the app over it.

Two projects are served here. `compiled_project` is a hand-written minimum - enough resources to
exercise reading, searching, and refusing. `capture_project` is the real thing: the compiled
Questionnaires and terminology the dhis2w-fhir package pins as its own goldens, plus the option-set
CodeSystem / ValueSet pairs the tracker form binds. The capture path is checked against those
goldens on purpose - the QuestionnaireResponse goldens *are* what a compliant client posts, so a
test that accepts them is a test that the server accepts the documented contract.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capture import CaptureIndexCache, CaptureNaming
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool, StoredResponseEnvelope
from dhis2w_fhir_serve.store import ResourceStore, load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    AGGREGATE_RESPONSE_FILE,
    CAPTURE_CANONICAL,
    CAPTURE_IDENTIFIER_BASE,
    EVENT_RESPONSE_FILE,
    TRACKER_RESPONSE_FILE,
    build_capture_project,
    golden,
)

CANONICAL = "http://example.org/fhir"

BASE_URL = "http://serve.test"

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


ANC_QUESTIONNAIRE_URL = f"{CANONICAL}/Questionnaire/d2-pr-anc-visit-q"
OTHER_QUESTIONNAIRE_URL = f"{CANONICAL}/Questionnaire/d2-ds-monthly-q"


def _envelope(response_id: str, received_at: str, questionnaire: str, form_kind: str) -> StoredResponseEnvelope:
    """One receipt as the capture path stores it."""
    return StoredResponseEnvelope(
        response_id=response_id,
        received_at=received_at,
        form_kind=form_kind,
        questionnaire=questionnaire,
        response={
            "resourceType": "QuestionnaireResponse",
            "id": response_id,
            "questionnaire": questionnaire,
            "status": "completed",
        },
    )


#: The receipts every serving fixture starts with, deliberately saved out of received order.
STORED_RESPONSES = (
    _envelope("receipt-middle", "2026-08-02T09:00:00Z", OTHER_QUESTIONNAIRE_URL, "aggregate"),
    _envelope("receipt-newest", "2026-08-03T09:00:00Z", ANC_QUESTIONNAIRE_URL, "event"),
    _envelope("receipt-oldest", "2026-08-01T09:00:00Z", ANC_QUESTIONNAIRE_URL, "event"),
)


@pytest.fixture
def stored_responses() -> tuple[StoredResponseEnvelope, ...]:
    """The receipts seeded into the spool before the app scans it; override to serve a different set."""
    return STORED_RESPONSES


@pytest.fixture
def app(compiled_project: FhirProject, stored_responses: tuple[StoredResponseEnvelope, ...]) -> FastAPI:
    """The facade over the compiled project, with its spool seeded on disk before startup."""
    spool = ResponseSpool.at(compiled_project.project_root)
    for envelope in stored_responses:
        spool.save(envelope)
    return create_app(ServeSettings(project_dir=compiled_project.project_root))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over the facade, with the lifespan run around the test."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


#: The capture fixture project - its resources, its names, and the builder that writes it - lives in
#: `fixture_project.py` because the Playwright suite runs the same builder to boot a real server.
AGGREGATE_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/BfMAe6Itzgt"
EVENT_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/EVTsupVis01"
TRACKER_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/ZzYYXq4fJie"
ANC_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/PsAncVisit1"

#: The extension urls and identifier systems the goldens were emitted under.
PERIOD_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-period"
ORGANISATION_UNIT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-organisation-unit"
TRACKER_ENROLLMENT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-tracker-enrollment"
TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
TRACKER_ENROLLMENT_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracker-enrollment"


@pytest.fixture
def capture_project(tmp_path: Path) -> FhirProject:
    """A project serving the dhis2w-fhir goldens: three form kinds plus the terminology they bind."""
    return build_capture_project(tmp_path)


@pytest.fixture
def strict_codes() -> bool:
    """Whether the capture app refuses a code outside the served terminology; override to flip it."""
    return False


@pytest.fixture
def capture_app(capture_project: FhirProject, strict_codes: bool) -> FastAPI:
    """The facade over the golden project, with an empty spool."""
    return create_app(ServeSettings(project_dir=capture_project.project_root, strict_codes=strict_codes))


@pytest.fixture
async def capture_client(capture_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over the golden project, with the lifespan run around the test."""
    async with capture_app.router.lifespan_context(capture_app):
        transport = httpx.ASGITransport(app=capture_app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


@pytest.fixture
def load_golden() -> Callable[[str], dict[str, Any]]:
    """Return a helper that parses one dhis2w-fhir golden resource by file name."""
    return golden


@pytest.fixture
def capture_store(capture_project: FhirProject) -> ResourceStore:
    """The golden project's resources, loaded the way the lifespan loads them."""
    return load_compiled_store(capture_project)


@pytest.fixture
def capture_naming(capture_project: FhirProject) -> CaptureNaming:
    """The capture contract's urls and identifier systems, derived from the golden project."""
    return CaptureNaming.from_project(capture_project)


@pytest.fixture
def capture_indexes() -> CaptureIndexCache:
    """An empty index cache, as a freshly started facade holds."""
    return CaptureIndexCache()


@pytest.fixture
def aggregate_response() -> dict[str, Any]:
    """The golden aggregate submission, exactly as the IG publishes it."""
    return golden(AGGREGATE_RESPONSE_FILE)


@pytest.fixture
def event_response() -> dict[str, Any]:
    """The golden event submission, exactly as the IG publishes it."""
    return golden(EVENT_RESPONSE_FILE)


@pytest.fixture
def tracker_response() -> dict[str, Any]:
    """The golden tracker-event submission, exactly as the IG publishes it."""
    return golden(TRACKER_RESPONSE_FILE)
