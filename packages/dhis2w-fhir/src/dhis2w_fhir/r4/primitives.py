"""Lexical and semantic checks for the R4 primitive types the emitted and captured documents carry.

The patterns are the shape only (https://hl7.org/fhir/R4/datatypes.html#primitive): `2026-99-99`
and `25:99:99` match them, so every check pairs the pattern with a real reading of the calendar,
the clock, or the zone. `zoned_date_time` and `seconds_precision` normalise the two DHIS2
spellings that are one keystroke short of a legal R4 primitive.
"""

from __future__ import annotations

import datetime
import re

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
_ASSUMED_ZONE = "Z"

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


def zoned_date_time(value: str) -> str:
    """Give a DHIS2 timestamp the UTC zone R4 requires whenever it carries a time but no offset.

    DHIS2 serves `occurredAt` and `DATETIME` data values as zone-less local timestamps
    (`2025-12-30T00:00:00.000`) under fields its OpenAPI types as `Instant`, and an R4
    `dateTime` carrying a time must carry an offset. See BUGS.md #62.
    """
    _, separator, time_part = value.partition("T")
    if not separator or time_part.endswith(("Z", "z")) or "+" in time_part or "-" in time_part:
        return value
    return f"{value}{_ASSUMED_ZONE}"


def seconds_precision(value: str) -> str:
    """Give a bare `HH:MM` the seconds R4 `time` makes mandatory."""
    return f"{value}:00" if len(value.split(":")) == _MINUTE_ONLY_TIME_PARTS else value
