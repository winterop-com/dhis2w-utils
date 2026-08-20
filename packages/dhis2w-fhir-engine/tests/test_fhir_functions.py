"""Tests for FHIR-specific functions."""

from typing import Any

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.fhir import (
    fn_check_modifiers,
    fn_conforms_to,
    fn_element_definition,
    fn_extension,
    fn_html_checks,
    fn_member_of,
    fn_resolve,
    fn_slice,
    fn_subsumed_by,
    fn_subsumes,
)


class TestResolve:
    """Tests for resolve function."""

    def test_resolve_without_resolver_returns_empty(self) -> None:
        """Test resolve returns empty when no resolver configured."""
        ctx = EvaluationContext()
        refs = [{"reference": "Patient/123"}]
        result = fn_resolve(ctx, refs)
        assert result == []

    def test_resolve_with_resolver(self) -> Any:
        """Test resolve with resolver callback."""
        patient = {"resourceType": "Patient", "id": "123", "name": [{"family": "Smith"}]}

        def resolver(ref: str) -> dict[str, Any] | None:
            if ref == "Patient/123":
                return patient
            return None

        ctx = EvaluationContext(reference_resolver=resolver)
        refs = [{"reference": "Patient/123"}]
        result = fn_resolve(ctx, refs)
        assert result == [patient]

    def test_resolve_string_reference(self) -> Any:
        """Test resolve with string reference."""
        patient = {"resourceType": "Patient", "id": "123"}

        def resolver(ref: str) -> dict[str, Any] | None:
            if ref == "Patient/123":
                return patient
            return None

        ctx = EvaluationContext(reference_resolver=resolver)
        refs = ["Patient/123"]
        result = fn_resolve(ctx, refs)
        assert result == [patient]

    def test_resolve_multiple_references(self) -> Any:
        """Test resolve with multiple references."""
        patient = {"resourceType": "Patient", "id": "123"}
        obs = {"resourceType": "Observation", "id": "456"}

        def resolver(ref: str) -> dict[str, Any] | None:
            if ref == "Patient/123":
                return patient
            if ref == "Observation/456":
                return obs
            return None

        ctx = EvaluationContext(reference_resolver=resolver)
        refs = [{"reference": "Patient/123"}, {"reference": "Observation/456"}]
        result = fn_resolve(ctx, refs)
        assert result == [patient, obs]

    def test_resolve_unresolvable_returns_empty(self) -> Any:
        """Test resolve with unresolvable reference."""

        def resolver(ref: str) -> dict[str, Any] | None:
            return None

        ctx = EvaluationContext(reference_resolver=resolver)
        refs = [{"reference": "Patient/unknown"}]
        result = fn_resolve(ctx, refs)
        assert result == []

    def test_resolve_non_dict_non_string_ignored(self) -> Any:
        """Test resolve ignores non-dict, non-string items."""

        def resolver(ref: str) -> dict[str, Any] | None:
            return {"id": "test"}

        ctx = EvaluationContext(reference_resolver=resolver)
        result = fn_resolve(ctx, [123, None, True])
        assert result == []


class TestExtension:
    """Tests for extension function."""

    def test_extension_finds_matching_url(self) -> None:
        """Test extension finds extensions with matching URL."""
        resource = {
            "resourceType": "Patient",
            "extension": [
                {"url": "http://example.org/ext1", "valueString": "value1"},
                {"url": "http://example.org/ext2", "valueString": "value2"},
            ],
        }
        ctx = EvaluationContext()
        result = fn_extension(ctx, [resource], "http://example.org/ext1")
        assert len(result) == 1
        assert result[0]["valueString"] == "value1"

    def test_extension_no_match(self) -> None:
        """Test extension returns empty when no match."""
        resource = {"extension": [{"url": "http://example.org/ext1", "valueString": "value1"}]}
        ctx = EvaluationContext()
        result = fn_extension(ctx, [resource], "http://example.org/other")
        assert result == []

    def test_extension_no_extensions(self) -> None:
        """Test extension on resource without extensions."""
        resource = {"resourceType": "Patient"}
        ctx = EvaluationContext()
        result = fn_extension(ctx, [resource], "http://example.org/ext1")
        assert result == []

    def test_extension_non_dict_item(self) -> None:
        """Test extension ignores non-dict items."""
        ctx = EvaluationContext()
        result = fn_extension(ctx, ["string", 123], "http://example.org/ext")
        assert result == []

    def test_extension_multiple_resources(self) -> None:
        """Test extension on multiple resources."""
        resources = [
            {"extension": [{"url": "http://example.org/ext", "valueString": "a"}]},
            {"extension": [{"url": "http://example.org/ext", "valueString": "b"}]},
        ]
        ctx = EvaluationContext()
        result = fn_extension(ctx, resources, "http://example.org/ext")
        assert len(result) == 2

    def test_extension_non_list_extensions(self) -> None:
        """Test extension handles non-list extension property."""
        resource = {"extension": "not a list"}
        ctx = EvaluationContext()
        result = fn_extension(ctx, [resource], "http://example.org/ext")
        assert result == []


class TestCheckModifiers:
    """Tests for checkModifiers function."""

    def test_check_modifiers_allowed(self) -> None:
        """Test checkModifiers with allowed modifier extensions."""
        resource = {"modifierExtension": [{"url": "http://example.org/allowed"}]}
        ctx = EvaluationContext()
        result = fn_check_modifiers(ctx, [resource], "http://example.org/allowed")
        assert result == [resource]

    def test_check_modifiers_no_modifiers(self) -> None:
        """Test checkModifiers on resource without modifier extensions."""
        resource = {"resourceType": "Patient"}
        ctx = EvaluationContext()
        result = fn_check_modifiers(ctx, [resource])
        assert result == [resource]

    def test_check_modifiers_non_dict_item(self) -> None:
        """Test checkModifiers with non-dict items."""
        ctx = EvaluationContext()
        result = fn_check_modifiers(ctx, ["string", 123])
        assert result == ["string", 123]

    def test_check_modifiers_disallowed(self) -> None:
        """Test checkModifiers with disallowed modifier (returns collection for now)."""
        resource = {"modifierExtension": [{"url": "http://example.org/disallowed"}]}
        ctx = EvaluationContext()
        # Currently just passes through, doesn't raise error
        result = fn_check_modifiers(ctx, [resource], "http://example.org/other")
        assert result == [resource]

    def test_check_modifiers_non_list_modifier_extension(self) -> None:
        """Test checkModifiers with non-list modifierExtension."""
        resource = {"modifierExtension": "not a list"}
        ctx = EvaluationContext()
        result = fn_check_modifiers(ctx, [resource])
        assert result == [resource]

    def test_check_modifiers_non_dict_extension(self) -> None:
        """Test checkModifiers with non-dict items in modifierExtension list."""
        resource = {"modifierExtension": ["string", 123]}
        ctx = EvaluationContext()
        result = fn_check_modifiers(ctx, [resource])
        assert result == [resource]


class TestHtmlChecks:
    """Tests for htmlChecks function."""

    def test_html_checks_valid_div(self) -> None:
        """Test htmlChecks with valid div."""
        narrative = {"div": "<div>Some content</div>"}
        ctx = EvaluationContext()
        result = fn_html_checks(ctx, [narrative])
        assert result == [True]

    def test_html_checks_invalid_div(self) -> None:
        """Test htmlChecks with invalid div."""
        narrative = {"div": "<p>Not a div</p>"}
        ctx = EvaluationContext()
        result = fn_html_checks(ctx, [narrative])
        assert result == [False]

    def test_html_checks_no_div(self) -> None:
        """Test htmlChecks without div property."""
        narrative = {"status": "generated"}
        ctx = EvaluationContext()
        result = fn_html_checks(ctx, [narrative])
        assert result == [True]

    def test_html_checks_non_string_div(self) -> None:
        """Test htmlChecks with non-string div."""
        narrative = {"div": 123}
        ctx = EvaluationContext()
        result = fn_html_checks(ctx, [narrative])
        assert result == [True]

    def test_html_checks_non_dict_item(self) -> None:
        """Test htmlChecks with non-dict items."""
        ctx = EvaluationContext()
        result = fn_html_checks(ctx, ["string"])
        assert result == [True]

    def test_html_checks_whitespace_before_div(self) -> None:
        """Test htmlChecks with whitespace before div tag."""
        narrative = {"div": "  \n<div>Content</div>"}
        ctx = EvaluationContext()
        result = fn_html_checks(ctx, [narrative])
        assert result == [True]


class TestUnimplementedFunctions:
    """Tests for unimplemented functions that return empty."""

    def test_element_definition_returns_empty(self) -> None:
        """Test elementDefinition returns empty."""
        ctx = EvaluationContext()
        result = fn_element_definition(ctx, [{"resourceType": "Patient"}])
        assert result == []

    def test_slice_returns_empty(self) -> None:
        """Test slice returns empty."""
        ctx = EvaluationContext()
        result = fn_slice(ctx, [{"resourceType": "Patient"}], "profile", "slice-name")
        assert result == []

    def test_conforms_to_basic(self) -> None:
        """Test conformsTo basic functionality."""
        ctx = EvaluationContext()
        # Resource without matching profile should return False
        result = fn_conforms_to(ctx, [{"resourceType": "Patient"}], "http://example.org/custom-profile")
        assert result == [False]
        # Resource should conform to its base type profile
        result = fn_conforms_to(ctx, [{"resourceType": "Patient"}], "http://hl7.org/fhir/StructureDefinition/Patient")
        assert result == [True]

    def test_member_of_returns_empty(self) -> None:
        """Test memberOf returns empty."""
        ctx = EvaluationContext()
        result = fn_member_of(ctx, [{"code": "123"}], "http://example.org/valueset")
        assert result == []

    def test_subsumes_returns_empty(self) -> None:
        """Test subsumes returns empty."""
        ctx = EvaluationContext()
        result = fn_subsumes(ctx, [{"code": "123"}], {"code": "456"})
        assert result == []

    def test_subsumed_by_returns_empty(self) -> None:
        """Test subsumedBy returns empty."""
        ctx = EvaluationContext()
        result = fn_subsumed_by(ctx, [{"code": "123"}], {"code": "456"})
        assert result == []
