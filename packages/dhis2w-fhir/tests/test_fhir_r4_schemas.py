"""Unit tests for the FHIR R4 schemas: exact round-trips of real SUSHI output plus optional-field omission."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir.r4 import (
    Bundle,
    CapabilityStatement,
    CodeSystem,
    CodeSystemConcept,
    ConceptMap,
    Element,
    Extension,
    JsonResource,
    Location,
    Organization,
    Questionnaire,
    QuestionnaireResponse,
    ValueSet,
    json_resource,
)

_DATA_DIRECTORY = Path(__file__).parent / "data" / "r4"

type ResourceModel = (
    Organization
    | Location
    | CodeSystem
    | ValueSet
    | ConceptMap
    | Questionnaire
    | QuestionnaireResponse
    | CapabilityStatement
)

_NAME_ELEMENT_CASES = [
    pytest.param(Organization, "Organization-richest.json", id="organization"),
    pytest.param(Location, "Location-richest.json", id="location"),
]

_ROUND_TRIP_CASES = [
    *_NAME_ELEMENT_CASES,
    pytest.param(CodeSystem, "CodeSystem-richest.json", id="code_system"),
    pytest.param(ValueSet, "ValueSet-richest.json", id="value_set"),
    pytest.param(CodeSystem, "CodeSystem-d2-de-cs.json", id="code_system_data_elements"),
    pytest.param(CodeSystem, "CodeSystem-d2-coc-cs.json", id="code_system_option_combos"),
    pytest.param(ConceptMap, "ConceptMap-d2-os-birth-type-cm.json", id="concept_map_option_set"),
    pytest.param(Questionnaire, "Questionnaire-BfMAe6Itzgt.json", id="questionnaire_aggregate"),
    pytest.param(Questionnaire, "Questionnaire-EVTsupVis01.json", id="questionnaire_event"),
    pytest.param(Questionnaire, "Questionnaire-ZzYYXq4fJie.json", id="questionnaire_tracker_event"),
    pytest.param(Questionnaire, "Questionnaire-PsAncVisit1.json", id="questionnaire_required_and_bounds"),
    pytest.param(QuestionnaireResponse, "QuestionnaireResponse-BfMAe6Itzgt-example-1.json", id="response_aggregate"),
    pytest.param(QuestionnaireResponse, "QuestionnaireResponse-EVTsupVis01-example-1.json", id="response_event"),
    pytest.param(
        QuestionnaireResponse, "QuestionnaireResponse-ZzYYXq4fJie-example-1.json", id="response_tracker_event"
    ),
    pytest.param(CapabilityStatement, "CapabilityStatement-d2-capture-server.json", id="capability_statement"),
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


def test_a_questionnaire_carries_its_sections_disaggregated_cells_and_item_control() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "Questionnaire-BfMAe6Itzgt.json").read_text(encoding="utf-8"))
    model = Questionnaire.model_validate(parsed)
    assert model.item is not None
    section = model.item[0]
    assert section.type == "group"
    assert section.extension is not None
    control = section.extension[0]
    assert control.valueCodeableConcept is not None
    assert control.valueCodeableConcept.coding is not None
    assert control.valueCodeableConcept.coding[0].code == "gtable"
    assert section.item is not None
    disaggregated = section.item[0]
    assert disaggregated.item is not None
    assert disaggregated.item[0].linkId == "s46m5MS0hxu.Prlt0C1RF0s"
    assert disaggregated.item[0].type == "integer"


def test_a_questionnaire_carries_the_program_identifier_of_a_stage() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "Questionnaire-ZzYYXq4fJie.json").read_text(encoding="utf-8"))
    model = Questionnaire.model_validate(parsed)
    assert model.identifier is not None
    assert [identifier.system for identifier in model.identifier] == [
        "http://dhis2.org/fhir/id/program-stage",
        "http://dhis2.org/fhir/id/program-stage-code",
        "http://dhis2.org/fhir/id/program",
    ]
    assert model.item is not None
    assert model.item[1].answerValueSet == "http://localhost:8080/fhir/ValueSet/d2-os-x31y45jvIQL-vs"


def test_a_questionnaire_carries_required_questions_and_their_bounds() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "Questionnaire-PsAncVisit1.json").read_text(encoding="utf-8"))
    model = Questionnaire.model_validate(parsed)
    assert model.item is not None
    bounded = model.item[0]
    assert bounded.required is True
    assert bounded.extension is not None
    assert bounded.extension[0].url == "http://hl7.org/fhir/StructureDefinition/minValue"
    assert bounded.extension[0].valueInteger == 1
    assert model.item[1].required is None


def test_an_aggregate_response_carries_the_reporting_period_extension() -> None:
    parsed = json.loads(
        (_DATA_DIRECTORY / "QuestionnaireResponse-BfMAe6Itzgt-example-1.json").read_text(encoding="utf-8")
    )
    model = QuestionnaireResponse.model_validate(parsed)
    assert model.extension is not None
    period_extension = model.extension[0]
    assert period_extension.extension is not None
    assert [nested.url for nested in period_extension.extension] == ["iso", "type", "period"]
    period = period_extension.extension[2].valuePeriod
    assert period is not None
    assert period.start == "2026-07-01"
    assert period.end == "2026-07-31"


def test_a_tracker_event_response_carries_its_enrollment_unit_and_subject_identifier() -> None:
    parsed = json.loads(
        (_DATA_DIRECTORY / "QuestionnaireResponse-ZzYYXq4fJie-example-1.json").read_text(encoding="utf-8")
    )
    model = QuestionnaireResponse.model_validate(parsed)
    assert model.extension is not None
    organisation_unit, enrollment, form_type = model.extension
    assert organisation_unit.valueReference is not None
    assert organisation_unit.valueReference.reference == "Location/ImspTQPwCqd"
    assert enrollment.valueIdentifier is not None
    assert enrollment.valueIdentifier.system == "http://dhis2.org/fhir/id/tracker-enrollment"
    assert form_type.valueCode == "tracker-event"
    assert model.subject is not None
    assert model.subject.type == "Patient"
    assert model.subject.identifier is not None
    assert model.subject.identifier.value == "tPpcmcRWO0g"


def test_a_capability_statement_carries_its_supported_profiles_and_interactions() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "CapabilityStatement-d2-capture-server.json").read_text(encoding="utf-8"))
    model = CapabilityStatement.model_validate(parsed)
    assert model.kind == "requirements"
    assert model.fhirVersion == "4.0.1"
    assert model.rest is not None
    rest = model.rest[0]
    assert rest.mode == "server"
    assert rest.resource is not None
    response_resource = rest.resource[0]
    assert response_resource.type == "QuestionnaireResponse"
    assert response_resource.interaction is not None
    assert [interaction.code for interaction in response_resource.interaction] == ["create"]
    assert response_resource.supportedProfile is not None
    assert len(response_resource.supportedProfile) == 3


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"resourceType": "QuestionnaireResponse", "quesitonnaire": "x"}, id="typo"),
        pytest.param({"resourceType": "QuestionnaireResponse", "contained": []}, id="contained"),
        pytest.param({"resourceType": "QuestionnaireResponse", "modifierExtension": []}, id="modifier_extension"),
    ],
)
def test_a_response_carrying_an_element_the_server_does_not_serve_is_rejected(document: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        QuestionnaireResponse.model_validate(document)


def test_a_response_carrying_the_benign_r4_furniture_is_accepted() -> None:
    document = {
        "resourceType": "QuestionnaireResponse",
        "id": "BfMAe6Itzgt-example-1",
        "meta": {"profile": ["http://localhost:8080/fhir/StructureDefinition/d2-aggregate-response"]},
        "language": "en",
        "text": {"status": "generated", "div": "<div xmlns='http://www.w3.org/1999/xhtml'>captured</div>"},
        "author": {"reference": "Practitioner/admin"},
        "source": {"reference": "Practitioner/admin"},
        "status": "completed",
    }
    assert _emit(QuestionnaireResponse.model_validate(document)) == document


def test_a_json_resource_keeps_the_keys_no_model_names() -> None:
    document = {
        "resourceType": "Practitioner",
        "id": "admin",
        "name": [{"family": "Doe", "given": ["Jane"]}],
        "active": True,
    }
    carried = JsonResource.model_validate(document)
    assert carried.resourceType == "Practitioner"
    assert json.loads(carried.model_dump_json(exclude_none=True, by_alias=True)) == document


def test_carrying_a_typed_resource_reproduces_its_own_emission() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "Questionnaire-EVTsupVis01.json").read_text(encoding="utf-8"))
    model = Questionnaire.model_validate(parsed)
    carried = json_resource(model)
    assert json.loads(carried.model_dump_json(exclude_none=True, by_alias=True)) == _emit(model)


def test_a_bundle_without_entries_or_links_omits_their_keys() -> None:
    emitted = json.loads(Bundle(id="search", type="searchset", total=0).model_dump_json(exclude_none=True))
    assert emitted == {"resourceType": "Bundle", "id": "search", "type": "searchset", "total": 0}


def test_a_bundle_carries_its_entries_as_verbatim_documents() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "Questionnaire-EVTsupVis01.json").read_text(encoding="utf-8"))
    document = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": 1,
        "link": [{"relation": "self", "url": "http://localhost:8000/fhir/Questionnaire"}],
        "entry": [
            {
                "fullUrl": "http://localhost:8000/fhir/Questionnaire/EVTsupVis01",
                "resource": parsed,
                "search": {"mode": "match"},
            }
        ],
    }
    assert json.loads(Bundle.model_validate(document).model_dump_json(exclude_none=True)) == document


def test_a_whole_decimal_keeps_its_wire_spelling() -> None:
    """`valueDecimal` is `int | float` so a whole number is not widened into `2896.0` on the way out."""
    emitted = Extension(url="urn:example", valueDecimal=2896).model_dump_json(exclude_none=True)
    assert '"valueDecimal":2896' in emitted
    assert "2896.0" not in emitted


def test_an_unrequired_question_never_serialises_its_required_key() -> None:
    parsed = json.loads((_DATA_DIRECTORY / "Questionnaire-PsAncVisit1.json").read_text(encoding="utf-8"))
    emitted = _emit(Questionnaire.model_validate(parsed))
    items = emitted["item"]
    assert items[0]["required"] is True
    assert "required" not in items[1]
    assert "repeats" not in items[0]
