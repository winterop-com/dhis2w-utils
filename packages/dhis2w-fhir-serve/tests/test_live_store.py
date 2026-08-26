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
from dhis2w_fhir_serve.live import build_live_store, open_live_client
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

#: Every vocabulary a generated guide publishes off its own definitions rather than off the
#: instance's data - the four foundation pairs and the identifier namespaces its maps target. They
#: are the parity set: a compiled build writes all of them, so a live run serves all of them.
_DEFINITIONAL_TERMINOLOGY_IDS = frozenset(
    {
        "d2-form-type-cs",
        "d2-form-type-vs",
        "d2-period-type-cs",
        "d2-period-type-vs",
        "d2-program-rule-action-cs",
        "d2-program-rule-action-vs",
        "d2-ou-level-cs",
        "d2-ou-level-vs",
        "d2-option-id-cs",
        "d2-option-code-id-cs",
        "d2-category-option-id-cs",
        "d2-category-option-code-id-cs",
    }
)


def _mock_instance(data_sets: dict[str, Any] | None = None, option_sets: dict[str, Any] | None = None) -> respx.Route:
    """Mock every endpoint the live fetch reads (respx-active), returning the system-info route.

    The system-info route is what a test counts to see how many times a client was opened: the
    version probe runs once per connect and never again. `data_sets` and `option_sets` stand in for
    those two payloads where a test needs the instance to hold different ones.
    """
    system_info = respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD if option_sets is None else option_sets)
    )
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD if data_sets is None else data_sets)
    )
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
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
    settings = ServeSettings(project_dir=project.project_root, live=True)
    async with open_live_client(project, settings) as client:
        return await build_live_store(project, settings, client)


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
    assert sorted(questionnaires) == ["A03MvHHogjR", "BfMAe6Itzgt", "IpHINAT79UW", "VBqh0ynB2wv"]
    data_set = questionnaires["BfMAe6Itzgt"]
    assert data_set["url"] == f"{_CANONICAL}/Questionnaire/BfMAe6Itzgt"
    assert data_set["name"] == "D2DS_BfMAe6Itzgt"
    assert data_set["title"] == "Child Health"
    assert {"system": f"{_IDENTIFIER_BASE}/data-set", "value": "BfMAe6Itzgt"} in data_set["identifier"]
    assert store.by_canonical(f"{_CANONICAL}/Questionnaire/VBqh0ynB2wv") is not None
    assert questionnaires[_TRACKER_STAGE_UID]["name"] == "D2PS_A03MvHHogjR"
    assert questionnaires[_TRACKER_PROGRAM_UID]["name"] == "D2PR_IpHINAT79UW"


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
    assert locations["O6uvpzGd5pu"]["extension"][-1] == {
        "url": f"{_CANONICAL}/StructureDefinition/d2-organisation-unit-level",
        "valueCoding": {
            "system": f"{_CANONICAL}/CodeSystem/d2-ou-level-cs",
            "code": "level-2",
            "display": "Level 2",
        },
    }


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
    assert sorted(entry.resource_id for entry in grouped) == [_TRACKER_STAGE_UID, _TRACKER_PROGRAM_UID]
    registry = store.search("Organization", _identifier_query(None, "ImspTQPwCqd"))
    assert [entry.resource_id for entry in registry] == ["ImspTQPwCqd"]


@respx.mock
async def test_a_live_run_hosts_the_conformance_resources_compiled_beside_the_project(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """One guide, either mode: the definitional layer is read off disk where a build has left one.

    Nothing else is taken from the compiled tree. What the instance answers is what the builders
    build, and the profiles are the one thing no builder here can produce - they are FSH until SUSHI
    has run - so a live run over a project that has also been compiled serves them and nothing more.
    """
    _mock_instance()
    _write_compiled_profile(live_project)

    store = await _built_store(live_project)

    assert "StructureDefinition" in store.types_present()
    profile = store.by_canonical(f"{_CANONICAL}/StructureDefinition/d2-aggregate-response")
    assert profile is not None
    assert profile.resource_id == "d2-aggregate-response"
    assert profile.source == "ig/fsh-generated/resources/StructureDefinition-d2-aggregate-response.json"
    assert "Questionnaire" not in {entry.resource_type for entry in store.entries if entry.source != "live"}


@respx.mock
async def test_a_live_run_over_a_project_that_was_never_compiled_hosts_none(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """The default live posture: no build on disk, so no definitional layer, and no claim of one."""
    _mock_instance()

    store = await _built_store(live_project)

    assert "StructureDefinition" not in store.types_present()
    assert "ImplementationGuide" not in store.types_present()


def _write_compiled_profile(project: FhirProject) -> None:
    """Put one compiled profile beside a live project, as a SUSHI run over the same project would."""
    compiled = project.ig_directory / "fsh-generated" / "resources"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / "StructureDefinition-d2-aggregate-response.json").write_text(
        json.dumps(
            {
                "resourceType": "StructureDefinition",
                "id": "d2-aggregate-response",
                "url": f"{_CANONICAL}/StructureDefinition/d2-aggregate-response",
                "status": "active",
                "kind": "resource",
                "type": "QuestionnaireResponse",
            }
        ),
        encoding="utf-8",
    )


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
async def test_the_live_store_serves_the_terminology_the_foundation_fsh_declares(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """The form-type, period-type, and organisation-unit level pairs are served without an FSH compiler."""
    _mock_instance()

    store = await _built_store(live_project)

    code_systems = _bodies(store, "CodeSystem")
    value_sets = _bodies(store, "ValueSet")
    assert code_systems["d2-form-type-cs"]["url"] == f"{_CANONICAL}/CodeSystem/d2-form-type-cs"
    assert [concept["code"] for concept in code_systems["d2-form-type-cs"]["concept"]] == [
        "aggregate",
        "event",
        "tracker",
        "tracker-event",
        "tracked-entity",
    ]
    assert value_sets["d2-form-type-vs"]["compose"]["include"] == [
        {"system": f"{_CANONICAL}/CodeSystem/d2-form-type-cs"}
    ]
    assert code_systems["d2-period-type-cs"]["concept"][0] == {"code": "Daily", "display": "Daily (yyyyMMdd)"}
    assert "d2-period-type-vs" in value_sets
    # The vocabulary every published Location states its level from - two units, two levels.
    assert [concept["code"] for concept in code_systems["d2-ou-level-cs"]["concept"]] == ["level-1", "level-2"]
    assert "d2-ou-level-vs" in value_sets
    # The whole-selection pair is off until `[generate.organisation_units] terminology` turns it on.
    assert "d2-ou-cs" not in code_systems
    assert "d2-ou-vs" not in value_sets


@respx.mock
async def test_the_live_store_serves_the_program_rule_action_pair(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """A served form states what each of its program rules does as a code, so the vocabulary is served too.

    The pair is declared beside the D2ProgramRule extension in FSH and has no JSON target of its own,
    which is why a live run builds it here rather than serving a required binding onto a 404.
    """
    _mock_instance()

    store = await _built_store(live_project)

    code_system = _bodies(store, "CodeSystem")["d2-program-rule-action-cs"]
    value_set = _bodies(store, "ValueSet")["d2-program-rule-action-vs"]

    assert code_system["url"] == f"{_CANONICAL}/CodeSystem/d2-program-rule-action-cs"
    assert code_system["content"] == "complete"
    assert {"code": "HIDEFIELD", "display": "Hide a question"} in code_system["concept"]
    assert code_system["count"] == len(code_system["concept"])
    assert value_set["compose"]["include"] == [{"system": f"{_CANONICAL}/CodeSystem/d2-program-rule-action-cs"}]


@respx.mock
async def test_the_live_store_enumerates_every_identifier_namespace_its_maps_target(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """A NamingSystem answers no `$validate-code`, so the enumeration a compiled build writes is built here.

    One CodeSystem per namespace the option-set, category, and attribute-combo maps target, at the
    same URL the NamingSystem declares, enumerating exactly the identifiers this selection uses.
    """
    _mock_instance()

    store = await _built_store(live_project)

    code_systems = _bodies(store, "CodeSystem")
    options = code_systems["d2-option-id-cs"]

    assert options["url"] == f"{_IDENTIFIER_BASE}/option"
    assert options["content"] == "complete"
    assert {concept["code"] for concept in options["concept"]} == {"kRRUtYaGett", "EBE0c8sZazS"}
    assert {concept["code"] for concept in code_systems["d2-option-code-id-cs"]["concept"]} == {"NB", "CS"}
    assert {concept["code"] for concept in code_systems["d2-category-option-id-cs"]["concept"]} == {
        "TNYQzTHdoxL",
        "apsOixVZlf1",
    }
    assert {concept["code"] for concept in code_systems["d2-category-option-code-id-cs"]["concept"]} == {"F", "M"}


@respx.mock
async def test_the_live_store_publishes_the_terminology_a_compiled_build_publishes(
    live_profile: None,  # noqa: ARG001
    live_project: FhirProject,
) -> None:
    """Parity, stated as one assertion: every vocabulary the generate targets write is served live.

    The two stores are built from different inputs - a compiled one reads files SUSHI wrote, a live
    one reads an instance - so what is compared is the artifact ids, which are the guide's own and
    are the same in both. Example instances are the one thing a compiled store holds and a live one
    does not, and that is by design: an example is a teaching document, not a read a client resolves.
    """
    _mock_instance()

    store = await _built_store(live_project)

    published = set(_bodies(store, "CodeSystem")) | set(_bodies(store, "ValueSet"))

    assert published >= _DEFINITIONAL_TERMINOLOGY_IDS


@respx.mock
async def test_the_live_store_serves_the_organisation_unit_code_list_when_it_is_turned_on(
    live_profile: None,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    """`terminology = true` publishes the whole-selection pair live, levels carried as integers."""
    _mock_instance()
    config_path = tmp_path / "terminology-fhir.toml"
    config_path.write_text(f"{_LIVE_FHIR_TOML}\n[generate.organisation_units]\nterminology = true\n", encoding="utf-8")
    project = FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())

    store = await _built_store(project)

    code_system = _bodies(store, "CodeSystem")["d2-ou-cs"]
    assert code_system["url"] == f"{_CANONICAL}/CodeSystem/d2-ou-cs"
    assert code_system["count"] == 2
    assert code_system["concept"][0] == {
        "code": "ImspTQPwCqd",
        "display": "Sierra Leone",
        "property": [{"code": "level", "valueInteger": 1}, {"code": "dhis2-code", "valueString": "SL"}],
    }
    assert _bodies(store, "ValueSet")["d2-ou-vs"]["compose"]["include"] == [
        {"system": f"{_CANONICAL}/CodeSystem/d2-ou-cs"}
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
    assert generated["BfMAe6Itzgt"].json()["subject"]["reference"] in {
        "Location/ImspTQPwCqd",
        "Location/O6uvpzGd5pu",
    }


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
    assert metadata.json()["implementation"]["description"].startswith(
        "A FHIR capture facade over a live DHIS2 instance."
    )
    assert read.status_code == 200
    assert read.json()["url"] == f"{_CANONICAL}/Questionnaire/BfMAe6Itzgt"
    bundle = search.json()
    # One search over the program identifier selects the program's whole capture surface: the
    # registration form that enrols a person, and every stage form the enrollment is captured on.
    assert bundle["total"] == 2
    assert sorted(entry["resource"]["id"] for entry in bundle["entry"]) == [_TRACKER_STAGE_UID, _TRACKER_PROGRAM_UID]


# ---------------------------------------------------------------------------------------------
# `[generate] hostile_names` in the live path: one project means one set of names.
# ---------------------------------------------------------------------------------------------


#: The DHIS2 name the IG publisher's own build cannot survive, beside the wording `substitute`
#: publishes in its place - and one DHIS2 code carrying a space, which is what the code half of the
#: screening is about.
_HOSTILE_NAME = "Mortality < 5 years"
_SUBSTITUTED_NAME = "Mortality under 5 years"
_HOSTILE_CODE = "Natural Birth"

#: The aggregate payload with one hostile name on the data set.
_HOSTILE_DATA_SETS_PAYLOAD: dict[str, Any] = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": _HOSTILE_NAME,
            "code": "DS_359711",
            "organisationUnits": [{"id": "ImspTQPwCqd"}, {"id": "O6uvpzGd5pu"}],
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

#: The option-set payload with one option whose DHIS2 code carries a space.
_HOSTILE_OPTION_SETS_PAYLOAD: dict[str, Any] = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "options": [
                {"id": "kRRUtYaGett", "code": _HOSTILE_CODE, "name": "Natural Birth", "sortOrder": 1},
                {"id": "EBE0c8sZazS", "code": "CS", "name": "Scheduled Cesarean", "sortOrder": 2},
            ],
        }
    ]
}


def _project_with(tmp_path: Path, hostile_names: str | None) -> FhirProject:
    """A live project whose `[generate]` states one hostile-names posture, or none at all."""
    stated = "" if hostile_names is None else f'\n[generate]\nhostile_names = "{hostile_names}"\n'
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(f"{_LIVE_FHIR_TOML}{stated}", encoding="utf-8")
    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


def _option_concepts(store: ResourceStore) -> list[dict[str, Any]]:
    """The concepts of the served option-set CodeSystem, in the order the guide publishes them."""
    concepts: list[dict[str, Any]] = _bodies(store, "CodeSystem")["d2-os-Xa1b2c3d4e5-cs"]["concept"]
    return concepts


@respx.mock
async def test_substitute_serves_live_the_names_generate_would_publish(
    live_profile: None,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    """A project stating `substitute` serves one UID under one name, live or compiled.

    The screening runs at the same choke point a generate run screens at - the four projections, once,
    before an identity or a stem is planned off any of them - so the questionnaire title, the concept
    displays, and the codes are one set of strings for the project rather than one per posture. The
    `dhis2-code` property still states what the instance holds, which is the path a captured answer is
    lowered back onto DHIS2 through.
    """
    _mock_instance(_HOSTILE_DATA_SETS_PAYLOAD, _HOSTILE_OPTION_SETS_PAYLOAD)

    store = await _built_store(_project_with(tmp_path, "substitute"))

    assert _bodies(store, "Questionnaire")["BfMAe6Itzgt"]["title"] == _SUBSTITUTED_NAME
    assert {"code": "dhis2-code", "valueString": _HOSTILE_CODE} in _option_concepts(store)[0]["property"]


@respx.mock
@pytest.mark.parametrize("hostile_names", ["refuse", None])
async def test_every_other_posture_serves_live_what_the_instance_holds_and_refuses_nothing(
    live_profile: None,  # noqa: ARG001
    tmp_path: Path,
    hostile_names: str | None,
) -> None:
    """Serving is not generating: `refuse` and an unset posture serve byte-true and abort over no name.

    `refuse` is an answer about what a build may publish - there is no page to strict-parse here and
    no build hour to lose - and an unset posture asks nobody, because a server has no one at a
    terminal to ask.
    """
    _mock_instance(_HOSTILE_DATA_SETS_PAYLOAD, _HOSTILE_OPTION_SETS_PAYLOAD)

    store = await _built_store(_project_with(tmp_path, hostile_names))

    assert _bodies(store, "Questionnaire")["BfMAe6Itzgt"]["title"] == _HOSTILE_NAME
    assert {"code": "dhis2-code", "valueString": _HOSTILE_CODE} in _option_concepts(store)[0]["property"]
