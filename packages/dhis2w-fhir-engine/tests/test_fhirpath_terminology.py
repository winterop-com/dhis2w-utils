"""Tests for FHIRPath terminology functions (memberOf, subsumes, subsumedBy)."""

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.fhir import (
    _extract_code_system,
    _get_subsumes_outcome,
    fn_member_of,
    fn_subsumed_by,
    fn_subsumes,
)


class MockTerminologyProvider:
    """Mock terminology provider for testing."""

    def __init__(self) -> None:
        # Define ValueSet memberships: valueset_url -> set of (code, system)
        self.valuesets: dict[str, set[tuple[str, str]]] = {
            "http://example.org/vs/gender": {
                ("male", "http://hl7.org/fhir/administrative-gender"),
                ("female", "http://hl7.org/fhir/administrative-gender"),
                ("other", "http://hl7.org/fhir/administrative-gender"),
            },
            "http://example.org/vs/diabetes": {
                ("E11", "http://hl7.org/fhir/sid/icd-10"),
                ("E11.9", "http://hl7.org/fhir/sid/icd-10"),
                ("73211009", "http://snomed.info/sct"),  # Diabetes mellitus
            },
        }
        # Define subsumption: (system, parent_code) -> set of child codes
        self.hierarchy: dict[tuple[str, str], set[str]] = {
            ("http://snomed.info/sct", "73211009"): {"46635009", "44054006"},  # Diabetes subtypes
            ("http://hl7.org/fhir/sid/icd-10", "E11"): {"E11.0", "E11.1", "E11.9"},
        }

    def member_of(self, valueset_url: str, code: str, system: str) -> bool:
        """Check if code is member of valueset."""
        vs = self.valuesets.get(valueset_url, set())
        # Check with system
        if (code, system) in vs:
            return True
        # Check without system if system is empty
        if system == "":
            for c, _ in vs:
                if c == code:
                    return True
        return False

    def subsumes(
        self,
        system: str,
        code_a: str,
        code_b: str,
        version: str | None = None,
    ) -> dict:
        """Check subsumption relationship."""
        # Equivalent
        if code_a == code_b:
            return {"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": "equivalent"}]}

        # Check if code_a subsumes code_b (code_a is parent)
        children = self.hierarchy.get((system, code_a), set())
        if code_b in children:
            return {"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": "subsumes"}]}

        # Check if code_a is subsumed by code_b (code_b is parent)
        children = self.hierarchy.get((system, code_b), set())
        if code_a in children:
            return {"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": "subsumed-by"}]}

        return {"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": "not-subsumed"}]}


class TestExtractCodeSystem:
    """Tests for _extract_code_system helper."""

    def test_string_code(self) -> None:
        """Plain string should return code with no system."""
        code, system = _extract_code_system("E11")
        assert code == "E11"
        assert system is None

    def test_coding(self) -> None:
        """Coding dict should extract code and system."""
        coding = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        code, system = _extract_code_system(coding)
        assert code == "E11"
        assert system == "http://hl7.org/fhir/sid/icd-10"

    def test_codeable_concept(self) -> None:
        """CodeableConcept should use first coding."""
        cc = {
            "coding": [
                {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"},
                {"code": "73211009", "system": "http://snomed.info/sct"},
            ],
            "text": "Diabetes",
        }
        code, system = _extract_code_system(cc)
        assert code == "E11"
        assert system == "http://hl7.org/fhir/sid/icd-10"

    def test_empty_codeable_concept(self) -> None:
        """Empty CodeableConcept should return None."""
        cc = {"coding": [], "text": "Unknown"}
        code, system = _extract_code_system(cc)
        assert code is None
        assert system is None

    def test_none_input(self) -> None:
        """None input should return None."""
        code, system = _extract_code_system(None)
        assert code is None
        assert system is None


class TestGetSubsumesOutcome:
    """Tests for _get_subsumes_outcome helper."""

    def test_valid_parameters(self) -> None:
        """Should extract outcome from valid Parameters."""
        params = {
            "resourceType": "Parameters",
            "parameter": [{"name": "outcome", "valueCode": "subsumes"}],
        }
        assert _get_subsumes_outcome(params) == "subsumes"

    def test_multiple_parameters(self) -> None:
        """Should find outcome among multiple parameters."""
        params = {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "message", "valueString": "Found"},
                {"name": "outcome", "valueCode": "equivalent"},
            ],
        }
        assert _get_subsumes_outcome(params) == "equivalent"

    def test_no_outcome(self) -> None:
        """Should return None if no outcome parameter."""
        params = {"resourceType": "Parameters", "parameter": []}
        assert _get_subsumes_outcome(params) is None

    def test_invalid_input(self) -> None:
        """Should return None for invalid input."""
        assert _get_subsumes_outcome(None) is None
        assert _get_subsumes_outcome("invalid") is None
        assert _get_subsumes_outcome({}) is None


class TestMemberOf:
    """Tests for memberOf function."""

    def test_no_provider(self) -> None:
        """Should return empty when no terminology provider."""
        ctx = EvaluationContext()
        result = fn_member_of(ctx, [{"code": "male"}], "http://example.org/vs/gender")
        assert result == []

    def test_coding_is_member(self) -> None:
        """Should return True when coding is in valueset."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        coding = {"code": "male", "system": "http://hl7.org/fhir/administrative-gender"}
        result = fn_member_of(ctx, [coding], "http://example.org/vs/gender")
        assert result == [True]

    def test_coding_not_member(self) -> None:
        """Should return False when coding is not in valueset."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        coding = {"code": "unknown", "system": "http://hl7.org/fhir/administrative-gender"}
        result = fn_member_of(ctx, [coding], "http://example.org/vs/gender")
        assert result == [False]

    def test_codeable_concept(self) -> None:
        """Should check first coding of CodeableConcept."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        cc = {
            "coding": [{"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}],
            "text": "Diabetes",
        }
        result = fn_member_of(ctx, [cc], "http://example.org/vs/diabetes")
        assert result == [True]

    def test_multiple_items(self) -> None:
        """Should check each item in collection."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        codings = [
            {"code": "male", "system": "http://hl7.org/fhir/administrative-gender"},
            {"code": "unknown", "system": "http://hl7.org/fhir/administrative-gender"},
            {"code": "female", "system": "http://hl7.org/fhir/administrative-gender"},
        ]
        result = fn_member_of(ctx, codings, "http://example.org/vs/gender")
        assert result == [True, False, True]


class TestSubsumes:
    """Tests for subsumes function."""

    def test_no_provider(self) -> None:
        """Should return empty when no terminology provider."""
        ctx = EvaluationContext()
        result = fn_subsumes(ctx, [{"code": "E11"}], {"code": "E11.9"})
        assert result == []

    def test_equivalent_codes(self) -> None:
        """Same code should return True (equivalent subsumes)."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        parent = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        child = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumes(ctx, [parent], child)
        assert result == [True]

    def test_parent_subsumes_child(self) -> None:
        """Parent code should subsume child."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        parent = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        child = {"code": "E11.9", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumes(ctx, [parent], child)
        assert result == [True]

    def test_child_does_not_subsume_parent(self) -> None:
        """Child code should not subsume parent."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        child = {"code": "E11.9", "system": "http://hl7.org/fhir/sid/icd-10"}
        parent = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumes(ctx, [child], parent)
        assert result == [False]

    def test_unrelated_codes(self) -> None:
        """Unrelated codes should return False."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        code1 = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        code2 = {"code": "J18", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumes(ctx, [code1], code2)
        assert result == [False]


class TestSubsumedBy:
    """Tests for subsumedBy function."""

    def test_no_provider(self) -> None:
        """Should return empty when no terminology provider."""
        ctx = EvaluationContext()
        result = fn_subsumed_by(ctx, [{"code": "E11.9"}], {"code": "E11"})
        assert result == []

    def test_equivalent_codes(self) -> None:
        """Same code should return True (equivalent is subsumed by itself)."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        code = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumed_by(ctx, [code], code)
        assert result == [True]

    def test_child_subsumed_by_parent(self) -> None:
        """Child code should be subsumed by parent."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        child = {"code": "E11.9", "system": "http://hl7.org/fhir/sid/icd-10"}
        parent = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumed_by(ctx, [child], parent)
        assert result == [True]

    def test_parent_not_subsumed_by_child(self) -> None:
        """Parent code should not be subsumed by child."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        parent = {"code": "E11", "system": "http://hl7.org/fhir/sid/icd-10"}
        child = {"code": "E11.9", "system": "http://hl7.org/fhir/sid/icd-10"}
        result = fn_subsumed_by(ctx, [parent], child)
        assert result == [False]

    def test_snomed_hierarchy(self) -> None:
        """Should work with SNOMED codes."""
        ctx = EvaluationContext(terminology_provider=MockTerminologyProvider())
        # 46635009 is a subtype of 73211009 (Diabetes mellitus)
        child = {"code": "46635009", "system": "http://snomed.info/sct"}
        parent = {"code": "73211009", "system": "http://snomed.info/sct"}
        result = fn_subsumed_by(ctx, [child], parent)
        assert result == [True]
