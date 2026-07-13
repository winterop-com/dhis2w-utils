"""Hand-written period enums + ISO period math.

`PeriodType` is the frequency a `DataSet` collects data at (Daily, Monthly,
Quarterly…). DHIS2's `/api/schemas` reports `DataSet.periodType` as `TEXT`
(not CONSTANT) because upstream it's a Java class hierarchy —
`MonthlyPeriodType`, `DailyPeriodType`, etc. are subclasses, not enum
constants. We list the canonical type-name strings here as a StrEnum.

`RelativePeriod` mirrors the 45 boolean flags on the generated
`RelativePeriods` model (`generated/v43/oas/relative_periods.py`) — the
rolling windows a `Visualization` / `EventVisualization` / `Map` can pin
itself to (`last12Months`, `thisYear`, `lastSixMonth`, …). Use the enum
on builder APIs so callers don't have to remember the exact flag casing,
and materialise the selected set into a `RelativePeriods` model by
toggling the matching fields to `True`.

`parse_period`, `next_period_id`, `previous_period_id`, and
`period_start_end` are pure-python helpers that round-trip DHIS2's six
absolute period-id shapes (Daily / Weekly / Monthly / Quarterly /
SixMonthly / Yearly) without any HTTP. Useful when iterating over a
window for analytics queries without leaning on DHIS2's relative-period
shortcuts.

Both enums + the period math are version-independent — the value sets
haven't changed across 2.40+.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PeriodType(StrEnum):
    """DHIS2 period types — the valid values for `DataSet.periodType`."""

    DAILY = "Daily"
    WEEKLY = "Weekly"
    WEEKLY_WEDNESDAY = "WeeklyWednesday"
    WEEKLY_THURSDAY = "WeeklyThursday"
    WEEKLY_FRIDAY = "WeeklyFriday"
    WEEKLY_SATURDAY = "WeeklySaturday"
    WEEKLY_SUNDAY = "WeeklySunday"
    BI_WEEKLY = "BiWeekly"
    MONTHLY = "Monthly"
    BI_MONTHLY = "BiMonthly"
    QUARTERLY = "Quarterly"
    QUARTERLY_NOV = "QuarterlyNov"
    SIX_MONTHLY = "SixMonthly"
    SIX_MONTHLY_APRIL = "SixMonthlyApril"
    SIX_MONTHLY_NOV = "SixMonthlyNov"
    YEARLY = "Yearly"
    TWO_YEARLY = "TwoYearly"
    FINANCIAL_FEB = "FinancialFeb"
    FINANCIAL_APRIL = "FinancialApril"
    FINANCIAL_JULY = "FinancialJuly"
    FINANCIAL_AUG = "FinancialAug"
    FINANCIAL_SEP = "FinancialSep"
    FINANCIAL_OCT = "FinancialOct"
    FINANCIAL_NOV = "FinancialNov"


class RelativePeriod(StrEnum):
    """Rolling-window flags on the `RelativePeriods` model."""

    BI_MONTHS_THIS_YEAR = "biMonthsThisYear"
    LAST_10_FINANCIAL_YEARS = "last10FinancialYears"
    LAST_10_YEARS = "last10Years"
    LAST_12_MONTHS = "last12Months"
    LAST_12_WEEKS = "last12Weeks"
    LAST_14_DAYS = "last14Days"
    LAST_180_DAYS = "last180Days"
    LAST_2_SIX_MONTHS = "last2SixMonths"
    LAST_30_DAYS = "last30Days"
    LAST_3_DAYS = "last3Days"
    LAST_3_MONTHS = "last3Months"
    LAST_4_BI_WEEKS = "last4BiWeeks"
    LAST_4_QUARTERS = "last4Quarters"
    LAST_4_WEEKS = "last4Weeks"
    LAST_52_WEEKS = "last52Weeks"
    LAST_5_FINANCIAL_YEARS = "last5FinancialYears"
    LAST_5_YEARS = "last5Years"
    LAST_60_DAYS = "last60Days"
    LAST_6_BI_MONTHS = "last6BiMonths"
    LAST_6_MONTHS = "last6Months"
    LAST_7_DAYS = "last7Days"
    LAST_90_DAYS = "last90Days"
    LAST_BI_WEEK = "lastBiWeek"
    LAST_BIMONTH = "lastBimonth"
    LAST_FINANCIAL_YEAR = "lastFinancialYear"
    LAST_MONTH = "lastMonth"
    LAST_QUARTER = "lastQuarter"
    LAST_SIX_MONTH = "lastSixMonth"
    LAST_WEEK = "lastWeek"
    LAST_YEAR = "lastYear"
    MONTHS_LAST_YEAR = "monthsLastYear"
    MONTHS_THIS_YEAR = "monthsThisYear"
    QUARTERS_LAST_YEAR = "quartersLastYear"
    QUARTERS_THIS_YEAR = "quartersThisYear"
    THIS_BI_WEEK = "thisBiWeek"
    THIS_BIMONTH = "thisBimonth"
    THIS_DAY = "thisDay"
    THIS_FINANCIAL_YEAR = "thisFinancialYear"
    THIS_MONTH = "thisMonth"
    THIS_QUARTER = "thisQuarter"
    THIS_SIX_MONTH = "thisSixMonth"
    THIS_WEEK = "thisWeek"
    THIS_YEAR = "thisYear"
    WEEKS_THIS_YEAR = "weeksThisYear"
    YESTERDAY = "yesterday"


class PeriodKind(StrEnum):
    """Coarse classification used by the period-math helpers."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SIX_MONTHLY = "sixMonthly"
    YEARLY = "yearly"


class Period(BaseModel):
    """A parsed DHIS2 absolute period id with its start/end date range."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: PeriodKind
    start: date
    end: date


_DAILY_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_WEEKLY_RE = re.compile(r"^(\d{4})W(\d{1,2})$")
_MONTHLY_RE = re.compile(r"^(\d{4})(\d{2})$")
_QUARTERLY_RE = re.compile(r"^(\d{4})Q([1-4])$")
_SIX_MONTHLY_RE = re.compile(r"^(\d{4})S([12])$")
_YEARLY_RE = re.compile(r"^(\d{4})$")


def parse_period(period_id: str) -> Period:
    """Parse a DHIS2 period id (e.g. `202403`, `2024W12`, `20240315`).

    Recognises the six absolute kinds: daily, weekly (ISO), monthly,
    quarterly, six-monthly, yearly. Raises `ValueError` for unrecognised
    shapes (relative-period names like `LAST_12_MONTHS` are not absolute
    period ids — use `RelativePeriod` for those).
    """
    if match := _DAILY_RE.match(period_id):
        year, month, day = (int(g) for g in match.groups())
        d = date(year, month, day)
        return Period(id=period_id, kind=PeriodKind.DAILY, start=d, end=d)
    if match := _WEEKLY_RE.match(period_id):
        year, week = int(match.group(1)), int(match.group(2))
        if not 1 <= week <= 53:
            raise ValueError(f"week out of range in {period_id!r}: {week}")
        start = date.fromisocalendar(year, week, 1)
        return Period(id=period_id, kind=PeriodKind.WEEKLY, start=start, end=start + timedelta(days=6))
    if match := _MONTHLY_RE.match(period_id):
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            raise ValueError(f"month out of range in {period_id!r}: {month}")
        start = date(year, month, 1)
        end_year = year + 1 if month == 12 else year
        end_month = 1 if month == 12 else month + 1
        return Period(
            id=period_id, kind=PeriodKind.MONTHLY, start=start, end=date(end_year, end_month, 1) - timedelta(days=1)
        )
    if match := _QUARTERLY_RE.match(period_id):
        year, quarter = int(match.group(1)), int(match.group(2))
        first_month = (quarter - 1) * 3 + 1
        start = date(year, first_month, 1)
        end_year = year + 1 if quarter == 4 else year
        end_month = 1 if quarter == 4 else first_month + 3
        return Period(
            id=period_id, kind=PeriodKind.QUARTERLY, start=start, end=date(end_year, end_month, 1) - timedelta(days=1)
        )
    if match := _SIX_MONTHLY_RE.match(period_id):
        year, half = int(match.group(1)), int(match.group(2))
        if half == 1:
            return Period(id=period_id, kind=PeriodKind.SIX_MONTHLY, start=date(year, 1, 1), end=date(year, 6, 30))
        return Period(id=period_id, kind=PeriodKind.SIX_MONTHLY, start=date(year, 7, 1), end=date(year, 12, 31))
    if match := _YEARLY_RE.match(period_id):
        year = int(match.group(1))
        return Period(id=period_id, kind=PeriodKind.YEARLY, start=date(year, 1, 1), end=date(year, 12, 31))
    raise ValueError(f"unrecognised DHIS2 period id: {period_id!r}")


def next_period_id(period_id: str) -> str:
    """Return the period id immediately following `period_id` in the same kind."""
    return _shift_period_id(period_id, +1)


def previous_period_id(period_id: str) -> str:
    """Return the period id immediately preceding `period_id` in the same kind."""
    return _shift_period_id(period_id, -1)


def period_start_end(period_id: str) -> tuple[date, date]:
    """Return `(start, end)` dates (both inclusive) for a DHIS2 period id."""
    parsed = parse_period(period_id)
    return parsed.start, parsed.end


def _shift_period_id(period_id: str, delta: int) -> str:
    """Move `period_id` forward (delta=+1) or backward (delta=-1) by one slot."""
    parsed = parse_period(period_id)
    if parsed.kind is PeriodKind.DAILY:
        next_day = parsed.start + timedelta(days=delta)
        return next_day.strftime("%Y%m%d")
    if parsed.kind is PeriodKind.WEEKLY:
        next_week_anchor = parsed.start + timedelta(days=delta * 7)
        iso_year, iso_week, _ = next_week_anchor.isocalendar()
        return f"{iso_year}W{iso_week:02d}"
    if parsed.kind is PeriodKind.MONTHLY:
        year, month = parsed.start.year, parsed.start.month
        return _format_monthly(year, month + delta)
    if parsed.kind is PeriodKind.QUARTERLY:
        year, quarter = parsed.start.year, (parsed.start.month - 1) // 3 + 1
        return _format_quarterly(year, quarter + delta)
    if parsed.kind is PeriodKind.SIX_MONTHLY:
        year, half = parsed.start.year, 1 if parsed.start.month == 1 else 2
        return _format_six_monthly(year, half + delta)
    return f"{parsed.start.year + delta:04d}"


def _format_monthly(year: int, month: int) -> str:
    """Wrap month into a valid `(year, 1..12)` pair and emit `YYYYMM`."""
    while month < 1:
        year -= 1
        month += 12
    while month > 12:
        year += 1
        month -= 12
    return f"{year:04d}{month:02d}"


def _format_quarterly(year: int, quarter: int) -> str:
    """Wrap quarter into a valid `(year, 1..4)` pair and emit `YYYYQN`."""
    while quarter < 1:
        year -= 1
        quarter += 4
    while quarter > 4:
        year += 1
        quarter -= 4
    return f"{year:04d}Q{quarter}"


def _format_six_monthly(year: int, half: int) -> str:
    """Wrap half into a valid `(year, 1..2)` pair and emit `YYYYSN`."""
    while half < 1:
        year -= 1
        half += 2
    while half > 2:
        year += 1
        half -= 2
    return f"{year:04d}S{half}"


__all__ = [
    "Period",
    "PeriodKind",
    "PeriodType",
    "RelativePeriod",
    "next_period_id",
    "parse_period",
    "period_start_end",
    "previous_period_id",
]
