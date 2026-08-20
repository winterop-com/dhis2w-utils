"""Tests for collection and existence function edge cases."""

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.collections import (
    _deep_equals,
    _ensure_list,
    fn_combine,
    fn_distinct,
    fn_exclude,
    fn_flatten,
    fn_intersect,
    fn_is_distinct,
    fn_subset_of,
    fn_superset_of,
    fn_union,
)
from dhis2w_fhir_engine.engine.fhirpath.functions.existence import (
    fn_all,
    fn_all_false,
    fn_all_true,
    fn_any_false,
    fn_any_true,
    fn_has_value,
)


class TestEnsureList:
    """Tests for _ensure_list helper."""

    def test_none_returns_empty(self) -> None:
        """Test None returns empty list."""
        assert _ensure_list(None) == []

    def test_list_returned_as_is(self) -> None:
        """Test list is returned unchanged."""
        lst = [1, 2, 3]
        result = _ensure_list(lst)
        assert result is lst

    def test_singleton_wrapped(self) -> None:
        """Test singleton value is wrapped in list."""
        assert _ensure_list(42) == [42]
        assert _ensure_list("hello") == ["hello"]


class TestDeepEquals:
    """Tests for _deep_equals helper."""

    def test_int_float_comparison(self) -> None:
        """Test int and float comparison."""
        assert _deep_equals(5, 5.0) is True
        assert _deep_equals(5, 6.0) is False

    def test_different_types(self) -> None:
        """Test different non-numeric types."""
        assert _deep_equals(5, "5") is False
        assert _deep_equals([1], {"a": 1}) is False

    def test_dict_comparison(self) -> None:
        """Test dict comparison."""
        assert _deep_equals({"a": 1, "b": 2}, {"a": 1, "b": 2}) is True
        assert _deep_equals({"a": 1}, {"a": 1, "b": 2}) is False
        assert _deep_equals({"a": 1}, {"a": 2}) is False

    def test_nested_dict(self) -> None:
        """Test nested dict comparison."""
        d1 = {"a": {"b": 1}}
        d2 = {"a": {"b": 1}}
        d3 = {"a": {"b": 2}}
        assert _deep_equals(d1, d2) is True
        assert _deep_equals(d1, d3) is False

    def test_list_comparison(self) -> None:
        """Test list comparison."""
        assert _deep_equals([1, 2, 3], [1, 2, 3]) is True
        assert _deep_equals([1, 2], [1, 2, 3]) is False
        assert _deep_equals([1, 2, 3], [1, 2, 4]) is False


class TestCollectionFunctions:
    """Tests for collection functions."""

    def test_union_with_none(self) -> None:
        """Test union with None right side."""
        ctx = EvaluationContext()
        result = fn_union(ctx, [1, 2], None)
        assert result == [1, 2]

    def test_union_with_singleton(self) -> None:
        """Test union with singleton value."""
        ctx = EvaluationContext()
        result = fn_union(ctx, [1, 2], 3)
        assert sorted(result) == [1, 2, 3]

    def test_intersect_with_singleton(self) -> None:
        """Test intersect with singleton value."""
        ctx = EvaluationContext()
        result = fn_intersect(ctx, [1, 2, 3], 2)
        assert result == [2]

    def test_exclude_with_singleton(self) -> None:
        """Test exclude with singleton value."""
        ctx = EvaluationContext()
        result = fn_exclude(ctx, [1, 2, 3], 2)
        assert sorted(result) == [1, 3]

    def test_combine_with_singleton(self) -> None:
        """Test combine with singleton value."""
        ctx = EvaluationContext()
        result = fn_combine(ctx, [1, 2], 3)
        assert result == [1, 2, 3]

    def test_flatten_nested_lists(self) -> None:
        """Test flatten with nested lists."""
        ctx = EvaluationContext()
        result = fn_flatten(ctx, [[1, 2], [3, 4], 5])
        assert result == [1, 2, 3, 4, 5]

    def test_subset_of_false(self) -> None:
        """Test subsetOf returns False when not subset."""
        ctx = EvaluationContext()
        result = fn_subset_of(ctx, [1, 2, 5], [1, 2, 3])
        assert result == [False]

    def test_superset_of_false(self) -> None:
        """Test supersetOf returns False when not superset."""
        ctx = EvaluationContext()
        result = fn_superset_of(ctx, [1, 2], [1, 2, 3])
        assert result == [False]

    def test_distinct_with_dicts(self) -> None:
        """Test distinct with dict elements."""
        ctx = EvaluationContext()
        result = fn_distinct(ctx, [{"a": 1}, {"a": 1}, {"a": 2}])
        assert len(result) == 2

    def test_is_distinct_false(self) -> None:
        """Test isDistinct returns False for duplicates."""
        ctx = EvaluationContext()
        result = fn_is_distinct(ctx, [1, 2, 1])
        assert result == [False]


class TestExistenceFunctions:
    """Tests for existence functions."""

    def test_all_empty_collection(self) -> None:
        """Test all() on empty collection returns True."""
        ctx = EvaluationContext()
        result = fn_all(ctx, [])
        assert result == [True]

    def test_all_with_criteria(self) -> None:
        """Test all() with criteria argument."""
        ctx = EvaluationContext()
        result = fn_all(ctx, [True, True, True], "dummy")
        assert result == [True]

    def test_all_false_values(self) -> None:
        """Test all() with False values."""
        ctx = EvaluationContext()
        result = fn_all(ctx, [True, False, True])
        assert result == [False]

    def test_all_true_empty(self) -> None:
        """Test allTrue on empty collection."""
        ctx = EvaluationContext()
        result = fn_all_true(ctx, [])
        assert result == [True]

    def test_all_true_with_non_boolean(self) -> None:
        """Test allTrue with non-boolean values."""
        ctx = EvaluationContext()
        result = fn_all_true(ctx, [True, "true"])
        assert result == [False]

    def test_all_false_empty(self) -> None:
        """Test allFalse on empty collection."""
        ctx = EvaluationContext()
        result = fn_all_false(ctx, [])
        assert result == [True]

    def test_any_true_mixed(self) -> None:
        """Test anyTrue with mixed values."""
        ctx = EvaluationContext()
        assert fn_any_true(ctx, [False, True, False]) == [True]
        assert fn_any_true(ctx, [False, False]) == [False]

    def test_any_false_mixed(self) -> None:
        """Test anyFalse with mixed values."""
        ctx = EvaluationContext()
        assert fn_any_false(ctx, [True, False, True]) == [True]
        assert fn_any_false(ctx, [True, True]) == [False]

    def test_has_value_with_none(self) -> None:
        """Test hasValue with None element."""
        ctx = EvaluationContext()
        result = fn_has_value(ctx, [None])
        assert result == [False]
