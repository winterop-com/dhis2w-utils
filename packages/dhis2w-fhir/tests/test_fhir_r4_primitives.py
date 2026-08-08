"""Unit tests for the R4 primitive checks: lexical shape, the calendar and the clock behind it, and normalisation."""

from __future__ import annotations

import pytest
from dhis2w_fhir.r4 import (
    FHIR_DATE_PATTERN,
    FHIR_DATE_TIME_PATTERN,
    FHIR_TIME_PATTERN,
    is_calendar_date,
    is_fhir_date,
    is_fhir_date_time,
    is_fhir_time,
    seconds_precision,
    zoned_date_time,
)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("2026", True),
        ("2026-12", True),
        ("2026-02-28", True),
        ("2024-02-29", True),
        ("2026-13", False),
        ("2026-00", False),
        ("2026-02-30", False),
        ("2026-99-99", False),
        ("26-01-01", False),
    ],
)
def test_an_r4_date_must_be_a_real_date(value: str, valid: bool) -> None:
    """The lexical shape is not enough: a date answer names a day the calendar actually has."""
    assert is_fhir_date(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("23:59:59", True),
        ("00:00:00", True),
        ("12:00:00.500", True),
        ("24:00:00", False),
        ("25:99:99", False),
        ("12:60:00", False),
    ],
)
def test_an_r4_time_must_be_a_real_time(value: str, valid: bool) -> None:
    """The lexical shape is not enough: a time answer names a reading the clock actually shows."""
    assert is_fhir_time(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("2026", True),
        ("2026-12", True),
        ("2026-01-01", True),
        ("2026-01-01T12:00:00Z", True),
        ("2026-01-01T12:00:00.000Z", True),
        ("2026-01-01T12:00:00+14:00", True),
        ("2026-01-01T12:00:00-12:00", True),
        ("2026-13", False),
        ("2026-02-30", False),
        ("2026-99-99", False),
        ("2026-99-99T25:99:99+99:00", False),
        ("2026-01-01T25:00:00Z", False),
        ("2026-01-01T12:00:00+99:00", False),
        ("2026-01-01T12:00:00+14:30", False),
        ("2026-01-01T12:00:00-13:00", False),
    ],
)
def test_an_r4_date_time_must_be_a_real_instant_in_a_real_zone(value: str, valid: bool) -> None:
    """A dateTime clears the calendar, the clock, and an offset no zone on earth sits outside of."""
    assert is_fhir_date_time(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("2026", True),
        ("2026-01", True),
        ("2026-12", True),
        ("2026-01-31", True),
        ("2026-00", False),
        ("2026-13", False),
        ("2026-02-30", False),
    ],
)
def test_the_calendar_check_reads_a_date_at_whatever_precision_it_carries(value: str, valid: bool) -> None:
    """A bare year passes unconditionally, a year-month names a month that exists, a full date is parsed."""
    assert is_calendar_date(value) is valid


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("2025-12-30T00:00:00.000", "2025-12-30T00:00:00.000Z"),
        ("2025-12-30T00:00:00Z", "2025-12-30T00:00:00Z"),
        ("2025-12-30T00:00:00+02:00", "2025-12-30T00:00:00+02:00"),
        ("2025-12-30", "2025-12-30"),
    ],
)
def test_a_zoneless_dhis2_timestamp_gains_the_utc_zone_fhir_requires(stored: str, expected: str) -> None:
    """DHIS2 serves zone-less local timestamps; an R4 dateTime carrying a time must carry a zone (BUGS.md #62)."""
    assert zoned_date_time(stored) == expected


@pytest.mark.parametrize(
    ("stored", "timezone", "expected"),
    [
        ("2025-12-30T00:00:00.000", "Asia/Vientiane", "2025-12-30T00:00:00.000+07:00"),
        ("2026-01-15T08:30:00", "Europe/Oslo", "2026-01-15T08:30:00+01:00"),
        ("2026-07-15T08:30:00", "Europe/Oslo", "2026-07-15T08:30:00+02:00"),
        ("2026-01-15T08:30:00", "America/New_York", "2026-01-15T08:30:00-05:00"),
        ("2026-07-15T08:30:00", "America/New_York", "2026-07-15T08:30:00-04:00"),
        ("2026-07-15T08:30:00", "Asia/Kathmandu", "2026-07-15T08:30:00+05:45"),
        ("2026-07-15T08:30:00", "UTC", "2026-07-15T08:30:00+00:00"),
    ],
)
def test_a_named_zone_stamps_the_offset_it_stood_at_on_that_very_timestamp(
    stored: str, timezone: str, expected: str
) -> None:
    """The offset is a fact about the instant, not about the zone: Oslo is +01:00 in January and +02:00 in July."""
    assert zoned_date_time(stored, timezone) == expected


def test_an_ambiguous_wall_clock_reading_resolves_to_one_offset() -> None:
    """The hour a DST-observing zone repeats has two offsets; the earlier one is taken, so a run is reproducible."""
    assert zoned_date_time("2026-10-25T02:30:00", "Europe/Oslo") == "2026-10-25T02:30:00+02:00"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("2025-12-30T00:00:00Z", "2025-12-30T00:00:00Z"),
        ("2025-12-30T00:00:00+02:00", "2025-12-30T00:00:00+02:00"),
        ("2025-12-30", "2025-12-30"),
        ("2026-99-99T25:99:99", "2026-99-99T25:99:99Z"),
    ],
)
def test_a_named_zone_touches_only_the_timestamps_that_need_one(stored: str, expected: str) -> None:
    """A value already zoned, or carrying no time, is left alone; one too malformed to read falls back to UTC."""
    assert zoned_date_time(stored, "Europe/Oslo") == expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("07:30", "07:30:00"),
        ("07:30:00", "07:30:00"),
        ("07:30:00.500", "07:30:00.500"),
    ],
)
def test_a_minute_precision_time_gains_the_seconds_r4_makes_mandatory(stored: str, expected: str) -> None:
    """R4 `time` has no minute precision, so a bare `HH:MM` is completed rather than refused."""
    assert seconds_precision(stored) == expected


def test_the_patterns_check_the_shape_and_nothing_more() -> None:
    """The patterns are lexical only, which is why every check pairs one with a real reading of the value."""
    assert FHIR_DATE_PATTERN.match("2026-99-99") is not None
    assert FHIR_TIME_PATTERN.match("25:99:99") is not None
    assert FHIR_DATE_TIME_PATTERN.match("2026-99-99T25:99:99Z") is not None
