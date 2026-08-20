"""Tests for the CQL date and time standard-library functions.

Covers the Today / Now / TimeOfDay clock readers, the Date / DateTime / Time
constructors with their range validation, every component extractor, the
timezone-offset reader and DurationBetween.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql.functions import datetime_funcs
from dhis2w_fhir_engine.engine.cql.functions.registry import get_registry
from dhis2w_fhir_engine.engine.exceptions import CQLError
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime


class TestClockFunctions:
    """Today, Now and TimeOfDay read the system clock."""

    def test_today_matches_the_system_date(self) -> None:
        today = date.today()
        result = datetime_funcs._today([])
        assert result == FHIRDate(year=today.year, month=today.month, day=today.day)

    def test_now_carries_full_precision_in_utc(self) -> None:
        before = datetime.now(UTC)
        result = datetime_funcs._now([])
        assert result.tz_offset == "Z"
        assert result.millisecond is not None
        assert result.year == before.year
        moment = result.to_datetime()
        assert moment is not None
        assert abs((moment - before).total_seconds()) < 60

    def test_time_of_day_carries_full_precision(self) -> None:
        result = datetime_funcs._time_of_day([])
        assert 0 <= result.hour <= 23
        assert result.minute is not None and 0 <= result.minute <= 59
        assert result.second is not None and 0 <= result.second <= 59
        assert result.millisecond is not None and 0 <= result.millisecond <= 999


class TestDateConstructor:
    """The Date constructor builds a FHIRDate from its components."""

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ([2020], FHIRDate(year=2020)),
            ([2020, 5], FHIRDate(year=2020, month=5)),
            ([2020, 5, 6], FHIRDate(year=2020, month=5, day=6)),
            (["2020", "5", "6"], FHIRDate(year=2020, month=5, day=6)),
        ],
    )
    def test_components(self, arguments: list[Any], expected: FHIRDate) -> None:
        assert datetime_funcs._date_constructor(arguments) == expected

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_missing_year_yields_null(self, arguments: list[Any]) -> None:
        assert datetime_funcs._date_constructor(arguments) is None


class TestDateTimeConstructor:
    """The DateTime constructor validates every component range."""

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_missing_year_yields_null(self, arguments: list[Any]) -> None:
        assert datetime_funcs._datetime_constructor(arguments) is None

    def test_full_precision_with_timezone(self) -> None:
        result = datetime_funcs._datetime_constructor([2020, 1, 2, 3, 4, 5, 6, "+02:00"])
        assert result == FHIRDateTime(
            year=2020,
            month=1,
            day=2,
            hour=3,
            minute=4,
            second=5,
            millisecond=6,
            tz_offset="+02:00",
        )

    def test_year_only(self) -> None:
        assert datetime_funcs._datetime_constructor([2020]) == FHIRDateTime(year=2020)

    def test_explicit_null_components_are_dropped(self) -> None:
        result = datetime_funcs._datetime_constructor([2020, 1, None, None])
        assert result == FHIRDateTime(year=2020, month=1)

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            ([0], "DateTime year 0 out of range (1-9999)"),
            ([10000], "DateTime year 10000 out of range (1-9999)"),
            ([2020, 13], "DateTime month 13 out of range (1-12)"),
            ([2020, 0], "DateTime month 0 out of range (1-12)"),
            ([2020, 1, 32], "DateTime day 32 out of range (1-31)"),
            ([2020, 1, 1, 24], "DateTime hour 24 out of range (0-23)"),
            ([2020, 1, 1, 1, 60], "DateTime minute 60 out of range (0-59)"),
            ([2020, 1, 1, 1, 1, 60], "DateTime second 60 out of range (0-59)"),
            ([2020, 1, 1, 1, 1, 1, 1000], "DateTime millisecond 1000 out of range (0-999)"),
        ],
    )
    def test_out_of_range_components_raise(self, arguments: list[Any], message: str) -> None:
        with pytest.raises(CQLError) as excinfo:
            datetime_funcs._datetime_constructor(arguments)
        assert str(excinfo.value) == message


class TestTimeConstructor:
    """The Time constructor validates every component range."""

    @pytest.mark.parametrize("arguments", [[], [None]])
    def test_missing_hour_yields_null(self, arguments: list[Any]) -> None:
        assert datetime_funcs._time_constructor(arguments) is None

    def test_full_precision(self) -> None:
        result = datetime_funcs._time_constructor([1, 2, 3, 4])
        assert result == FHIRTime(hour=1, minute=2, second=3, millisecond=4)

    def test_hour_only(self) -> None:
        assert datetime_funcs._time_constructor([9]) == FHIRTime(hour=9)

    @pytest.mark.parametrize(
        ("arguments", "message"),
        [
            ([24], "Time hour 24 out of range (0-23)"),
            ([-1], "Time hour -1 out of range (0-23)"),
            ([1, 60], "Time minute 60 out of range (0-59)"),
            ([1, 1, 60], "Time second 60 out of range (0-59)"),
            ([1, 1, 1, 1000], "Time millisecond 1000 out of range (0-999)"),
        ],
    )
    def test_out_of_range_components_raise(self, arguments: list[Any], message: str) -> None:
        with pytest.raises(CQLError) as excinfo:
            datetime_funcs._time_constructor(arguments)
        assert str(excinfo.value) == message


class TestDateComponentExtractors:
    """Year, Month and Day read the date part of any supported value."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020), 2020),
            (FHIRDateTime(year=2021), 2021),
            (date(2019, 1, 1), 2019),
            (datetime(2018, 1, 1), 2018),
        ],
    )
    def test_year(self, value: Any, expected: int) -> None:
        assert datetime_funcs._year([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020, month=3), 3),
            (FHIRDateTime(year=2020, month=4), 4),
            (date(2019, 5, 1), 5),
            (datetime(2018, 6, 1), 6),
            (FHIRDate(year=2020), None),
        ],
    )
    def test_month(self, value: Any, expected: int | None) -> None:
        assert datetime_funcs._month([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDate(year=2020, month=3, day=9), 9),
            (FHIRDateTime(year=2020, month=3, day=8), 8),
            (date(2019, 4, 7), 7),
            (datetime(2018, 4, 6), 6),
            (FHIRDate(year=2020, month=3), None),
        ],
    )
    def test_day(self, value: Any, expected: int | None) -> None:
        assert datetime_funcs._day([value]) == expected

    @pytest.mark.parametrize("extractor", [datetime_funcs._year, datetime_funcs._month, datetime_funcs._day])
    @pytest.mark.parametrize("arguments", [[], [None], ["not a date"], [FHIRTime(hour=1)]])
    def test_unsupported_input_yields_null(self, extractor: Any, arguments: list[Any]) -> None:
        assert extractor(arguments) is None


class TestTimeComponentExtractors:
    """Hour, Minute, Second and Millisecond read the time part of any supported value."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRDateTime(year=2020, hour=5), 5),
            (FHIRTime(hour=6), 6),
            (datetime(2020, 1, 1, 7), 7),
            (time(8), 8),
        ],
    )
    def test_hour(self, value: Any, expected: int) -> None:
        assert datetime_funcs._hour([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=1, minute=2), 2),
            (FHIRDateTime(year=2020, hour=1, minute=3), 3),
            (time(1, 4), 4),
            (datetime(2020, 1, 1, 1, 5), 5),
            (FHIRTime(hour=1), None),
        ],
    )
    def test_minute(self, value: Any, expected: int | None) -> None:
        assert datetime_funcs._minute([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=1, minute=2, second=3), 3),
            (FHIRDateTime(year=2020, hour=1, minute=2, second=4), 4),
            (time(1, 2, 5), 5),
            (datetime(2020, 1, 1, 1, 2, 6), 6),
            (FHIRTime(hour=1, minute=2), None),
        ],
    )
    def test_second(self, value: Any, expected: int | None) -> None:
        assert datetime_funcs._second([value]) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (FHIRTime(hour=1, millisecond=250), 250),
            (FHIRDateTime(year=2020, hour=1, millisecond=125), 125),
            (time(1, 0, 0, 123456), 123),
            (datetime(2020, 1, 1, 0, 0, 0, 7000), 7),
            (FHIRTime(hour=1), None),
        ],
    )
    def test_millisecond(self, value: Any, expected: int | None) -> None:
        assert datetime_funcs._millisecond([value]) == expected

    @pytest.mark.parametrize(
        "extractor",
        [
            datetime_funcs._hour,
            datetime_funcs._minute,
            datetime_funcs._second,
            datetime_funcs._millisecond,
        ],
    )
    @pytest.mark.parametrize("arguments", [[], [None], ["not a time"], [FHIRDate(year=2020)]])
    def test_unsupported_input_yields_null(self, extractor: Any, arguments: list[Any]) -> None:
        assert extractor(arguments) is None


class TestTimezoneOffset:
    """TimezoneOffset reports the offset of a DateTime in hours."""

    @pytest.mark.parametrize(
        ("tz_offset", "expected"),
        [
            ("Z", Decimal("0")),
            ("+05:30", Decimal("5.5")),
            ("-08:00", Decimal("-8.0")),
            ("+02:00", Decimal("2.0")),
            ("+05", Decimal("5.0")),
        ],
    )
    def test_offsets(self, tz_offset: str, expected: Decimal) -> None:
        value = FHIRDateTime(year=2020, tz_offset=tz_offset)
        assert datetime_funcs._timezone_offset([value]) == expected

    @pytest.mark.parametrize(
        "arguments",
        [[], [None], ["2020-01-01"], [FHIRDateTime(year=2020)], [FHIRDate(year=2020)]],
    )
    def test_missing_offset_yields_null(self, arguments: list[Any]) -> None:
        assert datetime_funcs._timezone_offset(arguments) is None


class TestDurationBetween:
    """DurationBetween counts whole units between two points in time."""

    @pytest.mark.parametrize("arguments", [[], [None, None], [FHIRDate(year=2020), None]])
    def test_missing_operands_yield_null(self, arguments: list[Any]) -> None:
        assert datetime_funcs._duration_between(arguments) is None

    def test_day_precision_is_the_default(self) -> None:
        low = FHIRDate(year=2020, month=1, day=1)
        high = FHIRDate(year=2020, month=1, day=11)
        assert datetime_funcs._duration_between([low, high]) == 10

    @pytest.mark.parametrize("precision", ["day", "days"])
    def test_day_precision_aliases(self, precision: str) -> None:
        low = FHIRDate(year=2020, month=1, day=1)
        high = FHIRDate(year=2020, month=1, day=11)
        assert datetime_funcs._duration_between([low, high, precision]) == 10

    @pytest.mark.parametrize(
        ("precision", "expected"),
        [
            ("hour", 27),
            ("hours", 27),
            ("minute", 1650),
            ("minutes", 1650),
            ("second", 99015),
            ("seconds", 99015),
        ],
    )
    def test_sub_day_precisions(self, precision: str, expected: int) -> None:
        low = FHIRDateTime(year=2020, month=1, day=1, hour=0, minute=0, second=0)
        high = FHIRDateTime(year=2020, month=1, day=2, hour=3, minute=30, second=15)
        assert datetime_funcs._duration_between([low, high, precision]) == expected

    def test_an_unsupported_precision_yields_null(self) -> None:
        low = FHIRDateTime(year=2020, month=1, day=1, hour=0)
        high = FHIRDateTime(year=2020, month=1, day=2, hour=0)
        assert datetime_funcs._duration_between([low, high, "year"]) is None

    def test_partial_precision_operands_yield_null(self) -> None:
        low = FHIRDate(year=2020)
        high = FHIRDate(year=2020, month=1, day=11)
        assert datetime_funcs._duration_between([low, high]) is None

    def test_python_dates_are_accepted(self) -> None:
        assert datetime_funcs._duration_between([date(2020, 1, 1), date(2020, 1, 5)]) == 4

    @pytest.mark.parametrize(
        "arguments",
        [["a", "b"], [datetime(2020, 1, 1), "b"], ["a", datetime(2020, 1, 1)]],
    )
    def test_non_temporal_operands_yield_null(self, arguments: list[Any]) -> None:
        assert datetime_funcs._duration_between(arguments) is None


class TestDateTimeRegistration:
    """Every date and time function is reachable through the shared registry."""

    @pytest.mark.parametrize(
        "name",
        [
            "Today",
            "Now",
            "TimeOfDay",
            "Date",
            "DateTime",
            "Time",
            "Year",
            "Month",
            "Day",
            "Hour",
            "Minute",
            "Second",
            "Millisecond",
            "TimezoneOffset",
            "DurationBetween",
        ],
    )
    def test_registered_under_the_datetime_category(self, name: str) -> None:
        registry = get_registry()
        assert registry.has(name)
        assert name in registry.list_functions(category="datetime")

    def test_call_goes_through_the_registry(self) -> None:
        registry = get_registry()
        assert registry.call("Year", [FHIRDate(year=2020, month=2, day=3)]) == 2020
        assert registry.call("date", [2020, 2, 3]) == FHIRDate(year=2020, month=2, day=3)
