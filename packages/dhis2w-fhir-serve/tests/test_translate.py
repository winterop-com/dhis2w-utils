"""`GET /ConceptMap/$translate`: the operation over the ConceptMaps the project publishes.

Self-contained by design - the fixtures here write their own project tree and emit its ConceptMaps
with the generator itself, so what the operation is asked to translate is exactly what
`d2w fhir generate` writes into `ig/input/resources/concept-maps/`. Two families land there, so
the operation is asked about an option set and about a category over the one store.

The third is asked over the compiled tree: the tracked-entity-type resource map is authored in FSH
beside the vocabulary it maps, so a compiled guide holds it in `fsh-generated/resources/` rather
than in the predefined tree. The operation reads every served map alike, which is what this proves -
hand it a DHIS2 tracked entity type and it answers with the FHIR resource type its registrations
are published as.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest
from dhis2w_fhir import build_category_concept_map_artifacts, build_option_set_concept_map_artifacts
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir.resources.categories.schemas import CategoryIn
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.questionnaires.documents import build_data_dictionary_documents
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireItemIn, QuestionnaireSourceIn
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

#: The category whose ConceptMap sits beside the option set's in the same served directory.
_SEX = CategoryIn(
    uid="O5P6e8yu1T6",
    name="Sex",
    options=[
        OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0),
        OptionIn(uid="apsOixVZlf1", code="M", name="Male", sort_order=1),
    ],
)

#: The systems the emitted map names: the option set's own CodeSystem, and the two DHIS2 identifier systems.
_CODE_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-os-Xa1b2c3d4e5-cs"
_CONCEPT_MAP = f"{_CANONICAL}/ConceptMap/d2-os-Xa1b2c3d4e5-cm"
_OPTION_SYSTEM = f"{_IDENTIFIER_BASE}/id/option"
_OPTION_CODE_SYSTEM = f"{_IDENTIFIER_BASE}/id/option-code"

#: The same three URLs for the category family, which the operation answers over the very same store.
_CATEGORY_CODE_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-cat-O5P6e8yu1T6-cs"
_CATEGORY_CONCEPT_MAP = f"{_CANONICAL}/ConceptMap/d2-cat-O5P6e8yu1T6-cm"
_CATEGORY_OPTION_SYSTEM = f"{_IDENTIFIER_BASE}/id/category-option"
_CATEGORY_OPTION_CODE_SYSTEM = f"{_IDENTIFIER_BASE}/id/category-option-code"

#: The tracked entity type family: the vocabulary the concept comes from, the map over it, and the
#: R4 code system of resource types the map answers in. The type is left unmapped by the project,
#: so what comes back is the default every person-tracking project relies on.
_TYPE_CODE_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-tet-cs"
_TYPE_CONCEPT_MAP = f"{_CANONICAL}/ConceptMap/d2-tet-cm"
_RESOURCE_TYPE_SYSTEM = "http://hl7.org/fhir/resource-types"
_TYPE_CONCEPT_CODE = "nEenWmSyUEp"

#: The person-only form of that type, which is what makes the run publish the type as a concept.
_PERSON_FORM = QuestionnaireSourceIn(
    uid=_TYPE_CONCEPT_CODE,
    name="Person",
    kind="tracked-entity",
    tracked_entity_type_uid=_TYPE_CONCEPT_CODE,
    flat_items=[QuestionnaireItemIn(uid="w75KJ2mc4zz", name="First name", value_type="TEXT")],
)

#: The concept the tests translate, and the two DHIS2 identifiers the map states for it.
_CONCEPT_CODE = "kRRUtYaGett"
_OPTION_CODE = "NB"

#: The category-option concept the tests translate, and the DHIS2 code the category map states for it.
_CATEGORY_CONCEPT_CODE = "TNYQzTHdoxL"
_CATEGORY_OPTION_CODE = "F"

_QUESTIONNAIRE = {
    "resourceType": "Questionnaire",
    "id": "d2-pr-anc-visit-q",
    "url": f"{_CANONICAL}/Questionnaire/d2-pr-anc-visit-q",
    "status": "active",
    "title": "ANC Visit",
}


@pytest.fixture
def translate_project(tmp_path: Path) -> FhirProject:
    """A project whose predefined tree holds the ConceptMaps the generator emits for one set and one category."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(_FHIR_TOML, encoding="utf-8")
    project = FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())

    compiled = project.ig_directory / "fsh-generated" / "resources"
    compiled.mkdir(parents=True)
    (compiled / "Questionnaire-d2-pr-anc-visit-q.json").write_text(json.dumps(_QUESTIONNAIRE), encoding="utf-8")
    dictionary = build_data_dictionary_documents(
        [_PERSON_FORM],
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    )
    for concept_map in dictionary.concept_maps:
        (compiled / f"ConceptMap-{concept_map.id}.json").write_text(
            concept_map.model_dump_json(exclude_none=True, by_alias=True), encoding="utf-8"
        )

    artifacts = [
        *build_option_set_concept_map_artifacts(
            [_BIRTH_TYPE],
            project.config.generate,
            project.config.ig.canonical,
            ig_status=project.config.ig.status,
        ),
        *build_category_concept_map_artifacts(
            [_SEX],
            project.config.generate,
            project.config.ig.canonical,
            ig_status=project.config.ig.status,
        ),
    ]
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


async def test_translate_answers_both_dhis2_identifiers_for_one_category_concept(
    translate_client: httpx.AsyncClient,
) -> None:
    """The store reads `input/resources` whole, so a category map is served the moment the target writes it."""
    response = await translate_client.get(
        _TRANSLATE_PATH, params={"system": _CATEGORY_CODE_SYSTEM, "code": _CATEGORY_CONCEPT_CODE}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameter"][0] == {"name": "result", "valueBoolean": True}
    codings = [_parts(match)["concept"]["valueCoding"] for match in _matches(body)]
    assert codings == [
        {"system": _CATEGORY_OPTION_SYSTEM, "code": _CATEGORY_CONCEPT_CODE, "display": "Female"},
        {"system": _CATEGORY_OPTION_CODE_SYSTEM, "code": _CATEGORY_OPTION_CODE, "display": "Female"},
    ]
    assert _parts(_matches(body)[0])["source"] == {"name": "source", "valueUri": _CATEGORY_CONCEPT_MAP}


async def test_translate_answers_the_resource_type_a_tracked_entity_type_is_published_as(
    translate_client: httpx.AsyncClient,
) -> None:
    """The map rides the same operation every other does: a type UID in, a FHIR resource type out."""
    response = await translate_client.get(
        _TRANSLATE_PATH, params={"system": _TYPE_CODE_SYSTEM, "code": _TYPE_CONCEPT_CODE}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameter"][0] == {"name": "result", "valueBoolean": True}
    parts = _parts(_matches(body)[0])
    assert parts["concept"]["valueCoding"] == {
        "system": _RESOURCE_TYPE_SYSTEM,
        "code": "Patient",
        "display": "Person",
    }
    assert parts["equivalence"] == {"name": "equivalence", "valueCode": "equal"}
    assert parts["source"] == {"name": "source", "valueUri": _TYPE_CONCEPT_MAP}


async def test_a_target_system_narrows_a_category_answer_to_one_group(translate_client: httpx.AsyncClient) -> None:
    """Narrowing works over the category namespaces the same way it does over the option ones."""
    response = await translate_client.get(
        _TRANSLATE_PATH,
        params={
            "system": _CATEGORY_CODE_SYSTEM,
            "code": _CATEGORY_CONCEPT_CODE,
            "targetsystem": _CATEGORY_OPTION_CODE_SYSTEM,
        },
    )

    assert response.status_code == 200
    codings = [_parts(match)["concept"]["valueCoding"] for match in _matches(response.json())]
    assert codings == [{"system": _CATEGORY_OPTION_CODE_SYSTEM, "code": _CATEGORY_OPTION_CODE, "display": "Female"}]


async def test_the_option_namespaces_do_not_narrow_a_category_concept(translate_client: httpx.AsyncClient) -> None:
    """The two families keep their own namespaces, so an option target system matches no category mapping."""
    response = await translate_client.get(
        _TRANSLATE_PATH,
        params={
            "system": _CATEGORY_CODE_SYSTEM,
            "code": _CATEGORY_CONCEPT_CODE,
            "targetsystem": _OPTION_CODE_SYSTEM,
        },
    )

    body = response.json()
    assert _named(body, "result") == {"name": "result", "valueBoolean": False}
    assert _matches(body) == []


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
    """`$translate` is a resource id as far as the catch-all is concerned, so mount order decides."""
    operation = await translate_client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE})
    missing = await translate_client.get("/ConceptMap/no-such-map")

    assert operation.status_code == 200
    assert operation.json()["resourceType"] == "Parameters"
    assert missing.status_code == 404
    assert missing.json()["issue"][0]["code"] == "not-found"


async def test_a_concept_map_is_read_as_the_document_the_project_published(
    translate_client: httpx.AsyncClient,
) -> None:
    response = await translate_client.get("/ConceptMap/d2-os-Xa1b2c3d4e5-cm")

    assert response.status_code == 200
    assert response.headers["content-type"] == _FHIR_JSON
    body = response.json()
    assert body["resourceType"] == "ConceptMap"
    assert body["url"] == _CONCEPT_MAP
    assert body["group"][0]["source"] == _CODE_SYSTEM
    assert _CONCEPT_CODE in [element["code"] for element in body["group"][0]["element"]]


async def test_searching_concept_maps_answers_every_family(translate_client: httpx.AsyncClient) -> None:
    """The search reads the whole store, so the compiled tree's maps sit beside the predefined tree's."""
    response = await translate_client.get("/ConceptMap")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "searchset"
    assert sorted(entry["resource"]["url"] for entry in body["entry"]) == [
        _CATEGORY_CONCEPT_MAP,
        _CONCEPT_MAP,
        _TYPE_CONCEPT_MAP,
    ]


async def test_searching_concept_maps_by_url_selects_one_map(translate_client: httpx.AsyncClient) -> None:
    response = await translate_client.get("/ConceptMap", params={"url": _CONCEPT_MAP})

    body = response.json()
    assert body["total"] == 1
    assert body["entry"][0]["resource"]["url"] == _CONCEPT_MAP
    assert body["link"][0]["url"] == f"{_BASE_URL}/ConceptMap?{urlencode({'url': _CONCEPT_MAP})}"


async def test_metadata_declares_the_operation_when_the_store_holds_concept_maps(
    translate_client: httpx.AsyncClient,
) -> None:
    body = (await translate_client.get("/metadata")).json()

    operations = body["rest"][0]["operation"]
    assert [operation["name"] for operation in operations] == ["translate"]
    assert operations[0]["definition"] == "http://hl7.org/fhir/OperationDefinition/ConceptMap-translate"
    assert operations[0]["documentation"]


async def test_metadata_declares_concept_map_as_a_read_type(translate_client: httpx.AsyncClient) -> None:
    """The maps are read as well as translated through, so the statement carries a ConceptMap entry."""
    body = (await translate_client.get("/metadata")).json()

    entry = next(resource for resource in body["rest"][0]["resource"] if resource["type"] == "ConceptMap")
    assert [interaction["code"] for interaction in entry["interaction"]] == ["read", "search-type"]
    assert [parameter["name"] for parameter in entry["searchParam"]] == ["_id", "url", "identifier"]
    assert "operation" not in entry


async def test_metadata_declares_no_operation_when_the_store_holds_no_concept_map(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get("/metadata")).json()

    assert "operation" not in body["rest"][0]


async def test_translate_over_a_store_without_concept_maps_answers_false(client: httpx.AsyncClient) -> None:
    response = await client.get(_TRANSLATE_PATH, params={"system": _CODE_SYSTEM, "code": _CONCEPT_CODE})

    assert response.status_code == 200
    assert _named(response.json(), "result") == {"name": "result", "valueBoolean": False}
