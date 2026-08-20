"""Tests for the FHIRPath math functions and the date/time functions beside them."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.datetime import (
    fn_day,
    fn_hour,
    fn_millisecond,
    fn_minute,
    fn_month,
    fn_now,
    fn_second,
    fn_time_of_day,
    fn_today,
    fn_year,
)
from dhis2w_fhir_engine.engine.fhirpath.functions.math import (
    fn_abs,
    fn_ceiling,
    fn_exp,
    fn_floor,
    fn_high_boundary,
    fn_ln,
    fn_log,
    fn_low_boundary,
    fn_power,
    fn_precision,
    fn_round,
    fn_sqrt,
    fn_truncate,
)
from dhis2w_fhir_engine.engine.fhirpath.visitor import _PrimitiveWithExtension
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity


@pytest.fixture
def context() -> EvaluationContext:
    """Build an evaluation context with no resource bound."""
    return EvaluationContext()


class TestMathOnEmptyInput:
    """Every math function propagates the empty collection."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda ctx: fn_abs(ctx, []),
            lambda ctx: fn_ceiling(ctx, []),
            lambda ctx: fn_floor(ctx, []),
            lambda ctx: fn_round(ctx, []),
            lambda ctx: fn_truncate(ctx, []),
            lambda ctx: fn_sqrt(ctx, []),
            lambda ctx: fn_ln(ctx, []),
            lambda ctx: fn_log(ctx, [], 10),
            lambda ctx: fn_power(ctx, [], 2),
            lambda ctx: fn_exp(ctx, []),
            lambda ctx: fn_low_boundary(ctx, []),
            lambda ctx: fn_high_boundary(ctx, []),
            lambda ctx: fn_precision(ctx, []),
        ],
    )
    def test_empty_in_empty_out(self, context: EvaluationContext, call: Any) -> None:
        assert call(context) == []


class TestMathOnNonNumericInput:
    """Every math function returns empty for a value it cannot interpret as a number."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda ctx: fn_abs(ctx, ["twelve"]),
            lambda ctx: fn_ceiling(ctx, ["twelve"]),
            lambda ctx: fn_floor(ctx, ["twelve"]),
            lambda ctx: fn_round(ctx, ["twelve"]),
            lambda ctx: fn_truncate(ctx, ["twelve"]),
            lambda ctx: fn_sqrt(ctx, ["twelve"]),
            lambda ctx: fn_ln(ctx, ["twelve"]),
            lambda ctx: fn_log(ctx, ["twelve"], 10),
            lambda ctx: fn_power(ctx, ["twelve"], 2),
            lambda ctx: fn_exp(ctx, ["twelve"]),
            lambda ctx: fn_precision(ctx, ["twelve"]),
        ],
    )
    def test_a_string_yields_empty(self, context: EvaluationContext, call: Any) -> None:
        assert call(context) == []


class TestMathResults:
    """Tests for the values the math functions produce."""

    @pytest.mark.parametrize(("value", "expected"), [(-5, 5), (5, 5), (-2.5, 2.5), (Decimal("-1.25"), Decimal("1.25"))])
    def test_abs(self, context: EvaluationContext, value: Any, expected: Any) -> None:
        assert fn_abs(context, [value]) == [expected]

    def test_abs_of_a_quantity_keeps_the_unit(self, context: EvaluationContext) -> None:
        result = fn_abs(context, [Quantity(value=Decimal("-4.5"), unit="mg")])
        assert result == [Quantity(value=Decimal("4.5"), unit="mg")]

    @pytest.mark.parametrize(("value", "expected"), [(1.1, 2), (-1.1, -1), (2, 2)])
    def test_ceiling(self, context: EvaluationContext, value: Any, expected: int) -> None:
        assert fn_ceiling(context, [value]) == [expected]

    @pytest.mark.parametrize(("value", "expected"), [(1.9, 1), (-1.1, -2), (2, 2)])
    def test_floor(self, context: EvaluationContext, value: Any, expected: int) -> None:
        assert fn_floor(context, [value]) == [expected]

    @pytest.mark.parametrize(
        ("value", "precision", "expected"),
        [(3.14159, 0, 3.0), (3.14159, 2, 3.14), (2.5, 0, 2.0), (Decimal("1.005"), 2, 1.0)],
    )
    def test_round(self, context: EvaluationContext, value: Any, precision: int, expected: float) -> None:
        assert fn_round(context, [value], precision) == [expected]

    @pytest.mark.parametrize(("value", "expected"), [(1.9, 1), (-1.9, -1), (Decimal("2.99"), 2)])
    def test_truncate(self, context: EvaluationContext, value: Any, expected: int) -> None:
        assert fn_truncate(context, [value]) == [expected]

    def test_sqrt_of_a_negative_number_is_empty(self, context: EvaluationContext) -> None:
        assert fn_sqrt(context, [-1]) == []

    def test_sqrt(self, context: EvaluationContext) -> None:
        assert fn_sqrt(context, [81]) == [9.0]

    @pytest.mark.parametrize("value", [0, -1])
    def test_ln_outside_its_domain_is_empty(self, context: EvaluationContext, value: int) -> None:
        assert fn_ln(context, [value]) == []

    def test_ln(self, context: EvaluationContext) -> None:
        assert fn_ln(context, [1]) == [0.0]

    @pytest.mark.parametrize("value", [0, -1])
    def test_log_outside_its_domain_is_empty(self, context: EvaluationContext, value: int) -> None:
        assert fn_log(context, [value], 10) == []

    def test_log(self, context: EvaluationContext) -> None:
        assert fn_log(context, [16], 2) == [4.0]

    def test_power(self, context: EvaluationContext) -> None:
        assert fn_power(context, [2], 3) == [8.0]

    def test_power_with_a_complex_result_is_empty(self, context: EvaluationContext) -> None:
        assert fn_power(context, [-1], 0.5) == []

    def test_exp(self, context: EvaluationContext) -> None:
        assert fn_exp(context, [0]) == [1.0]


class TestDecimalBoundaries:
    """Tests for lowBoundary and highBoundary on numbers and quantities."""

    def test_a_decimal_widens_by_half_its_last_digit(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [Decimal("1.587")]) == [Decimal("1.58650000")]
        assert fn_high_boundary(context, [Decimal("1.587")]) == [Decimal("1.58750000")]

    def test_an_explicit_output_precision_is_honoured(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [Decimal("1.587")], 4) == [Decimal("1.5865")]
        assert fn_high_boundary(context, [Decimal("1.587")], 4) == [Decimal("1.5875")]

    @pytest.mark.parametrize("precision", [-1, 29])
    def test_an_unusable_precision_yields_empty(self, context: EvaluationContext, precision: int) -> None:
        assert fn_low_boundary(context, [Decimal("1.587")], precision) == []
        assert fn_high_boundary(context, [Decimal("1.587")], precision) == []

    def test_a_magnitude_beyond_the_decimal_context_yields_empty(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [Decimal("1E+25")]) == []
        assert fn_high_boundary(context, [Decimal("1E+25")]) == []

    def test_a_quantity_keeps_its_unit(self, context: EvaluationContext) -> None:
        quantity = Quantity(value=Decimal("1.5"), unit="mg")
        assert fn_low_boundary(context, [quantity]) == [Quantity(value=Decimal("1.45000000"), unit="mg")]
        assert fn_high_boundary(context, [quantity]) == [Quantity(value=Decimal("1.55000000"), unit="mg")]

    def test_a_quantity_beyond_the_decimal_context_yields_empty(self, context: EvaluationContext) -> None:
        quantity = Quantity(value=Decimal("1E+25"), unit="mg")
        assert fn_low_boundary(context, [quantity]) == []
        assert fn_high_boundary(context, [quantity]) == []

    def test_a_wrapped_primitive_is_unwrapped_first(self, context: EvaluationContext) -> None:
        wrapped = _PrimitiveWithExtension(Decimal("1.587"), element_name="valueDecimal")
        assert fn_low_boundary(context, [wrapped]) == [Decimal("1.58650000")]

    @pytest.mark.parametrize("value", ["not a date", {"resourceType": "Patient"}, ["nested"]])
    def test_a_value_with_no_boundary_yields_empty(self, context: EvaluationContext, value: Any) -> None:
        assert fn_low_boundary(context, [value]) == []
        assert fn_high_boundary(context, [value]) == []


class TestDateBoundaries:
    """Tests for lowBoundary and highBoundary on dates, datetimes, and times."""

    def test_a_date_string_parses_before_the_boundary_is_taken(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, ["2024-03-01T08:30"]) == [
            FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=0, millisecond=0, tz_offset="+14:00")
        ]
        assert fn_high_boundary(context, ["2024-03"]) == [
            FHIRDateTime(year=2024, month=3, day=31, hour=23, minute=59, second=59, millisecond=999, tz_offset="-12:00")
        ]

    def test_a_date_defaults_to_full_datetime_precision(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [FHIRDate(year=2024, month=3, day=1)]) == [
            FHIRDateTime(year=2024, month=3, day=1, hour=0, minute=0, second=0, millisecond=0, tz_offset="+14:00")
        ]
        assert fn_high_boundary(context, [FHIRDate(year=2024)]) == [
            FHIRDateTime(
                year=2024, month=12, day=31, hour=23, minute=59, second=59, millisecond=999, tz_offset="-12:00"
            )
        ]

    @pytest.mark.parametrize(
        ("precision", "expected_low", "expected_high"),
        [
            (4, FHIRDate(year=2024), FHIRDate(year=2024)),
            (6, FHIRDate(year=2024, month=3), FHIRDate(year=2024, month=3)),
            (8, FHIRDate(year=2024, month=3, day=1), FHIRDate(year=2024, month=3, day=1)),
        ],
    )
    def test_a_date_at_a_date_level_precision(
        self,
        context: EvaluationContext,
        precision: int,
        expected_low: FHIRDate,
        expected_high: FHIRDate,
    ) -> None:
        date = FHIRDate(year=2024, month=3, day=1)
        assert fn_low_boundary(context, [date], precision) == [expected_low]
        assert fn_high_boundary(context, [date], precision) == [expected_high]

    def test_a_year_only_date_fills_the_missing_components(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [FHIRDate(year=2024)], 8) == [FHIRDate(year=2024, month=1, day=1)]
        assert fn_high_boundary(context, [FHIRDate(year=2024)], 8) == [FHIRDate(year=2024, month=12, day=31)]

    @pytest.mark.parametrize(
        ("precision", "expected"),
        [
            (4, FHIRDate(year=2024)),
            (6, FHIRDate(year=2024, month=3)),
            (8, FHIRDate(year=2024, month=3, day=1)),
            (10, FHIRDateTime(year=2024, month=3, day=1, hour=8)),
            (12, FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30)),
            (14, FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15)),
        ],
    )
    def test_a_datetime_low_boundary_at_each_precision(
        self, context: EvaluationContext, precision: int, expected: Any
    ) -> None:
        value = FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=250)
        assert fn_low_boundary(context, [value], precision) == [expected]

    @pytest.mark.parametrize(
        ("precision", "expected"),
        [
            (4, FHIRDate(year=2024)),
            (6, FHIRDate(year=2024, month=3)),
            (8, FHIRDate(year=2024, month=3, day=1)),
            (10, FHIRDateTime(year=2024, month=3, day=1, hour=8)),
            (12, FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30)),
            (14, FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15)),
        ],
    )
    def test_a_datetime_high_boundary_at_each_precision(
        self, context: EvaluationContext, precision: int, expected: Any
    ) -> None:
        value = FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=250)
        assert fn_high_boundary(context, [value], precision) == [expected]

    def test_a_datetime_keeps_its_own_timezone(self, context: EvaluationContext) -> None:
        value = FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, tz_offset="Z")
        assert fn_low_boundary(context, [value]) == [
            FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=0, tz_offset="Z")
        ]
        assert fn_high_boundary(context, [value]) == [
            FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=999, tz_offset="Z")
        ]

    def test_a_partial_datetime_high_boundary_fills_the_end_of_the_month(self, context: EvaluationContext) -> None:
        assert fn_high_boundary(context, [FHIRDateTime(year=2024, month=2)]) == [
            FHIRDateTime(year=2024, month=2, day=29, hour=23, minute=59, second=59, millisecond=999, tz_offset="-12:00")
        ]

    @pytest.mark.parametrize(
        ("precision", "expected"),
        [
            (2, FHIRTime(hour=8)),
            (4, FHIRTime(hour=8, minute=30)),
            (6, FHIRTime(hour=8, minute=30, second=15)),
            (9, FHIRTime(hour=8, minute=30, second=15, millisecond=250)),
        ],
    )
    def test_a_time_low_boundary_at_each_precision(
        self, context: EvaluationContext, precision: int, expected: FHIRTime
    ) -> None:
        value = FHIRTime(hour=8, minute=30, second=15, millisecond=250)
        assert fn_low_boundary(context, [value], precision) == [expected]

    def test_a_partial_time_fills_the_missing_components(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [FHIRTime(hour=8)]) == [FHIRTime(hour=8, minute=0, second=0, millisecond=0)]
        assert fn_high_boundary(context, [FHIRTime(hour=8)]) == [
            FHIRTime(hour=8, minute=59, second=59, millisecond=999)
        ]

    @pytest.mark.parametrize(
        ("precision", "expected"),
        [
            (2, FHIRTime(hour=8)),
            (4, FHIRTime(hour=8, minute=59)),
            (6, FHIRTime(hour=8, minute=59, second=59)),
        ],
    )
    def test_a_time_high_boundary_at_each_precision(
        self, context: EvaluationContext, precision: int, expected: FHIRTime
    ) -> None:
        assert fn_high_boundary(context, [FHIRTime(hour=8)], precision) == [expected]


class TestPrecision:
    """Tests for the precision function."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (5, 0),
            (Decimal("100"), 0),
            (Decimal("1.230"), 3),
            (1.58, 2),
            (FHIRDate(year=2024), 4),
            (FHIRDate(year=2024, month=3), 6),
            (FHIRDate(year=2024, month=3, day=1), 8),
            (FHIRDateTime(year=2024), 4),
            (FHIRDateTime(year=2024, month=3), 6),
            (FHIRDateTime(year=2024, month=3, day=1), 8),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), 10),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30), 12),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15), 14),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=250), 17),
            (FHIRTime(hour=8), 2),
            (FHIRTime(hour=8, minute=30), 4),
            (FHIRTime(hour=8, minute=30, second=15), 6),
            (FHIRTime(hour=8, minute=30, second=15, millisecond=250), 9),
        ],
    )
    def test_precision(self, context: EvaluationContext, value: Any, expected: int) -> None:
        assert fn_precision(context, [value]) == [expected]

    def test_a_value_with_no_precision_yields_empty(self, context: EvaluationContext) -> None:
        assert fn_precision(context, [{"resourceType": "Patient"}]) == []

    @pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
    def test_a_decimal_without_a_numeric_exponent_reads_as_zero(
        self, context: EvaluationContext, value: Decimal
    ) -> None:
        assert fn_precision(context, [value]) == [0]


class TestCurrentDateAndTime:
    """Tests for today, now, and timeOfDay."""

    def test_today_reads_the_context_clock(self, context: EvaluationContext) -> None:
        context.now = datetime(2024, 3, 1, 8, 30, 15, 250000, tzinfo=UTC)
        assert fn_today(context, []) == [FHIRDate(year=2024, month=3, day=1)]

    def test_time_of_day_reads_the_context_clock(self, context: EvaluationContext) -> None:
        context.now = datetime(2024, 3, 1, 8, 30, 15, 250000, tzinfo=UTC)
        assert fn_time_of_day(context, []) == [FHIRTime(hour=8, minute=30, second=15, millisecond=250)]

    def test_now_reads_utc_as_the_z_offset(self, context: EvaluationContext) -> None:
        context.now = datetime(2024, 3, 1, 8, 30, 15, 250000, tzinfo=UTC)
        assert fn_now(context, []) == [
            FHIRDateTime(year=2024, month=3, day=1, hour=8, minute=30, second=15, millisecond=250, tz_offset="Z")
        ]

    @pytest.mark.parametrize(
        ("offset", "expected_tz"),
        [
            (timedelta(hours=5, minutes=30), "+05:30"),
            (timedelta(hours=-8), "-08:00"),
            (timedelta(hours=-3, minutes=-30), "-03:30"),
        ],
    )
    def test_now_formats_a_non_utc_offset(
        self, context: EvaluationContext, offset: timedelta, expected_tz: str
    ) -> None:
        context.now = datetime(2024, 3, 1, 8, 30, 15, tzinfo=timezone(offset))
        assert fn_now(context, [])[0].tz_offset == expected_tz

    def test_now_without_a_timezone_reads_as_z(self, context: EvaluationContext) -> None:
        context.now = datetime(2024, 3, 1, 8, 30, 15)
        assert fn_now(context, [])[0].tz_offset == "Z"

    def test_the_clock_falls_back_to_the_wall_clock(self, context: EvaluationContext) -> None:
        today = fn_today(context, [])[0]
        assert (today.year, today.month, today.day) == (
            datetime.now(UTC).year,
            datetime.now(UTC).month,
            datetime.now(UTC).day,
        )


class TestDateComponents:
    """Tests for the date component functions."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2024, month=3, day=1), [2024]),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), [2024]),
            ("2024-03-01", [2024]),
            ("2024-03-01T08:30:15", [2024]),
            (42, []),
            ("not a date", []),
        ],
    )
    def test_year(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_year(context, [value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2024, month=3, day=1), [3]),
            (FHIRDate(year=2024), []),
            (FHIRDateTime(year=2024), []),
            (42, []),
        ],
    )
    def test_month(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_month(context, [value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2024, month=3, day=1), [1]),
            (FHIRDate(year=2024, month=3), []),
            (42, []),
        ],
    )
    def test_day(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_day(context, [value]) == expected

    def test_a_wrapped_primitive_is_unwrapped_first(self, context: EvaluationContext) -> None:
        wrapped = _PrimitiveWithExtension("2024-03-01", element_name="birthDate", resource_type="Patient")
        assert fn_year(context, [wrapped]) == [2024]
        assert fn_month(context, [wrapped]) == [3]
        assert fn_day(context, [wrapped]) == [1]

    @pytest.mark.parametrize("component", [fn_year, fn_month, fn_day])
    def test_empty_in_empty_out(self, context: EvaluationContext, component: Any) -> None:
        assert component(context, []) == []


class TestTimeComponents:
    """Tests for the time component functions."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=8, minute=30, second=15, millisecond=250), [8]),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), [8]),
            (FHIRDateTime(year=2024, month=3, day=1), []),
            ("08:30:15", [8]),
            ("2024-03-01T08:30:15", [8]),
            (42, []),
        ],
    )
    def test_hour(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_hour(context, [value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=8, minute=30), [30]),
            (FHIRTime(hour=8), []),
            (FHIRDateTime(year=2024, month=3, day=1, hour=8), []),
            (42, []),
        ],
    )
    def test_minute(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_minute(context, [value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=8, minute=30, second=15), [15]),
            (FHIRTime(hour=8, minute=30), []),
            (42, []),
        ],
    )
    def test_second(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_second(context, [value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=8, minute=30, second=15, millisecond=250), [250]),
            (FHIRTime(hour=8, minute=30, second=15), []),
            (42, []),
        ],
    )
    def test_millisecond(self, context: EvaluationContext, value: Any, expected: list[int]) -> None:
        assert fn_millisecond(context, [value]) == expected

    def test_a_wrapped_primitive_is_unwrapped_first(self, context: EvaluationContext) -> None:
        wrapped = _PrimitiveWithExtension("08:30:15.250", element_name="valueTime")
        assert fn_hour(context, [wrapped]) == [8]
        assert fn_minute(context, [wrapped]) == [30]
        assert fn_second(context, [wrapped]) == [15]
        assert fn_millisecond(context, [wrapped]) == [250]

    @pytest.mark.parametrize("component", [fn_hour, fn_minute, fn_second, fn_millisecond])
    def test_empty_in_empty_out(self, context: EvaluationContext, component: Any) -> None:
        assert component(context, []) == []
