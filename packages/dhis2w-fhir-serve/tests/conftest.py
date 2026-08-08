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
from dhis2w_fhir_serve.spool import RECEIVED_RESPONSES_RELATIVE_PATH, ResponseSpool, StoredResponseEnvelope
from dhis2w_fhir_serve.store import ResourceStore, load_compiled_store
from fastapi import FastAPI

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
    spool = ResponseSpool.scan(compiled_project.project_root / RECEIVED_RESPONSES_RELATIVE_PATH)
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


GOLDEN_DIRECTORY = Path(__file__).resolve().parents[2] / "dhis2w-fhir" / "tests" / "data" / "r4"

#: The canonical and identifier base the dhis2w-fhir goldens were compiled under.
CAPTURE_CANONICAL = "http://localhost:8080/fhir"
CAPTURE_IDENTIFIER_BASE = "http://dhis2.org/fhir"

CAPTURE_FHIR_TOML = f"""
[ig]
id = "dhis2.fhir.capture"
canonical = "{CAPTURE_CANONICAL}"
name = "Dhis2FhirCapture"
title = "DHIS2 FHIR Capture IG"
publisher = "Example Organisation"

[generate]
identifier_system_base = "{CAPTURE_IDENTIFIER_BASE}"

[generate.organisation_units]
root = ""
max_level = 0
"""

#: The compiled Questionnaires the capture project serves - one per form kind, plus the tracker
#: stage carrying a required question and a numeric bound.
CAPTURE_QUESTIONNAIRE_FILES = (
    "Questionnaire-BfMAe6Itzgt.json",
    "Questionnaire-EVTsupVis01.json",
    "Questionnaire-ZzYYXq4fJie.json",
    "Questionnaire-PsAncVisit1.json",
)

#: The data-dictionary terminology every generated form draws its question codes from.
CAPTURE_SUPPORT_FILES = (
    "CodeSystem-d2-de-cs.json",
    "CodeSystem-d2-coc-cs.json",
    "ValueSet-d2-de-vs.json",
    "ValueSet-d2-coc-vs.json",
)

AGGREGATE_RESPONSE_FILE = "QuestionnaireResponse-BfMAe6Itzgt-example-1.json"
EVENT_RESPONSE_FILE = "QuestionnaireResponse-EVTsupVis01-example-1.json"
TRACKER_RESPONSE_FILE = "QuestionnaireResponse-ZzYYXq4fJie-example-1.json"

#: The canonical of each served questionnaire, as its response names it.
AGGREGATE_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/BfMAe6Itzgt"
EVENT_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/EVTsupVis01"
TRACKER_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/ZzYYXq4fJie"
ANC_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/PsAncVisit1"

#: The extension urls and identifier systems the goldens were emitted under.
FORM_TYPE_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-form-type"
PERIOD_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-period"
ORGANISATION_UNIT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-organisation-unit"
TRACKER_ENROLLMENT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-tracker-enrollment"
TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
TRACKER_ENROLLMENT_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracker-enrollment"

#: The concept property an id-mode CodeSystem carries the DHIS2 option code on.
OPTION_CODE_PROPERTY_URI = f"{CAPTURE_IDENTIFIER_BASE}/property/dhis2-code"


#: The extensions a numeric question carries its inclusive bounds on.
MINIMUM_VALUE_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
MAXIMUM_VALUE_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"

TEMPORAL_QUESTIONNAIRE_UID = "PrTemporal1"
TEMPORAL_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{TEMPORAL_QUESTIONNAIRE_UID}"
SYMPTOM_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-os-OsSymptom01-cs"
SYMPTOM_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-os-OsSymptom01-vs"
UNPUBLISHED_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-os-Unpublished-vs"

#: An event form covering the value types the dhis2w-fhir goldens happen not to ask for - the three
#: temporal primitives, a URL, a repeating multi-select, a decimal with both bounds, and a question
#: bound to terminology this project never published. Written in the shape the emitter writes.
TEMPORAL_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": TEMPORAL_QUESTIONNAIRE_UID,
    "url": TEMPORAL_QUESTIONNAIRE,
    "title": "Temporal capture",
    "description": "DHIS2 event program Temporal capture (PrTemporal1) as a data capture form.",
    "extension": [{"url": FORM_TYPE_URL, "valueCode": "event"}],
    "identifier": [{"system": f"{CAPTURE_IDENTIFIER_BASE}/id/program", "value": TEMPORAL_QUESTIONNAIRE_UID}],
    "name": f"D2PR_{TEMPORAL_QUESTIONNAIRE_UID}",
    "status": "draft",
    "experimental": True,
    "subjectType": ["Location"],
    "item": [
        {"linkId": "DeVisitDate1", "text": "Visit date", "type": "date"},
        {"linkId": "DeVisitTime1", "text": "Visit time", "type": "time"},
        {"linkId": "DeVisitStamp", "text": "Visit stamp", "type": "dateTime"},
        {"linkId": "DeVisitLink1", "text": "Visit link", "type": "url"},
        {
            "linkId": "DeSymptoms01",
            "text": "Symptoms",
            "type": "choice",
            "repeats": True,
            "answerValueSet": SYMPTOM_VALUE_SET,
        },
        {
            "linkId": "DeCoverage01",
            "text": "Coverage",
            "type": "decimal",
            "extension": [
                {"url": MINIMUM_VALUE_URL, "valueDecimal": 0},
                {"url": MAXIMUM_VALUE_URL, "valueDecimal": 100},
            ],
        },
        {
            "linkId": "DeOpenBind01",
            "text": "Bound to terminology this project never published",
            "type": "choice",
            "answerValueSet": UNPUBLISHED_VALUE_SET,
        },
    ],
}

#: The option set the temporal form's multi-select is answered from, in id mode like every other pair.
SYMPTOM_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": SYMPTOM_CODE_SYSTEM.rsplit("/", 1)[-1],
    "url": SYMPTOM_CODE_SYSTEM,
    "status": "draft",
    "content": "complete",
    "caseSensitive": True,
    "valueSet": SYMPTOM_VALUE_SET,
    "property": [{"code": "dhis2-code", "uri": f"{CAPTURE_IDENTIFIER_BASE}/property/dhis2-code", "type": "string"}],
    "concept": [
        {"code": "OpFever0001", "display": "Fever", "property": [{"code": "dhis2-code", "valueString": "FEVER"}]},
        {"code": "OpCough0001", "display": "Cough", "property": [{"code": "dhis2-code", "valueString": "COUGH"}]},
    ],
    "count": 2,
}

SYMPTOM_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": SYMPTOM_VALUE_SET.rsplit("/", 1)[-1],
    "url": SYMPTOM_VALUE_SET,
    "status": "draft",
    "compose": {"include": [{"system": SYMPTOM_CODE_SYSTEM}]},
}


def golden(filename: str) -> dict[str, Any]:
    """One dhis2w-fhir golden resource, parsed."""
    parsed: dict[str, Any] = json.loads((GOLDEN_DIRECTORY / filename).read_text(encoding="utf-8"))
    return parsed


def _codings_by_system(response: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Every coded answer of one response golden, as `code -> display` per code system."""
    found: dict[str, dict[str, str]] = {}

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            for answer in item.get("answer", []):
                coding = answer.get("valueCoding")
                if coding is not None:
                    found.setdefault(coding["system"], {})[coding["code"]] = coding.get("display", "")
            walk(item.get("item", []))

    walk(response.get("item", []))
    return found


def _option_code(display: str) -> str:
    """A stable DHIS2-style option code for a synthesised concept, derived from its display."""
    return "".join(character if character.isalnum() else "_" for character in display).upper().strip("_")


def _option_terminology(response: dict[str, Any]) -> list[dict[str, Any]]:
    """The CodeSystem / ValueSet pair behind every option set the tracker response answers from.

    The goldens publish the questionnaires and the responses but not the option-set terminology
    they bind, so the pairs are built here in the shape the emitter writes: concept codes are
    DHIS2 option UIDs, and the option code rides along as the `dhis2-code` property.
    """
    resources: list[dict[str, Any]] = []
    for system, concepts in sorted(_codings_by_system(response).items()):
        code_system_id = system.rsplit("/", 1)[-1]
        value_set_id = f"{code_system_id.removesuffix('-cs')}-vs"
        value_set_url = f"{CAPTURE_CANONICAL}/ValueSet/{value_set_id}"
        resources.append(
            {
                "resourceType": "CodeSystem",
                "id": code_system_id,
                "url": system,
                "status": "draft",
                "content": "complete",
                "caseSensitive": True,
                "valueSet": value_set_url,
                "property": [
                    {
                        "code": "dhis2-code",
                        "uri": OPTION_CODE_PROPERTY_URI,
                        "description": "DHIS2 option code.",
                        "type": "string",
                    }
                ],
                "concept": [
                    {
                        "code": code,
                        "display": display,
                        "property": [{"code": "dhis2-code", "valueString": _option_code(display)}],
                    }
                    for code, display in sorted(concepts.items())
                ],
                "count": len(concepts),
            }
        )
        resources.append(
            {
                "resourceType": "ValueSet",
                "id": value_set_id,
                "url": value_set_url,
                "status": "draft",
                "compose": {"include": [{"system": system}]},
            }
        )
    return resources


@pytest.fixture
def capture_project(tmp_path: Path) -> FhirProject:
    """A project serving the dhis2w-fhir goldens: three form kinds plus the terminology they bind."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(CAPTURE_FHIR_TOML, encoding="utf-8")

    compiled = tmp_path / "ig" / "fsh-generated" / "resources"
    for filename in (*CAPTURE_QUESTIONNAIRE_FILES, *CAPTURE_SUPPORT_FILES):
        _write_resource(compiled / filename, golden(filename))
    _write_resource(compiled / f"Questionnaire-{TEMPORAL_QUESTIONNAIRE_UID}.json", TEMPORAL_QUESTIONNAIRE_BODY)

    terminology = tmp_path / "ig" / "input" / "resources" / "terminology"
    built = [*_option_terminology(golden(TRACKER_RESPONSE_FILE)), SYMPTOM_CODE_SYSTEM_BODY, SYMPTOM_VALUE_SET_BODY]
    for resource in built:
        _write_resource(terminology / f"{resource['resourceType']}-{resource['id']}.json", resource)

    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


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
