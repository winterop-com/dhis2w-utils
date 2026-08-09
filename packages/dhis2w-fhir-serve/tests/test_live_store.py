"""The live store: what `--live` serves, built off a mocked DHIS2 instance instead of a compiled IG.

Self-contained by design - the fixtures here write their own profile and their own project tree
rather than reaching for the compiled-IG fixtures next door, because a live run shares nothing
with them: no `fsh-generated`, no predefined resources, no files at all.

Mocked (respx); no live stack. The payloads are the smallest instance that still exercises every
builder the live store runs: one option set, one category, one data set, one event program, one
tracker program with a stage, and two organisation units.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_fhir import build_option_set_artifacts
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir.service import fetch_live_ig_inputs, resolve_generation_profile
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.live import build_live_store
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, SearchQuery

_HOST = "https://dhis2.example"

_BASE_URL = "http://serve.test"

_CANONICAL = "http://example.org/fhir"

_IDENTIFIER_BASE = "http://dhis2.org/fhir/id"

_LIVE_FHIR_TOML = """
[ig]
id = "dhis2.fhir.live"
canonical = "http://example.org/fhir"
name = "Dhis2FhirLive"
title = "DHIS2 FHIR Live IG"
publisher = "Example Organisation"
"""

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""

_SYSTEM_INFO = {"version": "2.42.0"}

_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "options": [
                {"id": "kRRUtYaGett", "code": "NB", "name": "Natural Birth", "sortOrder": 1},
                {"id": "EBE0c8sZazS", "code": "CS", "name": "Scheduled Cesarean", "sortOrder": 2},
            ],
        }
    ]
}

_CATEGORIES_PAYLOAD = {
    "categories": [
        {
            "id": "O5P6e8yu1T6",
            "name": "Sex",
            "categoryOptions": [
                {"id": "TNYQzTHdoxL", "code": "F", "name": "Female"},
                {"id": "apsOixVZlf1", "code": "M", "name": "Male"},
            ],
        }
    ]
}

_ORGANISATION_UNITS_PAYLOAD = {
    "organisationUnits": [
        {"id": "ImspTQPwCqd", "name": "Sierra Leone", "level": 1, "path": "/ImspTQPwCqd", "code": "SL"},
        {
            "id": "O6uvpzGd5pu",
            "name": "Bo",
            "level": 2,
            "path": "/ImspTQPwCqd/O6uvpzGd5pu",
            "parent": {"id": "ImspTQPwCqd"},
            "geometry": {"type": "Point", "coordinates": [-11.7383, 7.9647]},
        },
    ]
}

_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "code": "DS_359711",
            # Assigned to every published unit, so the data set publishes no assignment List.
            "organisationUnits": [{"id": "ImspTQPwCqd"}, {"id": "O6uvpzGd5pu"}],
            "sections": [{"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]}],
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "valueType": "INTEGER_ZERO_OR_POSITIVE",
                        "domainType": "AGGREGATE",
                        "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                    }
                }
            ],
        }
    ]
}

_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "programType": "WITHOUT_REGISTRATION",
            # A proper subset of the registry, so this program publishes an assignment List.
            "organisationUnits": [{"id": "O6uvpzGd5pu"}],
            "programStages": [
                {
                    "id": "pTo4uMt3xur",
                    "name": "Malaria case",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {"id": "qrur9Dvnyt5", "name": "Age in years", "valueType": "INTEGER"},
                        }
                    ],
                }
            ],
        },
        {
            "id": "IpHINAT79UW",
            "name": "Child Programme",
            "programType": "WITH_REGISTRATION",
            "programStages": [
                {
                    "id": "A03MvHHogjR",
                    "name": "Birth",
                    "sortOrder": 1,
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": False,
                            "dataElement": {
                                "id": "a3kGcGDCuk6",
                                "name": "Apgar score",
                                "valueType": "TEXT",
                                "optionSet": {"id": "Xa1b2c3d4e5"},
                            },
                        }
                    ],
                }
            ],
        },
    ]
}

#: The tracker program's single stage, and the program every artifact of it is grouped under.
_TRACKER_STAGE_UID = "A03MvHHogjR"
_TRACKER_PROGRAM_UID = "IpHINAT79UW"


def _mock_instance() -> respx.Route:
    """Mock every endpoint the live fetch reads (respx-active), returning the system-info route.

    The system-info route is what a test counts to see how many times a client was opened: the
    version probe runs once per connect and never again.
    """
    system_info = respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD))
    return system_info


@pytest.fixture
def live_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a profiles.toml with a Basic `probe` profile the live store can open a client on."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def live_project(tmp_path: Path) -> FhirProject:
    """A project holding a fhir.toml and nothing else - a live run needs no compiled IG on disk."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(_LIVE_FHIR_TOML, encoding="utf-8")
    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


async def _built_store(project: FhirProject) -> ResourceStore:
    """Build the live store for a project against the mocked instance."""
    return await build_live_store(project, ServeSettings(project_dir=project.project_root, live=True))


def _bodies(store: ResourceStore, resource_type: str) -> dict[str, dict[str, Any]]:
    """The store's documents of one type, by id."""
    return {entry.resource_id: entry.body for entry in store.entries if entry.resource_type == resource_type}


def _identifier_query(system: str | None, value: str) -> SearchQuery:
    """One identifier search, as the read route hands it to the store."""
    return SearchQuery(identifiers=(IdentifierToken(system=system, value=value),))


@respx.mock
async def test_live_store_publishes_the_questionnaires_the_compiled_ig_would(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """Every selected form is served under the id, canonical, and name the generate targets give it."""
    _mock_instance()

    store = await _built_store(live_project)

    questionnaires = _bodies(store, "Questionnaire")
    assert sorted(questionnaires) == ["A03MvHHogjR", "BfMAe6Itzgt", "VBqh0ynB2wv"]
    data_set = questionnaires["BfMAe6Itzgt"]
    assert data_set["url"] == f"{_CANONICAL}/Questionnaire/BfMAe6Itzgt"
    assert data_set["name"] == "D2DS_BfMAe6Itzgt"
    assert data_set["title"] == "Child Health"
    assert {"system": f"{_IDENTIFIER_BASE}/data-set", "value": "BfMAe6Itzgt"} in data_set["identifier"]
    assert store.by_canonical(f"{_CANONICAL}/Questionnaire/VBqh0ynB2wv") is not None
    assert questionnaires[_TRACKER_STAGE_UID]["name"] == "D2PS_A03MvHHogjR"


@respx.mock
async def test_live_store_serves_the_terminology_and_the_registry(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """The option-set and category pairs, the data dictionary, and the org-unit registry are all present."""
    _mock_instance()

    store = await _built_store(live_project)

    code_systems = _bodies(store, "CodeSystem")
    value_sets = _bodies(store, "ValueSet")
    assert code_systems["d2-os-Xa1b2c3d4e5-cs"]["url"] == f"{_CANONICAL}/CodeSystem/d2-os-Xa1b2c3d4e5-cs"
    assert code_systems["d2-os-Xa1b2c3d4e5-cs"]["title"] == "Birth type"
    assert value_sets["d2-os-Xa1b2c3d4e5-vs"]["url"] == f"{_CANONICAL}/ValueSet/d2-os-Xa1b2c3d4e5-vs"
    assert code_systems["d2-cat-O5P6e8yu1T6-cs"]["title"] == "Sex"
    assert "d2-cat-O5P6e8yu1T6-vs" in value_sets
    assert {concept["code"] for concept in code_systems["d2-de-cs"]["concept"]} == {
        "De1aaaaaaaa",
        "a3kGcGDCuk6",
        "qrur9Dvnyt5",
    }
    assert "d2-de-vs" in value_sets
    assert sorted(_bodies(store, "Organization")) == ["ImspTQPwCqd", "O6uvpzGd5pu"]
    locations = _bodies(store, "Location")
    assert sorted(locations) == ["ImspTQPwCqd", "O6uvpzGd5pu"]
    assert locations["O6uvpzGd5pu"]["position"] == {"longitude": -11.7383, "latitude": 7.9647}


@respx.mock
async def test_live_entries_are_indexed_and_marked_live(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """Every entry names the live marker as its source, and the identifiers are searchable as tokens."""
    _mock_instance()

    store = await _built_store(live_project)

    assert {entry.source for entry in store.entries} == {"live"}
    assert store.types_present() == (
        "CodeSystem",
        "ConceptMap",
        "List",
        "Location",
        "Organization",
        "Questionnaire",
        "ValueSet",
    )
    grouped = store.search("Questionnaire", _identifier_query(f"{_IDENTIFIER_BASE}/program", _TRACKER_PROGRAM_UID))
    assert [entry.resource_id for entry in grouped] == [_TRACKER_STAGE_UID]
    registry = store.search("Organization", _identifier_query(None, "ImspTQPwCqd"))
    assert [entry.resource_id for entry in registry] == ["ImspTQPwCqd"]


@respx.mock
async def test_the_live_store_holds_both_concept_map_families(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """A live run serves the same ConceptMaps the generate targets write, so `$translate` answers off it."""
    _mock_instance()

    store = await _built_store(live_project)

    concept_maps = _bodies(store, "ConceptMap")
    assert sorted(concept_maps) == ["d2-cat-O5P6e8yu1T6-cm", "d2-os-Xa1b2c3d4e5-cm"]
    groups = concept_maps["d2-os-Xa1b2c3d4e5-cm"]["group"]
    assert [group["target"] for group in groups] == [
        "http://dhis2.org/fhir/id/option",
        "http://dhis2.org/fhir/id/option-code",
    ]
    assert {group["source"] for group in groups} == {f"{_CANONICAL}/CodeSystem/d2-os-Xa1b2c3d4e5-cs"}
    category_groups = concept_maps["d2-cat-O5P6e8yu1T6-cm"]["group"]
    assert [group["target"] for group in category_groups] == [
        "http://dhis2.org/fhir/id/category-option",
        "http://dhis2.org/fhir/id/category-option-code",
    ]
    assert sorted(str(concept_map.url) for concept_map in store.concept_maps()) == [
        f"{_CANONICAL}/ConceptMap/d2-cat-O5P6e8yu1T6-cm",
        f"{_CANONICAL}/ConceptMap/d2-os-Xa1b2c3d4e5-cm",
    ]


@respx.mock
async def test_the_profile_is_opened_exactly_once(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """One store build opens one client: the instance is probed for its version a single time."""
    system_info = _mock_instance()

    await _built_store(live_project)

    assert system_info.call_count == 1


@respx.mock
async def test_a_served_document_is_the_file_the_generate_target_would_have_written(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """A pre-built JSON artifact is served as the very document its file would hold, key for key."""
    _mock_instance()
    store = await _built_store(live_project)

    generation = resolve_generation_profile(live_project, None)
    async with open_client(generation.profile) as client:
        inputs = await fetch_live_ig_inputs(client, live_project.config.generate)
    build = build_option_set_artifacts(
        inputs.option_sets,
        live_project.config.generate,
        _CANONICAL,
        ig_status=live_project.config.ig.status,
        attribute_codes=inputs.attribute_codes,
    )
    written = {artifact.relative_path.rsplit("/", 1)[-1]: json.loads(artifact.content) for artifact in build.artifacts}

    assert _bodies(store, "CodeSystem")["d2-os-Xa1b2c3d4e5-cs"] == written["CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]


@respx.mock
async def test_live_generate_output_posts_back_at_the_live_server(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """The `$generate` round trip holds against a live store too: same route, same synthesizer, same 201.

    A live store carries no example instances, so the aggregate form's reporting period falls back to
    the documented `Monthly` default - which is still a period this server's own capture path accepts.
    """
    _mock_instance()
    app = create_app(ServeSettings(project_dir=live_project.project_root, live=True))
    generated: dict[str, httpx.Response] = {}
    posted: dict[str, httpx.Response] = {}

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as client:
            for resource_id in ("BfMAe6Itzgt", "VBqh0ynB2wv", _TRACKER_STAGE_UID):
                generated[resource_id] = await client.get(f"/Questionnaire/{resource_id}/$generate?seed=13")
                posted[resource_id] = await client.post(
                    "/QuestionnaireResponse",
                    content=generated[resource_id].content,
                    headers={"Content-Type": "application/fhir+json"},
                )

    assert [response.status_code for response in generated.values()] == [200, 200, 200]
    assert [response.status_code for response in posted.values()] == [201, 201, 201]
    assert generated["BfMAe6Itzgt"].json()["subject"]["reference"] == "Location/ImspTQPwCqd"


@respx.mock
async def test_live_facade_answers_reads_and_searches_over_the_built_store(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """The app started in live mode serves `/metadata`, a read, and an identifier search off the instance.

    The lifespan runs inside the test rather than in a fixture: the store is built during startup,
    so the mocked instance has to be in place before the app is entered.
    """
    _mock_instance()
    app = create_app(ServeSettings(project_dir=live_project.project_root, live=True))

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as client:
            metadata = await client.get("/metadata")
            read = await client.get("/Questionnaire/BfMAe6Itzgt")
            search = await client.get(
                "/Questionnaire", params={"identifier": f"{_IDENTIFIER_BASE}/program|{_TRACKER_PROGRAM_UID}"}
            )

    assert metadata.status_code == 200
    assert "(live store)" in metadata.json()["implementation"]["description"]
    assert read.status_code == 200
    assert read.json()["url"] == f"{_CANONICAL}/Questionnaire/BfMAe6Itzgt"
    bundle = search.json()
    assert bundle["total"] == 1
    assert bundle["entry"][0]["resource"]["id"] == _TRACKER_STAGE_UID
