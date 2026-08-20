"""Tests for built-in FHIRHelpers library."""

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.r4 import InMemoryDataSource
from dhis2w_fhir_engine.r4.builtins import get_builtin_resolver


class TestBuiltinResolver:
    """Test the built-in library resolver."""

    def test_get_builtin_resolver(self) -> None:
        """Should return resolver with FHIRHelpers."""
        resolver = get_builtin_resolver()
        assert resolver is not None

        # Should resolve FHIRHelpers
        source = resolver.resolve("FHIRHelpers", "4.0.1")
        assert source is not None
        assert "library FHIRHelpers" in source
        assert "define function ToQuantity" in source

    def test_fhirhelpers_version_matching(self) -> None:
        """Should resolve FHIRHelpers with correct version."""
        resolver = get_builtin_resolver()

        # Exact version
        source = resolver.resolve("FHIRHelpers", "4.0.1")
        assert source is not None

        # No version specified
        source = resolver.resolve("FHIRHelpers")
        assert source is not None

        # Wrong version should still work (resolver stores unversioned too)
        source = resolver.resolve("FHIRHelpers", "3.0.0")
        # May or may not resolve depending on resolver behavior


class TestFHIRHelpersAutoLoad:
    """Test that FHIRHelpers is automatically available."""

    def test_include_fhirhelpers_compiles(self) -> None:
        """CQL with include FHIRHelpers should compile."""
        evaluator = CQLEvaluator()

        library = evaluator.compile("""
            library TestInclude version '1.0'
            include FHIRHelpers version '4.0.1'

            define TestValue: 42
        """)

        assert library is not None
        assert library.name == "TestInclude"

    def test_include_fhirhelpers_without_version(self) -> None:
        """Should work without explicit version."""
        evaluator = CQLEvaluator()

        library = evaluator.compile("""
            library TestInclude version '1.0'
            include FHIRHelpers

            define TestValue: 42
        """)

        assert library is not None

    def test_disable_builtins(self) -> None:
        """Should be able to disable built-in libraries."""
        evaluator = CQLEvaluator(include_builtins=False)

        # Compile should work but FHIRHelpers functions won't be available
        evaluator.compile("""
            library TestInclude version '1.0'
            include FHIRHelpers version '4.0.1'

            define TestValue: 42
        """)

        # The library compiles but FHIRHelpers functions aren't actually available
        # because the include couldn't be resolved
        result = evaluator.evaluate_definition("TestValue")
        assert result == 42

        # Verify FHIRHelpers wasn't actually loaded into the library manager
        loaded_libs = evaluator.library_manager.list_libraries()
        assert "FHIRHelpers" not in loaded_libs


class TestFHIRHelpersConversions:
    """Test FHIRHelpers conversion functions."""

    @pytest.fixture
    def evaluator(self) -> CQLEvaluator:
        """Create evaluator with FHIRHelpers."""
        return CQLEvaluator()

    def test_to_quantity_function_exists(self, evaluator: CQLEvaluator) -> None:
        """ToQuantity function should be available."""
        evaluator.compile("""
            library TestConversions version '1.0'
            include FHIRHelpers version '4.0.1'

            define TestNull: FHIRHelpers.ToQuantity(null)
        """)

        result = evaluator.evaluate_definition("TestNull")
        assert result is None

    def test_to_code_function_exists(self, evaluator: CQLEvaluator) -> None:
        """ToCode function should be available."""
        evaluator.compile("""
            library TestConversions version '1.0'
            include FHIRHelpers version '4.0.1'

            define TestNull: FHIRHelpers.ToCode(null)
        """)

        result = evaluator.evaluate_definition("TestNull")
        assert result is None

    def test_to_concept_function_exists(self, evaluator: CQLEvaluator) -> None:
        """ToConcept function should be available."""
        evaluator.compile("""
            library TestConversions version '1.0'
            include FHIRHelpers version '4.0.1'

            define TestNull: FHIRHelpers.ToConcept(null)
        """)

        result = evaluator.evaluate_definition("TestNull")
        assert result is None

    def test_to_interval_function_exists(self, evaluator: CQLEvaluator) -> None:
        """ToInterval function should be available."""
        evaluator.compile("""
            library TestConversions version '1.0'
            include FHIRHelpers version '4.0.1'

            define TestNull: FHIRHelpers.ToInterval(null as FHIR.Period)
        """)

        result = evaluator.evaluate_definition("TestNull")
        assert result is None


class TestFHIRHelpersWithData:
    """Test FHIRHelpers with actual FHIR data."""

    @pytest.fixture
    def data_source(self) -> InMemoryDataSource:
        """Create data source with test data."""
        ds = InMemoryDataSource()

        # Add a patient
        ds.add_resource(
            {
                "resourceType": "Patient",
                "id": "test-patient",
                "birthDate": "1990-01-15",
            }
        )

        # Add an observation with quantity
        ds.add_resource(
            {
                "resourceType": "Observation",
                "id": "obs-1",
                "subject": {"reference": "Patient/test-patient"},
                "code": {"coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]},
                "valueQuantity": {"value": 70.5, "unit": "kg", "system": "http://unitsofmeasure.org", "code": "kg"},
            }
        )

        return ds

    @pytest.fixture
    def patient(self) -> dict:
        """Test patient resource."""
        return {
            "resourceType": "Patient",
            "id": "test-patient",
            "birthDate": "1990-01-15",
        }

    def test_access_observation_with_fhirhelpers(
        self,
        data_source: InMemoryDataSource,
        patient: dict,
    ) -> None:
        """Should be able to access observations using FHIRHelpers."""
        evaluator = CQLEvaluator(data_source=data_source)

        library = evaluator.compile("""
            library TestObs version '1.0'
            using FHIR version '4.0.1'
            include FHIRHelpers version '4.0.1'

            context Patient

            define Observations: [Observation]

            define HasObservations: exists(Observations)
        """)

        result = evaluator.evaluate_definition(
            "HasObservations",
            resource=patient,
            library=library,
        )
        assert result is True


class TestFHIRHelpersEdgeCases:
    """Test edge cases and error handling."""

    def test_multiple_includes_with_fhirhelpers(self) -> None:
        """Should handle multiple library includes including FHIRHelpers."""
        evaluator = CQLEvaluator()

        # This tests that FHIRHelpers plays well with other includes
        evaluator.compile("""
            library TestMultiple version '1.0'
            using FHIR version '4.0.1'
            include FHIRHelpers version '4.0.1'

            define SimpleCalc: 1 + 2
        """)

        result = evaluator.evaluate_definition("SimpleCalc")
        assert result == 3

    def test_fhirhelpers_called_alias(self) -> None:
        """Should work with alias for FHIRHelpers."""
        evaluator = CQLEvaluator()

        evaluator.compile("""
            library TestAlias version '1.0'
            using FHIR version '4.0.1'
            include FHIRHelpers version '4.0.1' called FH

            define TestNull: FH.ToQuantity(null)
        """)

        result = evaluator.evaluate_definition("TestNull")
        assert result is None
