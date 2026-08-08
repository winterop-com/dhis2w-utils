"""`GET /ConceptMap/$translate`: the operation over the option-set ConceptMaps the project publishes.

Self-contained by design - the fixtures here write their own project tree and emit its ConceptMaps
with the generator itself, so what the operation is asked to translate is exactly what
`d2w fhir generate` writes into `ig/input/resources/concept-maps/`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir import build_option_set_concept_map_artifacts
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from fastapi import FastAPI

_BASE_URL = "http://serve.test"

_CANONICAL = "http://example.org/fhir"

_IDENTIFIER_BASE = "http://dhis2.org/fhir"

_FHIR_JSON = "application/fhir+json"

_TRANSLATE_PATH = "/ConceptMap/$translate"

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.translate"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTranslate"
title = "DHIS2 FHIR Translate IG"
publisher = "Example Organisation"

[generate.organisation_units]
root = ""
max_level = 0
"""

#: The option set whose ConceptMap the operation is asked about, in the shape the generator reads.
_BIRTH_TYPE = OptionSetIn(
    uid="Xa1b2c3d4e5",
    name="Birth type",
    options=[
        OptionIn(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1),
        OptionIn(uid="EBE0c8sZazS", code="CS", name="Scheduled Cesarean", sort_order=2),
    ],
)

#: The systems the emitted map names: the option set's own CodeSystem, and the two DHIS2 identifier systems.
_CODE_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-os-Xa1b2c3d4e5-cs"
_CONCEPT_MAP = f"{_CANONICAL}/ConceptMap/d2-os-Xa1b2c3d4e5-cm"
_OPTION_SYSTEM = f"{_IDENTIFIER_BASE}/id/option"
_OPTION_CODE_SYSTEM = f"{_IDENTIFIER_BASE}/id/option-code"

#: The concept the tests translate, and the two DHIS2 identifiers the map states for it.
_CONCEPT_CODE = "kRRUtYaGett"
_OPTION_CODE = "NB"

_QUESTIONNAIRE = {
    "resourceType": "Questionnaire",
    "id": "d2-pr-anc-visit-q",
    "url": f"{_CANONICAL}/Questionnaire/d2-pr-anc-visit-q",
    "status": "active",
    "title": "ANC Visit",
}


@pytest.fixture
def translate_project(tmp_path: Path) -> FhirProject:
    """A project whose predefined tree holds the ConceptMaps the generator emits for one option set."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(_FHIR_TOML, encoding="utf-8")
    project = FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())

    compiled = project.ig_directory / "fsh-generated" / "resources"
    compiled.mkdir(parents=True)
    (compiled / "Questionnaire-d2-pr-anc-visit-q.json").write_text(json.dumps(_QUESTIONNAIRE), encoding="utf-8")

    artifacts = build_option_set_concept_map_artifacts(
        [_BIRTH_TYPE],
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    )
    for artifact in artifacts:
        path = project.resources_directory / artifact.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
    return project


@pytest.fixture
def translate_app(translate_project: FhirProject) -> FastAPI:
    """The facade over the project holding the ConceptMaps."""
    return create_app(ServeSettings(project_dir=translate_project.project_root))


@pytest.fixture
async def translate_client(translate_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over the facade, with the lifespan run around the test."""
    async with translate_app.router.lifespan_context(translate_app):
        transport = httpx.ASGITransport(app=translate_app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
            yield http


def _parts(match: dict[str, Any]) -> dict[str, Any]:
    """One `match` parameter's parts, by name."""
    return {part["name"]: part for part in match["part"]}


def _matches(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Every `match` parameter of one operation body, in the order it was answered."""
    return [parameter for parameter in body["parameter"] if parameter["name"] == "match"]


def _named(body: dict[str, Any], name: str) -> dict[str, Any] | None:
    """The first parameter of one operation body carrying `name`, or None."""
    return next((parameter for parameter in body["parameter"] if parameter["name"] == name), None)


async def test_translate_answers_both_dhis2_identifiers_for_one_concept(translate_client: httpx.AsyncClient) -> None:
    response = await translate_client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE})

    assert response.status_code == 200
    assert response.headers["content-type"] == _FHIR_JSON
    body = response.json()
    assert body["resourceType"] == "Parameters"
    assert body["parameter"][0] == {"name": "result", "valueBoolean": True}
    codings = [_parts(match)["concept"]["valueCoding"] for match in _matches(body)]
    assert codings == [
        {"system": _OPTION_SYSTEM, "code": _CONCEPT_CODE, "display": "Natural Birth"},
        {"system": _OPTION_CODE_SYSTEM, "code": _OPTION_CODE, "display": "Natural Birth"},
    ]


async def test_a_match_states_its_equivalence_and_the_map_it_came_from(translate_client: httpx.AsyncClient) -> None:
    response = await translate_client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE})

    parts = _parts(_matches(response.json())[0])
    assert parts["equivalence"] == {"name": "equivalence", "valueCode": "equal"}
    assert parts["source"] == {"name": "source", "valueUri": _CONCEPT_MAP}


@pytest.mark.parametrize("spelling", ["targetsystem", "targetSystem"])
async def test_a_target_system_narrows_the_answer_to_one_group(
    translate_client: httpx.AsyncClient, spelling: str
) -> None:
    response = await translate_client.get(
        _TRANSLATE_PATH,
        params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE, spelling: _OPTION_CODE_SYSTEM},
    )

    assert response.status_code == 200
    body = response.json()
    codings = [_parts(match)["concept"]["valueCoding"] for match in _matches(body)]
    assert codings == [{"system": _OPTION_CODE_SYSTEM, "code": _OPTION_CODE, "display": "Natural Birth"}]


async def test_an_unknown_system_answers_false_with_a_message(translate_client: httpx.AsyncClient) -> None:
    response = await translate_client.get(
        _TRANSLATE_PATH, params={"system": "http://example.org/nowhere", "code": _CONCEPT_CODE}
    )

    assert response.status_code == 200
    body = response.json()
    assert _named(body, "result") == {"name": "result", "valueBoolean": False}
    message = _named(body, "message")
    assert message is not None
    assert "http://example.org/nowhere" in message["valueString"]
    assert _matches(body) == []


async def test_an_unknown_code_answers_false_with_a_message(translate_client: httpx.AsyncClient) -> None:
    response = await translate_client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": "nobody"})

    body = response.json()
    assert _named(body, "result") == {"name": "result", "valueBoolean": False}
    message = _named(body, "message")
    assert message is not None
    assert "nobody" in message["valueString"]


async def test_an_unknown_target_system_answers_false_with_a_message(translate_client: httpx.AsyncClient) -> None:
    response = await translate_client.get(
        _TRANSLATE_PATH,
        params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE, "targetsystem": "http://example.org/nowhere"},
    )

    body = response.json()
    assert _named(body, "result") == {"name": "result", "valueBoolean": False}
    assert _matches(body) == []


@pytest.mark.parametrize(
    ("params", "missing"),
    [
        pytest.param({"code": _CONCEPT_CODE}, "system", id="no_system"),
        pytest.param({"system": _CODE_SYSTEM}, "code", id="no_code"),
        pytest.param({}, "system", id="neither"),
        pytest.param({"system": "", "code": _CONCEPT_CODE}, "system", id="empty_system"),
    ],
)
async def test_a_call_missing_a_required_parameter_is_an_operation_outcome(
    translate_client: httpx.AsyncClient, params: dict[str, str], missing: str
) -> None:
    response = await translate_client.get(_TRANSLATE_PATH, params=params)

    assert response.status_code == 400
    assert response.headers["content-type"] == _FHIR_JSON
    body = response.json()
    assert body["resourceType"] == "OperationOutcome"
    assert body["issue"][0]["code"] == "invalid"
    assert f"`{missing}`" in body["issue"][0]["diagnostics"]


async def test_the_operation_wins_over_the_read_catch_all(translate_client: httpx.AsyncClient) -> None:
    operation = await translate_client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE})
    read = await translate_client.get("/ConceptMap/d2-os-Xa1b2c3d4e5-cm")

    assert operation.status_code == 200
    assert operation.json()["resourceType"] == "Parameters"
    assert read.status_code == 404
    assert read.json()["issue"][0]["code"] == "not-supported"


async def test_metadata_declares_the_operation_when_the_store_holds_concept_maps(
    translate_client: httpx.AsyncClient,
) -> None:
    body = (await translate_client.get("/metadata")).json()

    operations = body["rest"][0]["operation"]
    assert [operation["name"] for operation in operations] == ["translate"]
    assert operations[0]["definition"] == "http://hl7.org/fhir/OperationDefinition/ConceptMap-translate"
    assert operations[0]["documentation"]
    assert "ConceptMap" not in [resource["type"] for resource in body["rest"][0]["resource"]]


async def test_metadata_declares_no_operation_when_the_store_holds_no_concept_map(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get("/metadata")).json()

    assert "operation" not in body["rest"][0]


async def test_translate_over_a_store_without_concept_maps_answers_false(client: httpx.AsyncClient) -> None:
    response = await client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE})

    assert response.status_code == 200
    assert _named(response.json(), "result") == {"name": "result", "valueBoolean": False}
