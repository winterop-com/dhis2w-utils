"""Tests for the CQL value types.

Exercises CQLCode, CQLConcept, CQLInterval, CQLTuple and CQLRatio directly as
Python objects, plus the is_cql_type / cql_type_name type-name helpers.
"""

from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql.types import (
    CQLCode,
    CQLConcept,
    CQLInterval,
    CQLRatio,
    CQLTuple,
    cql_type_name,
    is_cql_type,
)
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, Quantity


def make_interval(
    low: Any,
    high: Any,
    low_closed: bool = True,
    high_closed: bool = True,
) -> CQLInterval[Any]:
    """Build an interval with explicit boundary closure."""
    return CQLInterval(low=low, high=high, low_closed=low_closed, high_closed=high_closed)


def make_quantity(value: str, unit: str) -> Quantity:
    """Build a quantity from a decimal string and a unit code."""
    return Quantity(value=Decimal(value), unit=unit)


class TestCQLCode:
    """CQL Code equality, hashing and string formatting."""

    def test_equality_ignores_display_and_version(self) -> None:
        left = CQLCode(code="A", system="http://s", display="Aye", version="1")
        right = CQLCode(code="A", system="http://s", display="Other", version="2")
        assert left == right

    def test_equality_against_other_type_is_false(self) -> None:
        assert CQLCode(code="A", system="http://s") != "A"

    def test_different_system_is_not_equal(self) -> None:
        assert CQLCode(code="A", system="http://s") != CQLCode(code="A", system="http://t")

    def test_hash_matches_for_equal_codes(self) -> None:
        left = CQLCode(code="A", system="http://s", display="Aye")
        right = CQLCode(code="A", system="http://s")
        assert hash(left) == hash(right)
        assert len({left, right}) == 1

    def test_string_with_display(self) -> None:
        code = CQLCode(code="A", system="http://s", display="Aye")
        assert str(code) == "Code 'A' from http://s display 'Aye'"

    def test_string_without_display(self) -> None:
        assert str(CQLCode(code="A", system="http://s")) == "Code 'A' from http://s"

    def test_equivalent_compares_code_and_system(self) -> None:
        code = CQLCode(code="A", system="http://s", display="Aye")
        assert code.equivalent(CQLCode(code="A", system="http://s")) is True
        assert code.equivalent(CQLCode(code="B", system="http://s")) is False


class TestCQLConcept:
    """CQL Concept construction, equality, hashing and string formatting."""

    def test_codes_given_as_list_become_a_tuple(self) -> None:
        code = CQLCode(code="A", system="http://s")
        codes_as_list: Any = [code]
        concept = CQLConcept(codes=codes_as_list)
        assert isinstance(concept.codes, tuple)
        assert concept.codes == (code,)

    def test_codes_given_as_tuple_stay_a_tuple(self) -> None:
        code = CQLCode(code="A", system="http://s")
        assert CQLConcept(codes=(code,)).codes == (code,)

    def test_equality_compares_the_set_of_codes(self) -> None:
        first = CQLCode(code="A", system="http://s")
        second = CQLCode(code="B", system="http://s")
        assert CQLConcept(codes=(first, second)) == CQLConcept(codes=(second, first))
        assert CQLConcept(codes=(first,)) != CQLConcept(codes=(second,))

    def test_equality_against_other_type_is_false(self) -> None:
        assert CQLConcept(codes=()) != "Concept"

    def test_hash_matches_for_the_same_code_tuple(self) -> None:
        code = CQLCode(code="A", system="http://s")
        assert hash(CQLConcept(codes=(code,), display="X")) == hash(CQLConcept(codes=(code,)))

    def test_string_with_display(self) -> None:
        code = CQLCode(code="A", system="http://s")
        assert str(CQLConcept(codes=(code,), display="Kay")) == "Concept { Code 'A' from http://s } display 'Kay'"

    def test_string_without_display(self) -> None:
        code = CQLCode(code="A", system="http://s")
        assert str(CQLConcept(codes=(code,))) == "Concept { Code 'A' from http://s }"


class TestIntervalMembership:
    """Interval contains and properly contains."""

    @pytest.mark.parametrize(
        ("low", "high", "low_closed", "high_closed", "value", "expected"),
        [
            (1, 10, True, True, 1, True),
            (1, 10, True, True, 10, True),
            (1, 10, False, True, 1, False),
            (1, 10, True, False, 10, False),
            (1, 10, False, False, 5, True),
            (None, 10, True, True, -99, True),
            (1, None, True, True, 9999, True),
            (1, 10, True, True, 0, False),
            (1, 10, True, True, 11, False),
        ],
    )
    def test_contains(
        self,
        low: Any,
        high: Any,
        low_closed: bool,
        high_closed: bool,
        value: Any,
        expected: bool,
    ) -> None:
        interval = make_interval(low, high, low_closed, high_closed)
        assert interval.contains(value) is expected
        assert (value in interval) is expected

    def test_null_value_is_never_contained(self) -> None:
        assert make_interval(1, 10).contains(None) is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(1, False), (5, True), (10, False), (0, False)],
    )
    def test_properly_contains(self, value: int, expected: bool) -> None:
        assert make_interval(1, 10).properly_contains(value) is expected

    def test_properly_contains_an_unbounded_interval_accepts_any_point(self) -> None:
        assert make_interval(None, None).properly_contains(5) is True


class TestIntervalIncludesAndOverlaps:
    """Interval includes, overlaps and meets."""

    @pytest.mark.parametrize(
        ("outer", "inner", "expected"),
        [
            (make_interval(1, 10), make_interval(3, 5), True),
            (make_interval(1, 10), make_interval(1, 10), True),
            (make_interval(1, 10), make_interval(0, 5), False),
            (make_interval(1, 10), make_interval(5, 20), False),
            (make_interval(1, 10, low_closed=False), make_interval(1, 5), False),
            (make_interval(1, 10, high_closed=False), make_interval(5, 10), False),
            (make_interval(None, None), make_interval(3, 5), True),
        ],
    )
    def test_includes(self, outer: CQLInterval[Any], inner: CQLInterval[Any], expected: bool) -> None:
        assert outer.includes(inner) is expected

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(1, 5), make_interval(3, 10), True),
            (make_interval(1, 2), make_interval(5, 10), False),
            (make_interval(5, 10), make_interval(1, 2), False),
            (make_interval(1, 5), make_interval(5, 10), True),
            (make_interval(1, 5, high_closed=False), make_interval(5, 10), False),
            (make_interval(1, 5), make_interval(5, 10, low_closed=False), False),
            (make_interval(5, 10), make_interval(1, 5, high_closed=False), False),
            (make_interval(5, 10, low_closed=False), make_interval(1, 5), False),
            (make_interval(None, None), make_interval(5, 10), True),
        ],
    )
    def test_overlaps(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: bool) -> None:
        assert left.overlaps(right) is expected

    def test_meets_requires_a_shared_point_with_opposite_closure(self) -> None:
        assert make_interval(1, 5).meets(make_interval(5, 10, low_closed=False)) is True
        assert make_interval(1, 5).meets(make_interval(5, 10)) is False

    def test_meets_needs_both_bounds(self) -> None:
        assert make_interval(1, None).meets(make_interval(5, 10)) is False
        assert make_interval(1, 5).meets(make_interval(None, 10)) is False

    def test_meets_before_and_after_are_mirror_images(self) -> None:
        left = make_interval(1, 5)
        right = make_interval(5, 10, low_closed=False)
        assert left.meets_before(right) is True
        assert right.meets_after(left) is True
        assert left.meets_after(right) is False


class TestIntervalStartsAndEnds:
    """Interval starts and ends."""

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(None, None), make_interval(None, None), True),
            (make_interval(None, 5), make_interval(None, None), True),
            (make_interval(None, 5), make_interval(1, 10), False),
            (make_interval(1, 5), make_interval(1, 10), True),
            (make_interval(1, 5), make_interval(1, None), True),
            (make_interval(1, None), make_interval(1, 10), False),
            (make_interval(1, 10), make_interval(1, 10), True),
            (make_interval(1, 10, high_closed=False), make_interval(1, 10), True),
            (make_interval(1, 10), make_interval(1, 10, high_closed=False), False),
            (make_interval(1, 20), make_interval(1, 10), False),
            (make_interval(1, 5, low_closed=False), make_interval(1, 10), False),
        ],
    )
    def test_starts(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: bool) -> None:
        assert left.starts(right) is expected

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(None, None), make_interval(None, None), True),
            (make_interval(3, None), make_interval(None, None), True),
            (make_interval(5, 10), make_interval(1, 10), True),
            (make_interval(5, 10), make_interval(None, 10), True),
            (make_interval(None, 10), make_interval(1, 10), False),
            (make_interval(1, 10), make_interval(1, 10), True),
            (make_interval(1, 10, low_closed=False), make_interval(1, 10), True),
            (make_interval(1, 10), make_interval(5, 10), False),
            (make_interval(1, 10, high_closed=False), make_interval(5, 10), False),
            (make_interval(1, 9), make_interval(1, 10), False),
        ],
    )
    def test_ends(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: bool) -> None:
        assert left.ends(right) is expected


class TestIntervalOverlapsBeforeAndAfter:
    """Interval overlaps before and overlaps after."""

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(1, 2), make_interval(5, 10), False),
            (make_interval(None, 5), make_interval(1, 10), True),
            (make_interval(None, 5), make_interval(None, 10), False),
            (make_interval(1, 5), make_interval(None, 10), False),
            (make_interval(5, 12), make_interval(1, 10), False),
            (make_interval(1, 5), make_interval(1, 10), False),
            (make_interval(1, 5), make_interval(1, 10, low_closed=False), True),
            (make_interval(1, 5), make_interval(3, 10), True),
            (make_interval(1, None), make_interval(3, 10), False),
            (make_interval(1, 5), make_interval(3, None), True),
            (make_interval(1, 20), make_interval(3, 10), False),
        ],
    )
    def test_overlaps_before(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: bool) -> None:
        assert left.overlaps_before(right) is expected

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(5, 10), make_interval(1, 2), False),
            (make_interval(None, 10), make_interval(1, 5), False),
            (make_interval(3, 10), make_interval(None, 5), True),
            (make_interval(1, 10), make_interval(3, 5), False),
            (make_interval(3, 10), make_interval(1, None), False),
            (make_interval(3, None), make_interval(1, 5), True),
            (make_interval(3, 4), make_interval(1, 5), False),
            (make_interval(3, 10), make_interval(1, 5), True),
            (make_interval(3, 5), make_interval(1, 5), False),
            (make_interval(3, 5), make_interval(1, 5, high_closed=False), True),
        ],
    )
    def test_overlaps_after(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: bool) -> None:
        assert left.overlaps_after(right) is expected


class TestIntervalSetOperations:
    """Interval union, intersect and except."""

    def test_union_returns_none_when_a_bound_is_null(self) -> None:
        assert make_interval(None, 5).union(make_interval(1, 10)) is None
        assert make_interval(1, 5).union(make_interval(1, None)) is None

    def test_union_of_disjoint_intervals_is_none(self) -> None:
        assert make_interval(1, 2).union(make_interval(5, 10)) is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(1, 5), make_interval(3, 10), make_interval(1, 10)),
            (make_interval(3, 10), make_interval(1, 5), make_interval(1, 10)),
            (make_interval(1, 20), make_interval(3, 10), make_interval(1, 20)),
            (make_interval(1, 5, low_closed=False), make_interval(1, 10), make_interval(1, 10)),
            (make_interval(1, 10, high_closed=False), make_interval(3, 10), make_interval(1, 10)),
        ],
    )
    def test_union(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: CQLInterval[Any]) -> None:
        assert left.union(right) == expected

    def test_union_of_meeting_intervals_keeps_the_widest_closure(self) -> None:
        result = make_interval(1, 5).union(make_interval(5, 10, low_closed=False))
        assert result == make_interval(1, 10)

    def test_intersect_returns_none_when_a_bound_is_null(self) -> None:
        assert make_interval(None, 5).intersect(make_interval(1, 10)) is None

    def test_intersect_of_disjoint_intervals_is_none(self) -> None:
        assert make_interval(1, 2).intersect(make_interval(5, 10)) is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (make_interval(3, 10), make_interval(1, 5), make_interval(3, 5)),
            (make_interval(1, 5), make_interval(3, 10), make_interval(3, 5)),
            (
                make_interval(1, 10, low_closed=False),
                make_interval(1, 5),
                make_interval(1, 5, low_closed=False),
            ),
            (
                make_interval(1, 10, high_closed=False),
                make_interval(3, 10),
                make_interval(3, 10, high_closed=False),
            ),
        ],
    )
    def test_intersect(self, left: CQLInterval[Any], right: CQLInterval[Any], expected: CQLInterval[Any]) -> None:
        assert left.intersect(right) == expected

    def test_except_returns_none_when_a_bound_is_null(self) -> None:
        assert make_interval(None, 5).except_(make_interval(1, 10)) is None

    def test_except_of_disjoint_intervals_returns_a_copy_of_self(self) -> None:
        original = make_interval(1, 2)
        result = original.except_(make_interval(5, 10))
        assert result == original
        assert result is not original

    def test_except_returns_none_when_the_other_interval_covers_self(self) -> None:
        assert make_interval(3, 5).except_(make_interval(1, 10)) is None

    def test_except_returns_none_when_the_result_would_split_in_two(self) -> None:
        assert make_interval(1, 10).except_(make_interval(3, 5)) is None

    def test_except_keeps_the_right_portion_when_the_other_covers_the_left(self) -> None:
        assert make_interval(3, 10).except_(make_interval(1, 5)) == make_interval(5, 10, low_closed=False)

    def test_except_keeps_the_left_portion_when_the_other_covers_the_right(self) -> None:
        assert make_interval(1, 10).except_(make_interval(5, 20)) == make_interval(1, 5, high_closed=False)

    def test_except_with_a_shared_closed_low_bound_keeps_the_right_portion(self) -> None:
        assert make_interval(1, 10).except_(make_interval(1, 5)) == make_interval(5, 10, low_closed=False)

    def test_except_returns_none_when_an_open_low_bound_makes_the_other_interior(self) -> None:
        assert make_interval(1, 10, low_closed=False).except_(make_interval(1, 5)) is None

    def test_except_returns_none_when_an_open_high_bound_makes_the_other_interior(self) -> None:
        assert make_interval(1, 10, high_closed=False).except_(make_interval(3, 10)) is None


class TestIntervalProperties:
    """Interval emptiness, width, start, end, equality, hashing and formatting."""

    @pytest.mark.parametrize(
        ("interval", "expected"),
        [
            (make_interval(1, 10), False),
            (make_interval(5, 1), True),
            (make_interval(5, 5), False),
            (make_interval(5, 5, low_closed=False), True),
            (make_interval(5, 5, high_closed=False), True),
            (make_interval(None, 5), False),
            (make_interval(1, None), False),
        ],
    )
    def test_is_empty(self, interval: CQLInterval[Any], expected: bool) -> None:
        assert interval.is_empty is expected

    def test_width_is_the_difference_of_the_bounds(self) -> None:
        assert make_interval(1, 10).width() == 9

    @pytest.mark.parametrize("interval", [make_interval(None, 3), make_interval(3, None)])
    def test_width_of_an_unbounded_interval_is_none(self, interval: CQLInterval[Any]) -> None:
        assert interval.width() is None

    def test_start_and_end_return_the_bounds(self) -> None:
        interval = make_interval(1, 10)
        assert interval.start() == 1
        assert interval.end() == 10

    def test_equality_compares_bounds_and_closure(self) -> None:
        assert make_interval(1, 10) == make_interval(1, 10)
        assert make_interval(1, 10) != make_interval(1, 10, high_closed=False)
        assert make_interval(1, 10) != make_interval(2, 10)

    def test_equality_against_other_type_is_false(self) -> None:
        assert make_interval(1, 10) != 5

    def test_hash_matches_for_equal_intervals(self) -> None:
        assert hash(make_interval(1, 10)) == hash(make_interval(1, 10))

    def test_hash_of_an_unbounded_interval_is_stable(self) -> None:
        assert hash(make_interval(None, None)) == hash(make_interval(None, None))

    @pytest.mark.parametrize(
        ("interval", "expected"),
        [
            (make_interval(1, 10), "Interval[1, 10]"),
            (make_interval(1, 10, low_closed=False, high_closed=False), "Interval(1, 10)"),
            (make_interval(1, 10, high_closed=False), "Interval[1, 10)"),
            (make_interval(None, None), "Interval[, ]"),
        ],
    )
    def test_string_formatting(self, interval: CQLInterval[Any], expected: str) -> None:
        assert str(interval) == expected


class TestCQLTuple:
    """CQL Tuple element access, equality, hashing and formatting."""

    def test_attribute_access_reads_elements(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann", "age": 5})
        assert tuple_value.name == "Ann"
        assert tuple_value.age == 5

    def test_attribute_access_for_a_missing_element_raises(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann"})
        with pytest.raises(AttributeError, match="has no attribute 'missing'"):
            _ = tuple_value.missing

    def test_attribute_access_before_construction_raises_instead_of_recursing(self) -> None:
        uninitialised = CQLTuple.__new__(CQLTuple)
        with pytest.raises(AttributeError, match="has no attribute 'whatever'"):
            _ = uninitialised.whatever

    def test_reading_elements_before_construction_raises(self) -> None:
        uninitialised = CQLTuple.__new__(CQLTuple)
        with pytest.raises(AttributeError, match="elements"):
            _ = uninitialised.elements

    def test_item_access_returns_none_for_a_missing_key(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann"})
        assert tuple_value["name"] == "Ann"
        assert tuple_value["missing"] is None

    def test_item_assignment_adds_an_element(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann"})
        tuple_value["city"] = "Oslo"
        assert tuple_value.elements == {"name": "Ann", "city": "Oslo"}

    def test_contains_checks_element_names(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann"})
        assert "name" in tuple_value
        assert "city" not in tuple_value

    def test_equality_against_another_tuple_and_a_plain_mapping(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann"})
        assert tuple_value == CQLTuple(elements={"name": "Ann"})
        assert tuple_value == {"name": "Ann"}
        assert tuple_value != {"name": "Bob"}

    def test_equality_against_other_type_is_false(self) -> None:
        assert CQLTuple(elements={"name": "Ann"}) != 5

    def test_hash_matches_for_equal_tuples(self) -> None:
        assert hash(CQLTuple(elements={"a": 1})) == hash(CQLTuple(elements={"a": 1}))

    def test_string_formatting(self) -> None:
        assert str(CQLTuple(elements={"a": 1, "b": "x"})) == "Tuple { a: 1, b: x }"

    def test_keys_values_and_items(self) -> None:
        tuple_value = CQLTuple(elements={"name": "Ann", "age": 5})
        assert tuple_value.keys() == ["name", "age"]
        assert tuple_value.values() == ["Ann", 5]
        assert tuple_value.items() == [("name", "Ann"), ("age", 5)]


class TestCQLRatio:
    """CQL Ratio equality, hashing, formatting and decimal conversion."""

    def test_equality_compares_both_quantities(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        same = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        other = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("3", "mg"))
        assert ratio == same
        assert ratio != other

    def test_equality_against_other_type_is_false(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        assert ratio != 0.5

    def test_hash_matches_for_equal_ratios(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        same = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        assert hash(ratio) == hash(same)

    def test_string_formatting(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        assert str(ratio) == "1 'mg' : 2 'mg'"

    def test_to_decimal_when_the_units_cancel(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        assert ratio.to_decimal() == Decimal("0.5")

    def test_to_decimal_is_none_for_differing_units(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "g"))
        assert ratio.to_decimal() is None

    def test_to_decimal_is_none_for_a_zero_denominator(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("0", "mg"))
        assert ratio.to_decimal() is None


class TestTypeNaming:
    """The is_cql_type and cql_type_name helpers."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, "Null"),
            (True, "Boolean"),
            (3, "Integer"),
            (Decimal("1.5"), "Decimal"),
            (2.5, "Decimal"),
            ("s", "String"),
            (FHIRDate(year=2020), "Date"),
            (FHIRDateTime(year=2020), "DateTime"),
            (Quantity(value=Decimal("1"), unit="mg"), "Quantity"),
            (CQLCode(code="a", system="b"), "Code"),
            (CQLConcept(codes=()), "Concept"),
            (make_interval(1, 2), "Interval"),
            (CQLTuple(elements={}), "Tuple"),
            ({"a": 1}, "Tuple"),
            ([1, 2], "List"),
            (object(), "Unknown"),
        ],
    )
    def test_cql_type_name(self, value: Any, expected: str) -> None:
        assert cql_type_name(value) == expected

    def test_cql_type_name_of_a_ratio(self) -> None:
        ratio = CQLRatio(numerator=make_quantity("1", "mg"), denominator=make_quantity("2", "mg"))
        assert cql_type_name(ratio) == "Ratio"

    @pytest.mark.parametrize(
        "value",
        [None, True, 3, Decimal("1.5"), 2.5, "s", FHIRDate(year=2020), FHIRDateTime(year=2020), [1], CQLTuple()],
    )
    def test_recognised_values(self, value: Any) -> None:
        assert is_cql_type(value) is True

    @pytest.mark.parametrize("value", [object(), {"a": 1}])
    def test_unrecognised_values(self, value: Any) -> None:
        assert is_cql_type(value) is False
