"""CQL retrieve expressions evaluated over a Bundle built from seeded DHIS2 Child Programme records."""

from __future__ import annotations

from typing import Any

import pytest

from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r4 import BundleDataSource, PatientBundleDataSource

from .conftest import SeededCohort

COHORT_LIBRARY = """
library Dhis2ChildProgrammeCohort version '1.0'
using FHIR version '4.0.1'

define "All Patients":
    [Patient]

define "All Observations":
    [Observation]

define "Female Patients":
    [Patient] P where P.gender = 'female'

define "Recorded Weights":
    [Observation] O return O.valueQuantity.value

define "Patient Count":
    Count([Patient])
"""

PATIENT_LIBRARY = """
library Dhis2ChildProgrammePerson version '1.0'
using FHIR version '4.0.1'

context Patient

define "Weights For Patient":
    [Observation] O return O.valueQuantity.value

define "Has A Recorded Weight":
    exists([Observation])
"""


@pytest.mark.slow
def test_cql_retrieve_counts_match_the_dhis2_records(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """`[Patient]` and `[Observation]` return one entry per DHIS2 record that was mapped."""
    expected_patients = len(seeded_cohort.tracked_people)
    expected_observations = seeded_cohort.weight_measurement_count
    assert expected_patients > 0
    assert expected_observations > 0

    evaluator = CQLEvaluator(data_source=BundleDataSource(cohort_bundle))
    library = evaluator.compile(COHORT_LIBRARY)

    patients = evaluator.evaluate_definition("All Patients", library=library)
    observations = evaluator.evaluate_definition("All Observations", library=library)

    assert len(patients) == expected_patients
    assert len(observations) == expected_observations
    assert evaluator.evaluate_definition("Patient Count", library=library) == expected_patients
    assert sorted(patient["id"] for patient in patients) == sorted(
        person.tracked_entity_identifier for person in seeded_cohort.tracked_people
    )


@pytest.mark.slow
def test_cql_query_filters_on_the_dhis2_gender_attribute(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """A `where` clause over the retrieve selects exactly the entities DHIS2 recorded as female."""
    expected_female_identifiers = sorted(
        person.tracked_entity_identifier for person in seeded_cohort.tracked_people if person.fhir_gender == "female"
    )
    assert expected_female_identifiers

    evaluator = CQLEvaluator(data_source=BundleDataSource(cohort_bundle))
    library = evaluator.compile(COHORT_LIBRARY)

    selected = evaluator.evaluate_definition("Female Patients", library=library)

    assert sorted(patient["id"] for patient in selected) == expected_female_identifiers


@pytest.mark.slow
def test_cql_returns_the_weights_dhis2_recorded_on_the_events(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """A `return` clause yields the numeric data values, not the Observation resources."""
    expected_weights = sorted(
        measurement.weight_in_grams
        for person in seeded_cohort.tracked_people
        for measurement in person.weight_measurements
    )
    assert expected_weights

    evaluator = CQLEvaluator(data_source=BundleDataSource(cohort_bundle))
    library = evaluator.compile(COHORT_LIBRARY)

    weights = evaluator.evaluate_definition("Recorded Weights", library=library)

    assert sorted(float(weight) for weight in weights) == expected_weights


@pytest.mark.slow
def test_patient_bundle_data_source_scopes_retrieve_to_one_dhis2_entity(seeded_cohort: SeededCohort) -> None:
    """A per-entity Bundle keeps the retrieve inside that one tracked entity's observations."""
    person = next(person for person in seeded_cohort.tracked_people if person.weight_measurements)
    expected_weights = sorted(measurement.weight_in_grams for measurement in person.weight_measurements)

    data_source = PatientBundleDataSource(seeded_cohort.person_bundle(person))
    assert data_source.patient is not None
    assert data_source.patient["id"] == person.tracked_entity_identifier

    evaluator = CQLEvaluator(data_source=data_source)
    library = evaluator.compile(PATIENT_LIBRARY)
    patient = seeded_cohort.patient_resource(person)

    weights = evaluator.evaluate_definition("Weights For Patient", resource=patient, library=library)

    assert sorted(float(weight) for weight in weights) == expected_weights
    assert evaluator.evaluate_definition("Has A Recorded Weight", resource=patient, library=library) is True
