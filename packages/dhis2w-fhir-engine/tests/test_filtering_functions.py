"""Tests for filtering functions."""

import pytest

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.filtering import (
    fn_of_type,
    fn_repeat,
    fn_select,
    fn_where,
)


class TestOfType:
    """Tests for ofType function."""

    def test_of_type_resource(self) -> None:
        """Test ofType filters by resourceType."""
        ctx = EvaluationContext()
        collection = [
            {"resourceType": "Patient", "id": "1"},
            {"resourceType": "Observation", "id": "2"},
            {"resourceType": "Patient", "id": "3"},
        ]
        result = fn_of_type(ctx, collection, "Patient")
        assert len(result) == 2
        assert all(r["resourceType"] == "Patient" for r in result)

    def test_of_type_string(self) -> None:
        """Test ofType filters strings."""
        ctx = EvaluationContext()
        collection = ["hello", 42, "world", True]
        result = fn_of_type(ctx, collection, "String")
        assert result == ["hello", "world"]

    def test_of_type_boolean(self) -> None:
        """Test ofType filters booleans."""
        ctx = EvaluationContext()
        collection = [True, "hello", False, 42]
        result = fn_of_type(ctx, collection, "Boolean")
        assert result == [True, False]

    def test_of_type_integer(self) -> None:
        """Test ofType filters integers."""
        ctx = EvaluationContext()
        collection = [1, 2.5, "three", 4, True]  # True is bool, not int
        result = fn_of_type(ctx, collection, "Integer")
        assert result == [1, 4]

    def test_of_type_decimal(self) -> None:
        """Test ofType filters decimals (floats)."""
        ctx = EvaluationContext()
        collection = [1.5, 2, "three", 4.0]
        result = fn_of_type(ctx, collection, "Decimal")
        assert result == [1.5, 4.0]

    def test_of_type_no_match(self) -> None:
        """Test ofType with no matches."""
        ctx = EvaluationContext()
        collection = [{"resourceType": "Patient"}]
        result = fn_of_type(ctx, collection, "Observation")
        assert result == []

    def test_of_type_empty_collection(self) -> None:
        """Test ofType with empty collection."""
        ctx = EvaluationContext()
        result = fn_of_type(ctx, [], "Patient")
        assert result == []


class TestVisitorHandledFunctions:
    """Tests for functions that are handled by the visitor."""

    def test_where_raises_not_implemented(self) -> None:
        """Test where raises NotImplementedError (handled by visitor)."""
        ctx = EvaluationContext()
        with pytest.raises(NotImplementedError, match="handled by the visitor"):
            fn_where(ctx, [])

    def test_select_raises_not_implemented(self) -> None:
        """Test select raises NotImplementedError (handled by visitor)."""
        ctx = EvaluationContext()
        with pytest.raises(NotImplementedError, match="handled by the visitor"):
            fn_select(ctx, [])

    def test_repeat_raises_not_implemented(self) -> None:
        """Test repeat raises NotImplementedError (handled by visitor)."""
        ctx = EvaluationContext()
        with pytest.raises(NotImplementedError, match="handled by the visitor"):
            fn_repeat(ctx, [])
