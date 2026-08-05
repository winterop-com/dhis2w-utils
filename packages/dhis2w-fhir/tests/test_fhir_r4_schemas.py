"""Unit tests for the FHIR R4 schemas: exact round-trips of real SUSHI output plus optional-field omission."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir.r4 import CodeSystem, CodeSystemConcept, Element, Location, Organization, ValueSet

_DATA_DIRECTORY = Path(__file__).parent / "data" / "r4"

type ResourceModel = Organization | Location | CodeSystem | ValueSet

_NAME_ELEMENT_CASES = [
    pytest.param(Organization, "Organization-richest.json", id="organization"),
    pytest.param(Location, "Location-richest.json", id="location"),
]

_ROUND_TRIP_CASES = [
    *_NAME_ELEMENT_CASES,
    pytest.param(CodeSystem, "CodeSystem-richest.json", id="code_system"),
    pytest.param(ValueSet, "ValueSet-richest.json", id="value_set"),
]


def _emit(model: ResourceModel) -> dict[str, Any]:
    """Serialise a model the way the emitter writes it, back into a plain JSON document."""
    dumped: dict[str, Any] = json.loads(model.model_dump_json(exclude_none=True, by_alias=True))
    return dumped


@pytest.mark.parametrize(("model_type", "filename"), _ROUND_TRIP_CASES)
def test_reference_documents_round_trip_exactly(model_type: type[ResourceModel], filename: str) -> None:
    parsed = json.loads((_DATA_DIRECTORY / filename).read_text(encoding="utf-8"))
    emitted = _emit(model_type.model_validate(parsed))
    assert emitted == parsed


@pytest.mark.parametrize(("model_type", "filename"), _NAME_ELEMENT_CASES)
def test_reference_documents_keep_the_primitive_name_extension(
    model_type: type[Organization] | type[Location], filename: str
) -> None:
    parsed = json.loads((_DATA_DIRECTORY / filename).read_text(encoding="utf-8"))
    model = model_type.model_validate(parsed)
    assert model.name_element is not None
    assert model.name_element.extension is not None
    translation = model.name_element.extension[0]
    assert translation.url == "http://hl7.org/fhir/StructureDefinition/translation"
    assert translation.extension is not None
    assert [nested.url for nested in translation.extension] == ["lang", "content"]
    assert "_name" in _emit(model)


def test_the_name_element_populates_by_field_name_too() -> None:
    model = Organization(name="HC Photang", name_element=Element(extension=[]))
    assert _emit(model) == {"resourceType": "Organization", "name": "HC Photang", "_name": {"extension": []}}


@pytest.mark.parametrize(
    ("model_type", "filename"),
    [
        pytest.param(CodeSystem, "CodeSystem-richest.json", id="code_system"),
        pytest.param(ValueSet, "ValueSet-richest.json", id="value_set"),
    ],
)
def test_reference_documents_keep_the_primitive_title_extension(
    model_type: type[CodeSystem] | type[ValueSet], filename: str
) -> None:
    parsed = json.loads((_DATA_DIRECTORY / filename).read_text(encoding="utf-8"))
    model = model_type.model_validate(parsed)
    assert model.title_element is not None
    assert model.title_element.extension is not None
    translation = model.title_element.extension[0]
    assert translation.url == "http://hl7.org/fhir/StructureDefinition/translation"
    assert translation.extension is not None
    assert [nested.url for nested in translation.extension] == ["lang", "content"]
    assert "_title" in _emit(model)


def test_the_title_element_populates_by_field_name_too() -> None:
    model = ValueSet(title="8p: 8programs", title_element=Element(extension=[]))
    assert _emit(model) == {"resourceType": "ValueSet", "title": "8p: 8programs", "_title": {"extension": []}}


def test_a_code_system_carries_its_concepts_properties_and_designations() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "CodeSystem-richest.json").read_text(encoding="utf-8"))
    model = CodeSystem.model_validate(parsed)
    assert model.count == 8
    assert model.property is not None
    assert [declaration.code for declaration in model.property] == ["dhis2-code"]
    assert model.concept is not None
    first_concept = model.concept[0]
    assert first_concept.code == "s6eRzXxw4Rq"
    assert first_concept.property is not None
    assert first_concept.property[0].valueString == "1.0.0.0"
    assert first_concept.designation is not None
    assert first_concept.designation[0].language == "lo"


def test_a_value_set_composes_the_matching_code_system() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "ValueSet-richest.json").read_text(encoding="utf-8"))
    model = ValueSet.model_validate(parsed)
    assert model.compose is not None
    assert model.compose.include is not None
    assert model.compose.include[0].system == "http://example.org/fhir/CodeSystem/d2-os-b4P0xzW5wcD-cs"


def test_a_code_system_without_title_extension_property_or_designation_omits_their_keys() -> None:
    model = CodeSystem(
        id="d2-os-b4P0xzW5wcD-cs",
        name="D2OS_b4P0xzW5wcD_CS",
        title="8p: 8programs",
        status="draft",
        content="complete",
        count=1,
        concept=[CodeSystemConcept(code="s6eRzXxw4Rq", display="I. Hygiene and health Promotion")],
    )
    emitted = _emit(model)
    assert emitted == {
        "resourceType": "CodeSystem",
        "id": "d2-os-b4P0xzW5wcD-cs",
        "name": "D2OS_b4P0xzW5wcD_CS",
        "title": "8p: 8programs",
        "status": "draft",
        "content": "complete",
        "count": 1,
        "concept": [{"code": "s6eRzXxw4Rq", "display": "I. Hygiene and health Promotion"}],
    }
    assert "_title" not in emitted
    assert "property" not in emitted
    assert "designation" not in emitted["concept"][0]
    assert "property" not in emitted["concept"][0]


def test_resource_type_is_emitted_without_being_supplied() -> None:
    assert _emit(Organization(id="mOsABqg3Cqw"))["resourceType"] == "Organization"
    assert _emit(Location(id="YvLOmtTQD6b"))["resourceType"] == "Location"
    assert _emit(CodeSystem(id="d2-os-b4P0xzW5wcD-cs"))["resourceType"] == "CodeSystem"
    assert _emit(ValueSet(id="d2-os-b4P0xzW5wcD-vs"))["resourceType"] == "ValueSet"


def test_an_organization_without_optional_fields_omits_their_keys() -> None:
    model = Organization(id="mOsABqg3Cqw", name="HC Photang", active=True)
    assert _emit(model) == {"resourceType": "Organization", "id": "mOsABqg3Cqw", "name": "HC Photang", "active": True}


def test_a_location_without_position_or_extension_omits_their_keys() -> None:
    model = Location(id="YvLOmtTQD6b", name="02 Phongsali", status="active")
    emitted = _emit(model)
    assert emitted == {"resourceType": "Location", "id": "YvLOmtTQD6b", "name": "02 Phongsali", "status": "active"}
    assert "position" not in emitted
    assert "extension" not in emitted
    assert "description" not in emitted


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        Organization.model_validate(
            {"resourceType": "Organization", "description": "R4 has no Organization.description"}
        )
