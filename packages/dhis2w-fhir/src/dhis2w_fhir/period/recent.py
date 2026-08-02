"""Enumerate the most recent completed DHIS2 ISO periods of one period type.

This is the inverse of `parser.parse_period`, and it is written as an inverse rather than
as a second transcription of the upstream month offsets: each period type declares only how
its ISO strings are *spelled* for a given year, and the parser decides which of those strings
are real and what dates they cover. A candidate the parser refuses (`2024W53` in a 52-week
year, `2024NovQ5`) simply drops out, so the two can never disagree about a period's dates.

"Completed" means the period's end date is strictly before the reference day: a period still
being reported into is not an example of anything.
"""

from __future__ import annotations

import calendar
import datetime
from collections.abc import Callable

from dhis2w_fhir.period.parser import parse_period
from dhis2w_fhir.period.schemas import PeriodValue

__all__ = ["recent_periods"]

#: Extra years to enumerate beyond the requested count, so the yearly and financial types -
#: one period per year - can still answer a request for several periods.
_EXTRA_YEARS = 2

#: The ISO infix of every weekly variant, in the parser's registration order.
_WEEKLY_INFIXES = ("W", "WedW", "ThuW", "FriW", "SatW", "SunW")

#: The suffix of every financial-year type, in the parser's registration order.
_FINANCIAL_SUFFIXES = ("Feb", "April", "July", "Aug", "Sep", "Oct", "Nov")

#: The most weeks a year can hold, plus the bi-week and month-family ordinals.
_MAXIMUM_WEEKS = 53
_MAXIMUM_BI_WEEKS = 27


def _daily(year: int) -> list[str]:
    """Every `yyyyMMdd` of one calendar year."""
    return [
        f"{year}{month:02d}{day:02d}"
        for month in range(1, 13)
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
    ]


def _weekly(infix: str) -> Callable[[int], list[str]]:
    """Build the enumerator for one weekly variant (`yyyyWn`, `yyyyThuWn`, ...)."""

    def _build(year: int) -> list[str]:
        """Every week ordinal of one year; the parser drops the ones that year does not have."""
        return [f"{year}{infix}{week}" for week in range(1, _MAXIMUM_WEEKS + 1)]

    return _build


def _financial(suffix: str) -> Callable[[int], list[str]]:
    """Build the enumerator for one financial-year type (`yyyyApril`, `yyyyNov`, ...)."""

    def _build(year: int) -> list[str]:
        """The single financial year labelled `year`."""
        return [f"{year}{suffix}"]

    return _build


def _ordinals(template: str, count: int) -> Callable[[int], list[str]]:
    """Build the enumerator for a type whose ISO is the year plus a single-digit ordinal."""

    def _build(year: int) -> list[str]:
        """Every ordinal of one year, formatted through the type's ISO template."""
        return [template.format(year=year, ordinal=ordinal) for ordinal in range(1, count + 1)]

    return _build


#: How each registered period type spells its ISO strings for one year. The parser decides
#: which of them exist, so an over-generous enumerator (week 53, bi-week 27) is harmless.
_ISO_ENUMERATORS: dict[str, Callable[[int], list[str]]] = {
    "Daily": _daily,
    "Weekly": _weekly(_WEEKLY_INFIXES[0]),
    "WeeklyWednesday": _weekly(_WEEKLY_INFIXES[1]),
    "WeeklyThursday": _weekly(_WEEKLY_INFIXES[2]),
    "WeeklyFriday": _weekly(_WEEKLY_INFIXES[3]),
    "WeeklySaturday": _weekly(_WEEKLY_INFIXES[4]),
    "WeeklySunday": _weekly(_WEEKLY_INFIXES[5]),
    "BiWeekly": _ordinals("{year}BiW{ordinal}", _MAXIMUM_BI_WEEKS),
    "Monthly": _ordinals("{year}{ordinal:02d}", 12),
    "BiMonthly": _ordinals("{year}{ordinal:02d}B", 6),
    "Quarterly": _ordinals("{year}Q{ordinal}", 4),
    "QuarterlyNov": _ordinals("{year}NovQ{ordinal}", 4),
    "SixMonthly": _ordinals("{year}S{ordinal}", 2),
    "SixMonthlyApril": _ordinals("{year}AprilS{ordinal}", 2),
    "SixMonthlyNov": _ordinals("{year}NovS{ordinal}", 2),
    "Yearly": _ordinals("{year}", 1),
    "FinancialFeb": _financial(_FINANCIAL_SUFFIXES[0]),
    "FinancialApril": _financial(_FINANCIAL_SUFFIXES[1]),
    "FinancialJuly": _financial(_FINANCIAL_SUFFIXES[2]),
    "FinancialAug": _financial(_FINANCIAL_SUFFIXES[3]),
    "FinancialSep": _financial(_FINANCIAL_SUFFIXES[4]),
    "FinancialOct": _financial(_FINANCIAL_SUFFIXES[5]),
    "FinancialNov": _financial(_FINANCIAL_SUFFIXES[6]),
}


def recent_periods(period_type: str, count: int, today: datetime.date) -> list[str]:
    """The `count` most recent completed ISO periods of `period_type`, newest first.

    A period counts as completed when its end date falls strictly before `today`. An
    unregistered period type, or a non-positive count, yields an empty list rather than
    raising - the caller is discovering data, not validating configuration.
    """
    enumerator = _ISO_ENUMERATORS.get(period_type)
    if enumerator is None or count <= 0:
        return []
    completed: list[PeriodValue] = []
    for year in range(today.year + 1, today.year - count - _EXTRA_YEARS, -1):
        completed.extend(value for value in _parsed(enumerator(year)) if value.end_date < today)
    completed.sort(key=lambda value: (value.end_date, value.iso), reverse=True)
    return [value.iso for value in completed[:count]]


def _parsed(candidates: list[str]) -> list[PeriodValue]:
    """Parse every candidate ISO string, dropping the ones the grammar does not admit."""
    values: list[PeriodValue] = []
    for candidate in candidates:
        try:
            values.append(parse_period(candidate))
        except ValueError:
            continue
    return values
