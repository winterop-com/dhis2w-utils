"""Tests for CQL operator, literal, and selector constructs evaluated through the visitor.

Every case here drives `CQLEvaluatorVisitor` by evaluating CQL source, which is the only way to
reach the grammar-shaped branches: quantity and ratio literals, interval and list selectors,
successor/predecessor, `convert`, `duration in`, type extents, and the interval/age built-ins.
"""

from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql import CQLCode, CQLConcept, CQLEvaluator, CQLInterval, CQLRatio, CQLTuple
from dhis2w_fhir_engine.engine.exceptions import CQLError
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

PATIENT_BORN_1990: dict[str, Any] = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}


@pytest.fixture
def evaluator() -> CQLEvaluator:
    """Create a CQL evaluator."""
    return CQLEvaluator()


class TestQuantityAndRatioLiterals:
    """Quantity and ratio literals build engine value types."""

    def test_integer_quantity(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("5 'mg'")
        assert result == Quantity(value=Decimal("5"), unit="mg")

    def test_decimal_quantity(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("5.5 'mg'")
        assert result == Quantity(value=Decimal("5.5"), unit="mg")

    def test_ratio_literal(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("1 'mg' : 10 'mL'")
        assert result == CQLRatio(
            numerator=Quantity(value=Decimal("1"), unit="mg"),
            denominator=Quantity(value=Decimal("10"), unit="mL"),
        )

    def test_long_number_literal(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("100L") == 100


class TestPartialPrecisionDateLiterals:
    """Date, time, and datetime literals keep the precision they were written with."""

    def test_year_only_date(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@2020") == FHIRDate(year=2020, month=None, day=None)

    def test_year_month_date(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@2020-05") == FHIRDate(year=2020, month=5, day=None)

    def test_full_date(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@2020-05-04") == FHIRDate(year=2020, month=5, day=4)

    def test_hour_only_time(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@T10") == FHIRTime(hour=10, minute=None, second=None, millisecond=None)

    def test_hour_minute_time(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@T10:30") == FHIRTime(hour=10, minute=30, second=None, millisecond=None)

    def test_datetime_with_milliseconds(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@2020-01-01T10:00:00.500") == FHIRDateTime(
            year=2020, month=1, day=1, hour=10, minute=0, second=0, millisecond=500
        )


class TestSelectors:
    """Tuple and instance selectors build tuples and typed dictionaries."""

    def test_tuple_selector_with_keyword(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Tuple { a: 1, b: 'x' }") == CQLTuple(elements={"a": 1, "b": "x"})

    def test_tuple_selector_without_keyword(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("{ a: 1, b: 2 }") == CQLTuple(elements={"a": 1, "b": 2})

    def test_instance_selector_records_type_name(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("FHIR.Patient { id: 'p1' }") == {
            "resourceType": "FHIR.Patient",
            "id": "p1",
        }

    def test_instance_selector_evaluates_element_expressions(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Quantity { value: 2 + 3 }") == {"resourceType": "Quantity", "value": 5}


class TestIntervalSelectorBounds:
    """Interval selectors honour open, closed, and null bounds."""

    def test_null_low_bound(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Interval[null, 10]")
        assert result == CQLInterval(low=None, high=10, low_closed=True, high_closed=True)

    def test_null_high_bound(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Interval[1, null]")
        assert result == CQLInterval(low=1, high=None, low_closed=True, high_closed=True)

    def test_both_bounds_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[null, null]") is None

    def test_unit_interval_is_allowed(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[5, 5]") == CQLInterval(low=5, high=5)


class TestQuantityArithmetic:
    """Arithmetic on quantities keeps the unit and rejects mismatched units."""

    def test_add_same_unit(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("5 'mg' + 3 'mg'") == Quantity(value=Decimal("8"), unit="mg")

    def test_add_mismatched_units_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("5 'mg' + 3 'g'") is None

    def test_subtract_same_unit(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("5 'mg' - 3 'mg'") == Quantity(value=Decimal("2"), unit="mg")

    def test_subtract_mismatched_units_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("5 'mg' - 3 'g'") is None

    def test_multiply_quantity_by_number(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("5 'mg' * 2") == Quantity(value=Decimal("10"), unit="mg")

    def test_multiply_number_by_quantity(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("2 * 5 'mg'") == Quantity(value=Decimal("10"), unit="mg")

    def test_divide_quantity_by_number(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("10 'mg' / 2") == Quantity(value=Decimal("5.00000000"), unit="mg")


class TestIntervalArithmetic:
    """Arithmetic on intervals shifts and scales both bounds."""

    def test_add_two_intervals(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[1, 2] + Interval[10, 20]") == CQLInterval(low=11, high=22)

    def test_add_scalar_to_interval(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[1, 2] + 5") == CQLInterval(low=6, high=7)

    def test_add_interval_to_scalar(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("5 + Interval[1, 2]") == CQLInterval(low=6, high=7)

    def test_subtract_two_intervals(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[10, 20] - Interval[1, 2]") == CQLInterval(low=8, high=19)

    def test_subtract_scalar_from_interval(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[10, 20] - 5") == CQLInterval(low=5, high=15)

    def test_subtract_interval_from_scalar_reverses_bounds(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("30 - Interval[1, 2]") == CQLInterval(low=28, high=29)

    def test_multiply_two_intervals(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[1, 2] * Interval[3, 4]") == CQLInterval(low=3, high=8)

    def test_multiply_interval_by_scalar(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[1, 2] * 3") == CQLInterval(low=3, high=6)

    def test_multiply_scalar_by_interval(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("3 * Interval[1, 2]") == CQLInterval(low=3, high=6)


DATE_ARITHMETIC_CASES: list[tuple[str, Any]] = [
    ("@2020-01-01 + 1 year", FHIRDate(year=2021, month=1, day=1)),
    ("@2020-02-29 + 1 year", FHIRDate(year=2021, month=2, day=28)),
    ("@2020-01-31 + 1 month", FHIRDate(year=2020, month=2, day=29)),
    ("@2020-01-01 + 2 weeks", FHIRDate(year=2020, month=1, day=15)),
    ("@2020-01-01 + 10 days", FHIRDate(year=2020, month=1, day=11)),
    ("@2020 + 1 year", FHIRDate(year=2021, month=None, day=None)),
    ("@2020-05 + 1 month", FHIRDate(year=2020, month=6, day=None)),
    ("@2020-01-01 - 1 year", FHIRDate(year=2019, month=1, day=1)),
    ("@2020-01-01 - 1 month", FHIRDate(year=2019, month=12, day=1)),
    ("@2020-03-01 - 10 days", FHIRDate(year=2020, month=2, day=20)),
]

DATETIME_ARITHMETIC_CASES: list[tuple[str, Any]] = [
    (
        "@2020-01-01T10:00:00 + 1 hour",
        FHIRDateTime(year=2020, month=1, day=1, hour=11, minute=0, second=0),
    ),
    (
        "@2020-01-01T10:00:00 + 30 minutes",
        FHIRDateTime(year=2020, month=1, day=1, hour=10, minute=30, second=0),
    ),
    (
        "@2020-01-01T10:00:00 + 45 seconds",
        FHIRDateTime(year=2020, month=1, day=1, hour=10, minute=0, second=45),
    ),
    (
        "@2020-01-01T10:00:00.000 + 500 milliseconds",
        FHIRDateTime(year=2020, month=1, day=1, hour=10, minute=0, second=0, millisecond=500),
    ),
    (
        "@2020-01-01T10:00:00 + 1 year",
        FHIRDateTime(year=2021, month=1, day=1, hour=10, minute=0, second=0),
    ),
    (
        "@2020-01-01T10:00:00 + 1 month",
        FHIRDateTime(year=2020, month=2, day=1, hour=10, minute=0, second=0),
    ),
    (
        "@2020-01-01T10:00:00 + 1 day",
        FHIRDateTime(year=2020, month=1, day=2, hour=10, minute=0, second=0),
    ),
    (
        "@2020-01-01T10:00:00 - 1 hour",
        FHIRDateTime(year=2020, month=1, day=1, hour=9, minute=0, second=0),
    ),
    (
        "@2020-05T + 1 month",
        FHIRDateTime(year=2020, month=6, day=None),
    ),
]


class TestDateArithmetic:
    """Adding and subtracting quantities from dates and datetimes."""

    @pytest.mark.parametrize(("expression", "expected"), DATE_ARITHMETIC_CASES)
    def test_date_plus_duration(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    @pytest.mark.parametrize(("expression", "expected"), DATETIME_ARITHMETIC_CASES)
    def test_datetime_plus_duration(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_month_on_year_only_date_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@2020 + 1 month") is None

    def test_time_plus_duration(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@T10:00:00 + 1 hour") == FHIRTime(hour=11, minute=0, second=0)

    def test_date_minus_date_is_days(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("@2020-01-11 - @2020-01-01") == 10


COMPONENT_CASES: list[tuple[str, Any]] = [
    ("year from @2020-05-04", 2020),
    ("month from @2020-05-04", 5),
    ("day from @2020-05-04", 4),
    ("hour from @2020-05-04T10:20:30.400", 10),
    ("minute from @2020-05-04T10:20:30.400", 20),
    ("second from @2020-05-04T10:20:30.400", 30),
    ("millisecond from @2020-05-04T10:20:30.400", 400),
    ("millisecond from @T10:20:30.400", 400),
    ("timezone from @2020-05-04T10:20:30.400Z", Decimal("0")),
    ("date from @2020-05-04T10:20:30.400", FHIRDate(year=2020, month=5, day=4)),
    ("time from @2020-05-04T10:20:30.400", FHIRTime(hour=10, minute=20, second=30, millisecond=400)),
]


class TestComponentExtraction:
    """The `<component> from <value>` form pulls one field out of a date, time, or datetime."""

    @pytest.mark.parametrize(("expression", "expected"), COMPONENT_CASES)
    def test_component(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_component_of_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("year from null") is None


TIMEZONE_CASES: list[tuple[str, Decimal]] = [
    ("TimezoneFrom(@2020-01-01T10:00:00Z)", Decimal("0")),
    ("TimezoneFrom(@2020-01-01T10:00:00+01:00)", Decimal("1.0")),
    ("TimezoneFrom(@2020-01-01T10:00:00-05:30)", Decimal("-5.5")),
    ("TimezoneOffsetFrom(@2020-01-01T10:00:00Z)", Decimal("0")),
]


class TestIntervalBuiltins:
    """The function-call spellings of the interval accessors."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Start(Interval[1, 10])", 1),
            ("StartOf(Interval[1, 10])", 1),
            ("End(Interval[1, 10])", 10),
            ("EndOf(Interval[1, 10])", 10),
            ("Width(Interval[1, 10])", 9),
            ("WidthOf(Interval[1, 10])", 9),
            ("Size(Interval[1, 10])", 10),
            ("SizeOf(Interval[1, 10])", 10),
        ],
    )
    def test_accessor(self, evaluator: CQLEvaluator, expression: str, expected: int) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    @pytest.mark.parametrize(
        "expression",
        ["Start(5)", "End(5)", "Width(5)", "Size(5)"],
    )
    def test_accessor_on_non_interval_is_null(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None

    def test_size_of_open_interval_drops_the_closed_bonus(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Size(Interval(1, 10))") == 9

    def test_point_from_function_on_unit_interval(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("PointFrom(Interval[3, 3])") == 3

    def test_point_from_function_on_scalar_returns_the_scalar(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("PointFrom(5)") == 5

    def test_collapse_function_merges_overlapping_intervals(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Collapse({Interval[1, 3], Interval[2, 5]})")
        assert result == [CQLInterval(low=1, high=5)]

    def test_collapse_function_keeps_disjoint_intervals(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Collapse({Interval[1, 3], Interval[7, 9]})")
        assert result == [CQLInterval(low=1, high=3), CQLInterval(low=7, high=9)]

    def test_collapse_function_on_non_list_is_empty(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Collapse(5)") == []

    def test_expand_function_without_step(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Expand(Interval[1, 4])") == [1, 2, 3, 4]

    def test_expand_function_with_step(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Expand(Interval[1, 10], 2)") == [1, 3, 5, 7, 9]

    def test_expand_function_on_non_interval_is_empty(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Expand(5)") == []

    @pytest.mark.parametrize(("expression", "expected"), TIMEZONE_CASES)
    def test_timezone_from(self, evaluator: CQLEvaluator, expression: str, expected: Decimal) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_timezone_from_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("TimezoneFrom(null)") is None


class TestKeywordIntervalOperators:
    """The keyword spellings `width of`, `start of`, `end of`, `collapse`, and `expand`."""

    def test_width_of(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("width of Interval[1, 10]") == 9

    def test_width_of_non_interval_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("width of 5") is None

    def test_start_of(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("start of Interval[1, 10]") == 1

    def test_end_of(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("end of Interval[1, 10]") == 10

    def test_start_of_non_interval_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("start of 5") is None

    def test_start_of_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("start of null") is None

    def test_collapse_keyword(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("collapse {Interval[1, 3], Interval[2, 6]}") == [
            CQLInterval(low=1, high=6)
        ]

    def test_collapse_keyword_on_non_list_is_empty(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("collapse 5") == []

    def test_expand_keyword_on_interval(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("expand Interval[1, 5]") == [1, 2, 3, 4, 5]

    def test_expand_keyword_on_list_of_intervals(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("expand {Interval[1, 3]}") == [1, 2, 3]

    def test_expand_keyword_on_non_interval_is_empty(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("expand 5") == []

    def test_expand_date_interval_per_month(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("expand Interval[@2020-01-01, @2020-03-01] per month")
        assert result == [
            CQLInterval(low=FHIRDate(year=2020, month=1, day=1), high=FHIRDate(year=2020, month=1, day=31)),
            CQLInterval(low=FHIRDate(year=2020, month=2, day=1), high=FHIRDate(year=2020, month=2, day=29)),
            CQLInterval(low=FHIRDate(year=2020, month=3, day=1), high=FHIRDate(year=2020, month=3, day=1)),
        ]

    def test_expand_list_of_date_intervals_per_month(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("expand {Interval[@2020-01-01, @2020-02-01]} per month")
        assert result == [
            CQLInterval(low=FHIRDate(year=2020, month=1, day=1), high=FHIRDate(year=2020, month=1, day=31)),
            CQLInterval(low=FHIRDate(year=2020, month=2, day=1), high=FHIRDate(year=2020, month=2, day=1)),
        ]


class TestElementAndPointExtractors:
    """`singleton from` and `point from`."""

    def test_singleton_from_one_element(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("singleton from {1}") == 1

    def test_singleton_from_empty_list_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("singleton from {}") is None

    def test_singleton_from_scalar_returns_the_scalar(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("singleton from 5") == 5

    def test_point_from_unit_interval(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("point from Interval[3, 3]") == 3

    def test_point_from_non_interval_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("point from 5") is None


class TestDistinctAndFlattenKeywords:
    """`distinct` and `flatten` as prefix operators."""

    def test_distinct_drops_duplicates_and_nulls(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("distinct {1, 1, 2, null}") == [1, 2]

    def test_distinct_on_scalar_returns_the_scalar(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("distinct 5") == 5

    def test_flatten_one_level(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("flatten {{1, 2}, {3}}") == [1, 2, 3]

    def test_flatten_on_scalar_returns_the_scalar(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("flatten 5") == 5


SUCCESSOR_CASES: list[tuple[str, Any]] = [
    ("successor of 1", 2),
    ("successor of 1.5", Decimal("1.50000001")),
    ("successor of @2020-01-31", FHIRDate(year=2020, month=2, day=1)),
    (
        "successor of @2020-01-01T10:00:00",
        FHIRDateTime(year=2020, month=1, day=1, hour=10, minute=0, second=0, millisecond=1),
    ),
    ("successor of @2020-01-01T", FHIRDateTime(year=2020, month=1, day=2)),
    ("successor of @T10:00:00.000", FHIRTime(hour=10, minute=0, second=0, millisecond=1)),
    ("successor of 5 'mg'", Quantity(value=Decimal("5.00000001"), unit="mg")),
]

PREDECESSOR_CASES: list[tuple[str, Any]] = [
    ("predecessor of 1", 0),
    ("predecessor of 1.5", Decimal("1.49999999")),
    ("predecessor of @2020-02-01", FHIRDate(year=2020, month=1, day=31)),
    (
        "predecessor of @2020-01-01T10:00:00.000",
        FHIRDateTime(year=2020, month=1, day=1, hour=9, minute=59, second=59, millisecond=999),
    ),
    ("predecessor of @T10:00:00.000", FHIRTime(hour=9, minute=59, second=59, millisecond=999)),
    ("predecessor of 5 'mg'", Quantity(value=Decimal("4.99999999"), unit="mg")),
]


class TestSuccessorAndPredecessor:
    """`successor of` and `predecessor of` step one unit at the value's own precision."""

    @pytest.mark.parametrize(("expression", "expected"), SUCCESSOR_CASES)
    def test_successor(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    @pytest.mark.parametrize(("expression", "expected"), PREDECESSOR_CASES)
    def test_predecessor(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    @pytest.mark.parametrize("expression", ["successor of null", "predecessor of null"])
    def test_step_of_null_is_null(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None

    @pytest.mark.parametrize("expression", ["successor of 'abc'", "predecessor of 'abc'"])
    def test_step_of_string_is_null(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None


CONVERT_CASES: list[tuple[str, Any]] = [
    ("convert 5 to String", "5"),
    ("convert '42' to Integer", 42),
    ("convert '2.5' to Decimal", Decimal("2.5")),
    ("convert 'true' to Boolean", True),
    ("convert 'no' to Boolean", False),
    ("convert '2020-01-02' to Date", FHIRDate(year=2020, month=1, day=2)),
    (
        "convert '2020-01-02T10:00:00' to DateTime",
        FHIRDateTime(year=2020, month=1, day=2, hour=10, minute=0, second=0),
    ),
    ("convert '10:30:00' to Time", FHIRTime(hour=10, minute=30, second=0)),
    ("convert 5 to Quantity", Quantity(value=Decimal("5"), unit="1")),
]


class TestConvert:
    """`convert X to <type>` and `convert X to '<unit>'`."""

    @pytest.mark.parametrize(("expression", "expected"), CONVERT_CASES)
    def test_convert_to_type(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_convert_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("convert null to Integer") is None

    def test_convert_number_to_unit(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("convert 5 to 'mg'") == Quantity(value=Decimal("5"), unit="mg")

    def test_convert_quantity_to_unit(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("convert 5 'g' to 'mg'") == Quantity(value=Decimal("5"), unit="mg")


DURATION_CASES: list[tuple[str, int]] = [
    ("duration in days of Interval[@2020-01-01, @2020-01-11]", 10),
    ("duration in years of Interval[@2020-01-01, @2024-06-01]", 4),
    ("duration in months of Interval[@2020-01-01, @2020-04-15]", 3),
    ("duration in weeks of Interval[@2020-01-01, @2020-01-29]", 4),
    ("duration in hours of Interval[@2020-01-01T00:00:00, @2020-01-01T10:00:00]", 10),
    ("duration in minutes of Interval[@2020-01-01T00:00:00, @2020-01-01T00:30:00]", 30),
    ("duration in seconds of Interval[@2020-01-01T00:00:00, @2020-01-01T00:00:45]", 45),
    (
        "duration in milliseconds of Interval[@2020-01-01T00:00:00.000, @2020-01-01T00:00:00.500]",
        500,
    ),
    ("duration in days of Interval[@2020-01-01T00:00:00, @2020-01-11T00:00:00]", 10),
    ("duration in hours of Interval[@T01:00:00, @T05:00:00]", 4),
    ("duration in minutes of Interval[@T01:00:00, @T01:45:00]", 45),
    ("duration in seconds of Interval[@T01:00:00, @T01:00:20]", 20),
    ("duration in milliseconds of Interval[@T01:00:00.000, @T01:00:00.250]", 250),
]


class TestDurationAndDifference:
    """`duration in <precision> of` and `difference in <precision> of` over an interval."""

    @pytest.mark.parametrize(("expression", "expected"), DURATION_CASES)
    def test_duration(self, evaluator: CQLEvaluator, expression: str, expected: int) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_difference_in_days(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("difference in days of Interval[@2020-01-01, @2020-01-11]") == 10

    def test_difference_in_months(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("difference in months of Interval[@2020-01-01, @2020-04-15]") == 3

    def test_duration_of_non_interval_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("duration in days of 5") is None

    def test_difference_of_non_interval_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("difference in days of 5") is None


TYPE_EXTENT_CASES: list[tuple[str, Any]] = [
    ("minimum Integer", -(2**31)),
    ("maximum Integer", 2**31 - 1),
    ("minimum Long", -(2**63)),
    ("maximum Long", 2**63 - 1),
    ("minimum Decimal", Decimal("-9999999999999999999999999999.99999999")),
    ("maximum Decimal", Decimal("9999999999999999999999999999.99999999")),
    ("minimum Date", FHIRDate(year=1, month=1, day=1)),
    ("maximum Date", FHIRDate(year=9999, month=12, day=31)),
    ("minimum DateTime", FHIRDateTime(year=1, month=1, day=1, hour=0, minute=0, second=0, millisecond=0)),
    (
        "maximum DateTime",
        FHIRDateTime(year=9999, month=12, day=31, hour=23, minute=59, second=59, millisecond=999),
    ),
    ("minimum Time", FHIRTime(hour=0, minute=0, second=0, millisecond=0)),
    ("maximum Time", FHIRTime(hour=23, minute=59, second=59, millisecond=999)),
    ("minimum Quantity", Quantity(value=Decimal("-9999999999999999999999999999.99999999"), unit="1")),
    ("maximum Quantity", Quantity(value=Decimal("9999999999999999999999999999.99999999"), unit="1")),
]


class TestTypeExtents:
    """`minimum <type>` and `maximum <type>`."""

    @pytest.mark.parametrize(("expression", "expected"), TYPE_EXTENT_CASES)
    def test_extent(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_extent_of_unsupported_type_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("minimum String") is None


IS_TYPE_CASES: list[tuple[str, bool]] = [
    ("1 is Integer", True),
    ("1 is Decimal", False),
    ("1.5 is Decimal", True),
    ("'x' is String", True),
    ("true is Boolean", True),
    ("@2020-01-01 is Date", True),
    ("@2020-01-01T10:00:00 is DateTime", True),
    ("@T10:00:00 is Time", True),
    ("5 'mg' is Quantity", True),
    ("null is Integer", False),
    ("1 is String", False),
    ("1 is Patient", False),
]


class TestTypeTestingAndCasting:
    """`is`, `as`, and `cast ... as`."""

    @pytest.mark.parametrize(("expression", "expected"), IS_TYPE_CASES)
    def test_is_type(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected

    def test_as_string(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("1 as String") == "1"

    def test_as_integer_from_numeric_string(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("'42' as Integer") == 42

    def test_as_integer_from_non_numeric_string_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("'x' as Integer") is None

    def test_as_decimal_from_numeric_string(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("'2.5' as Decimal") == Decimal("2.5")

    @pytest.mark.parametrize("expression", ["'x' as Decimal", "'1.2.3' as Decimal", "cast 'x' as Decimal"])
    def test_as_decimal_from_a_string_that_is_no_decimal_is_null(
        self, evaluator: CQLEvaluator, expression: str
    ) -> None:
        """A cast that cannot be made answers null; it does not leak the decimal module's own error."""
        assert evaluator.evaluate_expression(expression) is None

    @pytest.mark.parametrize("expression", ["ToDecimal('x')", "ToDecimal('1.2.3')"])
    def test_to_decimal_from_a_string_that_is_no_decimal_is_null(
        self, evaluator: CQLEvaluator, expression: str
    ) -> None:
        assert evaluator.evaluate_expression(expression) is None

    def test_as_boolean_from_string(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("'true' as Boolean") is True

    def test_as_boolean_from_boolean(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("true as Boolean") is True

    def test_as_unknown_type_passes_the_value_through(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("1 as Patient") == 1

    def test_as_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("null as String") is None

    def test_cast_as_string(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("cast 1 as String") == "1"

    def test_cast_as_integer(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("cast '42' as Integer") == 42

    def test_cast_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("cast null as Integer") is None


PRECISION_TIMING_CASES: list[tuple[str, bool]] = [
    ("@2020-05-10 after year of @2019-01-01", True),
    ("@2020-05-10 before year of @2021-01-01", True),
    ("@2020-05-10 after month of @2020-04-01", True),
    ("@2020-05-10 before day of @2020-05-11", True),
    ("@2020-05-10 same day as @2020-05-10", True),
    ("@2020-05-10 same month as @2020-05-20", True),
    ("@2020-05-10 same year as @2020-11-20", True),
    ("@2020-05-10 same day or before @2020-05-11", True),
    ("@2020-05-10 same day or after @2020-05-09", True),
    ("@2020-05-10 on or before @2020-05-11", True),
    ("@2020-05-10 on or after @2020-05-09", True),
    ("@2020-05-10 before @2020-05-11", True),
    ("@2020-05-10 after @2020-05-09", True),
    ("@2020-05-10 same day as @2020-05-11", False),
    ("@2020-05-10 same year as @2021-05-10", False),
    ("@2020-05-10 after year of @2021-01-01", False),
]


class TestPointTiming:
    """Point-to-point timing comparisons with and without a precision qualifier."""

    @pytest.mark.parametrize(("expression", "expected"), PRECISION_TIMING_CASES)
    def test_timing(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected

    @pytest.mark.parametrize(
        "expression",
        ["null before @2020-05-09", "@2020-05-10 same day as null", "null same day or before @2020-05-09"],
    )
    def test_timing_with_null_operand_is_null(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None


INTERVAL_TIMING_CASES: list[tuple[str, bool]] = [
    ("Interval[1, 5] starts Interval[1, 9]", True),
    ("Interval[1, 5] ends Interval[0, 5]", True),
    ("Interval[1, 5] overlaps before Interval[3, 9]", True),
    ("Interval[5, 9] overlaps after Interval[1, 7]", True),
    ("Interval[1, 5] meets Interval[6, 9]", True),
    ("Interval[1, 5] properly includes Interval[2, 4]", True),
    ("Interval[2, 4] properly included in Interval[1, 5]", True),
    ("Interval[1, 5] during Interval[0, 9]", True),
    ("Interval[1, 5] starts Interval[2, 9]", False),
    ("Interval[1, 5] ends Interval[0, 6]", False),
]

LIST_TIMING_CASES: list[tuple[str, bool]] = [
    ("{1, 2, 3} includes {1, 2}", True),
    ("{1, 2} included in {1, 2, 3}", True),
    ("{1, 2, 3} properly includes {1, 2}", True),
    ("{1, 2} properly included in {1, 2, 3}", True),
    ("{1, 2, 3} includes 2", True),
    ("2 included in {1, 2, 3}", True),
    ("{1, null} includes null", True),
    ("{1, 2, 3} includes {}", True),
    ("{} included in {1, 2}", True),
    ("{1, 2, 3} properly includes {}", True),
    ("{1, 2, 3} includes {4}", False),
    ("{1, 2, 3} properly includes {1, 2, 3}", False),
    ("{1, 2, 3} includes 9", False),
]


class TestIntervalAndListTiming:
    """Timing phrases applied to intervals and to lists."""

    @pytest.mark.parametrize(("expression", "expected"), INTERVAL_TIMING_CASES)
    def test_interval_timing(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected

    @pytest.mark.parametrize(("expression", "expected"), LIST_TIMING_CASES)
    def test_list_timing(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected


PROPER_INCLUSION_CASES: list[tuple[str, bool]] = [
    # An interval never properly includes an interval that includes it back - the same interval.
    ("Interval[1, 10] properly includes Interval[1, 10]", False),
    ("Interval[1, 10] properly included in Interval[1, 10]", False),
    ("Interval[1, 10] properly includes Interval[1, 9]", True),
    ("Interval[1, 10] properly includes Interval[2, 10]", True),
    ("Interval[1, 10] properly includes Interval[2, 9]", True),
    ("Interval[2, 9] properly included in Interval[1, 10]", True),
    ("Interval[1, 10] properly includes Interval[5, 20]", False),
    # Plain inclusion is unchanged: an interval does include itself.
    ("Interval[1, 10] includes Interval[1, 10]", True),
    ("Interval[1, 10] included in Interval[1, 10]", True),
    # A half-open bound narrows the operand, so the closed interval properly includes it.
    ("Interval[1, 10] properly includes Interval[1, 10)", True),
    ("Interval[1, 10) properly includes Interval[1, 10]", False),
    # Lists answer the same way.
    ("{1, 2, 3} properly includes {1, 2, 3}", False),
    ("{1, 2, 3} properly included in {1, 2, 3}", False),
    ("{1, 2, 3} properly includes {1, 2}", True),
]


class TestProperInclusion:
    """`properly includes` and `properly included in` demand more than plain inclusion."""

    @pytest.mark.parametrize(("expression", "expected"), PROPER_INCLUSION_CASES)
    def test_proper_inclusion(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected


class TestIndexingAndPropertyAccess:
    """List indexing and property access on tuples, intervals, dictionaries, and lists."""

    def test_index_into_list(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("{10, 20, 30}[1]") == 20

    def test_index_out_of_range_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("{10, 20, 30}[5]") is None

    def test_index_with_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("{10, 20, 30}[null]") is None

    def test_index_into_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("null[0]") is None

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Interval[1, 10].low", 1),
            ("Interval[1, 10].high", 10),
            ("Interval[1, 10].lowClosed", True),
            ("Interval[1, 10].highClosed", True),
        ],
    )
    def test_interval_property(self, evaluator: CQLEvaluator, expression: str, expected: Any) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_unknown_interval_property_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Interval[1, 10].nope") is None

    def test_tuple_property(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("(Tuple { a: 1 }).a") == 1

    def test_missing_tuple_property_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("(Tuple { a: 1 }).b") is None

    def test_property_over_a_list_flattens(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({Tuple { a: 1 }, Tuple { a: 2 }}).a") == [1, 2]

    def test_polymorphic_value_falls_back_to_a_typed_element(self, evaluator: CQLEvaluator) -> None:
        observation: dict[str, Any] = {"resourceType": "Observation", "valueString": "positive"}
        result = evaluator.evaluate_expression("Obs.value", resource=observation, parameters={"Obs": observation})
        assert result == "positive"


class TestClinicalAgeFunctions:
    """Age functions read the patient birth date out of the evaluation context."""

    def test_age_in_years_at_a_given_date(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("AgeInYearsAt(@2020-06-15)", resource=PATIENT_BORN_1990)
        assert result == 30

    def test_age_in_months_at_a_given_date(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("AgeInMonthsAt(@1990-07-01)", resource=PATIENT_BORN_1990)
        assert result == 6

    def test_age_functions_without_a_patient_are_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("AgeInYearsAt(@2020-06-15)") is None

    @pytest.mark.parametrize(
        ("age_expression", "reference_expression"),
        [
            ("AgeInYears()", "CalculateAgeInYears(@1990-01-01, Today())"),
            ("AgeInMonths()", "CalculateAgeInMonths(@1990-01-01, Today())"),
            ("AgeInWeeks()", "CalculateAgeInWeeks(@1990-01-01, Today())"),
            ("AgeInDays()", "CalculateAgeInDays(@1990-01-01, Today())"),
        ],
    )
    def test_age_matches_the_explicit_calculation(
        self, evaluator: CQLEvaluator, age_expression: str, reference_expression: str
    ) -> None:
        expected = evaluator.evaluate_expression(reference_expression, resource=PATIENT_BORN_1990)
        assert isinstance(expected, int)
        assert evaluator.evaluate_expression(age_expression, resource=PATIENT_BORN_1990) == expected

    @pytest.mark.parametrize(
        "expression",
        ["AgeInYears()", "AgeInMonths()", "AgeInWeeks()", "AgeInDays()"],
    )
    def test_age_without_a_patient_is_null(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("CalculateAgeInYears(@2000-01-01, @2020-06-15)", 20),
            ("CalculateAgeInMonths(@2000-01-01, @2000-07-15)", 6),
            ("CalculateAgeInWeeks(@2000-01-01, @2000-01-29)", 4),
            ("CalculateAgeInDays(@2000-01-01, @2000-01-11)", 10),
        ],
    )
    def test_calculate_age(self, evaluator: CQLEvaluator, expression: str, expected: int) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    @pytest.mark.parametrize(
        "expression",
        [
            "CalculateAgeInYears(@2000-01-01)",
            "CalculateAgeInMonths(@2000-01-01)",
            "CalculateAgeInWeeks(@2000-01-01)",
            "CalculateAgeInDays(@2000-01-01)",
        ],
    )
    def test_calculate_age_needs_two_arguments(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None

    def test_date_diff_counts_days(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("DateDiff(@2020-01-01, @2020-01-11)") == 10

    def test_date_diff_needs_two_arguments(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("DateDiff(@2020-01-01)") is None


class TestTerminologyConversionFunctions:
    """`ToCode` and `ToConcept` build terminology values."""

    def test_to_code_from_string(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("ToCode('abc')") == CQLCode(code="abc", system="")

    def test_to_code_of_null_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("ToCode(null)") is None

    def test_to_concept_wraps_a_code(self, evaluator: CQLEvaluator) -> None:
        source = """
        library Terminology version '1.0'
        codesystem SNOMED: 'http://snomed.info/sct'
        define Wrapped: ToConcept(Code '25064002' from SNOMED)
        """
        evaluator.compile(source)
        expected = CQLConcept(codes=(CQLCode(code="25064002", system="http://snomed.info/sct"),))
        assert evaluator.evaluate_definition("Wrapped") == expected


BETWEEN_CASES: list[tuple[str, int]] = [
    ("years between @2000-01-01 and @2020-06-15", 20),
    ("months between @2000-01-01 and @2000-07-15", 6),
    ("weeks between @2000-01-01 and @2000-01-29", 4),
    ("days between @2000-01-01 and @2000-01-11", 10),
    ("hours between @2020-01-01T00:00:00 and @2020-01-01T10:00:00", 10),
    ("minutes between @2020-01-01T00:00:00 and @2020-01-01T00:30:00", 30),
    ("duration in years between @2000-01-01 and @2020-06-15", 20),
    ("difference in years between @2000-01-01 and @2020-06-15", 20),
    ("difference in months between @2020-01-01 and @2020-04-15", 3),
    ("years between @2000 and @2020", 20),
]


class TestDurationBetweenTwoPoints:
    """The binary `<precision> between A and B` form."""

    @pytest.mark.parametrize(("expression", "expected"), BETWEEN_CASES)
    def test_between(self, evaluator: CQLEvaluator, expression: str, expected: int) -> None:
        assert evaluator.evaluate_expression(expression) == expected

    def test_between_with_a_null_operand(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("years between null and @2020") is None

    def test_partial_precision_widens_the_answer_into_an_interval(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("days between @2000-01 and @2000-03")
        assert result == CQLInterval(low=30, high=90)

    def test_year_only_operands_widen_a_month_count(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("months between @2000 and @2020")
        assert result == CQLInterval(low=229, high=251)


UNCERTAIN_COMPARISON_CASES: list[str] = [
    "@2020-01 < @2020-01-15",
    "@2020-01-15 > @2020-01",
    "@2020-01-01T10 < @2020-01-01T10:30",
    "@T10 < @T10:30",
]

DECIDABLE_COMPARISON_CASES: list[tuple[str, bool]] = [
    ("@2019 < @2020-01-15", True),
    ("@2020-01-01T10 > @2020-01-01T09:30", True),
    ("@2020-01-01T09 < @2020-01-02T10:30", True),
    ("@T10 > @T09:30", True),
    ("@T09 < @T10:30", True),
    ("@2020-01-01 < @2020-01-02", True),
]


class TestPrecisionUncertaintyInComparisons:
    """Ordering two partial-precision values is null only when the ranges overlap."""

    @pytest.mark.parametrize("expression", UNCERTAIN_COMPARISON_CASES)
    def test_overlapping_ranges_are_null(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None

    @pytest.mark.parametrize(("expression", "expected"), DECIDABLE_COMPARISON_CASES)
    def test_disjoint_ranges_still_compare(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected


UNCERTAINTY_INTERVAL_CASES: list[tuple[str, bool | None]] = [
    ("Interval[7, 18] > 5", True),
    ("Interval[7, 18] < 5", False),
    ("Interval[7, 18] > 10", None),
    ("5 < Interval[7, 18]", True),
    ("Interval[7, 18] >= 7", True),
    ("Interval[7, 18] <= 18", True),
]


class TestComparingAnUncertaintyIntervalToAScalar:
    """An interval compares to a scalar as a whole, answering null when the answer varies."""

    @pytest.mark.parametrize(("expression", "expected"), UNCERTAINTY_INTERVAL_CASES)
    def test_comparison(self, evaluator: CQLEvaluator, expression: str, expected: bool | None) -> None:
        assert evaluator.evaluate_expression(expression) is expected


QUANTITY_OFFSET_TIMING_CASES: list[tuple[str, bool]] = [
    ("Interval[@2020-01-02, @2020-01-05] starts 1 day or less on or after day of @2020-01-01", True),
    ("Interval[@2020-01-02, @2020-01-05] starts 1 day or more on or after day of @2020-01-01", True),
    ("Interval[@2020-01-02, @2020-01-05] ends 1 day or less on or before day of @2020-01-06", True),
    ("Interval[@2020-01-02, @2020-01-05] starts before day of @2020-01-05", False),
]


class TestQuantityOffsetTiming:
    """`starts`/`ends` against a point, qualified by a quantity offset."""

    @pytest.mark.parametrize(("expression", "expected"), QUANTITY_OFFSET_TIMING_CASES)
    def test_offset_timing(self, evaluator: CQLEvaluator, expression: str, expected: bool) -> None:
        assert evaluator.evaluate_expression(expression) is expected


class TestTimeAndDecimalIntervalExpansion:
    """`expand` over time and decimal intervals."""

    def test_expand_time_interval_per_hour(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("expand Interval[@T01:00:00, @T05:00:00] per hour")
        assert result == [CQLInterval(low=FHIRTime(hour=hour), high=FHIRTime(hour=hour)) for hour in (1, 2, 3, 4, 5)]

    def test_expand_time_interval_below_the_needed_precision_is_empty(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("expand Interval[@T01, @T05] per minute") == []

    def test_expand_decimal_interval_by_a_fractional_step(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Expand(Interval[1.0, 2.0], 0.5)")
        assert result == [
            CQLInterval(low=Decimal("1.0"), high=Decimal("1.0")),
            CQLInterval(low=Decimal("1.5"), high=Decimal("1.5")),
            CQLInterval(low=Decimal("2.0"), high=Decimal("2.0")),
        ]

    def test_expand_an_integer_point_by_a_fractional_step(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Expand(Interval[10, 10], 0.1)")
        assert [interval.low for interval in result] == [Decimal("10") + Decimal("0.1") * step for step in range(10)]


class TestConsistentEvaluationClock:
    """`Now()`, `Today()`, and `TimeOfDay()` are stable within one evaluation."""

    def test_now_equals_itself(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("Now() = Now()") is True

    def test_today_is_the_date_part_of_now(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Today() = date from Now()")
        assert result is True

    def test_time_of_day_is_a_time(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("TimeOfDay()")
        assert isinstance(result, FHIRTime)
        assert 0 <= (result.hour or 0) <= 23


WIRE_STRING_COMPARISON_CASES: list[tuple[str, bool]] = [
    # A FHIR date element reaches CQL as a JSON string; ordering it against a date literal reads it as a date.
    ("'1975-03-04' < @1980-01-01", True),
    ("'1985-03-04' < @1980-01-01", False),
    ("'1985-03-04' > @1980-01-01", True),
    ("'1980-01-01' <= @1980-01-01", True),
    ("@1980-01-01 < '1985-03-04'", True),
    ("@1980-01-01 > '1985-03-04'", False),
    # A dateTime string keeps its time component and reads as a dateTime.
    ("'2024-03-04T10:00:00Z' < @2025-01-01T00:00:00Z", True),
    ("'2024-03-04T10:00:00Z' > @2025-01-01T00:00:00Z", False),
    # A time string reads as a time when the literal beside it is one.
    ("'T10:00:00' < @T12:00:00", True),
    # Timing phrases read the string the same way.
    ("'1975-03-04' before @1980-01-01", True),
    ("'1985-03-04' after @1980-01-01", True),
    ("'2024-03-04' during Interval[@2020-01-01, @2025-01-01]", True),
    ("'2019-03-04' during Interval[@2020-01-01, @2025-01-01]", False),
    ("'2024-03-04T10:00:00Z' during Interval[@2020-01-01T00:00:00Z, @2025-01-01T00:00:00Z]", True),
    ("'2024-03-04' included in Interval[@2020-01-01, @2025-01-01]", True),
    # Interval membership and `between` read it too.
    ("'2024-03-04' in Interval[@2020-01-01, @2025-01-01]", True),
    ("'2019-03-04' in Interval[@2020-01-01, @2025-01-01]", False),
    ("'1985-03-04' between @1980-01-01 and @1990-01-01", True),
    # Equality reads a date-shaped string as the date it spells.
    ("'1980-01-01' = @1980-01-01", True),
    ("'1980-01-02' = @1980-01-01", False),
]

NON_TEMPORAL_STRING_REFUSALS: list[str] = [
    "'p1' < @1980-01-01",
    "'p1' > @1980-01-01",
    "@1980-01-01 < 'p1'",
    "'final' during Interval[@2020-01-01, @2025-01-01]",
    "'final' included in Interval[@2020-01-01, @2025-01-01]",
    "'final' before @1980-01-01",
    "'final' in Interval[@2020-01-01, @2025-01-01]",
]

UNCOERCED_COMPARISON_CASES: list[tuple[str, bool]] = [
    # Two strings order as strings; neither side is temporal, so nothing is read as a date.
    ("'apple' < 'banana'", True),
    ("'2024-01-01' < '2024-06-01'", True),
    # A date-shaped string facing a number is left alone as well.
    ("{1, 2, 3} includes 2", True),
]


class TestWireDateStringsInComparisons:
    """A FHIR date element arrives as a JSON string and is read as a temporal where one faces it."""

    @pytest.mark.parametrize(("expression", "expected"), WIRE_STRING_COMPARISON_CASES)
    def test_date_shaped_string_is_read_as_a_temporal(
        self, evaluator: CQLEvaluator, expression: str, expected: bool
    ) -> None:
        assert evaluator.evaluate_expression(expression) is expected

    @pytest.mark.parametrize("expression", NON_TEMPORAL_STRING_REFUSALS)
    def test_non_temporal_string_refuses(self, evaluator: CQLEvaluator, expression: str) -> None:
        with pytest.raises(CQLError, match="not a date, dateTime, or time"):
            evaluator.evaluate_expression(expression)

    @pytest.mark.parametrize(("expression", "expected"), UNCOERCED_COMPARISON_CASES)
    def test_comparisons_without_a_temporal_operand_are_untouched(
        self, evaluator: CQLEvaluator, expression: str, expected: bool
    ) -> None:
        assert evaluator.evaluate_expression(expression) is expected

    def test_explicit_to_date_still_works(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("ToDate('1975-03-04') < @1980-01-01") is True

    def test_explicit_to_datetime_still_works(self, evaluator: CQLEvaluator) -> None:
        assert (
            evaluator.evaluate_expression(
                "ToDateTime('2024-03-04T10:00:00Z') during Interval[@2020-01-01T00:00:00Z, @2025-01-01T00:00:00Z]"
            )
            is True
        )
