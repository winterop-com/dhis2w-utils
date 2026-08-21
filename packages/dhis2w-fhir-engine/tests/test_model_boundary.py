"""Tests for the engine's typed-model boundary: a pydantic resource evaluates exactly as its wire dict does."""

from __future__ import annotations

import json
from typing import Any

import pytest

from dhis2w_fhir_engine import CQLEvaluator, EvaluationContext, FHIRPathEvaluator, InMemoryDataSource
from dhis2w_fhir_engine.engine.cql.context import EncounterContext, PatientContext
from dhis2w_fhir_engine.ingest import as_evaluation_input, as_resource_dict, as_resource_dicts
from dhis2w_fhir_engine.r4 import BundleDataSource, PatientBundleDataSource
from dhis2w_fhir_engine.r4.resources import (
    Bundle,
    BundleEntry,
    CodeableConcept,
    Coding,
    Condition,
    HumanName,
    Identifier,
    Observation,
    Patient,
    Reference,
    json_resource,
)


def _patient_model() -> Patient:
    """A Patient carrying the elements the assertions below reach for."""
    return Patient(
        id="Kj9HgT4mQpz",
        active=True,
        name=[HumanName(family="Kamara", given=["Aminata", "Fatu"])],
        gender="female",
        birthDate="2024-06-01",
        identifier=[Identifier(system="http://example.org/fhir/id/tracked-entity", value="Kj9HgT4mQpz")],
    )


def _as_wire(model: Patient | Bundle) -> dict[str, Any]:
    """The wire document a caller would have handed over instead of the model."""
    dumped: dict[str, Any] = json.loads(model.model_dump_json(exclude_none=True, by_alias=True))
    return dumped


def _condition_bundle() -> Bundle:
    """A collection bundle of one Patient and two Conditions, as models throughout."""
    subject = Reference(reference="Patient/Kj9HgT4mQpz")
    malaria = Condition(
        id="cond-1",
        code=CodeableConcept(coding=[Coding(system="http://snomed.info/sct", code="61462000")]),
        subject=subject,
        recordedDate="2024-06-02",
    )
    anaemia = Condition(
        id="cond-2",
        code=CodeableConcept(coding=[Coding(system="http://snomed.info/sct", code="271737000")]),
        subject=subject,
        recordedDate="2024-06-03",
    )
    return Bundle(
        type="collection",
        entry=[
            BundleEntry(resource=json_resource(_patient_model())),
            BundleEntry(resource=json_resource(malaria)),
            BundleEntry(resource=json_resource(anaemia)),
        ],
    )


@pytest.mark.parametrize(
    "expression",
    [
        "Patient.name.given",
        "Patient.name.family",
        "Patient.gender",
        "Patient.birthDate",
        "Patient.identifier.value",
        "Patient.active",
        "Patient.name.given.count()",
        "Patient.where(gender = 'female').id",
    ],
)
def test_a_fhirpath_evaluation_over_a_model_equals_the_evaluation_over_its_dict(expression: str) -> None:
    model = _patient_model()
    evaluator = FHIRPathEvaluator()
    assert evaluator.evaluate(expression, model) == evaluator.evaluate(expression, _as_wire(model))


def test_a_fhirpath_evaluation_over_a_collection_of_models_equals_the_dict_form() -> None:
    models = [_patient_model(), Patient(id="second", gender="male")]
    evaluator = FHIRPathEvaluator()
    assert evaluator.evaluate("Patient.gender", models) == evaluator.evaluate(
        "Patient.gender", [_as_wire(model) for model in models]
    )


def test_the_boolean_and_single_result_helpers_read_a_model_too() -> None:
    model = _patient_model()
    evaluator = FHIRPathEvaluator()
    assert evaluator.evaluate_boolean("Patient.active", model) is True
    assert evaluator.evaluate_single("Patient.name.family", model) == "Kamara"
    assert evaluator.check("Patient.identifier.exists()", model) is True


def test_an_evaluation_context_holds_the_dumped_document_of_a_model_it_was_given() -> None:
    model = _patient_model()
    context = EvaluationContext(resource=model)
    assert context.resource == _as_wire(model)
    assert context.root_resource == _as_wire(model)
    assert context.get_constant("resource") == _as_wire(model)


def test_a_child_context_takes_a_model_as_readily_as_a_dict() -> None:
    context = EvaluationContext(resource={"resourceType": "Organization", "id": "mOsABqg3Cqw"})
    child = context.child(_patient_model())
    assert child.resource == _as_wire(_patient_model())


def test_the_cql_and_encounter_contexts_take_models() -> None:
    model = _patient_model()
    assert PatientContext(resource=model).patient == _as_wire(model)
    encounter = EncounterContext(patient=model, encounter={"resourceType": "Encounter", "id": "enc-1"})
    assert encounter.patient == _as_wire(model)
    assert encounter.encounter == {"resourceType": "Encounter", "id": "enc-1"}


def test_a_cql_retrieve_over_a_bundle_of_models_equals_the_dict_form() -> None:
    bundle = _condition_bundle()
    expression = "[Condition]"

    from_models = CQLEvaluator(data_source=BundleDataSource(bundle)).evaluate_expression(expression)
    from_dicts = CQLEvaluator(data_source=BundleDataSource(_as_wire(bundle))).evaluate_expression(expression)

    assert from_models == from_dicts
    assert [resource["id"] for resource in from_models] == ["cond-1", "cond-2"]


def test_a_cql_expression_over_a_model_context_resource_equals_the_dict_form() -> None:
    model = _patient_model()
    expression = "Patient.gender"

    evaluator = CQLEvaluator(data_source=BundleDataSource(_condition_bundle()))
    assert evaluator.evaluate_expression(expression, model) == evaluator.evaluate_expression(
        expression, _as_wire(model)
    )


def test_an_in_memory_data_source_stores_the_dumped_document_of_a_model() -> None:
    model = _patient_model()
    observation = Observation(id="obs-1", status="final", subject=Reference(reference="Patient/Kj9HgT4mQpz"))

    from_models = InMemoryDataSource()
    from_models.add_resources([model, observation])
    from_dicts = InMemoryDataSource()
    from_dicts.add_resources([_as_wire(model), json.loads(observation.model_dump_json(exclude_none=True))])

    assert from_models.retrieve("Patient") == from_dicts.retrieve("Patient")
    assert from_models.resolve_reference("Patient/Kj9HgT4mQpz") == _as_wire(model)
    assert from_models.retrieve("Observation") == from_dicts.retrieve("Observation")


def test_a_patient_bundle_data_source_finds_the_patient_in_a_bundle_of_models() -> None:
    source = PatientBundleDataSource(_condition_bundle())
    assert source.patient == _as_wire(_patient_model())
    assert [resource["id"] for resource in source.retrieve("Condition")] == ["cond-1", "cond-2"]


def test_a_data_source_takes_a_single_model_that_is_not_a_bundle() -> None:
    source = BundleDataSource(_patient_model())
    assert source.retrieve("Patient") == [_as_wire(_patient_model())]


def test_ingesting_a_model_never_reaches_back_into_the_caller_s_model() -> None:
    model = _patient_model()
    before = _as_wire(model)

    context = EvaluationContext(resource=model)
    assert context.resource is not None
    context.resource["gender"] = "male"
    context.resource["name"][0]["given"].append("Injected")

    source = InMemoryDataSource()
    source.add_resource(model)
    stored = source.retrieve("Patient")[0]
    stored["birthDate"] = "1900-01-01"

    assert _as_wire(model) == before
    assert model.gender == "female"
    assert model.name is not None
    assert model.name[0].given == ["Aminata", "Fatu"]


def test_the_boundary_helpers_pass_a_dict_through_untouched() -> None:
    document = {"resourceType": "Patient", "id": "Kj9HgT4mQpz"}
    assert as_resource_dict(document) is document
    assert as_resource_dict(None) is None
    assert as_resource_dicts([document]) == [document]
    assert as_evaluation_input([document]) == [document]
    assert as_evaluation_input(None) is None
