"""Tests for the D2AttributeValue extension: its definition, and the five resource types that emit it.

The live instance only proves two of the five paths - 244 of 300 organisation units carry
attribute values and 9 event programs do, while its option sets and data sets carry none - so
the CodeSystem, ValueSet, and data-set Questionnaire paths rest entirely on these unit tests.
Exactly one attribute on that instance carries a code (`ZvJJRvwt2Un` -> `hfid`) and eleven do
not, so both branches are asserted on every resource type, structure by structure rather than
by presence alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service
from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.organisation_units import build_organisation_unit_instances
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireItemIn, QuestionnaireSourceIn
from dhis2w_fhir.status import IgStatus
from dhis2w_fhir.writer import JsonBuild

_HOST = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"
_EXTENSION_URL = f"{_CANONICAL}/StructureDefinition/d2-attribute-value"

#: The one coded attribute of the Lao instance, and one of the eleven it left uncoded.
_CODED_ATTRIBUTE = "ZvJJRvwt2Un"
_UNCODED_ATTRIBUTE = "n2xYlNbsfko"

_CODES = AttributeCodeIndex(codes={_CODED_ATTRIBUTE: "hfid"})

#: One coded value then one uncoded one, in the order DHIS2 returned them.
_ATTRIBUTE_VALUES = [
    AttributeValueIn(attribute_uid=_CODED_ATTRIBUTE, value="KE03"),
    AttributeValueIn(attribute_uid=_UNCODED_ATTRIBUTE, value="Facility register"),
]

#: What those two values emit as, in full: the coded one carries `attributeCode`, the other omits it.
_EXPECTED_EXTENSIONS = [
    {
        "url": _EXTENSION_URL,
        "extension": [
            {"url": "attributeId", "valueString": _CODED_ATTRIBUTE},
            {"url": "attributeCode", "valueString": "hfid"},
            {"url": "value", "valueString": "KE03"},
        ],
    },
    {
        "url": _EXTENSION_URL,
        "extension": [
            {"url": "attributeId", "valueString": _UNCODED_ATTRIBUTE},
            {"url": "value", "valueString": "Facility register"},
        ],
    },
]

_BOUNDARY_GEOJSON = '{"coordinates":[[[0,0],[1,0],[1,1],[0,0]]],"type":"Polygon"}'

_UNIT = OrganisationUnitIn(
    uid="mOsABqg3Cqw",
    name="HC Photang",
    level=2,
    path="/ImspTQPwCqd/mOsABqg3Cqw",
    attribute_values=_ATTRIBUTE_VALUES,
)

_OPTION_SET = OptionSetIn(uid="Xa1b2c3d4e5", name="Birth type", attribute_values=_ATTRIBUTE_VALUES)

_ITEM = QuestionnaireItemIn(uid="De1aaaaaaaa", name="Doses given", value_type="INTEGER")

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    kind="aggregate",
    flat_items=[_ITEM],
    attribute_values=_ATTRIBUTE_VALUES,
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv",
    name="Malaria case registration",
    kind="event",
    flat_items=[_ITEM],
    attribute_values=_ATTRIBUTE_VALUES,
)

#: The three FSH lines a coded attribute value emits on a Questionnaire, then the two an uncoded one does.
_EXPECTED_FSH = (
    '* extension[D2AttributeValue][+].extension[attributeId].valueString = "ZvJJRvwt2Un"\n'
    '* extension[D2AttributeValue][=].extension[attributeCode].valueString = "hfid"\n'
    '* extension[D2AttributeValue][=].extension[value].valueString = "KE03"\n'
    '* extension[D2AttributeValue][+].extension[attributeId].valueString = "n2xYlNbsfko"\n'
    '* extension[D2AttributeValue][=].extension[value].valueString = "Facility register"\n'
)


def _foundation(config: GenerateConfig, *, ig_status: IgStatus = "draft") -> str:
    """The emitted `foundation/d2-attribute-value.fsh` for one config."""
    artifacts = build_foundation_artifacts(config, ig_status=ig_status)
    return next(
        artifact.content for artifact in artifacts if artifact.relative_path == "foundation/d2-attribute-value.fsh"
    )


def _documents(build: JsonBuild) -> dict[str, dict[str, Any]]:
    """Every emitted JSON artifact, keyed by its relative path, parsed back into a plain document."""
    return {artifact.relative_path: json.loads(artifact.content) for artifact in build.artifacts}


def _registry(
    organisation_units: list[OrganisationUnitIn],
    attribute_codes: AttributeCodeIndex = _CODES,
    config: GenerateConfig | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the org-unit registry for one selection against the test canonical."""
    return _documents(
        build_organisation_unit_instances(
            organisation_units, config or GenerateConfig(), _CANONICAL, attribute_codes=attribute_codes
        )
    )


def _terminology(
    option_sets: list[OptionSetIn], attribute_codes: AttributeCodeIndex = _CODES
) -> dict[str, dict[str, Any]]:
    """Build the option-set terminology for one selection against the test canonical."""
    return _documents(
        build_option_set_artifacts(
            option_sets, GenerateConfig(), _CANONICAL, ig_status="draft", attribute_codes=attribute_codes
        )
    )


def _questionnaire(source: QuestionnaireSourceIn, attribute_codes: AttributeCodeIndex = _CODES) -> str:
    """Build one form's Questionnaire FSH against the test canonical."""
    build = build_questionnaire_artifacts(
        [source],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=attribute_codes,
    )
    return next(
        artifact.content for artifact in build.artifacts if artifact.relative_path.endswith(f"{source.uid}.fsh")
    )


def test_the_extension_declares_its_three_sub_extensions() -> None:
    """attributeId and value are mandatory strings; attributeCode is optional because DHIS2 codes few attributes."""
    content = _foundation(GenerateConfig())
    assert "Extension: D2AttributeValue" in content
    assert "Id: d2-attribute-value" in content
    assert 'Title: "DHIS2 attribute value"' in content
    assert "    attributeId 1..1 and" in content
    assert "    attributeCode 0..1 and" in content
    assert "    value 1..1" in content
    assert "* extension[attributeId].value[x] only string" in content
    assert "* extension[attributeId].valueString 1..1" in content
    assert "* extension[attributeCode].value[x] only string" in content
    assert "* extension[attributeCode].valueString 1..1" not in content
    assert "* extension[value].value[x] only string" in content
    assert "* extension[value].valueString 1..1" in content


def test_the_extension_is_contexted_on_every_resource_that_carries_it() -> None:
    """The five emitting resource types are listed, and nothing else is."""
    content = _foundation(GenerateConfig())
    assert content.count("* ^context[+].type = #element") == 5
    for resource_type in ("Organization", "Location", "CodeSystem", "ValueSet", "Questionnaire"):
        assert f'* ^context[=].expression = "{resource_type}"' in content
    assert '* ^context[=].expression = "QuestionnaireResponse"' not in content


def test_the_extension_derives_its_publication_state_from_the_ig_status() -> None:
    """The extension follows the same `[ig] status` dial every definitional artifact does."""
    draft = _foundation(GenerateConfig())
    assert "* ^status = #draft" in draft
    assert "* ^experimental = true" in draft
    active = _foundation(GenerateConfig(), ig_status="active")
    assert "* ^status = #active" in active
    assert "* ^experimental = false" in active


def test_the_prefix_token_flows_into_the_extension_name_and_id() -> None:
    """The name and id derive from `[generate.naming] prefix`, falling back to D2 when it is empty."""
    custom = _foundation(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))
    assert "Extension: Dhis2AttributeValue" in custom
    assert "Id: dhis2-attribute-value" in custom
    bare = _foundation(GenerateConfig(naming=NamingConfig(prefix="")))
    assert "Extension: D2AttributeValue" in bare
    assert "Id: d2-attribute-value" in bare


def test_the_organization_carries_its_units_attribute_values() -> None:
    """One extension per value on the Organization, coded first, then the uncoded one."""
    organization = _registry([_UNIT])["registry/Organization-mOsABqg3Cqw.json"]
    assert organization["extension"] == _EXPECTED_EXTENSIONS


def test_the_location_carries_the_same_attribute_values_as_its_organization() -> None:
    """Both halves of the org-unit pair carry the unit's attribute values identically."""
    documents = _registry([_UNIT])
    assert documents["registry/Location-mOsABqg3Cqw.json"]["extension"] == _EXPECTED_EXTENSIONS
    assert documents["registry/Organization-mOsABqg3Cqw.json"]["extension"] == _EXPECTED_EXTENSIONS


def test_the_location_emits_the_boundary_first_and_the_attribute_values_after_it() -> None:
    """The extension order is a contract: the GeoJSON boundary leads, then one per value in wire order."""
    unit = _UNIT.model_copy(update={"boundary_geojson": _BOUNDARY_GEOJSON})
    extensions = _registry([unit])["registry/Location-mOsABqg3Cqw.json"]["extension"]
    assert [entry["url"] for entry in extensions] == [
        "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson",
        _EXTENSION_URL,
        _EXTENSION_URL,
    ]
    assert extensions[0]["valueAttachment"]["contentType"] == "application/geo+json"
    assert extensions[1:] == _EXPECTED_EXTENSIONS


def test_the_location_extension_order_is_byte_stable_across_runs() -> None:
    """`sync_artifacts` only reports an unchanged run quiet when the emitted bytes repeat exactly."""
    unit = _UNIT.model_copy(update={"boundary_geojson": _BOUNDARY_GEOJSON})
    first = build_organisation_unit_instances([unit], GenerateConfig(), _CANONICAL, attribute_codes=_CODES)
    second = build_organisation_unit_instances([unit], GenerateConfig(), _CANONICAL, attribute_codes=_CODES)
    assert [artifact.content for artifact in first.artifacts] == [artifact.content for artifact in second.artifacts]


def test_both_halves_of_the_option_set_pair_carry_the_attribute_values() -> None:
    """The CodeSystem and the ValueSet share the set's identity, so they share its attribute values."""
    documents = _terminology([_OPTION_SET])
    code_system = documents["terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]
    value_set = documents["terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json"]
    assert code_system["extension"] == _EXPECTED_EXTENSIONS
    assert value_set["extension"] == _EXPECTED_EXTENSIONS


def test_the_data_set_questionnaire_carries_its_attribute_values_in_fsh() -> None:
    """A data set's Questionnaire writes the three assignments per coded value, two per uncoded one."""
    assert _EXPECTED_FSH in _questionnaire(_DATA_SET)


def test_the_event_program_questionnaire_carries_its_attribute_values_in_fsh() -> None:
    """The event-program Questionnaire emits the identical FSH - the form kind changes nothing here."""
    assert _EXPECTED_FSH in _questionnaire(_EVENT_PROGRAM)


def test_the_questionnaire_emits_the_attribute_values_after_the_form_type_extension() -> None:
    """The root extensions are ordered: the form type first, then the attribute values, then the url."""
    content = _questionnaire(_DATA_SET)
    form_type = content.index("* extension[D2FormType].valueCode = #aggregate")
    attribute_value = content.index("* extension[D2AttributeValue][+]")
    url = content.index('* url = "')
    assert form_type < attribute_value < url


def test_an_uncoded_attribute_omits_the_code_sub_extension_entirely() -> None:
    """An instance that codes none of its attributes emits no `attributeCode` anywhere."""
    empty = AttributeCodeIndex()
    organization = _registry([_UNIT], empty)["registry/Organization-mOsABqg3Cqw.json"]
    assert organization["extension"] == [
        {
            "url": _EXTENSION_URL,
            "extension": [
                {"url": "attributeId", "valueString": _CODED_ATTRIBUTE},
                {"url": "value", "valueString": "KE03"},
            ],
        },
        _EXPECTED_EXTENSIONS[1],
    ]
    code_system = _terminology([_OPTION_SET], empty)["terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]
    assert all("attributeCode" not in json.dumps(entry) for entry in code_system["extension"])
    assert "attributeCode" not in _questionnaire(_DATA_SET, empty)


def test_an_object_without_attribute_values_emits_no_extension_at_all() -> None:
    """Most DHIS2 objects carry none, so the key is left off rather than emitted as an empty array."""
    unit = OrganisationUnitIn(uid="Ncd1aaaaaaa", name="Uncoded", level=1, path="/Ncd1aaaaaaa")
    documents = _registry([unit])
    assert "extension" not in documents["registry/Organization-Ncd1aaaaaaa.json"]
    assert "extension" not in documents["registry/Location-Ncd1aaaaaaa.json"]
    terminology = _terminology([OptionSetIn(uid="Xa1b2c3d4e5", name="Birth type")])
    assert "extension" not in terminology["terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]
    assert "extension" not in terminology["terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json"]
    assert "D2AttributeValue" not in _questionnaire(_DATA_SET.model_copy(update={"attribute_values": []}))


def test_a_geojson_valued_attribute_travels_as_the_string_dhis2_sent() -> None:
    """DHIS2 sends every value as a string, and one real attribute holds a whole GeoJSON document."""
    document = json.dumps({"type": "Point", "coordinates": [102.6, 17.97]})
    unit = _UNIT.model_copy(
        update={"attribute_values": [AttributeValueIn(attribute_uid=_UNCODED_ATTRIBUTE, value=document)]}
    )
    organization = _registry([unit])["registry/Organization-mOsABqg3Cqw.json"]
    assert organization["extension"][0]["extension"][1] == {"url": "value", "valueString": document}


def test_the_extension_url_follows_the_ig_canonical_and_the_naming_prefix() -> None:
    """The emitted url resolves to the StructureDefinition the same run's foundation target writes."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2"))
    build = build_organisation_unit_instances([_UNIT], config, "https://ig.example/fhir", attribute_codes=_CODES)
    organization = _documents(build)["registry/Organization-mOsABqg3Cqw.json"]
    assert organization["extension"][0]["url"] == "https://ig.example/fhir/StructureDefinition/dhis2-attribute-value"


_WIRE_ATTRIBUTE_VALUES = [
    {"attribute": {"id": _CODED_ATTRIBUTE}, "value": "KE03"},
    {"attribute": {"id": _UNCODED_ATTRIBUTE}, "value": "Facility register"},
]

_WIRE_ATTRIBUTES = {"attributes": [{"id": _CODED_ATTRIBUTE, "code": "hfid"}, {"id": _UNCODED_ATTRIBUTE}]}


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so the generate targets have a fhir.toml + ig tree."""
    options = InitOptions(
        ig_id="dhis2.fhir.attributeextension",
        canonical=_CANONICAL,
        name="Dhis2FhirAttributeExtension",
        title="Attribute extension IG",
        publisher="Attribute Org",
    )
    await service.init_project(directory, options)


def _written(project_root: Path, relative_path: str) -> str:
    """Read one generated file back off disk."""
    return (project_root / relative_path).read_text(encoding="utf-8")


@respx.mock
@pytest.mark.parametrize("target", ["organisation_units", "option_sets", "questionnaires"])
async def test_every_generate_target_resolves_the_attribute_codes_it_emits(
    target: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Each target joins the attribute codes inside its own client block, so the emitted code is the live one."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    attributes = respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json=_WIRE_ATTRIBUTES))
    respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "optionSets": [
                    {
                        "id": "Xa1b2c3d4e5",
                        "name": "Birth type",
                        "options": [],
                        "attributeValues": _WIRE_ATTRIBUTE_VALUES,
                    }
                ]
            },
        )
    )
    respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(
            200,
            json={
                "organisationUnits": [
                    {
                        "id": "mOsABqg3Cqw",
                        "name": "HC Photang",
                        "level": 1,
                        "path": "/mOsABqg3Cqw",
                        "attributeValues": _WIRE_ATTRIBUTE_VALUES,
                    }
                ]
            },
        )
    )
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [{"id": "BfMAe6Itzgt", "name": "Child Health", "attributeValues": _WIRE_ATTRIBUTE_VALUES}]
            },
        )
    )
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))

    generate = {
        "organisation_units": service.generate_organisation_units,
        "option_sets": service.generate_option_sets,
        "questionnaires": service.generate_questionnaires,
    }[target]
    report = await generate(resolve_profile("probe"), load_project(tmp_path))

    assert attributes.called
    emitted = {
        "organisation_units": "ig/input/resources/registry/Organization-mOsABqg3Cqw.json",
        "option_sets": "ig/input/resources/terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json",
        "questionnaires": "ig/input/fsh/data-sets/BfMAe6Itzgt.fsh",
    }[target]
    content = _written(report.project_root, emitted)
    assert "hfid" in content
    assert _UNCODED_ATTRIBUTE in content
