"""MeasureEvaluator run over the seeded DHIS2 Child Programme cohort mapped into FHIR R4."""

from __future__ import annotations

from typing import Any

import pytest

from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator, MeasureScoring, PopulationType

from .conftest import SeededCohort

WEIGHT_RECORDED_MEASURE = """
library Dhis2ChildProgrammeWeightRecorded version '1.0'
using FHIR version '4.0.1'

context Patient

define "Initial Population":
    true

define "Denominator":
    "Initial Population"

define "Numerator":
    exists([Observation])
"""


@pytest.mark.slow
def test_measure_report_population_counts_match_the_dhis2_cohort(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """Denominator is every mapped tracked entity; numerator is those with a weight on a DHIS2 event."""
    expected_denominator = len(seeded_cohort.tracked_people)
    expected_numerator = sum(1 for person in seeded_cohort.tracked_people if person.weight_measurements)
    assert expected_denominator > 0
    assert 0 < expected_numerator <= expected_denominator

    data_source = BundleDataSource(cohort_bundle)
    evaluator = MeasureEvaluator(data_source=data_source)
    evaluator.set_scoring(MeasureScoring.PROPORTION)
    evaluator.load_measure(WEIGHT_RECORDED_MEASURE)

    report = evaluator.evaluate_population(seeded_cohort.patient_resources(), data_source=data_source)

    assert report.measure_id == "Dhis2ChildProgrammeWeightRecorded"
    assert len(report.patient_results) == expected_denominator
    assert len(report.groups) == 1

    group = report.groups[0]
    assert group.populations[PopulationType.INITIAL_POPULATION.value].count == expected_denominator
    assert group.populations[PopulationType.DENOMINATOR.value].count == expected_denominator
    assert group.populations[PopulationType.NUMERATOR.value].count == expected_numerator
    assert group.measure_score == round(expected_numerator / expected_denominator, 4)


@pytest.mark.slow
def test_measure_numerator_names_the_tracked_entities_with_a_recorded_weight(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """The numerator's patient identifiers are the DHIS2 tracked entity identifiers that carry a weight."""
    expected_numerator_identifiers = sorted(
        person.tracked_entity_identifier for person in seeded_cohort.tracked_people if person.weight_measurements
    )
    assert expected_numerator_identifiers

    data_source = BundleDataSource(cohort_bundle)
    evaluator = MeasureEvaluator(data_source=data_source)
    evaluator.load_measure(WEIGHT_RECORDED_MEASURE)

    report = evaluator.evaluate_population(seeded_cohort.patient_resources(), data_source=data_source)
    group = report.groups[0]

    assert sorted(group.populations[PopulationType.NUMERATOR.value].patients) == expected_numerator_identifiers
    numerator_results = {
        result.patient_id for result in report.patient_results if result.populations[PopulationType.NUMERATOR.value]
    }
    assert sorted(numerator_results) == expected_numerator_identifiers


@pytest.mark.slow
def test_measure_report_serialises_to_a_fhir_measure_report(
    seeded_cohort: SeededCohort,
    cohort_bundle: dict[str, Any],
) -> None:
    """`to_fhir()` emits a FHIR MeasureReport carrying the same counts as the typed report."""
    expected_denominator = len(seeded_cohort.tracked_people)
    expected_numerator = sum(1 for person in seeded_cohort.tracked_people if person.weight_measurements)

    data_source = BundleDataSource(cohort_bundle)
    evaluator = MeasureEvaluator(data_source=data_source)
    evaluator.load_measure(WEIGHT_RECORDED_MEASURE)

    report = evaluator.evaluate_population(seeded_cohort.patient_resources(), data_source=data_source)
    fhir_report = report.to_fhir()

    assert fhir_report["resourceType"] == "MeasureReport"
    assert fhir_report["status"] == "complete"
    assert fhir_report["measure"] == "Dhis2ChildProgrammeWeightRecorded"

    counts = {
        population["code"]["coding"][0]["code"]: population["count"]
        for population in fhir_report["group"][0]["population"]
    }
    assert counts[PopulationType.DENOMINATOR.value] == expected_denominator
    assert counts[PopulationType.NUMERATOR.value] == expected_numerator
    assert fhir_report["group"][0]["measureScore"]["value"] == round(expected_numerator / expected_denominator, 4)
