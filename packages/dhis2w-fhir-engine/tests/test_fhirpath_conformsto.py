"""Tests for FHIRPath conformsTo function."""

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.fhir import fn_conforms_to


class TestConformsTo:
    """Test conformsTo function."""

    def test_resource_with_profile_in_meta(self) -> None:
        """Test resource that declares profile in meta."""
        patient = {
            "resourceType": "Patient",
            "id": "123",
            "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
        }
        ctx = EvaluationContext(resource=patient)

        result = fn_conforms_to(ctx, [patient], "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient")
        assert result == [True]

    def test_resource_without_profile(self) -> None:
        """Test resource without meta.profile checks base type."""
        patient = {
            "resourceType": "Patient",
            "id": "123",
        }
        ctx = EvaluationContext(resource=patient)

        # Should match base Patient profile
        result = fn_conforms_to(ctx, [patient], "http://hl7.org/fhir/StructureDefinition/Patient")
        assert result == [True]

    def test_resource_wrong_type(self) -> None:
        """Test resource doesn't conform to different type's profile."""
        patient = {
            "resourceType": "Patient",
            "id": "123",
        }
        ctx = EvaluationContext(resource=patient)

        # Patient shouldn't conform to Observation profile
        result = fn_conforms_to(ctx, [patient], "http://hl7.org/fhir/StructureDefinition/Observation")
        assert result == [False]

    def test_multiple_resources(self) -> None:
        """Test conformsTo with multiple resources."""
        patient = {
            "resourceType": "Patient",
            "id": "1",
            "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
        }
        observation = {
            "resourceType": "Observation",
            "id": "2",
        }
        ctx = EvaluationContext()

        # Check Patient profile
        result = fn_conforms_to(
            ctx, [patient, observation], "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
        )
        assert result == [True, False]

    def test_profile_with_version(self) -> None:
        """Test profile matching with version."""
        patient = {
            "resourceType": "Patient",
            "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient|4.0.0"]},
        }
        ctx = EvaluationContext(resource=patient)

        # Should match version-independent
        result = fn_conforms_to(ctx, [patient], "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient")
        assert result == [True]

        # Should match exact version
        result = fn_conforms_to(ctx, [patient], "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient|4.0.0")
        assert result == [True]

    def test_non_dict_returns_false(self) -> None:
        """Test non-dict input returns false."""
        ctx = EvaluationContext()

        result = fn_conforms_to(ctx, ["not a resource", 123, None], "http://hl7.org/fhir/StructureDefinition/Patient")
        assert result == [False, False, False]

    def test_empty_collection(self) -> None:
        """Test empty collection returns empty result."""
        ctx = EvaluationContext()

        result = fn_conforms_to(ctx, [], "http://hl7.org/fhir/StructureDefinition/Patient")
        assert result == []

    def test_resource_without_resource_type(self) -> None:
        """Test dict without resourceType returns false."""
        data = {"id": "123", "name": "Test"}
        ctx = EvaluationContext()

        result = fn_conforms_to(ctx, [data], "http://hl7.org/fhir/StructureDefinition/Patient")
        assert result == [False]

    def test_multiple_declared_profiles(self) -> None:
        """Test resource with multiple declared profiles."""
        patient = {
            "resourceType": "Patient",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/StructureDefinition/Patient",
                    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient",
                    "http://example.org/fhir/StructureDefinition/my-patient",
                ]
            },
        }
        ctx = EvaluationContext(resource=patient)

        # Should match any declared profile
        result = fn_conforms_to(ctx, [patient], "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient")
        assert result == [True]

        result = fn_conforms_to(ctx, [patient], "http://example.org/fhir/StructureDefinition/my-patient")
        assert result == [True]

    def test_common_base_profiles(self) -> None:
        """Test conformance to common base profiles."""
        resources = [
            {"resourceType": "Observation", "id": "1"},
            {"resourceType": "Condition", "id": "2"},
            {"resourceType": "Procedure", "id": "3"},
            {"resourceType": "Encounter", "id": "4"},
            {"resourceType": "MedicationRequest", "id": "5"},
        ]
        ctx = EvaluationContext()

        for resource in resources:
            resource_type = resource["resourceType"]
            profile = f"http://hl7.org/fhir/StructureDefinition/{resource_type}"
            result = fn_conforms_to(ctx, [resource], profile)
            assert result == [True], f"{resource_type} should conform to its base profile"
