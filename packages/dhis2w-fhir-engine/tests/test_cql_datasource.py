"""Tests for CQL data source implementations."""

from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql import (
    CQLCode,
    CQLEvaluator,
    PatientContext,
)
from dhis2w_fhir_engine.engine.exceptions import CQLError
from dhis2w_fhir_engine.r4 import (
    BundleDataSource,
    InMemoryDataSource,
    PatientBundleDataSource,
)


class TestInMemoryDataSource:
    """Tests for InMemoryDataSource."""

    def test_add_resource(self) -> None:
        """Test adding a single resource."""
        ds = InMemoryDataSource()
        patient = {"resourceType": "Patient", "id": "123", "name": [{"family": "Smith"}]}

        ds.add_resource(patient)

        assert "Patient" in ds._resources
        assert len(ds._resources["Patient"]) == 1
        assert ds._resources["Patient"][0]["id"] == "123"

    def test_add_resources(self) -> None:
        """Test adding multiple resources."""
        ds = InMemoryDataSource()
        resources = [
            {"resourceType": "Patient", "id": "1"},
            {"resourceType": "Patient", "id": "2"},
            {"resourceType": "Condition", "id": "c1"},
        ]

        ds.add_resources(resources)

        assert len(ds._resources["Patient"]) == 2
        assert len(ds._resources["Condition"]) == 1

    def test_retrieve_by_type(self) -> None:
        """Test retrieving resources by type."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "1"},
                {"resourceType": "Condition", "id": "c1"},
                {"resourceType": "Condition", "id": "c2"},
            ]
        )

        conditions = ds.retrieve("Condition")

        assert len(conditions) == 2

    def test_retrieve_with_patient_context(self) -> None:
        """Test retrieving resources filtered by patient context."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {"resourceType": "Patient", "id": "p2"},
                {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}},
                {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
                {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p2"}},
            ]
        )

        # Create patient context
        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})

        conditions = ds.retrieve("Condition", context=context)

        assert len(conditions) == 2
        assert all(c["subject"]["reference"] == "Patient/p1" for c in conditions)

    def test_resolve_reference(self) -> None:
        """Test resolving a FHIR reference."""
        ds = InMemoryDataSource()
        patient = {"resourceType": "Patient", "id": "123"}
        ds.add_resource(patient)

        resolved = ds.resolve_reference("Patient/123")

        assert resolved is not None
        assert resolved["id"] == "123"

    def test_resolve_reference_not_found(self) -> None:
        """Test resolving a nonexistent reference."""
        ds = InMemoryDataSource()

        resolved = ds.resolve_reference("Patient/999")

        assert resolved is None

    def test_retrieve_with_code_filter(self) -> None:
        """Test retrieving resources filtered by code."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {
                    "resourceType": "Condition",
                    "id": "c1",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]},
                },
                {
                    "resourceType": "Condition",
                    "id": "c2",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "73211009"}]},
                },
            ]
        )

        diabetes_code = CQLCode(code="44054006", system="http://snomed.info/sct")
        conditions = ds.retrieve(
            "Condition",
            code_path="code",
            codes=[diabetes_code],
        )

        assert len(conditions) == 1
        assert conditions[0]["id"] == "c1"

    def test_retrieve_with_valueset_filter(self) -> None:
        """Test retrieving resources filtered by valueset."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {
                    "resourceType": "Condition",
                    "id": "c1",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]},
                },
                {
                    "resourceType": "Condition",
                    "id": "c2",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "OTHER"}]},
                },
            ]
        )

        # Add valueset
        ds.add_valueset(
            "http://example.org/valueset/diabetes",
            [CQLCode(code="44054006", system="http://snomed.info/sct")],
        )

        conditions = ds.retrieve(
            "Condition",
            code_path="code",
            valueset="http://example.org/valueset/diabetes",
        )

        assert len(conditions) == 1
        assert conditions[0]["id"] == "c1"

    def test_clear(self) -> None:
        """Test clearing all resources."""
        ds = InMemoryDataSource()
        ds.add_resource({"resourceType": "Patient", "id": "1"})
        ds.add_valueset("http://example.org/vs", [])

        ds.clear()

        assert len(ds._resources) == 0
        assert len(ds._by_id) == 0
        assert len(ds._valuesets) == 0


class TestBundleDataSource:
    """Tests for BundleDataSource."""

    def test_load_bundle(self) -> None:
        """Test loading a FHIR Bundle."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": {"resourceType": "Condition", "id": "c1"}},
            ],
        }

        ds = BundleDataSource(bundle)

        assert len(ds.resources["Patient"]) == 1
        assert len(ds.resources["Condition"]) == 1

    def test_load_single_resource(self) -> None:
        """Test loading a single resource (not a bundle)."""
        patient = {"resourceType": "Patient", "id": "p1"}

        ds = BundleDataSource(patient)

        assert len(ds.resources["Patient"]) == 1

    def test_retrieve_from_bundle(self) -> None:
        """Test retrieving resources from a bundle."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": {"resourceType": "Observation", "id": "o1"}},
                {"resource": {"resourceType": "Observation", "id": "o2"}},
            ],
        }

        ds = BundleDataSource(bundle)
        observations = ds.retrieve("Observation")

        assert len(observations) == 2

    def test_resolve_reference_from_bundle(self) -> None:
        """Test resolving references within a bundle."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
            ],
        }

        ds = BundleDataSource(bundle)
        patient = ds.resolve_reference("Patient/p1")

        assert patient is not None
        assert patient["id"] == "p1"


class TestPatientBundleDataSource:
    """Tests for PatientBundleDataSource."""

    def test_extract_patient(self) -> None:
        """Test automatic patient extraction from bundle."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"family": "Smith"}]}},
                {"resource": {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}}},
            ],
        }

        ds = PatientBundleDataSource(bundle)

        assert ds.patient is not None
        assert ds.patient["id"] == "p1"

    def test_automatic_patient_filtering(self) -> None:
        """Test that retrieval is automatically filtered to the patient."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}}},
                {"resource": {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p2"}}},
            ],
        }

        ds = PatientBundleDataSource(bundle)
        conditions = ds.retrieve("Condition")

        # Should only get conditions for patient p1
        assert len(conditions) == 1
        assert conditions[0]["id"] == "c1"


class TestDataSourceIntegration:
    """Integration tests for data sources with CQL evaluator."""

    DIABETES_VALUE_SET_URL = "http://example.org/fhir/ValueSet/diabetes"

    LIBRARY_SCOPED_BY_A_VALUE_SET = f"""
        library ValueSetScoped version '1.0'
        using FHIR version '4.0.1'

        valueset "Diabetes": '{DIABETES_VALUE_SET_URL}'

        define "Diabetic Conditions": [Condition: "Diabetes"]
    """

    def _conditions_data_source(self) -> InMemoryDataSource:
        """Two conditions, one of which the diabetes valueset would name."""
        data_source = InMemoryDataSource()
        data_source.add_resources(
            [
                {
                    "resourceType": "Condition",
                    "id": "c1",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]},
                },
                {
                    "resourceType": "Condition",
                    "id": "c2",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "OTHER"}]},
                },
            ]
        )
        return data_source

    def test_a_declared_valueset_with_no_expansion_refuses_rather_than_widening(self) -> None:
        """A retrieve scoped to a valueset nothing expanded refuses instead of matching every Condition."""
        evaluator = CQLEvaluator(data_source=self._conditions_data_source())
        evaluator.compile(self.LIBRARY_SCOPED_BY_A_VALUE_SET)

        with pytest.raises(CQLError) as refusal:
            evaluator.evaluate_definition("Diabetic Conditions")

        assert self.DIABETES_VALUE_SET_URL in str(refusal.value)
        assert "holds no expansion for" in str(refusal.value)
        assert "add_valueset" not in str(refusal.value)

    def test_the_same_retrieve_narrows_once_the_valueset_is_expanded(self) -> None:
        """Expanding the valueset the refusal named answers the question the retrieve asked."""
        data_source = self._conditions_data_source()
        data_source.add_valueset(
            self.DIABETES_VALUE_SET_URL,
            [CQLCode(code="44054006", system="http://snomed.info/sct")],
        )
        evaluator = CQLEvaluator(data_source=data_source)
        evaluator.compile(self.LIBRARY_SCOPED_BY_A_VALUE_SET)

        assert [c["id"] for c in evaluator.evaluate_definition("Diabetic Conditions")] == ["c1"]

    def test_retrieve_with_evaluator(self) -> None:
        """Test CQL retrieve with data source."""
        # Set up data source
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"},
                {
                    "resourceType": "Condition",
                    "id": "c1",
                    "subject": {"reference": "Patient/p1"},
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]},
                },
            ]
        )

        # Create evaluator with data source
        evaluator = CQLEvaluator(data_source=ds)

        # Compile library with retrieve
        evaluator.compile("""
            library RetrieveTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define AllConditions: [Condition]
        """)

        # Evaluate with patient context
        patient = {"resourceType": "Patient", "id": "p1"}
        conditions = evaluator.evaluate_definition("AllConditions", resource=patient)

        assert isinstance(conditions, list)
        assert len(conditions) == 1

    def test_retrieve_with_bundle(self) -> None:
        """Test CQL retrieve with bundle data source."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}},
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "o1",
                        "subject": {"reference": "Patient/p1"},
                        "code": {"coding": [{"system": "http://loinc.org", "code": "2339-0"}]},
                        "valueQuantity": {"value": 100, "unit": "mg/dL"},
                    }
                },
            ],
        }

        ds = BundleDataSource(bundle)
        evaluator = CQLEvaluator(data_source=ds)

        evaluator.compile("""
            library BundleTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define Observations: [Observation]
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        observations = evaluator.evaluate_definition("Observations", resource=patient)

        assert isinstance(observations, list)
        assert len(observations) == 1
        assert observations[0]["id"] == "o1"

    def test_a_retrieve_under_a_non_patient_context_answers_the_context_resource(self) -> None:
        """A Questionnaire context names no patient, so `[Questionnaire]` finds the one it is."""
        questionnaire = {"resourceType": "Questionnaire", "id": "d2-pr-anc-visit-q", "status": "active"}
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": questionnaire}]}
        evaluator = CQLEvaluator(data_source=BundleDataSource(bundle))
        evaluator.compile("""
            library QuestionnaireContext version '1.0'
            using FHIR version '4.0.1'

            define Questionnaires: [Questionnaire]
        """)

        found = evaluator.evaluate_definition("Questionnaires", resource=questionnaire)

        assert [q["id"] for q in found] == ["d2-pr-anc-visit-q"]


class TestNestedValueAccess:
    """Tests for nested value access in data sources."""

    def test_get_nested_value_simple(self) -> None:
        """Test getting a simple nested value."""
        ds = InMemoryDataSource()
        resource = {"patient": {"name": "John"}}

        value = ds._get_nested_value(resource, "patient.name")

        assert value == "John"

    def test_get_nested_value_array_index(self) -> None:
        """Test getting a value from array by index."""
        ds = InMemoryDataSource()
        resource = {"name": [{"family": "Smith"}, {"family": "Jones"}]}

        value = ds._get_nested_value(resource, "name.0.family")

        assert value == "Smith"

    def test_get_nested_value_array_property(self) -> None:
        """Test getting property from all array elements."""
        ds = InMemoryDataSource()
        resource = {"name": [{"family": "Smith"}, {"family": "Jones"}]}

        value = ds._get_nested_value(resource, "name.family")

        assert value == ["Smith", "Jones"]

    def test_get_nested_value_missing(self) -> None:
        """Test getting a missing nested value."""
        ds = InMemoryDataSource()
        resource: dict[str, Any] = {"patient": {}}

        value = ds._get_nested_value(resource, "patient.name.family")

        assert value is None


class TestCodeMatching:
    """Tests for code matching in data sources."""

    def test_matches_code_with_cql_code(self) -> None:
        """Test matching with CQLCode."""
        ds = InMemoryDataSource()
        resource = {"code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]}}

        code = CQLCode(code="44054006", system="http://snomed.info/sct")

        assert ds._matches_code(resource, "code", codes=[code])

    def test_matches_code_no_match(self) -> None:
        """Test code that doesn't match."""
        ds = InMemoryDataSource()
        resource = {"code": {"coding": [{"system": "http://snomed.info/sct", "code": "OTHER"}]}}

        code = CQLCode(code="44054006", system="http://snomed.info/sct")

        assert not ds._matches_code(resource, "code", codes=[code])

    def test_matches_code_with_string(self) -> None:
        """Test matching with simple string code."""
        ds = InMemoryDataSource()
        resource = {"code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]}}

        assert ds._matches_code(resource, "code", codes=["44054006"])

    def test_matches_code_multiple_codings(self) -> None:
        """Test matching with multiple codings in CodeableConcept."""
        ds = InMemoryDataSource()
        resource = {
            "code": {
                "coding": [
                    {"system": "http://icd10.info", "code": "E11"},
                    {"system": "http://snomed.info/sct", "code": "44054006"},
                ]
            }
        }

        code = CQLCode(code="44054006", system="http://snomed.info/sct")

        assert ds._matches_code(resource, "code", codes=[code])


class TestPatientReference:
    """Tests for patient reference extraction."""

    def test_get_patient_reference_condition(self) -> None:
        """Test getting patient reference from Condition."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "Condition",
            "subject": {"reference": "Patient/123"},
        }

        ref = ds._get_patient_reference(resource)

        assert ref == "Patient/123"

    def test_get_patient_reference_observation(self) -> None:
        """Test getting patient reference from Observation."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "Observation",
            "subject": {"reference": "Patient/456"},
        }

        ref = ds._get_patient_reference(resource)

        assert ref == "Patient/456"

    def test_get_patient_reference_allergy(self) -> None:
        """Test getting patient reference from AllergyIntolerance."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "AllergyIntolerance",
            "patient": {"reference": "Patient/789"},
        }

        ref = ds._get_patient_reference(resource)

        assert ref == "Patient/789"

    def test_get_patient_reference_missing(self) -> None:
        """Test getting patient reference when missing."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "Condition",
        }

        ref = ds._get_patient_reference(resource)

        assert ref is None

    def test_get_patient_reference_medication_request(self) -> None:
        """Test getting patient reference from MedicationRequest."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "MedicationRequest",
            "subject": {"reference": "Patient/med-patient"},
        }

        ref = ds._get_patient_reference(resource)

        assert ref == "Patient/med-patient"

    def test_get_patient_reference_encounter(self) -> None:
        """Test getting patient reference from Encounter."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "Encounter",
            "subject": {"reference": "Patient/enc-patient"},
        }

        ref = ds._get_patient_reference(resource)

        assert ref == "Patient/enc-patient"

    def test_get_patient_reference_immunization(self) -> None:
        """Test getting patient reference from Immunization."""
        ds = InMemoryDataSource()
        resource = {
            "resourceType": "Immunization",
            "patient": {"reference": "Patient/imm-patient"},
        }

        ref = ds._get_patient_reference(resource)

        assert ref == "Patient/imm-patient"


class TestMedicationRequestRetrieval:
    """Tests for MedicationRequest retrieval with patient context."""

    def test_retrieve_medication_request_by_type(self) -> None:
        """Test retrieving MedicationRequest by resource type."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {
                    "resourceType": "MedicationRequest",
                    "id": "mr1",
                    "status": "active",
                    "intent": "order",
                    "medicationCodeableConcept": {
                        "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "860975"}]
                    },
                    "subject": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "MedicationRequest",
                    "id": "mr2",
                    "status": "completed",
                    "intent": "order",
                    "subject": {"reference": "Patient/p1"},
                },
            ]
        )

        requests = ds.retrieve("MedicationRequest")

        assert len(requests) == 2

    def test_retrieve_medication_request_with_patient_context(self) -> None:
        """Test retrieving MedicationRequest filtered by patient context."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {"resourceType": "Patient", "id": "p2"},
                {
                    "resourceType": "MedicationRequest",
                    "id": "mr1",
                    "status": "active",
                    "subject": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "MedicationRequest",
                    "id": "mr2",
                    "status": "active",
                    "subject": {"reference": "Patient/p2"},
                },
            ]
        )

        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})
        requests = ds.retrieve("MedicationRequest", context=context)

        assert len(requests) == 1
        assert requests[0]["id"] == "mr1"

    def test_medication_request_with_cql_evaluator(self) -> None:
        """Test MedicationRequest retrieval via CQL evaluator."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {
                    "resourceType": "MedicationRequest",
                    "id": "mr1",
                    "status": "active",
                    "intent": "order",
                    "subject": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "MedicationRequest",
                    "id": "mr2",
                    "status": "completed",
                    "intent": "order",
                    "subject": {"reference": "Patient/p1"},
                },
            ]
        )

        evaluator = CQLEvaluator(data_source=ds)
        evaluator.compile("""
            library MedTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define AllMedications: [MedicationRequest]
            define ActiveMedications: [MedicationRequest] M where M.status = 'active'
            define ActiveCount: Count(AllMedications M where M.status = 'active')
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        all_meds = evaluator.evaluate_definition("AllMedications", resource=patient)
        active_meds = evaluator.evaluate_definition("ActiveMedications", resource=patient)
        active_count = evaluator.evaluate_definition("ActiveCount", resource=patient)

        assert len(all_meds) == 2
        assert len(active_meds) == 1
        # Single-source queries return items directly, not wrapped in alias
        assert active_meds[0]["status"] == "active"
        assert active_count == 1


class TestEncounterRetrieval:
    """Tests for Encounter retrieval with patient context."""

    def test_retrieve_encounter_by_type(self) -> None:
        """Test retrieving Encounter by resource type."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {
                    "resourceType": "Encounter",
                    "id": "e1",
                    "status": "finished",
                    "class": {"code": "IMP"},
                    "subject": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "Encounter",
                    "id": "e2",
                    "status": "in-progress",
                    "class": {"code": "AMB"},
                    "subject": {"reference": "Patient/p1"},
                },
            ]
        )

        encounters = ds.retrieve("Encounter")

        assert len(encounters) == 2

    def test_retrieve_encounter_with_patient_context(self) -> None:
        """Test retrieving Encounter filtered by patient context."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {"resourceType": "Patient", "id": "p2"},
                {
                    "resourceType": "Encounter",
                    "id": "e1",
                    "status": "finished",
                    "subject": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "Encounter",
                    "id": "e2",
                    "status": "finished",
                    "subject": {"reference": "Patient/p2"},
                },
            ]
        )

        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})
        encounters = ds.retrieve("Encounter", context=context)

        assert len(encounters) == 1
        assert encounters[0]["id"] == "e1"

    def test_encounter_with_cql_evaluator(self) -> None:
        """Test Encounter retrieval via CQL evaluator."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {
                    "resourceType": "Encounter",
                    "id": "e1",
                    "status": "finished",
                    "class": {"code": "IMP"},
                    "subject": {"reference": "Patient/p1"},
                    "period": {"start": "2024-01-01", "end": "2024-01-05"},
                },
                {
                    "resourceType": "Encounter",
                    "id": "e2",
                    "status": "in-progress",
                    "class": {"code": "AMB"},
                    "subject": {"reference": "Patient/p1"},
                },
            ]
        )

        evaluator = CQLEvaluator(data_source=ds)
        evaluator.compile("""
            library EncTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define AllEncounters: [Encounter]
            define FinishedEncounters: [Encounter] E where E.status = 'finished'
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        all_enc = evaluator.evaluate_definition("AllEncounters", resource=patient)
        finished = evaluator.evaluate_definition("FinishedEncounters", resource=patient)

        assert len(all_enc) == 2
        assert len(finished) == 1


class TestAllergyIntoleranceRetrieval:
    """Tests for AllergyIntolerance retrieval with patient context."""

    def test_retrieve_allergy_by_type(self) -> None:
        """Test retrieving AllergyIntolerance by resource type."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {
                    "resourceType": "AllergyIntolerance",
                    "id": "a1",
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{"display": "Penicillin"}]},
                    "patient": {"reference": "Patient/p1"},
                },
            ]
        )

        allergies = ds.retrieve("AllergyIntolerance")

        assert len(allergies) == 1

    def test_retrieve_allergy_with_patient_context(self) -> None:
        """Test retrieving AllergyIntolerance filtered by patient context."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {"resourceType": "Patient", "id": "p2"},
                {
                    "resourceType": "AllergyIntolerance",
                    "id": "a1",
                    "patient": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "AllergyIntolerance",
                    "id": "a2",
                    "patient": {"reference": "Patient/p2"},
                },
            ]
        )

        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})
        allergies = ds.retrieve("AllergyIntolerance", context=context)

        assert len(allergies) == 1
        assert allergies[0]["id"] == "a1"

    def test_allergy_with_cql_evaluator(self) -> None:
        """Test AllergyIntolerance retrieval via CQL evaluator."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {
                    "resourceType": "AllergyIntolerance",
                    "id": "a1",
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{"display": "Penicillin"}]},
                    "patient": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "AllergyIntolerance",
                    "id": "a2",
                    "clinicalStatus": {"coding": [{"code": "resolved"}]},
                    "code": {"coding": [{"display": "Aspirin"}]},
                    "patient": {"reference": "Patient/p1"},
                },
            ]
        )

        evaluator = CQLEvaluator(data_source=ds)
        evaluator.compile("""
            library AllergyTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define AllAllergies: [AllergyIntolerance]
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        allergies = evaluator.evaluate_definition("AllAllergies", resource=patient)

        assert len(allergies) == 2


class TestImmunizationRetrieval:
    """Tests for Immunization retrieval with patient context."""

    def test_retrieve_immunization_with_patient_context(self) -> None:
        """Test retrieving Immunization filtered by patient context."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {"resourceType": "Patient", "id": "p2"},
                {
                    "resourceType": "Immunization",
                    "id": "i1",
                    "status": "completed",
                    "vaccineCode": {"coding": [{"display": "Influenza"}]},
                    "patient": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "Immunization",
                    "id": "i2",
                    "status": "completed",
                    "vaccineCode": {"coding": [{"display": "COVID-19"}]},
                    "patient": {"reference": "Patient/p2"},
                },
            ]
        )

        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})
        immunizations = ds.retrieve("Immunization", context=context)

        assert len(immunizations) == 1
        assert immunizations[0]["id"] == "i1"

    def test_immunization_with_cql_evaluator(self) -> None:
        """Test Immunization retrieval via CQL evaluator."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {
                    "resourceType": "Immunization",
                    "id": "i1",
                    "status": "completed",
                    "vaccineCode": {"coding": [{"display": "Influenza"}]},
                    "patient": {"reference": "Patient/p1"},
                    "occurrenceDateTime": "2024-10-01",
                },
            ]
        )

        evaluator = CQLEvaluator(data_source=ds)
        evaluator.compile("""
            library ImmTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define AllImmunizations: [Immunization]
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        immunizations = evaluator.evaluate_definition("AllImmunizations", resource=patient)

        assert len(immunizations) == 1
        assert immunizations[0]["vaccineCode"]["coding"][0]["display"] == "Influenza"


class TestProcedureRetrieval:
    """Tests for Procedure retrieval with patient context."""

    def test_retrieve_procedure_with_patient_context(self) -> None:
        """Test retrieving Procedure filtered by patient context."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {
                    "resourceType": "Procedure",
                    "id": "proc1",
                    "status": "completed",
                    "code": {"coding": [{"display": "Appendectomy"}]},
                    "subject": {"reference": "Patient/p1"},
                },
                {
                    "resourceType": "Procedure",
                    "id": "proc2",
                    "status": "completed",
                    "subject": {"reference": "Patient/p2"},
                },
            ]
        )

        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})
        procedures = ds.retrieve("Procedure", context=context)

        assert len(procedures) == 1
        assert procedures[0]["id"] == "proc1"

    def test_procedure_with_cql_evaluator(self) -> None:
        """Test Procedure retrieval via CQL evaluator."""
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1"},
                {
                    "resourceType": "Procedure",
                    "id": "proc1",
                    "status": "completed",
                    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "80146002"}]},
                    "subject": {"reference": "Patient/p1"},
                },
            ]
        )

        evaluator = CQLEvaluator(data_source=ds)
        evaluator.compile("""
            library ProcTest version '1.0'
            using FHIR version '4.0.1'

            context Patient

            define AllProcedures: [Procedure]
            define CompletedProcedures: [Procedure] P where P.status = 'completed'
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        all_procs = evaluator.evaluate_definition("AllProcedures", resource=patient)
        completed = evaluator.evaluate_definition("CompletedProcedures", resource=patient)

        assert len(all_procs) == 1
        assert len(completed) == 1


class TestWireDateStringsInRetrieveFilters:
    """A `where` clause compares a FHIR date element, which the wire delivers as a JSON string."""

    @staticmethod
    def _patients() -> InMemoryDataSource:
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {"resourceType": "Patient", "id": "p1", "birthDate": "1975-03-04"},
                {"resourceType": "Patient", "id": "p2", "birthDate": "1991-08-20"},
            ]
        )
        return ds

    @staticmethod
    def _observations() -> InMemoryDataSource:
        ds = InMemoryDataSource()
        ds.add_resources(
            [
                {
                    "resourceType": "Observation",
                    "id": "o1",
                    "status": "final",
                    "effectiveDateTime": "2024-03-04T10:00:00Z",
                },
                {
                    "resourceType": "Observation",
                    "id": "o2",
                    "status": "final",
                    "effectiveDateTime": "2019-01-02T10:00:00Z",
                },
            ]
        )
        return ds

    def test_birth_date_orders_against_a_date_literal(self) -> None:
        evaluator = CQLEvaluator(data_source=self._patients())
        result = evaluator.evaluate_expression("[Patient] P where P.birthDate < @1980-01-01")
        assert [patient["id"] for patient in result] == ["p1"]

    def test_explicit_to_date_answers_the_same(self) -> None:
        evaluator = CQLEvaluator(data_source=self._patients())
        result = evaluator.evaluate_expression("[Patient] P where ToDate(P.birthDate) < @1980-01-01")
        assert [patient["id"] for patient in result] == ["p1"]

    def test_a_non_temporal_element_refuses(self) -> None:
        evaluator = CQLEvaluator(data_source=self._patients())
        with pytest.raises(CQLError, match="not a date, dateTime, or time"):
            evaluator.evaluate_expression("[Patient] P where P.id < @1980-01-01")

    def test_choice_element_falls_during_an_interval(self) -> None:
        evaluator = CQLEvaluator(data_source=self._observations())
        result = evaluator.evaluate_expression(
            "[Observation] O where O.effective during Interval[@2020-01-01, @2025-01-01]"
        )
        assert [observation["id"] for observation in result] == ["o1"]

    def test_named_choice_type_falls_during_an_interval(self) -> None:
        evaluator = CQLEvaluator(data_source=self._observations())
        result = evaluator.evaluate_expression(
            "[Observation] O where O.effectiveDateTime during Interval[@2020-01-01, @2025-01-01]"
        )
        assert [observation["id"] for observation in result] == ["o1"]

    def test_a_non_temporal_element_in_during_refuses_rather_than_answering_empty(self) -> None:
        evaluator = CQLEvaluator(data_source=self._observations())
        with pytest.raises(CQLError, match="not a date, dateTime, or time"):
            evaluator.evaluate_expression("[Observation] O where O.status during Interval[@2020-01-01, @2025-01-01]")

    def test_a_choice_element_written_as_a_period_answers_the_period(self) -> None:
        ds = InMemoryDataSource()
        ds.add_resource(
            {
                "resourceType": "Observation",
                "id": "o3",
                "effectivePeriod": {"start": "2024-01-01", "end": "2024-01-31"},
            }
        )
        evaluator = CQLEvaluator(data_source=ds)
        result = evaluator.evaluate_expression("[Observation] O return O.effective")
        assert result == [{"start": "2024-01-01", "end": "2024-01-31"}]

    def test_a_name_that_only_prefixes_another_element_stays_null(self) -> None:
        ds = InMemoryDataSource()
        ds.add_resource(
            {
                "resourceType": "Observation",
                "id": "o4",
                "referenceRange": [{"text": "normal"}],
                "linkId": "q1",
            }
        )
        evaluator = CQLEvaluator(data_source=ds)
        assert evaluator.evaluate_expression("[Observation] O return O.reference") == [None]
        assert evaluator.evaluate_expression("[Observation] O return O.link") == [None]
