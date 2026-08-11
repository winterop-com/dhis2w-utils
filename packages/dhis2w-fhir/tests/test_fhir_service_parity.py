"""Service tests against every DHIS2 major - the client auto-detects and the service stays version-neutral.

Mocked (respx); no live stack. Endpoints derive from the generated resource
accessors: `/api/optionSets` and `/api/organisationUnits`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import (
    GENERATED_HEADER,
    GENERATED_MARKDOWN_HEADER,
    InitOptions,
    clean_generated_files,
    load_project,
    service,
)

_HOST = "https://dhis2.example"

#: One annotating attribute value and one unique one - the two halves of the attribute surface.
_ATTRIBUTE_VALUES_PAYLOAD = [
    {"attribute": {"id": "ihn1wb9eho8"}, "value": "KE03"},
    {"attribute": {"id": "AtrFhirOrU1"}, "value": "LA-17-042"},
]

#: The instance's attribute declarations: one coded and annotating, one coded and unique.
_ATTRIBUTES_PAYLOAD = {
    "attributes": [
        {"id": "ihn1wb9eho8", "code": "hfid"},
        {"id": "AtrFhirOrU1", "code": "registry number", "unique": True},
    ]
}

_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "attributeValues": _ATTRIBUTE_VALUES_PAYLOAD,
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


_TRANSLATED_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "translations": [
                {"locale": "lo", "property": "NAME", "value": "ປະເພດການເກີດ"},
                {"locale": "lo", "property": "SHORT_NAME", "value": "ປະເພດ"},
                {"property": "NAME", "value": "no locale"},
            ],
            "options": [
                {
                    "id": "kRRUtYaGett",
                    "code": "NB",
                    "name": "Natural Birth",
                    "sortOrder": 1,
                    "translations": [{"locale": "lo", "property": "NAME", "value": "ການເກີດແບບທຳມະຊາດ"}],
                }
            ],
        }
    ]
}

_TRANSLATED_ORGANISATION_UNITS_PAYLOAD = {
    "organisationUnits": [
        {
            "id": "ImspTQPwCqd",
            "name": "Sierra Leone",
            "level": 1,
            "path": "/ImspTQPwCqd",
            "code": "SL",
            "translations": [{"locale": "lo", "property": "NAME", "value": "ຊຽຣາລີໂອນ"}],
        }
    ]
}


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so generate targets have a fhir.toml + ig tree."""
    options = InitOptions(
        ig_id="dhis2.fhir.parity",
        canonical="http://example.org/fhir",
        name="Dhis2FhirParity",
        title="Parity IG",
        publisher="Parity Org",
    )
    report = await service.init_project(directory, options)
    assert "fhir.toml" in report.created_files


@respx.mock
async def test_generate_option_sets_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_option_sets` writes a CodeSystem/ValueSet pair per set against every DHIS2 major.

    The set carries attribute values, whose wire shape reaches the mapper as typed models on v41 and
    as plain dicts on v42 and v43, so the emitted extension and identifier are asserted on all three.
    """
    mock_system_info(wire_version)
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json=_ATTRIBUTES_PAYLOAD))
    await _scaffold_project(tmp_path)
    route = respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.option_set_count == 1
    assert report.target_base == "ig/input"
    assert report.target_directory == "resources/terminology, resources/concept-maps"
    assert report.written_files == [
        "terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json",
        "terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json",
        "concept-maps/ConceptMap-d2-os-Xa1b2c3d4e5-cm.json",
    ]
    resources = tmp_path / "ig" / "input" / "resources"
    code_system = json.loads(
        (resources / "terminology" / "CodeSystem-d2-os-Xa1b2c3d4e5-cs.json").read_text(encoding="utf-8")
    )
    assert code_system["name"] == "D2OS_Xa1b2c3d4e5_CS"
    assert code_system["title"] == "Birth type"
    assert code_system["extension"] == [
        {
            "url": "http://example.org/fhir/StructureDefinition/d2-attribute-value",
            "extension": [
                {"url": "attributeId", "valueString": "ihn1wb9eho8"},
                {"url": "attributeCode", "valueString": "hfid"},
                {"url": "value", "valueString": "KE03"},
            ],
        }
    ]
    assert code_system["identifier"][-1] == {
        "system": "http://dhis2.org/fhir/attribute/AtrFhirOrU1",
        "value": "LA-17-042",
    }
    concept_map = json.loads(
        (resources / "concept-maps" / "ConceptMap-d2-os-Xa1b2c3d4e5-cm.json").read_text(encoding="utf-8")
    )
    assert concept_map["name"] == "D2OS_Xa1b2c3d4e5_CM"
    assert concept_map["sourceCanonical"].endswith("/ValueSet/d2-os-Xa1b2c3d4e5-vs")


@respx.mock
async def test_generate_option_sets_sweeps_terminology_fsh_it_no_longer_writes(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Generated terminology FSH is removed: SUSHI refuses a definition duplicating a pre-defined resource."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    fsh_terminology = tmp_path / "ig" / "input" / "fsh" / "terminology"
    fsh_terminology.mkdir(parents=True, exist_ok=True)
    superseded = fsh_terminology / "Xa1b2c3d4e5.fsh"
    superseded.write_text(f"{GENERATED_HEADER}\n\nCodeSystem: D2OS_Xa1b2c3d4e5_CS\n", encoding="utf-8")
    hand_authored = fsh_terminology / "notes.fsh"
    hand_authored.write_text("// mine\n", encoding="utf-8")
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert not superseded.exists()
    assert hand_authored.read_text(encoding="utf-8") == "// mine\n"
    assert "Xa1b2c3d4e5.fsh" in report.deleted_files


@respx.mock
async def test_generate_categories_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_categories` writes the CodeSystem/ValueSet/ConceptMap triple against every DHIS2 major."""
    mock_system_info(wire_version)
    mock_attributes()
    await _scaffold_project(tmp_path)
    route = respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))

    report = await service.generate_categories(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.category_count == 1
    assert report.target_base == "ig/input"
    assert report.target_directory == "resources/categories, resources/concept-maps"
    assert report.written_files == [
        "categories/CodeSystem-d2-cat-O5P6e8yu1T6-cs.json",
        "categories/ValueSet-d2-cat-O5P6e8yu1T6-vs.json",
        "concept-maps/ConceptMap-d2-cat-O5P6e8yu1T6-cm.json",
    ]
    resources = tmp_path / "ig" / "input" / "resources"
    code_system = json.loads(
        (resources / "categories" / "CodeSystem-d2-cat-O5P6e8yu1T6-cs.json").read_text(encoding="utf-8")
    )
    assert code_system["name"] == "D2CAT_O5P6e8yu1T6_CS"
    assert code_system["title"] == "Sex"
    assert [concept["code"] for concept in code_system["concept"]] == ["TNYQzTHdoxL", "apsOixVZlf1"]
    concept_map = json.loads(
        (resources / "concept-maps" / "ConceptMap-d2-cat-O5P6e8yu1T6-cm.json").read_text(encoding="utf-8")
    )
    assert concept_map["name"] == "D2CAT_O5P6e8yu1T6_CM"
    assert [group["target"] for group in concept_map["group"]] == [
        "http://dhis2.org/fhir/id/category-option",
        "http://dhis2.org/fhir/id/category-option-code",
    ]


@respx.mock
async def test_the_two_concept_map_families_share_a_directory_without_sweeping_each_other(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`concept-maps/` holds both families behind one publisher glob, so neither target owns it outright."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    concept_maps = tmp_path / "ig" / "input" / "resources" / "concept-maps"

    await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))
    await service.generate_categories(resolve_profile("probe"), load_project(tmp_path))
    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.deleted_files == []
    assert sorted(path.name for path in concept_maps.glob("*.json")) == [
        "ConceptMap-d2-cat-O5P6e8yu1T6-cm.json",
        "ConceptMap-d2-os-Xa1b2c3d4e5-cm.json",
    ]


@respx.mock
async def test_a_category_map_a_rerun_no_longer_produces_is_swept(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Owning a prefix rather than the directory still converges: a dropped category takes its map with it."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    await service.generate_categories(resolve_profile("probe"), load_project(tmp_path))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))

    report = await service.generate_categories(resolve_profile("probe"), load_project(tmp_path))

    assert report.deleted_files == [
        "CodeSystem-d2-cat-O5P6e8yu1T6-cs.json",
        "ValueSet-d2-cat-O5P6e8yu1T6-vs.json",
        "ConceptMap-d2-cat-O5P6e8yu1T6-cm.json",
    ]


@respx.mock
async def test_generate_organisation_units_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_organisation_units` writes profiles, level terminology, and per-level instances on every major."""
    mock_system_info(wire_version)
    mock_attributes()
    await _scaffold_project(tmp_path)
    route = respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD)
    )

    report = await service.generate_organisation_units(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.organisation_unit_count == 2
    assert report.position_count == 1
    assert report.boundary_count == 1
    assert report.written_files == [
        "organization/org-unit-levels.fsh",
        "organization/profiles.fsh",
        "organization/registry-examples.fsh",
        "registry/Location-ImspTQPwCqd.json",
        "registry/Location-O6uvpzGd5pu.json",
        "registry/Organization-ImspTQPwCqd.json",
        "registry/Organization-O6uvpzGd5pu.json",
    ]
    registry = tmp_path / "ig" / "input" / "resources" / "registry"
    district_organization = json.loads((registry / "Organization-O6uvpzGd5pu.json").read_text(encoding="utf-8"))
    district_location = json.loads((registry / "Location-O6uvpzGd5pu.json").read_text(encoding="utf-8"))
    assert district_organization["meta"]["profile"] == ["http://example.org/fhir/StructureDefinition/d2-organization"]
    assert district_organization["partOf"] == {"reference": "Organization/ImspTQPwCqd"}
    assert district_location["position"] == {"longitude": -11.7383, "latitude": 7.9647}
    assert district_location["extension"][0]["url"] == (
        "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"
    )
    assert district_location["partOf"] == {"reference": "Location/ImspTQPwCqd"}
    assert (registry / "Location-ImspTQPwCqd.json").is_file()


_QUESTIONNAIRE_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "code": "DS_359711",
            "sections": [{"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]}],
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "valueType": "INTEGER_ZERO_OR_POSITIVE",
                        "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                    }
                }
            ],
        }
    ]
}

_QUESTIONNAIRE_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "programType": "WITHOUT_REGISTRATION",
            "programStages": [
                {
                    "id": "pTo4uMt3xur",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {"id": "qrur9Dvnyt5", "name": "Age in years", "valueType": "INTEGER"},
                        }
                    ],
                }
            ],
        }
    ]
}


@respx.mock
async def test_generate_questionnaires_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_questionnaires` maps data sets and event programs on every DHIS2 major."""
    mock_system_info(wire_version)
    mock_attributes()
    await _scaffold_project(tmp_path)
    (tmp_path / "fhir.toml").write_text(
        (tmp_path / "fhir.toml").read_text(encoding="utf-8")
        + '\n[generate.data_sets]\ninclude_ids = ["BfMAe6Itzgt"]\n'
        + '\n[generate.event_programs]\ninclude_ids = ["VBqh0ynB2wv"]\n',
        encoding="utf-8",
    )
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_QUESTIONNAIRE_DATA_SETS_PAYLOAD)
    )
    programs = respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(200, json=_QUESTIONNAIRE_PROGRAMS_PAYLOAD)
    )
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json={"organisationUnits": []}))

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert data_sets.called
    assert programs.called
    assert report.questionnaire_count == 2
    assert "data-sets/BfMAe6Itzgt.fsh" in report.written_files
    assert "event-programs/VBqh0ynB2wv.fsh" in report.written_files
    content = (tmp_path / "ig" / "input" / "fsh" / "event-programs" / "VBqh0ynB2wv.fsh").read_text(encoding="utf-8")
    assert content.startswith(GENERATED_HEADER)
    assert "* code = D2FormType_CS#event" in content


@respx.mock
async def test_validate_codes_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """`validate_codes` reads option sets and reports FHIR-safety findings on every major."""
    mock_system_info(wire_version)
    payload = {
        "optionSets": [
            {
                "id": "Xa1b2c3d4e5",
                "name": "Sample",
                "options": [{"id": "AcdAzPoqdtd", "code": " bad ", "name": "Bad", "sortOrder": 1}],
            }
        ]
    }
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=payload))
    for resource in ("dataSets", "programs", "categories", "organisationUnits"):
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: []}))
    sweep = {"dataElements": [{"id": "De1aaaaaaaa", "name": "Bad DE", "code": "DE 1  x"}]}
    respx.get(f"{_HOST}/api/metadata").mock(return_value=httpx.Response(200, json=sweep))

    context = service.resolve_validation_context()
    report = await service.validate_codes(resolve_profile("probe"), context.config)

    # Default id mode: the empty selection puts the option set in scope but no container binds the
    # data element, so its sweep defect is instance hygiene and the option code finding stays
    # informational for the id-source reason.
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.info_count == 2
    assert {finding.resource_type for finding in report.findings} == {"options", "dataElements"}
    assert {finding.scope for finding in report.findings} == {"selection", "instance"}
    assert report.resource_type_count == 1
    assert report.object_count == 1
    assert report.code_coverage is not None

    in_code_mode = await service.validate_codes(resolve_profile("probe"), context.config, "code")
    # Code mode makes the in-scope option defect bite as a warning; the out-of-scope sweep defect stays info.
    assert in_code_mode.error_count == 0
    assert in_code_mode.warning_count == 1
    assert in_code_mode.info_count == 1


@respx.mock
async def test_translations_are_requested_and_mapped(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Both fetches ask for translations, and the wire entries reach the emitted FSH as designations."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    option_sets = respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(200, json=_TRANSLATED_OPTION_SETS_PAYLOAD)
    )
    organisation_units = respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(200, json=_TRANSLATED_ORGANISATION_UNITS_PAYLOAD)
    )

    await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))
    await service.generate_organisation_units(resolve_profile("probe"), load_project(tmp_path))

    option_set_fields = option_sets.calls.last.request.url.params["fields"]
    assert "translations[locale,property,value]" in option_set_fields
    assert "options[id,code,name,sortOrder,translations[locale,property,value]]" in option_set_fields
    assert "translations[locale,property,value]" in organisation_units.calls.last.request.url.params["fields"]

    terminology = tmp_path / "ig" / "input" / "resources" / "terminology"
    code_system = json.loads((terminology / "CodeSystem-d2-os-Xa1b2c3d4e5-cs.json").read_text(encoding="utf-8"))
    assert code_system["_title"]["extension"][0]["extension"][1]["valueString"] == "ປະເພດການເກີດ"
    assert code_system["concept"][0]["designation"] == [{"language": "lo", "value": "ການເກີດແບບທຳມະຊາດ"}]
    registry = tmp_path / "ig" / "input" / "resources" / "registry"
    for stem in ("Organization-ImspTQPwCqd", "Location-ImspTQPwCqd"):
        document = json.loads((registry / f"{stem}.json").read_text(encoding="utf-8"))
        assert document["_name"]["extension"][0]["extension"][1]["valueString"] == "ຊຽຣາລີໂອນ"


@respx.mock
async def test_generate_is_idempotent(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A second generate run replaces the previously generated files instead of stacking new ones."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    first = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))
    second = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert first.deleted_files == []
    assert first.written_files == [
        "terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json",
        "terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json",
        "concept-maps/ConceptMap-d2-os-Xa1b2c3d4e5-cm.json",
    ]
    assert second.written_files == []
    assert second.deleted_files == []
    assert second.unchanged_count == 3
    resources = tmp_path / "ig" / "input" / "resources"
    assert sorted(path.name for path in (resources / "terminology").glob("*.json")) == [
        "CodeSystem-d2-os-Xa1b2c3d4e5-cs.json",
        "ValueSet-d2-os-Xa1b2c3d4e5-vs.json",
    ]
    assert [path.name for path in (resources / "concept-maps").glob("*.json")] == [
        "ConceptMap-d2-os-Xa1b2c3d4e5-cm.json"
    ]


@respx.mock
async def test_generate_full_is_byte_stable_across_two_runs(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Every target - the capture contract included - writes nothing on a second run of unchanged metadata."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    _mock_page_endpoints()

    first = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))
    second = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    assert "foundation/d2-responses.fsh" in first.foundation.written_files
    assert "foundation/d2-capture-server.fsh" in first.foundation.written_files
    assert "pagecontent/capture.md" in first.pages.written_files
    for report in (
        second.foundation,
        second.option_sets,
        second.categories,
        second.questionnaires,
        second.examples,
        second.organisation_units,
        second.pages,
    ):
        assert report.written_files == []
        assert report.deleted_files == []


def _mock_page_endpoints() -> None:
    """Mock every endpoint the pages target reads: option sets, data sets, programs, and org units."""
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_QUESTIONNAIRE_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_QUESTIONNAIRE_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD))


@respx.mock
async def test_generate_pages_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_pages` writes the site pages and the Questionnaire intros into pagecontent on every major."""
    mock_system_info(wire_version)
    await _scaffold_project(tmp_path)
    _mock_page_endpoints()

    report = await service.generate_pages(resolve_profile("probe"), load_project(tmp_path))

    assert report.target_base == "ig/input"
    assert report.target_directory == "pagecontent"
    assert report.page_count == 6
    assert report.intro_count == 2
    assert "pagecontent/forms.md" in report.written_files
    assert "pagecontent/Questionnaire-BfMAe6Itzgt-intro.md" in report.written_files
    forms = (tmp_path / "ig" / "input" / "pagecontent" / "forms.md").read_text(encoding="utf-8")
    assert forms.startswith(GENERATED_MARKDOWN_HEADER)
    assert "[Child Health](Questionnaire-BfMAe6Itzgt.html)" in forms


@respx.mock
async def test_generate_pages_spares_the_hand_authored_index(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The scaffolded index.md survives a clean-and-regenerate cycle, and a second run writes nothing."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_page_endpoints()
    index = tmp_path / "ig" / "input" / "pagecontent" / "index.md"
    scaffolded = index.read_text(encoding="utf-8")

    first = await service.generate_pages(resolve_profile("probe"), load_project(tmp_path))
    clean_generated_files(index.parent)
    second = await service.generate_pages(resolve_profile("probe"), load_project(tmp_path))
    third = await service.generate_pages(resolve_profile("probe"), load_project(tmp_path))

    assert first.written_files == second.written_files
    assert third.written_files == []
    assert third.deleted_files == []
    assert third.unchanged_count == len(first.written_files)
    assert index.read_text(encoding="utf-8") == scaffolded


def test_polygon_centroid_of_a_square() -> None:
    """A square ring's area-weighted centroid is its middle."""
    ring = [[0, 0], [4, 0], [4, 2], [0, 2], [0, 0]]
    centroid = service._polygon_centroid("Polygon", [ring], [])
    assert centroid.longitude == 2.0
    assert centroid.latitude == 1.0


def test_polygon_centroid_of_an_l_shape_is_not_the_bounding_box_midpoint() -> None:
    """An L-shaped ring (area 6) pulls the shoelace centroid off the bounding-box midpoint (2.0, 1.5)."""
    ring = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3], [0, 0]]
    centroid = service._polygon_centroid("Polygon", [ring], [])
    assert centroid.longitude == 1.5
    assert centroid.latitude == 1.0


def test_polygon_centroid_uses_the_largest_outer_ring() -> None:
    """A MultiPolygon takes the centroid of the outer ring with the largest absolute area."""
    small = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    large = [[10, 10], [14, 10], [14, 12], [10, 12], [10, 10]]
    centroid = service._polygon_centroid("MultiPolygon", [[small], [large]], [])
    assert centroid.longitude == 12.0
    assert centroid.latitude == 11.0


def test_degenerate_ring_falls_back_to_the_vertex_mean() -> None:
    """A zero-area ring has no shoelace centroid, so its vertices are averaged."""
    ring = [[0, 0], [2, 2], [4, 4], [0, 0]]
    centroid = service._polygon_centroid("Polygon", [ring], [])
    assert centroid.longitude == 1.5
    assert centroid.latitude == 1.5


def test_entry_point_plugin_is_discovered() -> None:
    """The `dhis2.plugins` entry point exposes the fhir plugin to core discovery on every tree."""
    from dhis2w_core.plugin import discover_plugins

    for version_key in ("v41", "v42", "v43"):
        names = {plugin.name for plugin in discover_plugins(version_key)}
        assert "fhir" in names
