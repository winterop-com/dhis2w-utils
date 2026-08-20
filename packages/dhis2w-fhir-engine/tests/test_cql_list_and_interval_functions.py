"""Tests for the CQL list functions and the interval timing helpers.

Covers the list standard library (First through Except) and the interval
support module: successor computation, interval-to-interval and
interval-to-point timing, adjacency and interval collapsing.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql.functions import list_funcs
from dhis2w_fhir_engine.engine.cql.functions.intervals import (
    _are_adjacent,
    collapse_intervals,
    get_successor,
    interval_point_timing,
    interval_timing,
    point_interval_timing,
)
from dhis2w_fhir_engine.engine.cql.functions.registry import get_registry
from dhis2w_fhir_engine.engine.cql.types import CQLInterval
from dhis2w_fhir_engine.engine.exceptions import CQLError
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity


def make_interval(
    low: Any,
    high: Any,
    low_closed: bool = True,
    high_closed: bool = True,
) -> CQLInterval[Any]:
    """Build an interval with explicit boundary closure."""
    return CQLInterval(low=low, high=high, low_closed=low_closed, high_closed=high_closed)


class TestListAccessors:
    """First, Last, Tail, Take and Skip."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3]], 1),
            ([[]], None),
            ([], None),
            (["not a list"], None),
            ([None], None),
        ],
    )
    def test_first(self, arguments: list[Any], expected: Any) -> None:
        assert list_funcs._first(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3]], 3),
            ([[]], None),
            ([], None),
            (["not a list"], None),
        ],
    )
    def test_last(self, arguments: list[Any], expected: Any) -> None:
        assert list_funcs._last(arguments) == expected

    def test_tail_of_a_null_list_is_null(self) -> None:
        assert list_funcs._tail([None]) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3]], [2, 3]),
            ([[1]], []),
            ([[]], []),
            ([], []),
            (["not a list"], []),
        ],
    )
    def test_tail(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._tail(arguments) == expected

    def test_take_of_a_null_list_is_null(self) -> None:
        assert list_funcs._take([None, 2]) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3], 2], [1, 2]),
            ([[1, 2, 3], 0], []),
            ([[1, 2, 3], 9], [1, 2, 3]),
            ([[1, 2], "two"], []),
            ([[1, 2]], []),
            ([], []),
        ],
    )
    def test_take(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._take(arguments) == expected

    def test_skip_of_a_null_list_is_null(self) -> None:
        assert list_funcs._skip([None, 2]) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3], 2], [3]),
            ([[1, 2, 3], 0], [1, 2, 3]),
            ([[1, 2, 3], 9], []),
            ([[1, 2], "two"], []),
            ([], []),
        ],
    )
    def test_skip(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._skip(arguments) == expected


class TestListPredicates:
    """Length and Exists."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2]], 2),
            (["abc"], 3),
            ([None], 0),
            ([[]], 0),
            ([5], 0),
            ([], 0),
        ],
    )
    def test_length(self, arguments: list[Any], expected: int) -> None:
        assert list_funcs._length(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1]], True),
            ([[None, 1]], True),
            ([[None, None]], False),
            ([[]], False),
            ([5], True),
            ([None], False),
            ([], False),
        ],
    )
    def test_exists(self, arguments: list[Any], expected: bool) -> None:
        assert list_funcs._exists(arguments) is expected


class TestListReshaping:
    """Flatten, Distinct, Sort, Reverse and Slice."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[[1, 2], 3]], [1, 2, 3]),
            ([[[1], [2], []]], [1, 2]),
            ([[1, 2]], [1, 2]),
            (["not a list"], []),
            ([], []),
        ],
    )
    def test_flatten(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._flatten(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, None, 1, 2]], [1, 2]),
            ([[None]], []),
            ([[]], []),
            (["not a list"], []),
            ([], []),
        ],
    )
    def test_distinct(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._distinct(arguments) == expected

    def test_sort_orders_comparable_values(self) -> None:
        assert list_funcs._sort([[3, 1, 2]]) == [1, 2, 3]

    def test_sort_returns_the_input_when_values_are_not_comparable(self) -> None:
        assert list_funcs._sort([[1, "a"]]) == [1, "a"]

    @pytest.mark.parametrize("arguments", [[], ["not a list"]])
    def test_sort_of_a_non_list_is_empty(self, arguments: list[Any]) -> None:
        assert list_funcs._sort(arguments) == []

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3]], [3, 2, 1]),
            ([[]], []),
            (["not a list"], []),
            ([], []),
        ],
    )
    def test_reverse(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._reverse(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3, 4], 1, 2], [2, 3]),
            ([[1, 2, 3], None, None], [1, 2, 3]),
            ([[1, 2, 3], 0, 1], [1]),
            (["not a list", 0, 1], []),
            ([[1, 2]], []),
            ([], []),
        ],
    )
    def test_slice(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._slice(arguments) == expected


class TestListSearchAndSingleton:
    """IndexOf, Singleton and SingletonFrom."""

    def test_index_of_a_null_source_is_null(self) -> None:
        assert list_funcs._index_of([None, 1]) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2, 3], 2], 1),
            ([[1, 2], 9], -1),
            ([[None], None], 0),
            (["hello", "ll"], 2),
            (["hello", "zz"], -1),
            ([5, 1], -1),
            ([], -1),
        ],
    )
    def test_index_of(self, arguments: list[Any], expected: int) -> None:
        assert list_funcs._index_of(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[7]], 7),
            ([[1, 2]], None),
            ([[]], None),
            (["not a list"], None),
            ([], None),
        ],
    )
    def test_singleton(self, arguments: list[Any], expected: Any) -> None:
        assert list_funcs._singleton(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[7]], 7),
            ([[]], None),
            (["not a list"], None),
            ([], None),
        ],
    )
    def test_singleton_from(self, arguments: list[Any], expected: Any) -> None:
        assert list_funcs._singleton_from(arguments) == expected

    def test_singleton_from_rejects_more_than_one_element(self) -> None:
        with pytest.raises(CQLError, match="at most one element"):
            list_funcs._singleton_from([[1, 2]])


class TestListCombination:
    """Combine, Union, Intersect and Except."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([["a", "b"]], "ab"),
            ([["a", "b"], "-"], "a-b"),
            ([["a", None, "b"]], "ab"),
            ([[1, 2], [3]], [1, 2, 3]),
            (["not a list"], None),
            ([None], None),
            ([], None),
        ],
    )
    def test_combine(self, arguments: list[Any], expected: Any) -> None:
        assert list_funcs._combine(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1], [2]], [1, 2]),
            ([[1, 1], [1]], [1, 1, 1]),
            ([1, 2], [1, 2]),
            ([[1], 2], [1, 2]),
            ([[1]], []),
            ([], []),
        ],
    )
    def test_union(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._union(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2], [2, 3]], [2]),
            ([[1], [9]], []),
            ([1, 2], []),
            ([[1]], []),
            ([], []),
        ],
    )
    def test_intersect(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._intersect(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[1, 2], [2, 3]], [1]),
            ([[1], [1]], []),
            ([1, 2], []),
            ([[1]], []),
            ([], []),
        ],
    )
    def test_except(self, arguments: list[Any], expected: list[Any]) -> None:
        assert list_funcs._except(arguments) == expected


class TestListRegistration:
    """Every list function is reachable through the shared registry."""

    @pytest.mark.parametrize(
        "name",
        [
            "First",
            "Last",
            "Tail",
            "Take",
            "Skip",
            "Length",
            "Exists",
            "Flatten",
            "Distinct",
            "Sort",
            "IndexOf",
            "Singleton",
            "SingletonFrom",
            "Reverse",
            "Slice",
            "Combine",
            "Union",
            "Intersect",
            "Except",
        ],
    )
    def test_registered_under_the_list_category(self, name: str) -> None:
        registry = get_registry()
        assert registry.has(name)
        assert name in registry.list_functions(category="list")

    def test_call_goes_through_the_registry(self) -> None:
        assert get_registry().call("first", [[4, 5]]) == 4


class TestGetSuccessor:
    """The successor of a value is the next representable value of its type."""

    def test_null_has_no_successor(self) -> None:
        assert get_successor(None) is None

    def test_integer_successor(self) -> None:
        assert get_successor(5) == 6

    def test_decimal_successor_steps_by_the_smallest_unit(self) -> None:
        assert get_successor(Decimal("1.0")) == Decimal("1.00000001")

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020, month=1, day=1), FHIRDate(year=2020, month=1, day=2)),
            (FHIRDate(year=2020, month=1, day=28), FHIRDate(year=2020, month=2, day=1)),
            (FHIRDate(year=2020, month=12, day=28), FHIRDate(year=2021, month=1, day=1)),
        ],
    )
    def test_date_successor_rolls_over(self, value: FHIRDate, expected: FHIRDate) -> None:
        assert get_successor(value) == expected

    def test_datetime_with_a_time_component_steps_one_millisecond(self) -> None:
        value = FHIRDateTime(year=2020, month=1, day=1, hour=1, minute=2, second=3, millisecond=4)
        expected = FHIRDateTime(year=2020, month=1, day=1, hour=1, minute=2, second=3, millisecond=5)
        assert get_successor(value) == expected

    def test_datetime_millisecond_step_cascades_into_the_next_day(self) -> None:
        value = FHIRDateTime(year=2020, month=1, day=1, hour=23, minute=59, second=59, millisecond=999)
        expected = FHIRDateTime(year=2020, month=1, day=2, hour=0, minute=0, second=0, millisecond=0)
        assert get_successor(value) == expected

    def test_datetime_without_a_time_component_steps_one_day(self) -> None:
        value = FHIRDateTime(year=2020, month=1, day=1)
        assert get_successor(value) == FHIRDateTime(year=2020, month=1, day=2)

    def test_time_successor_steps_one_millisecond(self) -> None:
        value = FHIRTime(hour=1, minute=2, second=3, millisecond=4)
        assert get_successor(value) == FHIRTime(hour=1, minute=2, second=3, millisecond=5)

    def test_time_successor_wraps_around_midnight(self) -> None:
        value = FHIRTime(hour=23, minute=59, second=59, millisecond=999)
        assert get_successor(value) == FHIRTime(hour=0, minute=0, second=0, millisecond=0)

    def test_quantity_successor_keeps_the_unit(self) -> None:
        value = Quantity(value=Decimal("1"), unit="mg")
        assert get_successor(value) == Quantity(value=Decimal("1.00000001"), unit="mg")

    def test_a_value_without_a_successor_is_returned_unchanged(self) -> None:
        assert get_successor("abc") == "abc"


class TestIntervalTiming:
    """Interval-to-interval timing operators."""

    @pytest.mark.parametrize(
        ("left", "right", "op", "expected"),
        [
            (make_interval(1, 5), make_interval(3, 10), "overlaps before", True),
            (make_interval(3, 12), make_interval(1, 10), "overlaps after", True),
            (make_interval(1, 5), make_interval(3, 10), "overlaps", True),
            (make_interval(1, 2), make_interval(5, 10), "overlaps", False),
            (make_interval(1, 2), make_interval(3, 10), "meets before", True),
            (make_interval(3, 10), make_interval(1, 2), "meets after", True),
            (make_interval(1, 2), make_interval(3, 10), "meets", True),
            (make_interval(3, 10), make_interval(1, 2), "meets", True),
            (make_interval(1, 2), make_interval(3, 10), "before", True),
            (make_interval(3, 10), make_interval(1, 2), "after", True),
            (make_interval(1, 5), make_interval(1, 10), "starts", True),
            (make_interval(2, 5), make_interval(1, 10), "starts", False),
            (make_interval(1, 5, low_closed=False), make_interval(1, 10), "starts", False),
            (make_interval(1, None), make_interval(1, None), "starts", True),
            (make_interval(3, 10), make_interval(1, 10), "ends", True),
            (make_interval(1, 5), make_interval(1, 10), "ends", False),
            (make_interval(1, 10, high_closed=False), make_interval(1, 10), "ends", False),
            (make_interval(None, 10), make_interval(None, 10), "ends", True),
            (make_interval(None, 10), make_interval(1, 10), "ends", False),
            (make_interval(3, 10), make_interval(None, 10), "ends", True),
            (make_interval(3, 5), make_interval(1, 10), "during", True),
            (make_interval(3, 5), make_interval(1, 10), "included in", True),
            (make_interval(1, 10), make_interval(3, 5), "includes", True),
            (make_interval(1, 10), make_interval(1, 10), "same as", True),
            (make_interval(1, 10), make_interval(2, 10), "same as", False),
        ],
    )
    def test_operators(
        self,
        left: CQLInterval[Any],
        right: CQLInterval[Any],
        op: str,
        expected: bool,
    ) -> None:
        assert interval_timing(left, right, op) is expected

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        [
            (make_interval(None, 5), make_interval(1, 10), "overlaps before"),
            (make_interval(1, 5), make_interval(None, 10), "overlaps before"),
            (make_interval(1, None), make_interval(1, 10), "overlaps after"),
            (make_interval(1, 10), make_interval(1, None), "overlaps after"),
            (make_interval(1, None), make_interval(3, 10), "meets before"),
            (make_interval(3, 10), make_interval(1, None), "meets after"),
            (make_interval(1, None), make_interval(3, 10), "before"),
            (make_interval(None, 5), make_interval(1, 2), "after"),
            (make_interval(None, 5), make_interval(1, 2), "starts"),
            (make_interval(1, None), make_interval(1, 2), "ends"),
        ],
    )
    def test_unbounded_operands_yield_null(
        self,
        left: CQLInterval[Any],
        right: CQLInterval[Any],
        op: str,
    ) -> None:
        assert interval_timing(left, right, op) is None

    def test_an_unrecognised_operator_yields_null(self) -> None:
        assert interval_timing(make_interval(1, 10), make_interval(1, 10), "wobble") is None


class TestIntervalPointTiming:
    """Interval-to-point timing operators."""

    @pytest.mark.parametrize("op", ["on or before", "onorbefore"])
    @pytest.mark.parametrize(("point", "expected"), [(5, False), (15, True), (10, True)])
    def test_on_or_before(self, op: str, point: int, expected: bool) -> None:
        assert interval_point_timing(make_interval(1, 10), point, op) is expected

    @pytest.mark.parametrize("op", ["on or after", "onorafter"])
    @pytest.mark.parametrize(("point", "expected"), [(0, True), (1, True), (5, False)])
    def test_on_or_after(self, op: str, point: int, expected: bool) -> None:
        assert interval_point_timing(make_interval(1, 10), point, op) is expected

    @pytest.mark.parametrize(("point", "expected"), [(15, True), (10, False), (5, False)])
    def test_before(self, point: int, expected: bool) -> None:
        assert interval_point_timing(make_interval(1, 10), point, "before") is expected

    @pytest.mark.parametrize(("point", "expected"), [(0, True), (1, False), (5, False)])
    def test_after(self, point: int, expected: bool) -> None:
        assert interval_point_timing(make_interval(1, 10), point, "after") is expected

    @pytest.mark.parametrize("op", ["contains", "includes"])
    @pytest.mark.parametrize(("point", "expected"), [(5, True), (1, True), (15, False)])
    def test_contains(self, op: str, point: int, expected: bool) -> None:
        assert interval_point_timing(make_interval(1, 10), point, op) is expected

    @pytest.mark.parametrize(("point", "expected"), [(5, True), (1, False), (10, False)])
    def test_properly_contains(self, point: int, expected: bool) -> None:
        assert interval_point_timing(make_interval(1, 10), point, "properly contains") is expected

    @pytest.mark.parametrize("op", ["before", "after", "on or before", "on or after"])
    def test_unbounded_intervals_answer_false(self, op: str) -> None:
        assert interval_point_timing(make_interval(None, None), 5, op) is False

    def test_an_unrecognised_operator_yields_null(self) -> None:
        assert interval_point_timing(make_interval(1, 10), 5, "wobble") is None


class TestPointIntervalTiming:
    """Point-to-interval timing operators."""

    @pytest.mark.parametrize("op", ["on or before", "onorbefore"])
    @pytest.mark.parametrize(("point", "expected"), [(0, True), (1, True), (5, False)])
    def test_on_or_before(self, op: str, point: int, expected: bool) -> None:
        assert point_interval_timing(point, make_interval(1, 10), op) is expected

    @pytest.mark.parametrize("op", ["on or after", "onorafter"])
    @pytest.mark.parametrize(("point", "expected"), [(15, True), (10, True), (5, False)])
    def test_on_or_after(self, op: str, point: int, expected: bool) -> None:
        assert point_interval_timing(point, make_interval(1, 10), op) is expected

    @pytest.mark.parametrize(("point", "expected"), [(0, True), (1, False), (5, False)])
    def test_before(self, point: int, expected: bool) -> None:
        assert point_interval_timing(point, make_interval(1, 10), "before") is expected

    @pytest.mark.parametrize(("point", "expected"), [(15, True), (10, False), (5, False)])
    def test_after(self, point: int, expected: bool) -> None:
        assert point_interval_timing(point, make_interval(1, 10), "after") is expected

    @pytest.mark.parametrize("op", ["during", "in", "included in"])
    @pytest.mark.parametrize(("point", "expected"), [(5, True), (1, True), (15, False)])
    def test_during(self, op: str, point: int, expected: bool) -> None:
        assert point_interval_timing(point, make_interval(1, 10), op) is expected

    @pytest.mark.parametrize(("point", "expected"), [(5, True), (1, False), (10, False)])
    def test_properly_in(self, point: int, expected: bool) -> None:
        assert point_interval_timing(point, make_interval(1, 10), "properly in") is expected

    @pytest.mark.parametrize("op", ["before", "after", "on or before", "on or after"])
    def test_unbounded_intervals_answer_false(self, op: str) -> None:
        assert point_interval_timing(5, make_interval(None, None), op) is False

    def test_an_unrecognised_operator_yields_null(self) -> None:
        assert point_interval_timing(5, make_interval(1, 10), "wobble") is None


class TestAreAdjacent:
    """Adjacency checks used when collapsing intervals."""

    @pytest.mark.parametrize(
        ("high", "low", "expected"),
        [
            (1, 2, True),
            (1, 3, False),
            (Decimal("1.0"), Decimal("1.00000001"), True),
            (Decimal("1.0"), Decimal("2"), False),
            (Decimal("2"), Decimal("1"), False),
            (date(2020, 1, 1), date(2020, 1, 2), True),
            (date(2020, 1, 1), date(2020, 1, 3), False),
            ("a", "b", False),
        ],
    )
    def test_scalar_and_python_date_adjacency(self, high: Any, low: Any, expected: bool) -> None:
        assert _are_adjacent(high, low) is expected

    @pytest.mark.parametrize(
        ("high", "low", "expected"),
        [
            (FHIRDate(year=2020, month=1, day=1), FHIRDate(year=2020, month=1, day=2), True),
            (FHIRDate(year=2020, month=1, day=1), FHIRDate(year=2020, month=1, day=3), False),
            (FHIRDate(year=2020), FHIRDate(year=2021), False),
        ],
    )
    def test_fhir_date_adjacency(self, high: FHIRDate, low: FHIRDate, expected: bool) -> None:
        assert _are_adjacent(high, low) is expected

    def test_day_precision_datetimes_are_adjacent_one_day_apart(self) -> None:
        high = FHIRDateTime(year=2020, month=1, day=1)
        low = FHIRDateTime(year=2020, month=1, day=2)
        assert _are_adjacent(high, low) is True

    def test_full_precision_datetimes_are_adjacent_one_millisecond_apart(self) -> None:
        high = FHIRDateTime(year=2020, month=1, day=1, hour=0, minute=0, second=0, millisecond=0)
        low = FHIRDateTime(year=2020, month=1, day=1, hour=0, minute=0, second=0, millisecond=1)
        assert _are_adjacent(high, low) is True

    def test_month_precision_datetimes_are_never_adjacent(self) -> None:
        assert _are_adjacent(FHIRDateTime(year=2020, month=1), FHIRDateTime(year=2020, month=2)) is False

    def test_times_are_adjacent_one_millisecond_apart(self) -> None:
        high = FHIRTime(hour=1, minute=0, second=0, millisecond=0)
        low = FHIRTime(hour=1, minute=0, second=0, millisecond=1)
        assert _are_adjacent(high, low) is True

    def test_hour_precision_times_are_not_adjacent(self) -> None:
        assert _are_adjacent(FHIRTime(hour=1), FHIRTime(hour=2)) is False


class TestCollapseIntervals:
    """Collapsing merges overlapping, touching and adjacent intervals."""

    def test_an_empty_input_collapses_to_nothing(self) -> None:
        assert collapse_intervals([], CQLInterval) == []

    def test_intervals_without_a_low_bound_are_dropped(self) -> None:
        assert collapse_intervals([make_interval(None, 5)], CQLInterval) == []

    def test_overlapping_intervals_merge(self) -> None:
        result = collapse_intervals([make_interval(1, 5), make_interval(3, 10)], CQLInterval)
        assert result == [make_interval(1, 10)]

    def test_adjacent_closed_intervals_merge(self) -> None:
        result = collapse_intervals([make_interval(1, 5), make_interval(6, 10)], CQLInterval)
        assert result == [make_interval(1, 10)]

    def test_disjoint_intervals_stay_separate(self) -> None:
        result = collapse_intervals([make_interval(1, 5), make_interval(7, 10)], CQLInterval)
        assert result == [make_interval(1, 5), make_interval(7, 10)]

    def test_a_contained_interval_is_absorbed(self) -> None:
        result = collapse_intervals([make_interval(1, 10), make_interval(3, 5)], CQLInterval)
        assert result == [make_interval(1, 10)]

    def test_an_unbounded_high_stops_merging(self) -> None:
        result = collapse_intervals([make_interval(1, None), make_interval(3, 5)], CQLInterval)
        assert result == [make_interval(1, None), make_interval(3, 5)]

    def test_merging_into_an_unbounded_high_widens_the_result(self) -> None:
        result = collapse_intervals([make_interval(1, 5), make_interval(3, None)], CQLInterval)
        assert result == [make_interval(1, None)]

    def test_input_order_does_not_matter(self) -> None:
        result = collapse_intervals([make_interval(3, 10), make_interval(1, 5)], CQLInterval)
        assert result == [make_interval(1, 10)]
