"""Tests for CQL interval operations.

Tests cover:
- Basic interval creation and properties
- Timing relationships (before, after, meets, overlaps, starts, ends, during, includes)
- Compound timing (overlaps before, overlaps after)
- Collapse and expand operations
- Edge cases with open/closed bounds
"""

from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.exceptions import CQLError


@pytest.fixture
def evaluator() -> Any:
    """Create a CQL evaluator."""
    return CQLEvaluator()


class TestIntervalCreation:
    """Test interval literal creation."""

    def test_closed_interval(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("Interval[1, 10]")
        assert result is not None
        assert result.low == 1
        assert result.high == 10
        assert result.low_closed is True
        assert result.high_closed is True

    def test_open_interval(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("Interval(1, 10)")
        assert result is not None
        assert result.low == 1
        assert result.high == 10
        assert result.low_closed is False
        assert result.high_closed is False

    def test_half_open_interval(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("Interval[1, 10)")
        assert result is not None
        assert result.low_closed is True
        assert result.high_closed is False

    def test_half_open_interval_reversed(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("Interval(1, 10]")
        assert result is not None
        assert result.low_closed is False
        assert result.high_closed is True


class TestIntervalContains:
    """Test interval contains/in operations."""

    def test_contains_point_in_closed(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("5 in Interval[1, 10]") is True

    def test_contains_point_at_boundary_closed(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("1 in Interval[1, 10]") is True
        assert evaluator.evaluate_expression("10 in Interval[1, 10]") is True

    def test_contains_point_at_boundary_open(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("1 in Interval(1, 10)") is False
        assert evaluator.evaluate_expression("10 in Interval(1, 10)") is False

    def test_contains_point_outside(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("0 in Interval[1, 10]") is False
        assert evaluator.evaluate_expression("11 in Interval[1, 10]") is False


class TestIntervalBefore:
    """Test interval before operator."""

    def test_before_simple(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 5] before Interval[10, 15]") is True

    def test_before_adjacent(self, evaluator: Any) -> None:
        # Adjacent but not overlapping - still before
        assert evaluator.evaluate_expression("Interval[1, 5] before Interval[6, 10]") is True

    def test_before_touching(self, evaluator: Any) -> None:
        # Touching at point 5 - not before (meets)
        assert evaluator.evaluate_expression("Interval[1, 5] before Interval[5, 10]") is False

    def test_before_overlapping(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 7] before Interval[5, 10]") is False

    def test_after_simple(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[10, 15] after Interval[1, 5]") is True


class TestIntervalMeets:
    """Test interval meets operator.

    In CQL, two intervals "meet" if they are adjacent, meaning:
    - successor(left.high) == right.low (for meets before)
    - left.low == successor(right.high) (for meets after)

    This means [1,5] meets [6,10] (successor(5)=6) but [1,5] does NOT meet [5,10]
    (they share endpoint 5, so they overlap, not meet).
    """

    def test_meets_adjacent(self, evaluator: Any) -> None:
        # [1,5] and [6,10] are adjacent: successor(5) = 6
        assert evaluator.evaluate_expression("Interval[1, 5] meets Interval[6, 10]") is True

    def test_meets_adjacent_reverse(self, evaluator: Any) -> None:
        # [6,10] and [1,5] are adjacent: 6 = successor(5)
        assert evaluator.evaluate_expression("Interval[6, 10] meets Interval[1, 5]") is True

    def test_meets_sharing_endpoint(self, evaluator: Any) -> None:
        # [1,5] and [5,10] share endpoint 5, so they overlap, not meet
        assert evaluator.evaluate_expression("Interval[1, 5] meets Interval[5, 10]") is False


class TestIntervalOverlaps:
    """Test interval overlaps operators."""

    def test_overlaps_simple(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 6] overlaps Interval[5, 10]") is True

    def test_overlaps_no_overlap(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 4] overlaps Interval[6, 10]") is False

    def test_overlaps_before(self, evaluator: Any) -> None:
        # [1,6] overlaps [5,10] AND starts before [5,10]
        assert evaluator.evaluate_expression("Interval[1, 6] overlaps before Interval[5, 10]") is True

    def test_overlaps_before_false(self, evaluator: Any) -> None:
        # [5,10] overlaps [1,6] but does NOT start before [1,6]
        assert evaluator.evaluate_expression("Interval[5, 10] overlaps before Interval[1, 6]") is False

    def test_overlaps_after(self, evaluator: Any) -> None:
        # [5,10] overlaps [1,6] AND ends after [1,6]
        assert evaluator.evaluate_expression("Interval[5, 10] overlaps after Interval[1, 6]") is True

    def test_overlaps_after_false(self, evaluator: Any) -> None:
        # [1,6] overlaps [5,10] but does NOT end after [5,10]
        assert evaluator.evaluate_expression("Interval[1, 6] overlaps after Interval[5, 10]") is False


class TestIntervalStarts:
    """Test interval starts operator."""

    def test_starts_true(self, evaluator: Any) -> None:
        # [1,5] starts [1,10] - same start, [1,5] is contained
        assert evaluator.evaluate_expression("Interval[1, 5] starts Interval[1, 10]") is True

    def test_starts_equal(self, evaluator: Any) -> None:
        # Equal intervals - one starts the other
        assert evaluator.evaluate_expression("Interval[1, 10] starts Interval[1, 10]") is True

    def test_starts_false_longer(self, evaluator: Any) -> None:
        # [1,10] does NOT start [1,5] - [1,10] extends beyond [1,5]
        assert evaluator.evaluate_expression("Interval[1, 10] starts Interval[1, 5]") is False

    def test_starts_false_different(self, evaluator: Any) -> None:
        # Different start points
        assert evaluator.evaluate_expression("Interval[2, 5] starts Interval[1, 10]") is False


class TestIntervalEnds:
    """Test interval ends operator."""

    def test_ends_true(self, evaluator: Any) -> None:
        # [5,10] ends [1,10] - same end, [5,10] is contained
        assert evaluator.evaluate_expression("Interval[5, 10] ends Interval[1, 10]") is True

    def test_ends_equal(self, evaluator: Any) -> None:
        # Equal intervals - one ends the other
        assert evaluator.evaluate_expression("Interval[1, 10] ends Interval[1, 10]") is True

    def test_ends_false_longer(self, evaluator: Any) -> None:
        # [1,10] does NOT end [5,10] - [1,10] extends before [5,10]
        assert evaluator.evaluate_expression("Interval[1, 10] ends Interval[5, 10]") is False

    def test_ends_false_different(self, evaluator: Any) -> None:
        # Different end points
        assert evaluator.evaluate_expression("Interval[1, 8] ends Interval[1, 10]") is False


class TestIntervalDuring:
    """Test interval during/included in operators."""

    def test_during_true(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[3, 7] during Interval[1, 10]") is True

    def test_during_equal(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 10] during Interval[1, 10]") is True

    def test_during_false(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 10] during Interval[3, 7]") is False

    def test_included_in(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[3, 7] included in Interval[1, 10]") is True


class TestIntervalIncludes:
    """Test interval includes operator."""

    def test_includes_interval(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 10] includes Interval[3, 7]") is True

    def test_includes_point(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("Interval[1, 10] includes 5") is True


class TestCollapse:
    """Test collapse function for merging intervals."""

    def test_collapse_overlapping(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("collapse { Interval[1, 5], Interval[3, 8] }")
        assert len(result) == 1
        assert result[0].low == 1
        assert result[0].high == 8

    def test_collapse_separate(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("collapse { Interval[1, 5], Interval[10, 15] }")
        assert len(result) == 2

    def test_collapse_multiple(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("collapse { Interval[1, 5], Interval[3, 8], Interval[10, 15] }")
        assert len(result) == 2
        assert result[0].low == 1
        assert result[0].high == 8
        assert result[1].low == 10
        assert result[1].high == 15

    def test_collapse_adjacent(self, evaluator: Any) -> None:
        # Adjacent intervals should merge
        result = evaluator.evaluate_expression("collapse { Interval[1, 5], Interval[5, 10] }")
        assert len(result) == 1
        assert result[0].low == 1
        assert result[0].high == 10


class TestExpand:
    """Test expand function for interval expansion."""

    def test_expand_integer(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("expand Interval[1, 5]")
        assert result == [1, 2, 3, 4, 5]

    def test_expand_integer_open(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("expand Interval(1, 5)")
        assert result == [2, 3, 4]

    def test_expand_half_open(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("expand Interval[1, 5)")
        assert result == [1, 2, 3, 4]


class TestIntervalWidth:
    """Test interval width calculation."""

    def test_width_integer(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("width of Interval[1, 10]") == 9

    def test_width_decimal(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("width of Interval[1.0, 5.5]")
        assert result == pytest.approx(4.5)


class TestIntervalStartEnd:
    """Test interval start/end accessors."""

    def test_start_of(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("start of Interval[1, 10]") == 1

    def test_end_of(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("end of Interval[1, 10]") == 10


class TestIntervalPropertyAccess:
    """Test interval property access via dot notation."""

    def test_low_property(self, evaluator: Any) -> None:
        """Test .low property access."""
        assert evaluator.evaluate_expression("Interval[1, 10].low") == 1

    def test_high_property(self, evaluator: Any) -> None:
        """Test .high property access."""
        assert evaluator.evaluate_expression("Interval[1, 10].high") == 10

    def test_low_closed_property_true(self, evaluator: Any) -> None:
        """Test .lowClosed property for closed interval."""
        assert evaluator.evaluate_expression("Interval[1, 10].lowClosed") is True

    def test_low_closed_property_false(self, evaluator: Any) -> None:
        """Test .lowClosed property for open interval."""
        assert evaluator.evaluate_expression("Interval(1, 10].lowClosed") is False

    def test_high_closed_property_true(self, evaluator: Any) -> None:
        """Test .highClosed property for closed interval."""
        assert evaluator.evaluate_expression("Interval[1, 10].highClosed") is True

    def test_high_closed_property_false(self, evaluator: Any) -> None:
        """Test .highClosed property for open interval."""
        assert evaluator.evaluate_expression("Interval[1, 10).highClosed") is False

    def test_low_with_dates(self, evaluator: Any) -> None:
        """Test .low property with date interval."""
        result = evaluator.evaluate_expression("Interval[@2024-01-01, @2024-12-31].low")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_high_with_dates(self, evaluator: Any) -> None:
        """Test .high property with date interval."""
        result = evaluator.evaluate_expression("Interval[@2024-01-01, @2024-12-31].high")
        assert result is not None
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 31

    def test_low_with_decimals(self, evaluator: Any) -> None:
        """Test .low property with decimal interval."""
        result = evaluator.evaluate_expression("Interval[1.5, 9.9].low")
        assert float(result) == 1.5

    def test_high_with_decimals(self, evaluator: Any) -> None:
        """Test .high property with decimal interval."""
        result = evaluator.evaluate_expression("Interval[1.5, 9.9].high")
        assert float(result) == 9.9

    def test_chained_property_in_expression(self, evaluator: Any) -> None:
        """Test interval properties used in expressions."""
        result = evaluator.evaluate_expression("Interval[1, 10].low + Interval[1, 10].high")
        assert result == 11

    def test_property_comparison(self, evaluator: Any) -> None:
        """Test interval property in comparison."""
        result = evaluator.evaluate_expression("Interval[1, 10].low < Interval[1, 10].high")
        assert result is True


class TestIntervalPointFrom:
    """Test point from unit interval."""

    def test_point_from_unit(self, evaluator: Any) -> None:
        assert evaluator.evaluate_expression("point from Interval[5, 5]") == 5

    def test_point_from_non_unit_raises(self, evaluator: Any) -> None:
        with pytest.raises(CQLError):
            evaluator.evaluate_expression("point from Interval[1, 5]")


class TestIntervalMeetsBefore:
    """Test interval meets before operator.

    In CQL, interval A meets before interval B if successor(A.high) == B.low.
    """

    def test_meets_before_true(self, evaluator: Any) -> None:
        # [1,10] meets before [11,20]: successor(10) = 11
        result = evaluator.evaluate_expression("Interval[1, 10] meets before Interval[11, 20]")
        assert result is True

    def test_meets_before_false(self, evaluator: Any) -> None:
        # [5,10] does not meet before [1,5] - wrong order
        result = evaluator.evaluate_expression("Interval[5, 10] meets before Interval[1, 5]")
        assert result is False


class TestIntervalMeetsAfter:
    """Test interval meets after operator.

    In CQL, interval A meets after interval B if A.low == successor(B.high).
    """

    def test_meets_after_true(self, evaluator: Any) -> None:
        # [11,20] meets after [1,10]: 11 = successor(10)
        result = evaluator.evaluate_expression("Interval[11, 20] meets after Interval[1, 10]")
        assert result is True

    def test_meets_after_false(self, evaluator: Any) -> None:
        # [1,5] does not meet after [5,10] - wrong order
        result = evaluator.evaluate_expression("Interval[1, 5] meets after Interval[5, 10]")
        assert result is False


class TestIntervalUnion:
    """Test interval union as list operation."""

    def test_union_overlapping(self, evaluator: Any) -> None:
        # Union returns a list containing both intervals
        result = evaluator.evaluate_expression("{ Interval[1, 5] } union { Interval[3, 8] }")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_union_preserves_duplicates(self, evaluator: Any) -> None:
        # CQL spec: union concatenates lists, preserving duplicates
        result = evaluator.evaluate_expression("{ Interval[1, 5] } union { Interval[1, 5] }")
        assert len(result) == 2


class TestIntervalIntersect:
    """Test interval intersect as list operation."""

    def test_intersect_common(self, evaluator: Any) -> None:
        # Intersect returns items in both lists
        result = evaluator.evaluate_expression("{ Interval[1, 5] } intersect { Interval[1, 5] }")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_intersect_different(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression("{ Interval[1, 5] } intersect { Interval[10, 15] }")
        assert result == []


class TestIntervalExcept:
    """Test interval except as list operation."""

    def test_except_removes_matching(self, evaluator: Any) -> None:
        # Except removes items from first list that are in second
        result = evaluator.evaluate_expression("{ Interval[1, 5], Interval[10, 15] } except { Interval[10, 15] }")
        assert len(result) == 1
        assert result[0].low == 1


class TestCollapseDateIntervals:
    """Test collapse with date intervals."""

    def test_collapse_date_overlapping(self, evaluator: Any) -> None:
        result = evaluator.evaluate_expression(
            "collapse { Interval[@2024-01-01, @2024-01-15], Interval[@2024-01-10, @2024-01-25] }"
        )
        assert len(result) == 1


class TestExpandWithPer:
    """Test expand with per quantity."""

    def test_expand_per_2(self, evaluator: Any) -> None:
        # Expand with step of 2
        result = evaluator.evaluate_expression("expand Interval[1, 6] per 2")
        # Should create intervals of width 2
        assert len(result) >= 1
