"""Tests for the CQL conversion, math and aggregate standard-library functions.

Covers the ToX conversions, null handling helpers, the math functions and their
error paths, the precision and boundary helpers, MinValue / MaxValue, and the
aggregate functions over lists.
"""

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql.functions import aggregate, conversion
from dhis2w_fhir_engine.engine.cql.functions.registry import get_registry
from dhis2w_fhir_engine.engine.cql.types import CQLCode, CQLConcept
from dhis2w_fhir_engine.engine.exceptions import CQLError
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity


class TestToString:
    """ToString renders CQL values in their canonical text form."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, "true"),
            (False, "false"),
            (42, "42"),
            ("plain", "plain"),
            (Quantity(value=Decimal("5.5"), unit="cm"), "5.5cm"),
            (FHIRDate(year=2020, month=1, day=2), "2020-01-02"),
        ],
    )
    def test_values(self, value: Any, expected: str) -> None:
        assert conversion._to_string([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDateTime(year=2020), "2020"),
            (FHIRDateTime(year=2020, month=1), "2020-01"),
            (FHIRDateTime(year=2020, month=1, day=2), "2020-01-02"),
            (FHIRDateTime(year=2020, month=1, day=2, hour=3), "2020-01-02T03"),
            (FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=4), "2020-01-02T03:04"),
            (
                FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=4, second=5),
                "2020-01-02T03:04:05",
            ),
            (
                FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=4, second=5, millisecond=6, tz_offset="Z"),
                "2020-01-02T03:04:05.006",
            ),
        ],
    )
    def test_datetime_drops_the_timezone(self, value: FHIRDateTime, expected: str) -> None:
        assert conversion._to_string([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_null_input_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_string(arguments) is None


class TestScalarConversions:
    """ToInteger, ToDecimal and ToBoolean."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, 1), (False, 0), ("12", 12), (3.9, 3), (Decimal("4.7"), 4)],
    )
    def test_to_integer(self, value: Any, expected: int) -> None:
        assert conversion._to_integer([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None], ["not a number"], [[1]]])
    def test_to_integer_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_integer(arguments) is None

    @pytest.mark.parametrize(("value", "expected"), [("1.5", Decimal("1.5")), (2, Decimal("2"))])
    def test_to_decimal(self, value: Any, expected: Decimal) -> None:
        assert conversion._to_decimal([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None], ["not a number"]])
    def test_to_decimal_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_decimal(arguments) is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, True),
            (False, False),
            ("true", True),
            ("T", True),
            ("yes", True),
            ("Y", True),
            ("1", True),
            ("false", False),
            ("f", False),
            ("no", False),
            ("N", False),
            ("0", False),
            (0, False),
            (3, True),
            (2.5, True),
            (0.0, False),
        ],
    )
    def test_to_boolean(self, value: Any, expected: bool) -> None:
        assert conversion._to_boolean([value]) is expected

    @pytest.mark.parametrize("arguments", [[], [None], ["maybe"], [[1]]])
    def test_to_boolean_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_boolean(arguments) is None


class TestTemporalConversions:
    """ToDate, ToDateTime and ToTime."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020), FHIRDate(year=2020)),
            (FHIRDateTime(year=2020, month=1, day=2), FHIRDate(year=2020, month=1, day=2)),
            (datetime(2020, 3, 4, 5), FHIRDate(year=2020, month=3, day=4)),
            (date(2019, 2, 3), FHIRDate(year=2019, month=2, day=3)),
            ("2020-05-06", FHIRDate(year=2020, month=5, day=6)),
        ],
    )
    def test_to_date(self, value: Any, expected: FHIRDate) -> None:
        assert conversion._to_date([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None], ["bogus"], [5]])
    def test_to_date_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_date(arguments) is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDateTime(year=2020), FHIRDateTime(year=2020)),
            (FHIRDate(year=2020, month=1, day=2), FHIRDateTime(year=2020, month=1, day=2)),
            (date(2019, 2, 3), FHIRDateTime(year=2019, month=2, day=3)),
            ("2020-05-06", FHIRDateTime(year=2020, month=5, day=6)),
        ],
    )
    def test_to_datetime(self, value: Any, expected: FHIRDateTime) -> None:
        assert conversion._to_datetime([value]) == expected

    def test_to_datetime_from_a_python_datetime_keeps_the_time(self) -> None:
        result = conversion._to_datetime([datetime(2020, 3, 4, 5, 6, 7, 8000)])
        assert result == FHIRDateTime(year=2020, month=3, day=4, hour=5, minute=6, second=7, millisecond=8)

    @pytest.mark.parametrize("arguments", [[], [None], [5]])
    def test_to_datetime_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_datetime(arguments) is None

    def test_to_datetime_rejects_slash_separated_text(self) -> None:
        with pytest.raises(CQLError, match="Malformed datetime string"):
            conversion._to_datetime(["2020/05/06"])

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=1), FHIRTime(hour=1)),
            ("12:30:00", FHIRTime(hour=12, minute=30, second=0)),
        ],
    )
    def test_to_time(self, value: Any, expected: FHIRTime) -> None:
        assert conversion._to_time([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None], [5]])
    def test_to_time_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_time(arguments) is None


class TestToQuantityAndConcept:
    """ToQuantity, ConvertQuantity and ToConcept."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            (["5.5 cm"], Quantity(value=Decimal("5.5"), unit="cm")),
            (["5.5cm"], Quantity(value=Decimal("5.5"), unit="cm")),
            (["-2 mg"], Quantity(value=Decimal("-2"), unit="mg")),
            (["5.5"], Quantity(value=Decimal("5.5"), unit="1")),
            ([5.5], Quantity(value=Decimal("5.5"), unit="1")),
            ([5.5, "mg"], Quantity(value=Decimal("5.5"), unit="mg")),
            ([Decimal("2"), "kg"], Quantity(value=Decimal("2"), unit="kg")),
        ],
    )
    def test_to_quantity(self, arguments: list[Any], expected: Quantity) -> None:
        assert conversion._to_quantity(arguments) == expected

    @pytest.mark.parametrize("arguments", [[], [None], ["nope"], [[1, 2]]])
    def test_to_quantity_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_quantity(arguments) is None

    def test_convert_quantity_uses_ucum(self) -> None:
        result = conversion._convert_quantity([Quantity(value=Decimal("1"), unit="g"), "mg"])
        assert result is not None
        assert result.unit == "mg"
        assert result.value == Decimal("1000.0")

    def test_convert_quantity_keeps_the_value_when_the_units_are_unknown(self) -> None:
        result = conversion._convert_quantity([Quantity(value=Decimal("1"), unit="g"), "zzz"])
        assert result == Quantity(value=Decimal("1"), unit="zzz")

    @pytest.mark.parametrize(
        "arguments",
        [
            [],
            [None, "mg"],
            [5, "mg"],
            [Quantity(value=Decimal("1"), unit="g"), None],
        ],
    )
    def test_convert_quantity_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._convert_quantity(arguments) is None

    def test_to_concept_wraps_a_code(self) -> None:
        code = CQLCode(code="a", system="b")
        assert conversion._to_concept([code]) == CQLConcept(codes=(code,))

    def test_to_concept_passes_a_concept_through(self) -> None:
        code = CQLCode(code="a", system="b")
        concept = CQLConcept(codes=(code,), display="Kay")
        assert conversion._to_concept([concept]) is concept

    def test_to_concept_accepts_a_code_instance_selector(self) -> None:
        selector = {"resourceType": "Code", "code": "c", "system": "s", "display": "See"}
        result = conversion._to_concept([selector])
        assert result == CQLConcept(codes=(CQLCode(code="c", system="s", display="See"),))

    @pytest.mark.parametrize("arguments", [[], [None], [{"resourceType": "Other"}], [5]])
    def test_to_concept_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_concept(arguments) is None


class TestNullHandling:
    """Coalesce, IsNull, IsNotNull, IsTrue, IsFalse, ToList and ToChars."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[None, 2, 3]], 2),
            ([[None]], None),
            ([[]], None),
            ([None, 3], 3),
            ([None, None], None),
            ([], None),
        ],
    )
    def test_coalesce(self, arguments: list[Any], expected: Any) -> None:
        assert conversion._coalesce(arguments) == expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [([None], True), ([[]], True), ([], True), ([[1]], False), ([0], False)],
    )
    def test_is_null(self, arguments: list[Any], expected: bool) -> None:
        assert conversion._is_null(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [([None], False), ([[]], False), ([], False), ([[1]], True), ([0], True)],
    )
    def test_is_not_null(self, arguments: list[Any], expected: bool) -> None:
        assert conversion._is_not_null(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [([True], True), ([1], False), ([False], False), ([], False)],
    )
    def test_is_true(self, arguments: list[Any], expected: bool) -> None:
        assert conversion._is_true(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [([False], True), ([0], False), ([True], False), ([], False)],
    )
    def test_is_false(self, arguments: list[Any], expected: bool) -> None:
        assert conversion._is_false(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [([5], [5]), ([[1, 2]], [1, 2]), ([None], []), ([], [])],
    )
    def test_to_list(self, arguments: list[Any], expected: list[Any]) -> None:
        assert conversion._to_list(arguments) == expected

    @pytest.mark.parametrize(("value", "expected"), [("ab", ["a", "b"]), (12, ["1", "2"])])
    def test_to_chars(self, value: Any, expected: list[str]) -> None:
        assert conversion._to_chars([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_to_chars_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._to_chars(arguments) is None


class TestMathFunctions:
    """Abs, Ceiling, Floor, Truncate, Round, Ln, Log, Exp, Power and Sqrt."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(-3, 3), (3, 3), (Decimal("-1.5"), Decimal("1.5")), (-2.5, 2.5)],
    )
    def test_abs(self, value: Any, expected: Any) -> None:
        assert conversion._abs([value]) == expected

    def test_abs_of_a_quantity_keeps_the_unit(self) -> None:
        value = Quantity(value=Decimal("-2"), unit="mg")
        assert conversion._abs([value]) == Quantity(value=Decimal("2"), unit="mg")

    @pytest.mark.parametrize("arguments", [[], [None], ["text"]])
    def test_abs_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._abs(arguments) is None

    @pytest.mark.parametrize(("value", "expected"), [(1.2, 2), (-1.2, -1), (3, 3)])
    def test_ceiling(self, value: Any, expected: int) -> None:
        assert conversion._ceiling([value]) == expected

    @pytest.mark.parametrize(("value", "expected"), [(1.8, 1), (-1.2, -2), (3, 3)])
    def test_floor(self, value: Any, expected: int) -> None:
        assert conversion._floor([value]) == expected

    @pytest.mark.parametrize(("value", "expected"), [(1.8, 1), (-1.8, -1), (3, 3)])
    def test_truncate(self, value: Any, expected: int) -> None:
        assert conversion._truncate([value]) == expected

    @pytest.mark.parametrize(
        "rounder",
        [conversion._ceiling, conversion._floor, conversion._truncate],
    )
    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_rounders_yield_null(self, rounder: Any, arguments: list[Any]) -> None:
        assert rounder(arguments) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([0.5], 1),
            ([-0.5], 0),
            ([-1.5], -1),
            ([1.4], 1),
            ([1.2345, 2], Decimal("1.23")),
            ([1.2355, 2], Decimal("1.24")),
            ([2, None], 2),
        ],
    )
    def test_round(self, arguments: list[Any], expected: Any) -> None:
        assert conversion._round(arguments) == expected

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_round_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._round(arguments) is None

    def test_ln_of_one_is_zero(self) -> None:
        assert conversion._ln([1]) == 0.0

    def test_ln_of_e_is_one(self) -> None:
        assert conversion._ln([math.e]) == pytest.approx(1.0)

    def test_ln_of_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Ln\\(0\\) is undefined"):
            conversion._ln([0])

    @pytest.mark.parametrize("arguments", [[], [None], [-1]])
    def test_ln_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._ln(arguments) is None

    @pytest.mark.parametrize(("arguments", "expected"), [([8, 2], 3.0), ([1, 1], 0.0), ([100, 10], 2.0)])
    def test_log(self, arguments: list[Any], expected: float) -> None:
        result = conversion._log(arguments)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize(
        "arguments",
        [[], [1], [None, 2], [2, None], [0, 2], [-1, 2], [2, 0], [2, -1], [5, 1]],
    )
    def test_log_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._log(arguments) is None

    @pytest.mark.parametrize(("value", "expected"), [(0, 1.0), (1, math.e)])
    def test_exp(self, value: Any, expected: float) -> None:
        result = conversion._exp([value])
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_exp_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._exp(arguments) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([0, 0], 1),
            ([2, 3], Decimal("8")),
            ([Decimal("2"), Decimal("3")], Decimal("8")),
            ([2, 0], Decimal("1")),
        ],
    )
    def test_power(self, arguments: list[Any], expected: Any) -> None:
        assert conversion._power(arguments) == expected

    @pytest.mark.parametrize("arguments", [[], [2], [None, 2], [2, None], [-2, Decimal("0.5")]])
    def test_power_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._power(arguments) is None

    @pytest.mark.parametrize(("value", "expected"), [(9, 3.0), (0, 0.0), (2, math.sqrt(2))])
    def test_sqrt(self, value: Any, expected: float) -> None:
        result = conversion._sqrt([value])
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize("arguments", [[], [None], [-1]])
    def test_sqrt_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._sqrt(arguments) is None


class TestPrecision:
    """Precision reports decimal places or the temporal precision level."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("1.230"), 3),
            (Decimal("5"), 0),
            (Decimal("NaN"), 0),
            (1.25, 2),
            (2.0, 0),
            (7, 0),
        ],
    )
    def test_numeric_precision(self, value: Any, expected: int) -> None:
        assert conversion._precision([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=4, second=5, millisecond=6), 17),
            (FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=4, second=5), 14),
            (FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=4), 12),
            (FHIRDateTime(year=2020, month=1, day=2, hour=3), 10),
            (FHIRDateTime(year=2020, month=1, day=2), 8),
            (FHIRDateTime(year=2020, month=1), 6),
            (FHIRDateTime(year=2020), 4),
            (FHIRDate(year=2020, month=1, day=2), 8),
            (FHIRDate(year=2020, month=1), 6),
            (FHIRDate(year=2020), 4),
            (FHIRTime(hour=1, minute=2, second=3, millisecond=4), 9),
            (FHIRTime(hour=1, minute=2, second=3), 6),
            (FHIRTime(hour=1, minute=2), 4),
            (FHIRTime(hour=1), 2),
            (date(2020, 1, 1), 8),
            (datetime(2020, 1, 1), 8),
        ],
    )
    def test_temporal_precision(self, value: Any, expected: int) -> None:
        assert conversion._precision([value]) == expected

    @pytest.mark.parametrize("arguments", [[], [None], ["text"]])
    def test_precision_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._precision(arguments) is None


class TestBoundaries:
    """LowBoundary and HighBoundary fill in the unstated part of a value."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([Decimal("1.5"), 4], Decimal("1.5000")),
            ([2, 0], Decimal("2")),
            ([Decimal("1.5"), None], Decimal("1.5")),
        ],
    )
    def test_low_boundary_of_a_number(self, arguments: list[Any], expected: Decimal) -> None:
        assert conversion._low_boundary(arguments) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020), FHIRDate(year=2020, month=1, day=1)),
            (FHIRDate(year=2020, month=6), FHIRDate(year=2020, month=6, day=1)),
        ],
    )
    def test_low_boundary_of_a_date(self, value: FHIRDate, expected: FHIRDate) -> None:
        assert conversion._low_boundary([value, 8]) == expected

    def test_low_boundary_of_a_datetime(self) -> None:
        result = conversion._low_boundary([FHIRDateTime(year=2020), 17])
        assert result == FHIRDateTime(year=2020, month=1, day=1, hour=0, minute=0, second=0, millisecond=0)

    def test_low_boundary_of_a_time(self) -> None:
        result = conversion._low_boundary([FHIRTime(hour=5), 9])
        assert result == FHIRTime(hour=5, minute=0, second=0, millisecond=0)

    def test_low_boundary_passes_unsupported_values_through(self) -> None:
        assert conversion._low_boundary(["text", 2]) == "text"

    @pytest.mark.parametrize("arguments", [[], [1], [None, 2]])
    def test_low_boundary_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._low_boundary(arguments) is None

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([Decimal("1.5"), 4], Decimal("1.5999")),
            ([Decimal("1.5871"), 2], Decimal("1.59")),
            ([Decimal("1.5"), 0], Decimal("2")),
            ([Decimal("1.5"), -1], Decimal("1.5")),
            ([Decimal("1.5"), None], Decimal("1.5")),
        ],
    )
    def test_high_boundary_of_a_number(self, arguments: list[Any], expected: Decimal) -> None:
        assert conversion._high_boundary(arguments) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020), FHIRDate(year=2020, month=12, day=31)),
            (FHIRDate(year=2020, month=2), FHIRDate(year=2020, month=2, day=29)),
            (FHIRDate(year=2021, month=2), FHIRDate(year=2021, month=2, day=28)),
            (FHIRDate(year=1900, month=2), FHIRDate(year=1900, month=2, day=28)),
            (FHIRDate(year=2000, month=2), FHIRDate(year=2000, month=2, day=29)),
            (FHIRDate(year=2020, month=4), FHIRDate(year=2020, month=4, day=30)),
            (FHIRDate(year=2020, month=1), FHIRDate(year=2020, month=1, day=31)),
        ],
    )
    def test_high_boundary_of_a_date(self, value: FHIRDate, expected: FHIRDate) -> None:
        assert conversion._high_boundary([value, 8]) == expected

    @pytest.mark.parametrize(
        ("value", "expected_month", "expected_day"),
        [
            (FHIRDateTime(year=2020), 12, 31),
            (FHIRDateTime(year=2020, month=2), 2, 29),
            (FHIRDateTime(year=2021, month=2), 2, 28),
            (FHIRDateTime(year=2020, month=4), 4, 30),
        ],
    )
    def test_high_boundary_of_a_datetime(
        self,
        value: FHIRDateTime,
        expected_month: int,
        expected_day: int,
    ) -> None:
        result = conversion._high_boundary([value, 17])
        assert result == FHIRDateTime(
            year=value.year,
            month=expected_month,
            day=expected_day,
            hour=23,
            minute=59,
            second=59,
            millisecond=999,
        )

    def test_high_boundary_of_a_time(self) -> None:
        result = conversion._high_boundary([FHIRTime(hour=5), 9])
        assert result == FHIRTime(hour=5, minute=59, second=59, millisecond=999)

    def test_high_boundary_passes_unsupported_values_through(self) -> None:
        assert conversion._high_boundary(["text", 2]) == "text"

    @pytest.mark.parametrize("arguments", [[], [1], [None, 2]])
    def test_high_boundary_yields_null(self, arguments: list[Any]) -> None:
        assert conversion._high_boundary(arguments) is None


class TestTypeExtremes:
    """MinValue and MaxValue for each named CQL type."""

    @pytest.mark.parametrize(
        ("type_name", "expected"),
        [
            ("Integer", -(2**63)),
            ("int", -(2**63)),
            ("Decimal", Decimal("-99999999999999999999999999.99999999")),
            ("Date", FHIRDate(year=1, month=1, day=1)),
            ("DateTime", FHIRDateTime(year=1, month=1, day=1, hour=0, minute=0, second=0, millisecond=0)),
            ("Time", FHIRTime(hour=0, minute=0, second=0, millisecond=0)),
            ("Quantity", Quantity(value=Decimal("-99999999999999999999999999.99999999"), unit="1")),
        ],
    )
    def test_min_value(self, type_name: str, expected: Any) -> None:
        assert conversion._min_value([type_name]) == expected

    @pytest.mark.parametrize(
        ("type_name", "expected"),
        [
            ("Integer", 2**63 - 1),
            ("int", 2**63 - 1),
            ("Decimal", Decimal("99999999999999999999999999.99999999")),
            ("Date", FHIRDate(year=9999, month=12, day=31)),
            (
                "DateTime",
                FHIRDateTime(year=9999, month=12, day=31, hour=23, minute=59, second=59, millisecond=999),
            ),
            ("Time", FHIRTime(hour=23, minute=59, second=59, millisecond=999)),
            ("Quantity", Quantity(value=Decimal("99999999999999999999999999.99999999"), unit="1")),
        ],
    )
    def test_max_value(self, type_name: str, expected: Any) -> None:
        assert conversion._max_value([type_name]) == expected

    @pytest.mark.parametrize("extreme", [conversion._min_value, conversion._max_value])
    @pytest.mark.parametrize("arguments", [[], [None], ["Bogus"]])
    def test_unknown_types_yield_null(self, extreme: Any, arguments: list[Any]) -> None:
        assert extreme(arguments) is None


class TestAggregateCounts:
    """Count, Sum, Avg, Min and Max."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [([[1, None, 2]], 2), ([[]], 0), (["not a list"], 0), ([], 0)],
    )
    def test_count(self, arguments: list[Any], expected: int) -> None:
        assert aggregate._count(arguments) == expected

    def test_sum_ignores_nulls(self) -> None:
        assert aggregate._sum([[1, 2, None]]) == 3

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_sum_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._sum(arguments) is None

    @pytest.mark.parametrize(
        ("values", "expected"),
        [([1, 2], 1.5), ([Decimal("1"), Decimal("2")], Decimal("1.5"))],
    )
    def test_avg(self, values: list[Any], expected: Any) -> None:
        assert aggregate._avg([values]) == expected

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_avg_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._avg(arguments) is None

    def test_min_and_max_ignore_nulls(self) -> None:
        assert aggregate._min([[3, None, 1]]) == 1
        assert aggregate._max([[3, None, 1]]) == 3

    @pytest.mark.parametrize("extreme", [aggregate._min, aggregate._max])
    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_extremes_yield_null(self, extreme: Any, arguments: list[Any]) -> None:
        assert extreme(arguments) is None


class TestAggregateBooleans:
    """AllTrue, AnyTrue, AllFalse and AnyFalse."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[True, True]], True),
            ([[True, None]], True),
            ([[True, False]], False),
            ([[]], True),
            (["not a list"], True),
            ([], True),
        ],
    )
    def test_all_true(self, arguments: list[Any], expected: bool) -> None:
        assert aggregate._all_true(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[False, True]], True),
            ([[False, False]], False),
            ([[None]], False),
            ([[]], False),
            (["not a list"], False),
            ([], False),
        ],
    )
    def test_any_true(self, arguments: list[Any], expected: bool) -> None:
        assert aggregate._any_true(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[False, False]], True),
            ([[False, None]], True),
            ([[True]], False),
            ([[]], True),
            (["not a list"], True),
            ([], True),
        ],
    )
    def test_all_false(self, arguments: list[Any], expected: bool) -> None:
        assert aggregate._all_false(arguments) is expected

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([[True, False]], True),
            ([[True, True]], False),
            ([[None]], False),
            ([[]], False),
            (["not a list"], False),
            ([], False),
        ],
    )
    def test_any_false(self, arguments: list[Any], expected: bool) -> None:
        assert aggregate._any_false(arguments) is expected


class TestAggregateStatistics:
    """Product, GeometricMean, variance, standard deviation, Median and Mode."""

    def test_product_multiplies_the_non_null_values(self) -> None:
        assert aggregate._product([[2, 3, 4, None]]) == 24

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_product_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._product(arguments) is None

    def test_geometric_mean(self) -> None:
        assert aggregate._geometric_mean([[1, 4]]) == pytest.approx(2.0)

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[-1, 0]]])
    def test_geometric_mean_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._geometric_mean(arguments) is None

    def test_population_variance(self) -> None:
        assert aggregate._population_variance([[1, 2, 3]]) == pytest.approx(2 / 3)

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_population_variance_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._population_variance(arguments) is None

    def test_sample_variance(self) -> None:
        assert aggregate._variance([[1, 2, 3]]) == pytest.approx(1.0)

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[1]]])
    def test_sample_variance_needs_two_values(self, arguments: list[Any]) -> None:
        assert aggregate._variance(arguments) is None

    def test_population_standard_deviation(self) -> None:
        assert aggregate._population_stddev([[1, 2, 3]]) == pytest.approx(math.sqrt(2 / 3))

    def test_population_standard_deviation_yields_null_for_an_empty_list(self) -> None:
        assert aggregate._population_stddev([[]]) is None

    def test_sample_standard_deviation(self) -> None:
        assert aggregate._stddev([[1, 2, 3]]) == pytest.approx(1.0)

    def test_sample_standard_deviation_needs_two_values(self) -> None:
        assert aggregate._stddev([[1]]) is None

    @pytest.mark.parametrize(
        ("values", "expected"),
        [([1, 2, 3], 2), ([1, 2, 3, 4], 2.5), ([3, 1, 2], 2), ([1, None, 3], 2)],
    )
    def test_median(self, values: list[Any], expected: Any) -> None:
        assert aggregate._median([values]) == expected

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_median_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._median(arguments) is None

    def test_mode_returns_the_single_most_frequent_value(self) -> None:
        assert aggregate._mode([[1, 1, 2]]) == 1

    def test_mode_returns_every_tied_value(self) -> None:
        assert aggregate._mode([[1, 2]]) == [1, 2]

    @pytest.mark.parametrize("arguments", [[], ["not a list"], [[]], [[None]]])
    def test_mode_yields_null(self, arguments: list[Any]) -> None:
        assert aggregate._mode(arguments) is None


class TestFunctionRegistration:
    """Conversion, math and aggregate functions are reachable through the registry."""

    @pytest.mark.parametrize(
        ("name", "category"),
        [
            ("ToString", "conversion"),
            ("ToInteger", "conversion"),
            ("ToDecimal", "conversion"),
            ("ToBoolean", "conversion"),
            ("ToDate", "conversion"),
            ("ToDateTime", "conversion"),
            ("ToTime", "conversion"),
            ("ToQuantity", "conversion"),
            ("ToConcept", "conversion"),
            ("Coalesce", "conversion"),
            ("IsNull", "conversion"),
            ("IsNotNull", "conversion"),
            ("IsTrue", "conversion"),
            ("IsFalse", "conversion"),
            ("ToList", "conversion"),
            ("ToChars", "conversion"),
            ("ConvertQuantity", "conversion"),
            ("Abs", "math"),
            ("Ceiling", "math"),
            ("Floor", "math"),
            ("Truncate", "math"),
            ("Round", "math"),
            ("Ln", "math"),
            ("Log", "math"),
            ("Exp", "math"),
            ("Power", "math"),
            ("Sqrt", "math"),
            ("Precision", "math"),
            ("LowBoundary", "math"),
            ("HighBoundary", "math"),
            ("MinValue", "math"),
            ("MaxValue", "math"),
            ("Count", "aggregate"),
            ("Sum", "aggregate"),
            ("Avg", "aggregate"),
            ("Min", "aggregate"),
            ("Max", "aggregate"),
            ("Product", "aggregate"),
            ("Median", "aggregate"),
            ("Mode", "aggregate"),
        ],
    )
    def test_registered_under_the_expected_category(self, name: str, category: str) -> None:
        registry = get_registry()
        assert registry.has(name)
        assert name in registry.list_functions(category=category)

    def test_average_is_an_alias_of_avg(self) -> None:
        registry = get_registry()
        assert registry.get("Average") is registry.get("Avg")
        assert registry.call("Average", [[2, 4]]) == 3

    def test_calling_an_unregistered_function_raises(self) -> None:
        with pytest.raises(KeyError, match="Function not found: NoSuchFunction"):
            get_registry().call("NoSuchFunction", [])
