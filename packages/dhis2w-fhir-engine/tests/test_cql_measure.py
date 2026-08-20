"""Tests for CQL measure evaluation.

Tests the MeasureEvaluator class for evaluating clinical quality measures.
"""

from datetime import datetime

import pytest

from dhis2w_fhir_engine.engine.cql import (
    CQLEvaluator,
)
from dhis2w_fhir_engine.r4 import (
    InMemoryDataSource,
    MeasureEvaluator,
    MeasureScoring,
    PopulationType,
)
from dhis2w_fhir_engine.r4.measure import (
    GroupResult,
    MeasureGroup,
    MeasurePopulation,
    MeasureReport,
    PatientResult,
    PopulationCount,
    StratifierResult,
)

# ============================================================================
# Test Data
# ============================================================================


def create_patient(patient_id: str, age: int, gender: str = "male") -> dict:
    """Create a test patient with given age."""
    birth_year = datetime.now().year - age
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "gender": gender,
        "birthDate": f"{birth_year}-06-15",
    }


def create_condition(patient_id: str, code: str, system: str = "http://snomed.info/sct") -> dict:
    """Create a condition for a patient."""
    return {
        "resourceType": "Condition",
        "id": f"cond-{patient_id}-{code}",
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {"coding": [{"system": system, "code": code}]},
    }


def create_observation(patient_id: str, code: str, value: float, unit: str = "mg/dL") -> dict:
    """Create an observation for a patient."""
    return {
        "resourceType": "Observation",
        "id": f"obs-{patient_id}-{code}",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
        "valueQuantity": {"value": value, "unit": unit},
    }


# ============================================================================
# MeasureEvaluator Basic Tests
# ============================================================================


class TestMeasureEvaluatorBasic:
    """Basic MeasureEvaluator tests."""

    def test_create_measure_evaluator(self) -> None:
        """Test creating a MeasureEvaluator."""
        evaluator = MeasureEvaluator()
        assert evaluator._evaluator is not None
        assert evaluator._library is None
        assert evaluator._groups == []

    def test_create_with_cql_evaluator(self) -> None:
        """Test creating with existing CQL evaluator."""
        cql = CQLEvaluator()
        evaluator = MeasureEvaluator(cql_evaluator=cql)
        assert evaluator._evaluator is cql

    def test_create_with_data_source(self) -> None:
        """Test creating with data source."""
        ds = InMemoryDataSource()
        evaluator = MeasureEvaluator(data_source=ds)
        assert evaluator._evaluator._data_source is ds

    def test_load_measure(self) -> None:
        """Test loading a measure from CQL source."""
        evaluator = MeasureEvaluator()
        library = evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                true
        """)
        assert library is not None
        assert library.name == "TestMeasure"
        assert evaluator._library is library

    def test_detect_populations(self) -> None:
        """Test automatic population detection."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                true

            define "Denominator Exclusion":
                false
        """)

        assert len(evaluator._groups) == 1
        group = evaluator._groups[0]
        pop_types = [p.type for p in group.populations]

        assert PopulationType.INITIAL_POPULATION in pop_types
        assert PopulationType.DENOMINATOR in pop_types
        assert PopulationType.NUMERATOR in pop_types
        assert PopulationType.DENOMINATOR_EXCLUSION in pop_types

    def test_detect_stratifiers(self) -> None:
        """Test automatic stratifier detection."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Stratifier 1":
                'Group A'

            define "Stratification by Gender":
                'Male'
        """)

        assert len(evaluator._groups) == 1
        assert "Stratifier 1" in evaluator._groups[0].stratifiers
        assert "Stratification by Gender" in evaluator._groups[0].stratifiers

    def test_set_scoring(self) -> None:
        """Test setting measure scoring type."""
        evaluator = MeasureEvaluator()
        evaluator.set_scoring(MeasureScoring.COHORT)
        assert evaluator._scoring == MeasureScoring.COHORT

    def test_add_population(self) -> None:
        """Test manually adding a population."""
        evaluator = MeasureEvaluator()
        evaluator.add_population(
            PopulationType.INITIAL_POPULATION,
            "MyInitialPop",
            group_id="group1",
        )

        assert len(evaluator._groups) == 1
        assert evaluator._groups[0].id == "group1"
        assert len(evaluator._groups[0].populations) == 1
        assert evaluator._groups[0].populations[0].definition == "MyInitialPop"

    def test_add_stratifier(self) -> None:
        """Test manually adding a stratifier."""
        evaluator = MeasureEvaluator()
        evaluator.add_stratifier("AgeGroup", group_id="group1")

        assert len(evaluator._groups) == 1
        assert "AgeGroup" in evaluator._groups[0].stratifiers


# ============================================================================
# Patient Evaluation Tests
# ============================================================================


class TestPatientEvaluation:
    """Tests for single patient evaluation."""

    def test_evaluate_patient_basic(self) -> None:
        """Test basic patient evaluation."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                true
        """)

        patient = create_patient("p1", 45)
        result = evaluator.evaluate_patient(patient)

        assert result.patient_id == "p1"
        assert result.populations["initial-population"] is True
        assert result.populations["denominator"] is True
        assert result.populations["numerator"] is True

    def test_evaluate_patient_with_conditions(self) -> None:
        """Test patient evaluation with conditional logic."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                AgeInYears() >= 18

            define "Denominator":
                "Initial Population"

            define "Numerator":
                AgeInYears() >= 40
        """)

        # Adult under 40
        patient1 = create_patient("p1", 25)
        result1 = evaluator.evaluate_patient(patient1)
        assert result1.populations["initial-population"] is True
        assert result1.populations["numerator"] is False

        # Adult 40+
        patient2 = create_patient("p2", 50)
        result2 = evaluator.evaluate_patient(patient2)
        assert result2.populations["initial-population"] is True
        assert result2.populations["numerator"] is True

        # Minor
        patient3 = create_patient("p3", 15)
        result3 = evaluator.evaluate_patient(patient3)
        assert result3.populations["initial-population"] is False

    def test_evaluate_patient_with_exclusions(self) -> None:
        """Test patient evaluation with exclusions."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Denominator Exclusion":
                AgeInYears() > 85

            define "Numerator":
                true
        """)

        # Regular patient
        patient1 = create_patient("p1", 50)
        result1 = evaluator.evaluate_patient(patient1)
        assert result1.populations["denominator-exclusion"] is False

        # Elderly patient (excluded)
        patient2 = create_patient("p2", 90)
        result2 = evaluator.evaluate_patient(patient2)
        assert result2.populations["denominator-exclusion"] is True

    def test_evaluate_patient_with_stratifier(self) -> None:
        """Test patient evaluation with stratifier."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Stratifier Age Group":
                if AgeInYears() < 40 then 'Under 40'
                else if AgeInYears() < 65 then '40-64'
                else '65+'
        """)

        patient1 = create_patient("p1", 30)
        result1 = evaluator.evaluate_patient(patient1)
        assert result1.stratifier_values["Stratifier Age Group"] == "Under 40"

        patient2 = create_patient("p2", 50)
        result2 = evaluator.evaluate_patient(patient2)
        assert result2.stratifier_values["Stratifier Age Group"] == "40-64"

        patient3 = create_patient("p3", 70)
        result3 = evaluator.evaluate_patient(patient3)
        assert result3.stratifier_values["Stratifier Age Group"] == "65+"

    def test_evaluate_patient_no_measure_loaded(self) -> None:
        """Test error when no measure is loaded."""
        evaluator = MeasureEvaluator()
        patient = create_patient("p1", 45)

        with pytest.raises(ValueError, match="No measure loaded"):
            evaluator.evaluate_patient(patient)


# ============================================================================
# Population Evaluation Tests
# ============================================================================


class TestPopulationEvaluation:
    """Tests for population evaluation."""

    def test_evaluate_population_basic(self) -> None:
        """Test basic population evaluation."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                AgeInYears() >= 40
        """)

        patients = [
            create_patient("p1", 30),
            create_patient("p2", 45),
            create_patient("p3", 55),
            create_patient("p4", 25),
        ]

        report = evaluator.evaluate_population(patients)

        assert report.measure_id == "TestMeasure"
        assert len(report.patient_results) == 4
        assert len(report.groups) == 1

        group = report.groups[0]
        assert group.populations["initial-population"].count == 4
        assert group.populations["denominator"].count == 4
        assert group.populations["numerator"].count == 2  # Only p2 and p3

    def test_evaluate_population_with_exclusions(self) -> None:
        """Test population evaluation with exclusions."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                AgeInYears() >= 18

            define "Denominator":
                "Initial Population"

            define "Denominator Exclusion":
                AgeInYears() > 85

            define "Numerator":
                AgeInYears() >= 40 and AgeInYears() <= 85
        """)

        patients = [
            create_patient("p1", 15),  # Minor - not in IP
            create_patient("p2", 30),  # Adult - IP, Denom, not Num
            create_patient("p3", 50),  # Adult - IP, Denom, Num
            create_patient("p4", 90),  # Elderly - IP, Denom, Excl
        ]

        report = evaluator.evaluate_population(patients)
        group = report.groups[0]

        assert group.populations["initial-population"].count == 3  # All adults
        assert group.populations["denominator"].count == 3
        assert group.populations["denominator-exclusion"].count == 1  # p4
        assert group.populations["numerator"].count == 1  # p3

    def test_proportion_score_calculation(self) -> None:
        """Test proportion measure score calculation."""
        evaluator = MeasureEvaluator()
        evaluator.set_scoring(MeasureScoring.PROPORTION)
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                AgeInYears() >= 50
        """)

        patients = [
            create_patient("p1", 30),
            create_patient("p2", 40),
            create_patient("p3", 50),
            create_patient("p4", 60),
        ]

        report = evaluator.evaluate_population(patients)
        group = report.groups[0]

        # 2 in numerator, 4 in denominator = 0.5
        assert group.measure_score == 0.5

    def test_proportion_score_with_exclusions(self) -> None:
        """Test proportion score with exclusions."""
        evaluator = MeasureEvaluator()
        evaluator.set_scoring(MeasureScoring.PROPORTION)
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Denominator Exclusion":
                AgeInYears() > 80

            define "Numerator":
                AgeInYears() >= 50 and AgeInYears() <= 80
        """)

        patients = [
            create_patient("p1", 30),  # Denom, not Num
            create_patient("p2", 50),  # Denom, Num
            create_patient("p3", 60),  # Denom, Num
            create_patient("p4", 85),  # Excluded from denom
        ]

        report = evaluator.evaluate_population(patients)
        group = report.groups[0]

        # Denom = 4, Excl = 1, effective denom = 3
        # Num = 2 (p2, p3 - ages 50-80, p4 excluded by numerator criteria)
        # Score = 2 / 3 = 0.6667
        assert group.measure_score == pytest.approx(0.6667, rel=0.01)

    def test_population_stratification(self) -> None:
        """Test population evaluation with stratification."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                AgeInYears() >= 50

            define "Stratifier Age Group":
                if AgeInYears() < 50 then 'Under 50'
                else '50+'
        """)

        patients = [
            create_patient("p1", 30),
            create_patient("p2", 40),
            create_patient("p3", 55),
            create_patient("p4", 65),
        ]

        report = evaluator.evaluate_population(patients)
        group = report.groups[0]

        assert "Stratifier Age Group" in group.stratifiers
        strat_results = group.stratifiers["Stratifier Age Group"]

        # Find results by value
        under_50 = next(s for s in strat_results if s.value == "Under 50")
        over_50 = next(s for s in strat_results if s.value == "50+")

        assert under_50.populations["initial-population"].count == 2
        assert under_50.populations["numerator"].count == 0

        assert over_50.populations["initial-population"].count == 2
        assert over_50.populations["numerator"].count == 2

    def test_evaluate_population_no_measure_loaded(self) -> None:
        """Test error when no measure is loaded."""
        evaluator = MeasureEvaluator()
        patients = [create_patient("p1", 45)]

        with pytest.raises(ValueError, match="No measure loaded"):
            evaluator.evaluate_population(patients)


# ============================================================================
# MeasureReport Tests
# ============================================================================


class TestMeasureReport:
    """Tests for MeasureReport class."""

    def test_measure_report_to_fhir_basic(self) -> None:
        """Test converting MeasureReport to FHIR."""
        report = MeasureReport(
            measure_id="TestMeasure",
            period_start=datetime(2024, 1, 1),
            period_end=datetime(2024, 12, 31),
        )

        fhir = report.to_fhir()

        assert fhir["resourceType"] == "MeasureReport"
        assert fhir["status"] == "complete"
        assert fhir["type"] == "summary"
        assert fhir["measure"] == "TestMeasure"
        assert "period" in fhir
        assert fhir["period"]["start"] == "2024-01-01T00:00:00"

    def test_measure_report_to_fhir_with_populations(self) -> None:
        """Test converting MeasureReport with populations to FHIR."""
        group_result = GroupResult(
            id="group1",
            populations={
                "initial-population": PopulationCount(type=PopulationType.INITIAL_POPULATION, count=100),
                "denominator": PopulationCount(type=PopulationType.DENOMINATOR, count=80),
                "numerator": PopulationCount(type=PopulationType.NUMERATOR, count=60),
            },
            measure_score=0.75,
        )

        report = MeasureReport(
            measure_id="TestMeasure",
            groups=[group_result],
        )

        fhir = report.to_fhir()

        assert "group" in fhir
        assert len(fhir["group"]) == 1

        group = fhir["group"][0]
        assert group["id"] == "group1"
        assert "population" in group
        assert len(group["population"]) == 3
        assert group["measureScore"]["value"] == 0.75

    def test_measure_report_to_fhir_with_stratifiers(self) -> None:
        """Test converting MeasureReport with stratifiers to FHIR."""
        strat_result = StratifierResult(
            value="Male",
            populations={
                "initial-population": PopulationCount(type=PopulationType.INITIAL_POPULATION, count=50),
            },
        )

        group_result = GroupResult(
            id="group1",
            populations={
                "initial-population": PopulationCount(type=PopulationType.INITIAL_POPULATION, count=100),
            },
            stratifiers={"Gender": [strat_result]},
        )

        report = MeasureReport(
            measure_id="TestMeasure",
            groups=[group_result],
        )

        fhir = report.to_fhir()

        group = fhir["group"][0]
        assert "stratifier" in group
        assert len(group["stratifier"]) == 1
        assert group["stratifier"][0]["code"][0]["text"] == "Gender"
        assert len(group["stratifier"][0]["stratum"]) == 1


# ============================================================================
# Data Classes Tests
# ============================================================================


class TestDataClasses:
    """Tests for measure data classes."""

    def test_population_type_values(self) -> None:
        """Test PopulationType enum values."""
        assert PopulationType.INITIAL_POPULATION.value == "initial-population"
        assert PopulationType.NUMERATOR.value == "numerator"
        assert PopulationType.DENOMINATOR.value == "denominator"

    def test_measure_scoring_values(self) -> None:
        """Test MeasureScoring enum values."""
        assert MeasureScoring.PROPORTION.value == "proportion"
        assert MeasureScoring.RATIO.value == "ratio"
        assert MeasureScoring.COHORT.value == "cohort"

    def test_measure_population(self) -> None:
        """Test the MeasurePopulation model."""
        pop = MeasurePopulation(
            type=PopulationType.NUMERATOR,
            definition="MyNumerator",
            description="Test numerator",
        )
        assert pop.type == PopulationType.NUMERATOR
        assert pop.definition == "MyNumerator"
        assert pop.description == "Test numerator"

    def test_measure_group(self) -> None:
        """Test the MeasureGroup model."""
        group = MeasureGroup(
            id="group1",
            populations=[MeasurePopulation(type=PopulationType.INITIAL_POPULATION, definition="IP")],
            stratifiers=["AgeGroup"],
        )
        assert group.id == "group1"
        assert len(group.populations) == 1
        assert len(group.stratifiers) == 1

    def test_patient_result(self) -> None:
        """Test the PatientResult model."""
        result = PatientResult(
            patient_id="p1",
            populations={"initial-population": True, "numerator": False},
            stratifier_values={"AgeGroup": "40-64"},
        )
        assert result.patient_id == "p1"
        assert result.populations["initial-population"] is True
        assert result.stratifier_values["AgeGroup"] == "40-64"

    def test_population_count(self) -> None:
        """Test the PopulationCount model."""
        count = PopulationCount(
            type=PopulationType.NUMERATOR,
            count=10,
            patients=["p1", "p2", "p3"],
        )
        assert count.type == PopulationType.NUMERATOR
        assert count.count == 10
        assert len(count.patients) == 3


# ============================================================================
# Integration Tests
# ============================================================================


class TestMeasureIntegration:
    """Integration tests with data sources."""

    def test_measure_with_retrieve(self) -> None:
        """Test measure evaluation with retrieve operations."""
        # Create data source with patient and conditions
        ds = InMemoryDataSource()
        patient = create_patient("p1", 50)
        ds.add_resource(patient)
        ds.add_resource(create_condition("p1", "44054006"))  # Diabetes

        evaluator = MeasureEvaluator(data_source=ds)
        evaluator.load_measure("""
            library DiabetesMeasure version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define "Initial Population":
                AgeInYears() >= 18

            define "Denominator":
                "Initial Population"

            define "Numerator":
                exists([Condition])
        """)

        result = evaluator.evaluate_patient(patient, data_source=ds)

        assert result.populations["initial-population"] is True
        assert result.populations["numerator"] is True

    def test_measure_population_with_data_source(self) -> None:
        """Test population evaluation with data source."""
        ds = InMemoryDataSource()

        # Add patients
        patients = []
        for i in range(5):
            patient = create_patient(f"p{i}", 40 + i * 10)  # Ages 40, 50, 60, 70, 80
            ds.add_resource(patient)
            patients.append(patient)

        # Add conditions for some patients
        ds.add_resource(create_condition("p1", "44054006"))  # p1 has diabetes
        ds.add_resource(create_condition("p2", "44054006"))  # p2 has diabetes
        ds.add_resource(create_condition("p3", "44054006"))  # p3 has diabetes

        evaluator = MeasureEvaluator(data_source=ds)
        evaluator.load_measure("""
            library DiabetesMeasure version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define "Initial Population":
                AgeInYears() >= 18

            define "Denominator":
                "Initial Population"

            define "Numerator":
                exists([Condition])
        """)

        report = evaluator.evaluate_population(patients, data_source=ds)

        assert len(report.patient_results) == 5
        group = report.groups[0]
        assert group.populations["initial-population"].count == 5
        assert group.populations["denominator"].count == 5
        assert group.populations["numerator"].count == 3  # p1, p2, p3 have conditions


class TestGetPopulationSummary:
    """Tests for population summary."""

    def test_get_population_summary(self) -> None:
        """Test getting population summary from report."""
        evaluator = MeasureEvaluator()
        evaluator.load_measure("""
            library TestMeasure version '1.0'

            define "Initial Population":
                true

            define "Denominator":
                true

            define "Numerator":
                AgeInYears() >= 50
        """)

        patients = [
            create_patient("p1", 30),
            create_patient("p2", 50),
            create_patient("p3", 60),
        ]

        report = evaluator.evaluate_population(patients)
        summary = evaluator.get_population_summary(report)

        assert summary["measure"] == "TestMeasure"
        assert summary["total_patients"] == 3
        assert len(summary["groups"]) == 1

        group_summary = summary["groups"][0]
        assert group_summary["populations"]["initial-population"] == 3
        assert group_summary["populations"]["denominator"] == 3
        assert group_summary["populations"]["numerator"] == 2
        assert group_summary["measure_score"] == pytest.approx(0.6667, rel=0.01)
