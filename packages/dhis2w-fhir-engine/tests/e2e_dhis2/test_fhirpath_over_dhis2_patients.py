"""FHIRPath evaluated over FHIR Patients built from seeded DHIS2 Child Programme records."""

from __future__ import annotations

from typing import Any

import pytest

from dhis2w_fhir_engine import FHIRPathEvaluator

from .conftest import SeededCohort


@pytest.mark.slow
def test_fhirpath_reads_one_dhis2_tracked_entity_as_a_patient(seeded_cohort: SeededCohort) -> None:
    """Every Patient element asserted here traces back to a field DHIS2 returned for that entity."""
    person = seeded_cohort.tracked_people[0]
    patient = seeded_cohort.patient_resource(person)
    evaluator = FHIRPathEvaluator()

    assert evaluator.evaluate("Patient.id", patient) == [person.tracked_entity_identifier]
    assert evaluator.evaluate("Patient.identifier.value", patient) == [person.tracked_entity_identifier]
    assert evaluator.evaluate("Patient.name.given", patient) == [person.given_name]
    assert evaluator.evaluate("Patient.name.family", patient) == [person.family_name]
    assert evaluator.evaluate("Patient.gender", patient) == [person.fhir_gender]

    assert person.date_of_birth is not None
    assert evaluator.evaluate("Patient.birthDate", patient) == [person.date_of_birth.isoformat()]
    assert evaluator.evaluate("Patient.managingOrganization.reference", patient) == [
        f"Organization/{person.organisation_unit_identifier}"
    ]


@pytest.mark.slow
def test_fhirpath_counts_the_resources_mapped_from_dhis2(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """Bundle counts equal the number of DHIS2 records that went into the mapping."""
    expected_patients = len(seeded_cohort.tracked_people)
    expected_observations = seeded_cohort.weight_measurement_count
    expected_organizations = len(seeded_cohort.districts)

    assert expected_patients > 0
    assert expected_observations > 0
    assert expected_organizations > 0

    evaluator = FHIRPathEvaluator()

    assert evaluator.evaluate("Bundle.entry.resource.ofType(Patient).count()", cohort_bundle) == [expected_patients]
    assert evaluator.evaluate("Bundle.entry.resource.ofType(Observation).count()", cohort_bundle) == [
        expected_observations
    ]
    assert evaluator.evaluate("Bundle.entry.resource.ofType(Organization).count()", cohort_bundle) == [
        expected_organizations
    ]


@pytest.mark.slow
def test_fhirpath_filters_the_bundle_by_the_dhis2_gender_attribute(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """A `where(gender = 'female')` filter picks out exactly the entities DHIS2 recorded as female."""
    expected_female_identifiers = sorted(
        person.tracked_entity_identifier for person in seeded_cohort.tracked_people if person.fhir_gender == "female"
    )
    assert expected_female_identifiers

    evaluator = FHIRPathEvaluator()
    selected = evaluator.evaluate(
        "Bundle.entry.resource.ofType(Patient).where(gender = 'female').id",
        cohort_bundle,
    )

    assert sorted(str(identifier) for identifier in selected) == expected_female_identifiers


@pytest.mark.slow
def test_fhirpath_reads_the_weights_recorded_on_dhis2_events(seeded_cohort: SeededCohort) -> None:
    """Observation quantities carry the numeric data values DHIS2 stored on the program stage events."""
    person = next(person for person in seeded_cohort.tracked_people if person.weight_measurements)
    observations = seeded_cohort.observation_resources(person)
    expected_weights = sorted(measurement.weight_in_grams for measurement in person.weight_measurements)

    evaluator = FHIRPathEvaluator()
    weights = [
        value
        for observation in observations
        for value in evaluator.evaluate("Observation.valueQuantity.value", observation)
    ]
    units = {
        str(unit)
        for observation in observations
        for unit in evaluator.evaluate("Observation.valueQuantity.unit", observation)
    }
    subjects = {
        str(subject)
        for observation in observations
        for subject in evaluator.evaluate("Observation.subject.reference", observation)
    }

    assert sorted(float(str(weight)) for weight in weights) == expected_weights
    assert units == {"g"}
    assert subjects == {f"Patient/{person.tracked_entity_identifier}"}
