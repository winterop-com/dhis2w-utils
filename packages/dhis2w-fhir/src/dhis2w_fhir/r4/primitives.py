"""Lexical and semantic checks for the R4 primitive types the emitted and captured documents carry.

The patterns are the shape only (https://hl7.org/fhir/R4/datatypes.html#primitive): `2026-99-99`
and `25:99:99` match them, so every check pairs the pattern with a real reading of the calendar,
the clock, or the zone. `zoned_date_time` and `seconds_precision` normalise the two DHIS2
spellings that are one keystroke short of a legal R4 primitive.
"""

from __future__ import annotations

import datetime
import re
import zoneinfo

#: The lexical shape of an R4 `date`: a year, optionally a month, optionally a day.
FHIR_DATE_PATTERN = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

#: The lexical shape of an R4 `dateTime`: an R4 date, optionally a zoned time.
FHIR_DATE_TIME_PATTERN = re.compile(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2}))?)?)?$")

#: The lexical shape of an R4 `time`: hours, minutes, and mandatory seconds.
FHIR_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}(\.\d+)?$")

#: How many dash-separated parts a year-only and a year-month R4 date carry.
_YEAR_ONLY_DATE_PARTS = 1
_YEAR_MONTH_DATE_PARTS = 2

#: The month numbers a year-month R4 date may name.
_FIRST_MONTH = 1
_LAST_MONTH = 12

#: The UTC offsets an R4 dateTime may carry. The stdlib accepts anything under a full day, so
#: the real-world span is enforced here: no zone sits west of -12:00 or east of +14:00.
_EARLIEST_UTC_OFFSET = datetime.timedelta(hours=-12)
_LATEST_UTC_OFFSET = datetime.timedelta(hours=14)

#: The zone FHIR requires on a dateTime that carries a time, and DHIS2 leaves off (BUGS.md #62).
#: This is the reading a project that names no zone gets: the wall clock read as UTC.
_ASSUMED_ZONE = "Z"

#: How many minutes an hour of UTC offset spans, which the offset literal is written out of.
_MINUTES_PER_HOUR = 60
_SECONDS_PER_MINUTE = 60

#: How many colon-separated parts a bare `HH:MM` time has, before FHIR's mandatory seconds.
_MINUTE_ONLY_TIME_PARTS = 2


def is_fhir_date(value: str) -> bool:
    """Check an R4 `date`: the lexical shape, then the calendar at whatever precision it carries."""
    return bool(FHIR_DATE_PATTERN.match(value)) and is_calendar_date(value)


def is_fhir_time(value: str) -> bool:
    """Check an R4 `time`: the lexical shape, then a real reading of the clock (`24:00:00` is not one)."""
    if not FHIR_TIME_PATTERN.match(value):
        return False
    try:
        datetime.time.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_fhir_date_time(value: str) -> bool:
    """Check an R4 `dateTime`: the lexical shape, then a real instant inside the offsets R4 allows.

    A date-only dateTime is exactly an R4 date, so it clears the calendar the same way. A value
    carrying a time clears the calendar, the clock, and the zone in one parse, and then its
    offset is bounded, which the stdlib leaves open all the way to a full day either side.
    """
    if not FHIR_DATE_TIME_PATTERN.match(value):
        return False
    if "T" not in value:
        return is_calendar_date(value)
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return offset is not None and _EARLIEST_UTC_OFFSET <= offset <= _LATEST_UTC_OFFSET


def is_calendar_date(value: str) -> bool:
    """Check a lexically valid R4 date against the calendar: a bare year passes, a month must exist."""
    parts = value.split("-")
    if len(parts) == _YEAR_ONLY_DATE_PARTS:
        return True
    if len(parts) == _YEAR_MONTH_DATE_PARTS:
        return _FIRST_MONTH <= int(parts[1]) <= _LAST_MONTH
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def zoned_date_time(value: str, timezone: str | None = None) -> str:
    """Give a DHIS2 timestamp the offset R4 requires whenever it carries a time but carries no zone.

    DHIS2 serves `occurredAt` and `DATETIME` data values as zone-less local timestamps
    (`2025-12-30T00:00:00.000`) under fields its OpenAPI types as `Instant`, and an R4
    `dateTime` carrying a time must carry an offset. See BUGS.md #62.

    `timezone` is the IANA zone those wall-clock readings are taken in, which the project states
    as `[generate] timezone`. The offset is resolved against the timestamp itself, so a zone that
    observes DST stamps its summer readings and its winter readings differently. Naming no zone
    reads the wall clock as UTC, and so does a timestamp too malformed to resolve an offset for -
    the value then fails `is_fhir_date_time` and its caller answers it as a string.
    """
    _, separator, time_part = value.partition("T")
    if not separator or time_part.endswith(("Z", "z")) or "+" in time_part or "-" in time_part:
        return value
    offset = _utc_offset_literal(value, timezone) if timezone is not None else None
    return f"{value}{offset or _ASSUMED_ZONE}"


def _utc_offset_literal(value: str, timezone: str) -> str | None:
    """The `+HH:MM` / `-HH:MM` one IANA zone stood at on one zone-less timestamp; None when neither reads."""
    try:
        wall_clock = datetime.datetime.fromisoformat(value)
        zone = zoneinfo.ZoneInfo(timezone)
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        return None
    offset = wall_clock.replace(tzinfo=zone).utcoffset()
    if offset is None:
        return None
    total_minutes = round(offset.total_seconds() / _SECONDS_PER_MINUTE)
    hours, minutes = divmod(abs(total_minutes), _MINUTES_PER_HOUR)
    return f"{'-' if total_minutes < 0 else '+'}{hours:02d}:{minutes:02d}"


def seconds_precision(value: str) -> str:
    """Give a bare `HH:MM` the seconds R4 `time` makes mandatory."""
    return f"{value}:00" if len(value.split(":")) == _MINUTE_ONLY_TIME_PARTS else value
