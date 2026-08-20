"""Tests for the FHIRPath comparison operators and the type-checking functions beside them."""

from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.comparison import (
    _compare_datetime_to_precision,
    _compare_time_to_precision,
    _get_datetime_precision,
    _get_quantity_precision,
    _get_time_precision,
    compare,
    equals,
    equivalent,
    fn_comparable,
)
from dhis2w_fhir_engine.engine.fhirpath.functions.filtering import (
    _get_type_name,
    fn_as,
    fn_is,
    fn_of_type,
    fn_type,
)
from dhis2w_fhir_engine.engine.fhirpath.visitor import _PrimitiveWithExtension
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity


@pytest.fixture
def context() -> EvaluationContext:
    """Build an evaluation context with no resource bound."""
    return EvaluationContext()


def date_time(**components: Any) -> FHIRDateTime:
    """Build a FHIRDateTime from the components a test cares about."""
    return FHIRDateTime(**components)


class TestEquals:
    """Tests for FHIRPath equality."""

    @pytest.mark.parametrize(
        ("left", "right"),
        [(None, 5), (5, None), ([], 5), (5, []), ([], [])],
    )
    def test_an_absent_operand_makes_equality_unknown(self, left: Any, right: Any) -> None:
        assert equals(left, right) is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            ([1, 2], [1, 2], True),
            ([1, 2], [1, 3], False),
            ([1, 2], [1, 2, 3], False),
            ([1, 2], 1, False),
            (1, [1, 2], False),
        ],
    )
    def test_collections_compare_element_by_element(self, left: Any, right: Any, expected: bool) -> None:
        assert equals(left, right) is expected

    def test_an_incomparable_element_makes_the_whole_collection_unknown(self) -> None:
        left = [FHIRDate(year=2024, month=3, day=1), 1]
        right = [date_time(year=2024, month=3, day=1, hour=8), 1]
        assert equals(left, right) is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (FHIRDate(year=2024, month=3, day=1), FHIRDateTime(year=2024, month=3, day=1), True),
            (FHIRDate(year=2024, month=3, day=2), FHIRDateTime(year=2024, month=3, day=1), False),
            (FHIRDateTime(year=2024, month=3, day=1), FHIRDate(year=2024, month=3, day=1), True),
            (FHIRDateTime(year=2024, month=3, day=2), FHIRDate(year=2024, month=3, day=1), False),
        ],
    )
    def test_a_date_and_a_datetime_compare_on_their_date_parts(self, left: Any, right: Any, expected: bool) -> None:
        assert equals(left, right) is expected

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            (FHIRDate(year=2024, month=3, day=1), FHIRDateTime(year=2024, month=3, day=1, hour=8)),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), FHIRDate(year=2024, month=3, day=1)),
        ],
    )
    def test_a_datetime_carrying_a_time_is_incomparable_with_a_date(self, left: Any, right: Any) -> None:
        assert equals(left, right) is None

    def test_datetimes_at_different_second_precision_are_incomparable(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=30)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=30, second=0)
        assert equals(left, right) is None

    def test_one_datetime_with_a_timezone_and_one_without_are_incomparable(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, tz_offset="Z")
        right = date_time(year=2024, month=3, day=1, hour=8)
        assert equals(left, right) is None

    def test_two_datetimes_with_timezones_compare_in_utc(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0, tz_offset="Z")
        right = date_time(year=2024, month=3, day=1, hour=9, minute=0, second=0, tz_offset="+01:00")
        assert equals(left, right) is True

    def test_a_missing_millisecond_reads_as_zero(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0, millisecond=0)
        assert equals(left, right) is True

    def test_times_at_different_second_precision_are_incomparable(self) -> None:
        assert equals(FHIRTime(hour=8, minute=30), FHIRTime(hour=8, minute=30, second=0)) is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (FHIRTime(hour=8, minute=30, second=15), FHIRTime(hour=8, minute=30, second=15, millisecond=0), True),
            (FHIRTime(hour=8, minute=30, second=15), FHIRTime(hour=8, minute=30, second=16), False),
            (FHIRTime(hour=8, second=15), FHIRTime(hour=8, minute=0, second=15), True),
        ],
    )
    def test_times_at_the_same_precision(self, left: FHIRTime, right: FHIRTime, expected: bool) -> None:
        assert equals(left, right) is expected

    def test_dates_at_different_precision_are_incomparable(self) -> None:
        assert equals(FHIRDate(year=2024, month=3), FHIRDate(year=2024, month=3, day=1)) is None

    def test_quantities_with_incompatible_units_are_incomparable(self) -> None:
        left = Quantity(value=Decimal("1"), unit="mg")
        right = Quantity(value=Decimal("1"), unit="m")
        assert equals(left, right) is None

    def test_quantities_convert_before_comparing(self) -> None:
        left = Quantity(value=Decimal("1000"), unit="mg")
        right = Quantity(value=Decimal("1"), unit="g")
        assert equals(left, right) is True

    @pytest.mark.parametrize(("left", "right", "expected"), [(1, 1.0, True), (1, Decimal("1"), True), (1, "a", False)])
    def test_values_of_different_types(self, left: Any, right: Any, expected: bool) -> None:
        assert equals(left, right) is expected

    def test_a_fhir_quantity_dictionary_normalizes_to_a_quantity(self) -> None:
        assert equals({"value": 1000, "code": "mg"}, Quantity(value=Decimal("1"), unit="g")) is True

    def test_a_wrapped_primitive_is_unwrapped_before_comparing(self) -> None:
        wrapped = _PrimitiveWithExtension("final", element_name="status", resource_type="Observation")
        assert equals(wrapped, "final") is True


class TestEquivalent:
    """Tests for FHIRPath equivalence."""

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            ([1, 2], [2, 1], True),
            ([1, 2], [1], False),
            ([], [], True),
            ([1], 1, True),
            ([1, 2], 1, False),
            (1, [1, 2], False),
            ([], 1, False),
            (None, None, True),
            (None, 1, False),
            (1, None, False),
        ],
    )
    def test_collections_and_absent_values(self, left: Any, right: Any, expected: bool) -> None:
        assert equivalent(left, right) is expected

    def test_a_collection_with_no_match_for_an_element_is_not_equivalent(self) -> None:
        assert equivalent([1, 2], [1, 3]) is False

    def test_strings_compare_without_case(self) -> None:
        assert equivalent("Final", "final") is True
        assert equivalent("Final", "amended") is False

    @pytest.mark.parametrize(("left", "right", "expected"), [(1.0, 1.01, True), (1.0, 1.5, False)])
    def test_decimals_compare_at_the_coarser_precision(self, left: float, right: float, expected: bool) -> None:
        assert equivalent(left, right) is expected

    def test_quantities_convert_before_comparing(self) -> None:
        left = Quantity(value=Decimal("1000"), unit="mg")
        right = Quantity(value=Decimal("1"), unit="g")
        assert equivalent(left, right) is True

    def test_quantities_with_incompatible_units_are_not_equivalent(self) -> None:
        left = Quantity(value=Decimal("1"), unit="mg")
        right = Quantity(value=Decimal("1"), unit="m")
        assert equivalent(left, right) is False

    def test_one_datetime_with_a_timezone_and_one_without_are_not_equivalent(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, tz_offset="Z")
        right = date_time(year=2024, month=3, day=1, hour=8)
        assert equivalent(left, right) is False

    def test_two_datetimes_with_timezones_compare_in_utc(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0, tz_offset="Z")
        right = date_time(year=2024, month=3, day=1, hour=9, minute=0, second=0, tz_offset="+01:00")
        assert equivalent(left, right) is True

    def test_two_datetimes_without_timezones_normalize_the_millisecond(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0, millisecond=0)
        assert equivalent(left, right) is True
        assert equivalent(left, date_time(year=2024, month=3, day=1, hour=8, minute=0, second=1)) is False

    def test_times_normalize_their_missing_components(self) -> None:
        assert equivalent(FHIRTime(hour=8, minute=30), FHIRTime(hour=8, minute=30, second=0)) is True
        assert equivalent(FHIRTime(hour=8, minute=30), FHIRTime(hour=8, minute=31)) is False

    def test_values_of_unrelated_types_fall_back_to_plain_equality(self) -> None:
        assert equivalent({"code": "final"}, {"code": "final"}) is True
        assert equivalent({"code": "final"}, {"code": "amended"}) is False


class TestCompare:
    """Tests for FHIRPath ordering."""

    @pytest.mark.parametrize(("left", "right"), [(None, 1), (1, None), ([], 1), (1, [])])
    def test_an_absent_operand_is_not_orderable(self, left: Any, right: Any) -> None:
        assert compare(left, right) is None

    @pytest.mark.parametrize(("left", "right", "expected"), [(1, 2, -1), (2, 1, 1), (1, 1, 0)])
    def test_numbers(self, left: int, right: int, expected: int) -> None:
        assert compare(left, right) == expected

    def test_values_that_cannot_be_ordered_yield_nothing(self) -> None:
        assert compare(1, "a") is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (FHIRDate(year=2024, month=3, day=1), FHIRDateTime(year=2024, month=3, day=1, hour=8), None),
            (FHIRDate(year=2023, month=3, day=1), FHIRDateTime(year=2024, month=3, day=1, hour=8), -1),
            (FHIRDate(year=2025, month=3, day=1), FHIRDateTime(year=2024, month=3, day=1, hour=8), 1),
            (FHIRDate(year=2024, month=2, day=1), FHIRDateTime(year=2024, month=3, day=1, hour=8), -1),
            (FHIRDate(year=2024, month=4, day=1), FHIRDateTime(year=2024, month=3, day=1, hour=8), 1),
            (FHIRDate(year=2024, month=3, day=1), FHIRDateTime(year=2024, month=3, day=2, hour=8), -1),
            (FHIRDate(year=2024, month=3, day=3), FHIRDateTime(year=2024, month=3, day=2, hour=8), 1),
        ],
    )
    def test_a_date_against_a_datetime_carrying_a_time(self, left: Any, right: Any, expected: int | None) -> None:
        assert compare(left, right) == expected

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), FHIRDate(year=2024, month=3, day=1), None),
            (FHIRDateTime(year=2023, month=3, day=1, hour=8), FHIRDate(year=2024, month=3, day=1), -1),
            (FHIRDateTime(year=2025, month=3, day=1, hour=8), FHIRDate(year=2024, month=3, day=1), 1),
            (FHIRDateTime(year=2024, month=2, day=1, hour=8), FHIRDate(year=2024, month=3, day=1), -1),
            (FHIRDateTime(year=2024, month=4, day=1, hour=8), FHIRDate(year=2024, month=3, day=1), 1),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), FHIRDate(year=2024, month=3, day=2), -1),
            (FHIRDateTime(year=2024, month=3, day=3, hour=8), FHIRDate(year=2024, month=3, day=2), 1),
        ],
    )
    def test_a_datetime_carrying_a_time_against_a_date(self, left: Any, right: Any, expected: int | None) -> None:
        assert compare(left, right) == expected

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            (FHIRDate(year=2024), FHIRDateTime(year=2024, month=3, day=1, hour=8)),
            (FHIRDateTime(year=2024, hour=8), FHIRDate(year=2024, month=3, day=1)),
        ],
    )
    def test_a_year_only_operand_orders_as_equal_on_the_year(self, left: Any, right: Any) -> None:
        assert compare(left, right) == 0

    def test_one_datetime_with_a_timezone_and_one_without_are_not_orderable(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, tz_offset="Z")
        right = date_time(year=2024, month=3, day=1, hour=8)
        assert compare(left, right) is None

    def test_datetimes_at_different_date_precision_order_on_what_they_share(self) -> None:
        assert compare(date_time(year=2024, month=2), date_time(year=2024, month=3, day=5)) == -1
        assert compare(date_time(year=2024, month=3), date_time(year=2024, month=3, day=5)) is None

    def test_datetimes_at_different_second_precision_order_up_to_the_minute(self) -> None:
        coarse = date_time(year=2024, month=3, day=1, hour=8, minute=20)
        fine = date_time(year=2024, month=3, day=1, hour=8, minute=30, second=15)
        assert compare(coarse, fine) == -1
        assert compare(date_time(year=2024, month=3, day=1, hour=8, minute=30), fine) is None

    @pytest.mark.parametrize(
        ("left_hour", "right_hour", "right_tz", "expected"),
        [(8, 9, "Z", -1), (10, 9, "Z", 1), (9, 10, "+01:00", 0)],
    )
    def test_two_datetimes_with_timezones_order_in_utc(
        self, left_hour: int, right_hour: int, right_tz: str, expected: int
    ) -> None:
        left = date_time(year=2024, month=3, day=1, hour=left_hour, minute=0, second=0, tz_offset="Z")
        right = date_time(year=2024, month=3, day=1, hour=right_hour, minute=0, second=0, tz_offset=right_tz)
        assert compare(left, right) == expected

    def test_two_datetimes_without_timezones_order_on_their_components(self) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=0)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=0, second=1)
        assert compare(left, right) == -1

    def test_times_at_different_second_precision_order_up_to_the_minute(self) -> None:
        assert compare(FHIRTime(hour=8, minute=20), FHIRTime(hour=8, minute=30, second=15)) == -1
        assert compare(FHIRTime(hour=8, minute=30), FHIRTime(hour=8, minute=30, second=15)) is None

    def test_times_at_the_same_precision_order_on_their_components(self) -> None:
        assert compare(FHIRTime(hour=8, minute=30, second=15), FHIRTime(hour=8, minute=30, second=16)) == -1

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (FHIRDate(year=2023, month=3), FHIRDate(year=2024, month=3, day=1), -1),
            (FHIRDate(year=2025, month=3), FHIRDate(year=2024, month=3, day=1), 1),
            (FHIRDate(year=2024, month=2), FHIRDate(year=2024, month=3, day=1), -1),
            (FHIRDate(year=2024, month=4), FHIRDate(year=2024, month=3, day=1), 1),
            (FHIRDate(year=2024, month=3), FHIRDate(year=2024, month=3, day=1), None),
        ],
    )
    def test_dates_at_different_precision(self, left: FHIRDate, right: FHIRDate, expected: int | None) -> None:
        assert compare(left, right) == expected

    def test_date_strings_parse_before_ordering(self) -> None:
        assert compare("2023-06-15", "2024-01-01") == -1


class TestPrecisionHelpers:
    """Tests for the precision helpers the ordering rules lean on."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDateTime(year=2024), 1),
            (FHIRDateTime(year=2024, month=3), 2),
            (FHIRDateTime(year=2024, month=3, day=1), 3),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), 4),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30), 5),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15), 6),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=250), 7),
        ],
    )
    def test_datetime_precision(self, value: FHIRDateTime, expected: int) -> None:
        assert _get_datetime_precision(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=8), 1),
            (FHIRTime(hour=8, minute=30), 2),
            (FHIRTime(hour=8, minute=30, second=15), 3),
            (FHIRTime(hour=8, minute=30, second=15, millisecond=250), 4),
        ],
    )
    def test_time_precision(self, value: FHIRTime, expected: int) -> None:
        assert _get_time_precision(value) == expected

    @pytest.mark.parametrize(
        ("left", "right", "precision", "expected"),
        [
            (date_time(year=2023), date_time(year=2024), 1, -1),
            (date_time(year=2025), date_time(year=2024), 1, 1),
            (date_time(year=2024), date_time(year=2024), 1, 0),
            (date_time(year=2024, month=2), date_time(year=2024, month=3), 2, -1),
            (date_time(year=2024, month=4), date_time(year=2024, month=3), 2, 1),
            (date_time(year=2024, month=3), date_time(year=2024, month=3), 2, 0),
            (date_time(year=2024, month=3, day=1), date_time(year=2024, month=3, day=2), 3, -1),
            (date_time(year=2024, month=3, day=3), date_time(year=2024, month=3, day=2), 3, 1),
            (date_time(year=2024, month=3, day=2), date_time(year=2024, month=3, day=2), 3, 0),
            (date_time(year=2024, month=3, day=2, hour=7), date_time(year=2024, month=3, day=2, hour=8), 4, -1),
            (date_time(year=2024, month=3, day=2, hour=9), date_time(year=2024, month=3, day=2, hour=8), 4, 1),
            (date_time(year=2024, month=3, day=2, hour=8), date_time(year=2024, month=3, day=2, hour=8), 4, 0),
        ],
    )
    def test_datetime_comparison_stops_at_the_requested_precision(
        self, left: FHIRDateTime, right: FHIRDateTime, precision: int, expected: int
    ) -> None:
        assert _compare_datetime_to_precision(left, right, precision) == expected

    @pytest.mark.parametrize(
        ("left_minute", "right_minute", "expected"),
        [(20, 30, -1), (40, 30, 1), (30, 30, 0)],
    )
    def test_datetime_comparison_at_minute_precision(self, left_minute: int, right_minute: int, expected: int) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=left_minute)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=right_minute)
        assert _compare_datetime_to_precision(left, right, 5) == expected

    @pytest.mark.parametrize(
        ("left_second", "right_second", "expected"),
        [(10, 15, -1), (20, 15, 1), (15, 15, 0)],
    )
    def test_datetime_comparison_at_second_precision(self, left_second: int, right_second: int, expected: int) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=30, second=left_second)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=30, second=right_second)
        assert _compare_datetime_to_precision(left, right, 6) == expected

    @pytest.mark.parametrize(
        ("left_millisecond", "right_millisecond", "expected"),
        [(100, 250, -1), (400, 250, 1), (250, 250, 0)],
    )
    def test_datetime_comparison_at_millisecond_precision(
        self, left_millisecond: int, right_millisecond: int, expected: int
    ) -> None:
        left = date_time(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=left_millisecond)
        right = date_time(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=right_millisecond)
        assert _compare_datetime_to_precision(left, right, 7) == expected

    @pytest.mark.parametrize(
        ("left", "right", "precision", "expected"),
        [
            (FHIRTime(hour=7), FHIRTime(hour=8), 1, -1),
            (FHIRTime(hour=9), FHIRTime(hour=8), 1, 1),
            (FHIRTime(hour=8), FHIRTime(hour=8), 1, 0),
            (FHIRTime(hour=8, minute=20), FHIRTime(hour=8, minute=30), 2, -1),
            (FHIRTime(hour=8, minute=40), FHIRTime(hour=8, minute=30), 2, 1),
            (FHIRTime(hour=8, minute=30), FHIRTime(hour=8, minute=30), 2, 0),
            (FHIRTime(hour=8, minute=30, second=10), FHIRTime(hour=8, minute=30, second=15), 3, -1),
            (FHIRTime(hour=8, minute=30, second=20), FHIRTime(hour=8, minute=30, second=15), 3, 1),
            (FHIRTime(hour=8, minute=30, second=15), FHIRTime(hour=8, minute=30, second=15), 3, 0),
            (
                FHIRTime(hour=8, minute=30, second=15, millisecond=100),
                FHIRTime(hour=8, minute=30, second=15, millisecond=250),
                4,
                -1,
            ),
            (
                FHIRTime(hour=8, minute=30, second=15, millisecond=400),
                FHIRTime(hour=8, minute=30, second=15, millisecond=250),
                4,
                1,
            ),
            (
                FHIRTime(hour=8, minute=30, second=15, millisecond=250),
                FHIRTime(hour=8, minute=30, second=15, millisecond=250),
                4,
                0,
            ),
        ],
    )
    def test_time_comparison_stops_at_the_requested_precision(
        self, left: FHIRTime, right: FHIRTime, precision: int, expected: int
    ) -> None:
        assert _compare_time_to_precision(left, right, precision) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(Decimal("1.230"), 3), (Decimal("100"), 0), (Decimal("NaN"), 0), (Decimal("Infinity"), 0)],
    )
    def test_quantity_precision(self, value: Decimal, expected: int) -> None:
        assert _get_quantity_precision(value) == expected


class TestComparableFunction:
    """Tests for the comparable() function on quantities."""

    def test_quantities_with_convertible_units_are_comparable(self, context: EvaluationContext) -> None:
        left = Quantity(value=Decimal("1"), unit="mg")
        right = Quantity(value=Decimal("1"), unit="g")
        assert fn_comparable(context, [left], right) == [True]
        assert fn_comparable(context, [left], [right]) == [True]

    def test_quantities_with_unrelated_units_are_not_comparable(self, context: EvaluationContext) -> None:
        left = Quantity(value=Decimal("1"), unit="mg")
        right = Quantity(value=Decimal("1"), unit="m")
        assert fn_comparable(context, [left], right) == [False]

    @pytest.mark.parametrize(
        ("collection", "other"),
        [
            ([], Quantity(value=Decimal("1"), unit="mg")),
            (["not a quantity"], Quantity(value=Decimal("1"), unit="mg")),
            ([Quantity(value=Decimal("1"), unit="mg")], []),
            ([Quantity(value=Decimal("1"), unit="mg")], "not a quantity"),
        ],
    )
    def test_anything_that_is_not_a_pair_of_quantities_yields_empty(
        self, context: EvaluationContext, collection: list[Any], other: Any
    ) -> None:
        assert fn_comparable(context, collection, other) == []


class TestTypeChecking:
    """Tests for is(), as(), ofType(), and type()."""

    @pytest.mark.parametrize(
        ("item", "type_name"),
        [
            (True, "FHIR.Boolean"),
            (5, "FHIR.Integer"),
            (1.5, "FHIR.Decimal"),
            ("final", "FHIR.String"),
            (True, "System.boolean"),
            (5, "System.integer"),
            (1.5, "System.decimal"),
            ("final", "System.string"),
            ({"resourceType": "Patient"}, "System.Patient"),
        ],
    )
    def test_a_namespace_that_cannot_hold_the_type_never_matches(self, item: Any, type_name: str) -> None:
        assert fn_is(EvaluationContext(), [item], type_name) == [False]

    @pytest.mark.parametrize(
        ("value", "type_name"),
        [(True, "Boolean"), (5, "Integer"), (1.5, "Decimal"), ("final", "String")],
    )
    def test_a_fhir_element_is_not_a_system_type(self, value: Any, type_name: str) -> None:
        wrapped = _PrimitiveWithExtension(value, element_name="field", resource_type="Observation")
        assert fn_is(EvaluationContext(), [wrapped], type_name) == [False]
        assert fn_is(EvaluationContext(), [value], type_name) == [True]

    def test_a_fhir_element_type_is_not_a_system_type(self) -> None:
        wrapped = _PrimitiveWithExtension("final", element_name="status", resource_type="Observation")
        assert fn_is(EvaluationContext(), [wrapped], "System.code") == [False]
        assert fn_is(EvaluationContext(), [wrapped], "code") == [True]

    @pytest.mark.parametrize(
        ("item", "type_name", "expected"),
        [
            (5, "positiveInt", True),
            (0, "positiveInt", False),
            (-1, "positiveInt", False),
            (0, "unsignedInt", True),
            (-1, "unsignedInt", False),
            (7, "integer64", True),
            ("seven", "integer64", False),
            ("anything", "Element", True),
            ({"resourceType": "Patient"}, "Resource", True),
            ({"coding": []}, "Resource", False),
        ],
    )
    def test_the_fhir_numeric_and_base_types(self, item: Any, type_name: str, expected: bool) -> None:
        assert fn_is(EvaluationContext(), [item], type_name) == [expected]

    @pytest.mark.parametrize(
        ("item", "type_name", "expected"),
        [
            ({"_fhir_type": "Age", "value": 5}, "Quantity", True),
            ({"_fhir_type": "Age", "value": 5}, "Age", True),
            ({"_fhir_type": "Age", "value": 5}, "Duration", False),
            ({"_fhir_type": "Age", "value": 5}, "Coding", False),
        ],
    )
    def test_a_choice_type_carries_its_own_type_name(self, item: Any, type_name: str, expected: bool) -> None:
        assert fn_is(EvaluationContext(), [item], type_name) == [expected]

    @pytest.mark.parametrize(
        ("item", "type_name"),
        [
            ({"code": "final"}, "Coding"),
            ({"text": "blood pressure"}, "CodeableConcept"),
            ({"reference": "Patient/1"}, "Reference"),
            ({"value": "12345"}, "Identifier"),
            ({"start": "2024-03-01"}, "Period"),
            ({"family": "Lovelace"}, "HumanName"),
            ({"city": "Oslo"}, "Address"),
            ({"system": "phone"}, "ContactPoint"),
        ],
    )
    def test_a_complex_type_is_recognised_by_its_characteristic_fields(self, item: Any, type_name: str) -> None:
        assert fn_is(EvaluationContext(), [item], type_name) == [True]

    def test_a_string_subtype_is_a_string_for_is_but_not_for_as(self) -> None:
        wrapped = _PrimitiveWithExtension("final", element_name="status", resource_type="Observation")
        assert fn_is(EvaluationContext(), [wrapped], "string") == [True]
        assert fn_as(EvaluationContext(), [wrapped], "string") == []
        assert fn_as(EvaluationContext(), [wrapped], "code") == [wrapped]

    def test_a_uri_subtype_is_a_uri(self) -> None:
        url = _PrimitiveWithExtension("http://example.org/Questionnaire/1", element_name="url", resource_type=None)
        assert fn_is(EvaluationContext(), [url], "uri") == [True]

    def test_a_plain_string_carries_no_fhir_element_type(self) -> None:
        assert fn_is(EvaluationContext(), ["final"], "code") == [False]

    @pytest.mark.parametrize(
        ("item", "expected"),
        [
            (FHIRDateTime(year=2024), {"namespace": "System", "name": "DateTime"}),
            (FHIRDate(year=2024), {"namespace": "System", "name": "Date"}),
            (FHIRTime(hour=8), {"namespace": "System", "name": "Time"}),
            (True, {"namespace": "System", "name": "Boolean"}),
            (5, {"namespace": "System", "name": "Integer"}),
            (1.5, {"namespace": "System", "name": "Decimal"}),
            (Decimal("1.5"), {"namespace": "System", "name": "Decimal"}),
            ("final", {"namespace": "System", "name": "String"}),
            (Quantity(value=Decimal("1"), unit="mg"), {"namespace": "System", "name": "Quantity"}),
            ({"resourceType": "Patient"}, {"namespace": "FHIR", "name": "Patient"}),
            ({"coding": []}, {"namespace": "FHIR", "name": "Element"}),
            (None, {"namespace": "System", "name": "Any"}),
        ],
    )
    def test_type_names_the_namespace_and_the_type(self, item: Any, expected: dict[str, str]) -> None:
        assert fn_type(EvaluationContext(), [item]) == [expected]

    @pytest.mark.parametrize(
        ("value", "expected_name"),
        [(True, "boolean"), (5, "integer"), (1.5, "decimal"), ("final", "string")],
    )
    def test_a_wrapped_primitive_reads_as_a_fhir_type(self, value: Any, expected_name: str) -> None:
        wrapped = _PrimitiveWithExtension(value, element_name="field", resource_type="Observation")
        assert fn_type(EvaluationContext(), [wrapped]) == [{"namespace": "FHIR", "name": expected_name}]

    @pytest.mark.parametrize(
        ("item", "expected"),
        [(FHIRDate(year=2024), "Date"), (5, "Integer"), ({"resourceType": "Patient"}, "Patient"), (None, "Any")],
    )
    def test_the_bare_type_name_drops_the_namespace(self, item: Any, expected: str) -> None:
        assert _get_type_name(item) == expected

    def test_of_type_keeps_only_exact_matches(self) -> None:
        collection: list[Any] = [
            5,
            "final",
            {"resourceType": "Patient", "id": "p1"},
            {"resourceType": "Observation", "id": "o1"},
        ]
        assert fn_of_type(EvaluationContext(), collection, "Patient") == [{"resourceType": "Patient", "id": "p1"}]

    def test_the_type_functions_propagate_the_empty_collection(self) -> None:
        context = EvaluationContext()
        assert fn_type(context, []) == []
        assert fn_is(context, [], "Patient") == []
        assert fn_as(context, [], "Patient") == []
        assert fn_of_type(context, [], "Patient") == []
