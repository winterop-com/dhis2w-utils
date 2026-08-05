"""Unit tests for the FHIR R4 schemas: exact round-trips of real SUSHI output plus optional-field omission."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir.r4 import Location, NameElement, Organization

_DATA_DIRECTORY = Path(__file__).parent / "data" / "r4"

_ROUND_TRIP_CASES = [
    pytest.param(Organization, "Organization-richest.json", id="organization"),
    pytest.param(Location, "Location-richest.json", id="location"),
]


def _emit(model: Organization | Location) -> dict[str, Any]:
    """Serialise a model the way the emitter writes it, back into a plain JSON document."""
    dumped: dict[str, Any] = json.loads(model.model_dump_json(exclude_none=True, by_alias=True))
    return dumped


@pytest.mark.parametrize(("model_type", "filename"), _ROUND_TRIP_CASES)
def test_reference_documents_round_trip_exactly(model_type: type[Organization] | type[Location], filename: str) -> None:
    parsed = json.loads((_DATA_DIRECTORY / filename).read_text(encoding="utf-8"))
    emitted = _emit(model_type.model_validate(parsed))
    assert emitted == parsed


@pytest.mark.parametrize(("model_type", "filename"), _ROUND_TRIP_CASES)
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
    model = Organization(name="HC Photang", name_element=NameElement(extension=[]))
    assert _emit(model) == {"resourceType": "Organization", "name": "HC Photang", "_name": {"extension": []}}


def test_resource_type_is_emitted_without_being_supplied() -> None:
    assert _emit(Organization(id="mOsABqg3Cqw"))["resourceType"] == "Organization"
    assert _emit(Location(id="YvLOmtTQD6b"))["resourceType"] == "Location"


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
