"""Unit tests for the FHIR R4 resource models: closed shapes, alias round-trips, and optional-field omission."""

from __future__ import annotations

import json
from typing import Any

import pytest

from dhis2w_fhir_engine.r4.resources import (
    DATA_ABSENT_REASON_EXTENSION_URL,
    AllergyIntolerance,
    Bundle,
    BundleEntry,
    CapabilityStatement,
    CodeableConcept,
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptProperty,
    Coding,
    Composition,
    CompositionSection,
    Condition,
    Element,
    Extension,
    HumanName,
    Identifier,
    JsonResource,
    Location,
    Narrative,
    Observation,
    Organization,
    Parameters,
    ParametersParameter,
    Patient,
    Questionnaire,
    QuestionnaireItem,
    QuestionnaireResponse,
    Reference,
    ValueSet,
    json_resource,
)

type ResourceModel = (
    Organization
    | Location
    | CodeSystem
    | ValueSet
    | Questionnaire
    | QuestionnaireResponse
    | CapabilityStatement
    | Parameters
    | Patient
    | Composition
    | Condition
    | AllergyIntolerance
    | Observation
)


def _emit(model: ResourceModel) -> dict[str, Any]:
    """Serialise a model the way the emitter writes it, back into a plain JSON document."""
    dumped: dict[str, Any] = json.loads(model.model_dump_json(exclude_none=True, by_alias=True))
    return dumped


def test_the_name_element_populates_by_field_name_too() -> None:
    model = Organization(name="HC Photang", name_element=Element(extension=[]))
    assert _emit(model) == {"resourceType": "Organization", "name": "HC Photang", "_name": {"extension": []}}


def test_the_title_element_populates_by_field_name_too() -> None:
    model = ValueSet(title="8p: 8programs", title_element=Element(extension=[]))
    assert _emit(model) == {"resourceType": "ValueSet", "title": "8p: 8programs", "_title": {"extension": []}}


def test_a_concept_property_emits_one_value_element_at_a_time() -> None:
    """A property carrying an integer writes `valueInteger` and none of its sibling choices."""
    emitted = json.loads(
        CodeSystemConceptProperty(code="level", valueInteger=4).model_dump_json(exclude_none=True, by_alias=True)
    )
    assert emitted == {"code": "level", "valueInteger": 4}


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


def test_a_capability_statement_declares_operations_on_its_rest_element() -> None:
    document = {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "rest": [
            {
                "mode": "server",
                "operation": [
                    {
                        "name": "translate",
                        "definition": "http://hl7.org/fhir/OperationDefinition/ConceptMap-translate",
                        "documentation": "Translate a concept code into the DHIS2 identifiers it stands for.",
                    }
                ],
            }
        ],
    }
    model = CapabilityStatement.model_validate(document)
    assert model.rest is not None
    operations = model.rest[0].operation
    assert operations is not None
    assert operations[0].name == "translate"
    assert _emit(model) == document


def test_a_parameters_body_carries_the_translate_answer_shape() -> None:
    document = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "result", "valueBoolean": True},
            {
                "name": "match",
                "part": [
                    {"name": "equivalence", "valueCode": "equal"},
                    {
                        "name": "concept",
                        "valueCoding": {
                            "system": "http://dhis2.org/fhir/id/option",
                            "code": "kRRUtYaGett",
                            "display": "Natural Birth",
                        },
                    },
                    {"name": "source", "valueUri": "http://example.org/fhir/ConceptMap/d2-os-Xa1b2c3d4e5-cm"},
                ],
            },
        ],
    }
    model = Parameters.model_validate(document)
    assert model.parameter is not None
    nested = model.parameter[1].part
    assert nested is not None
    assert nested[1].valueCoding is not None
    assert nested[1].valueCoding.code == "kRRUtYaGett"
    assert _emit(model) == document


def test_a_parameters_body_omits_the_values_it_does_not_carry() -> None:
    model = Parameters(
        parameter=[
            ParametersParameter(name="result", valueBoolean=False),
            ParametersParameter(name="message", valueString="nothing maps that code"),
        ]
    )
    emitted = _emit(model)
    assert emitted == {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "result", "valueBoolean": False},
            {"name": "message", "valueString": "nothing maps that code"},
        ],
    }
    assert "id" not in emitted
    assert "part" not in emitted["parameter"][0]


def test_a_parameters_body_carries_no_narrative() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        Parameters.model_validate({"resourceType": "Parameters", "text": {"status": "generated", "div": "<div/>"}})


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
    model = Questionnaire(
        id="EVTsupVis01",
        url="http://example.org/fhir/Questionnaire/EVTsupVis01",
        title="Supervision visit",
        status="active",
        item=[QuestionnaireItem(linkId="s46m5MS0hxu", text="Visit date", type="date")],
    )
    carried = json_resource(model)
    assert json.loads(carried.model_dump_json(exclude_none=True, by_alias=True)) == _emit(model)


def test_a_bundle_without_entries_or_links_omits_their_keys() -> None:
    emitted = json.loads(Bundle(id="search", type="searchset", total=0).model_dump_json(exclude_none=True))
    assert emitted == {"resourceType": "Bundle", "id": "search", "type": "searchset", "total": 0}


def test_a_bundle_carries_its_entries_as_verbatim_documents() -> None:
    document = {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": 1,
        "link": [{"relation": "self", "url": "http://localhost:8000/fhir/Questionnaire"}],
        "entry": [
            {
                "fullUrl": "http://localhost:8000/fhir/Questionnaire/EVTsupVis01",
                "resource": {
                    "resourceType": "Questionnaire",
                    "id": "EVTsupVis01",
                    "title": "Supervision visit",
                    "status": "active",
                    "item": [{"linkId": "s46m5MS0hxu", "text": "Visit date", "type": "date"}],
                },
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


#: One SNOMED CT concept the IPS names for a section a system holds nothing for - "No information
#: available" - which is what the document resources below assert absence with.
_NO_INFORMATION_AVAILABLE = CodeableConcept(
    coding=[Coding(system="http://snomed.info/sct", code="1287211007", display="No information available")]
)


def _document_bundle() -> Bundle:
    """A four-entry document: the Composition, its subject, one populated entry, one asserted absence."""
    patient = Patient(
        id="Kj9HgT4mQpz",
        name=[HumanName(family="Kamara", given=["Aminata"])],
        birthDate="2024-06-01",
        identifier=[Identifier(system="http://example.org/fhir/id/tracked-entity", value="Kj9HgT4mQpz")],
    )
    observation = Observation(
        id="obs-1",
        status="final",
        code=CodeableConcept(coding=[Coding(system="http://example.org/fhir/de", code="UXz7xuGCEhU")]),
        subject=Reference(reference="urn:uuid:00000000-0000-0000-0000-000000000001"),
        effectiveDateTime="2024-06-02T00:00:00Z",
        valueString="3.2",
    )
    condition = Condition(id="cond-1", code=_NO_INFORMATION_AVAILABLE, subject=observation.subject)
    composition = Composition(
        id="ips-1",
        status="final",
        type=CodeableConcept(coding=[Coding(system="http://loinc.org", code="60591-5")]),
        subject=observation.subject,
        date="2026-01-19T09:00:00Z",
        author=[Reference(reference="urn:uuid:00000000-0000-0000-0000-000000000004")],
        title="International Patient Summary",
        section=[
            CompositionSection(
                title="Problems",
                code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="11450-4")]),
                text=Narrative(status="generated", div="<div xmlns='http://www.w3.org/1999/xhtml'>none</div>"),
                entry=[Reference(reference="urn:uuid:00000000-0000-0000-0000-000000000002")],
            ),
            CompositionSection(
                title="Medication Summary",
                code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="10160-0")]),
                text=Narrative(status="generated", div="<div xmlns='http://www.w3.org/1999/xhtml'>none</div>"),
                emptyReason=CodeableConcept(
                    coding=[
                        Coding(system="http://terminology.hl7.org/CodeSystem/list-empty-reason", code="unavailable")
                    ]
                ),
            ),
        ],
    )
    return Bundle(
        type="document",
        identifier=Identifier(system="urn:ietf:rfc:3986", value="urn:uuid:00000000-0000-0000-0000-000000000000"),
        timestamp="2026-01-19T09:00:00Z",
        entry=[
            BundleEntry(fullUrl="urn:uuid:00000000-0000-0000-0000-000000000000", resource=json_resource(composition)),
            BundleEntry(fullUrl="urn:uuid:00000000-0000-0000-0000-000000000001", resource=json_resource(patient)),
            BundleEntry(fullUrl="urn:uuid:00000000-0000-0000-0000-000000000002", resource=json_resource(condition)),
            BundleEntry(fullUrl="urn:uuid:00000000-0000-0000-0000-000000000003", resource=json_resource(observation)),
        ],
    )


def test_a_document_bundle_round_trips_every_resource_it_carries() -> None:
    emitted = json.loads(_document_bundle().model_dump_json(exclude_none=True, by_alias=True))
    assert emitted["type"] == "document"
    assert emitted["identifier"]["value"] == "urn:uuid:00000000-0000-0000-0000-000000000000"
    assert emitted["timestamp"] == "2026-01-19T09:00:00Z"
    assert [entry["resource"]["resourceType"] for entry in emitted["entry"]] == [
        "Composition",
        "Patient",
        "Condition",
        "Observation",
    ]
    assert json.loads(Bundle.model_validate(emitted).model_dump_json(exclude_none=True, by_alias=True)) == emitted


def test_a_composition_states_either_its_entries_or_why_it_has_none() -> None:
    sections = json.loads(_document_bundle().model_dump_json(exclude_none=True, by_alias=True))["entry"][0]["resource"][
        "section"
    ]
    assert "entry" in sections[0]
    assert "emptyReason" not in sections[0]
    assert "entry" not in sections[1]
    assert sections[1]["emptyReason"]["coding"][0]["code"] == "unavailable"
    assert all("section" not in section for section in sections)


def test_a_patient_states_an_absent_birth_date_on_the_primitive_element() -> None:
    model = Patient(
        id="Kj9HgT4mQpz",
        name=[HumanName(text="Aminata Kamara")],
        birthDate_element=Element(
            extension=[Extension(url=DATA_ABSENT_REASON_EXTENSION_URL, valueCode="unknown")],
        ),
    )
    emitted = _emit(model)
    assert "birthDate" not in emitted
    assert emitted["_birthDate"]["extension"][0]["url"] == DATA_ABSENT_REASON_EXTENSION_URL
    assert emitted["_birthDate"]["extension"][0]["valueCode"] == "unknown"
    read_back = Patient.model_validate(emitted)
    assert read_back.birthDate_element is not None
    assert _emit(read_back) == emitted


def test_a_patient_carries_the_two_halves_of_a_nominated_name() -> None:
    emitted = _emit(Patient(id="Kj9HgT4mQpz", name=[HumanName(family="Kamara", given=["Aminata"])], gender="female"))
    assert emitted["name"] == [{"family": "Kamara", "given": ["Aminata"]}]
    assert emitted["gender"] == "female"


def test_an_observation_carries_a_dhis2_value_as_the_string_dhis2_sent() -> None:
    emitted = _emit(
        Observation(
            id="obs-1",
            status="final",
            code=CodeableConcept(coding=[Coding(system="http://example.org/fhir/de", code="UXz7xuGCEhU")]),
            valueString="3.2",
        )
    )
    assert emitted["valueString"] == "3.2"
    assert "valueInteger" not in emitted
    assert "dataAbsentReason" not in emitted


@pytest.mark.parametrize(
    ("model_type", "document"),
    [
        pytest.param(Patient, {"resourceType": "Patient", "photo": []}, id="patient"),
        pytest.param(Composition, {"resourceType": "Composition", "titel": "typo"}, id="composition"),
        pytest.param(Condition, {"resourceType": "Condition", "severity": {}}, id="condition"),
        pytest.param(AllergyIntolerance, {"resourceType": "AllergyIntolerance", "reaction": []}, id="allergy"),
        pytest.param(Observation, {"resourceType": "Observation", "valueQuantity": {}}, id="observation"),
    ],
)
def test_the_document_resources_reject_the_elements_they_do_not_carry(
    model_type: type[ResourceModel], document: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        model_type.model_validate(document)


def test_an_allergy_intolerance_asserts_absence_without_the_removed_code_system() -> None:
    emitted = _emit(
        AllergyIntolerance(
            id="allergy-absent",
            code=_NO_INFORMATION_AVAILABLE,
            patient=Reference(reference="urn:uuid:00000000-0000-0000-0000-000000000001"),
        )
    )
    assert emitted["code"]["coding"][0]["system"] == "http://snomed.info/sct"
    assert emitted["code"]["coding"][0]["code"] == "1287211007"
    assert "clinicalStatus" not in emitted
