"""Parse a DHIS2 ISO period string into its period type and the date range it covers.

The rules below are transcribed from dhis2-core `master`: `Period.Input.of` tokenizes the
string, `org.hisp.dhis.calendar.DateUnitPeriodTypeParser` resolves it to a date interval, and
the individual `*PeriodType` classes supply the month offsets. Everything here assumes the
default `Iso8601Calendar`; DHIS2's alternative system calendars (Ethiopian, Nepali) take a
different branch upstream and are out of scope.

Two properties of the upstream tokenizer are reproduced deliberately:

- **Parsing is length-driven, not pattern-driven.** The string length picks the branch, so
  zero-padding changes the meaning: `2024W01` is week 1, but `2024Q01` is not a quarter at all
  (quarter, semester, and `NovQ`/`NovS` ordinals are single-digit only).
- **The week-1 rule is `WeekFields.of(firstDayOfWeek, 4)`.** Week 1 of year Y is the earliest
  week, aligned to that type's start-of-week day, holding at least four days of year Y. For the
  Monday-start `Weekly` type that is plain ISO-8601 (the week containing 4 January). The named
  variants shift the alignment day only - the four-day rule is unchanged - so `2024ThuW1` starts
  Thursday 2024-01-04 while `2024FriW1` starts Friday 2023-12-29. `BiWeekly` always aligns to
  Monday and maps bi-week `n` onto ISO week `2n - 1`.

The November family is the exception to year labelling: `FinancialNov`, `QuarterlyNov` Q1, and
`SixMonthlyNov` S1 all start in `yyyy - 1`, so their `yyyy` names the year the period ends in.
Every other multi-year-spanning type (`FinancialApril`, `SixMonthlyApril` S2, ...) is labelled by
the year it starts in.
"""

from __future__ import annotations

import calendar
import datetime

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.period.schemas import PeriodValue

__all__ = ["parse_period"]

_MINIMUM_LENGTH = 4
_MAXIMUM_LENGTH = 11
#: DHIS2's `WeekFields` minimal-days-in-first-week constant.
_MINIMAL_DAYS_IN_FIRST_WEEK = 4
_DAYS_PER_WEEK = 7


class _WeeklyVariant(BaseModel):
    """One weekly period type: its name, the ISO infix, and the weekday its weeks start on."""

    model_config = ConfigDict(frozen=True)

    period_type: str
    infix: str
    first_weekday: int


#: The six registered weekly types. `first_weekday` is Python's Monday=0 ... Sunday=6 index,
#: matching `PeriodType.MAP_WEEK_TYPE`.
_WEEKLY_VARIANTS: tuple[_WeeklyVariant, ...] = (
    _WeeklyVariant(period_type="Weekly", infix="W", first_weekday=0),
    _WeeklyVariant(period_type="WeeklyWednesday", infix="WedW", first_weekday=2),
    _WeeklyVariant(period_type="WeeklyThursday", infix="ThuW", first_weekday=3),
    _WeeklyVariant(period_type="WeeklyFriday", infix="FriW", first_weekday=4),
    _WeeklyVariant(period_type="WeeklySaturday", infix="SatW", first_weekday=5),
    _WeeklyVariant(period_type="WeeklySunday", infix="SunW", first_weekday=6),
)

#: The named-weekday variants only, keyed by the four-character infix at offset 4.
_NAMED_WEEKLY_VARIANTS: tuple[_WeeklyVariant, ...] = tuple(
    variant for variant in _WEEKLY_VARIANTS if variant.infix != "W"
)


class _FinancialVariant(BaseModel):
    """One financial-year period type: its name, ISO suffix, start month, and year shift."""

    model_config = ConfigDict(frozen=True)

    period_type: str
    suffix: str
    start_month: int
    year_offset: int = 0


#: The seven registered financial types. Only November shifts the start into the previous year.
_FINANCIAL_VARIANTS: tuple[_FinancialVariant, ...] = (
    _FinancialVariant(period_type="FinancialFeb", suffix="Feb", start_month=2),
    _FinancialVariant(period_type="FinancialApril", suffix="April", start_month=4),
    _FinancialVariant(period_type="FinancialJuly", suffix="July", start_month=7),
    _FinancialVariant(period_type="FinancialAug", suffix="Aug", start_month=8),
    _FinancialVariant(period_type="FinancialSep", suffix="Sep", start_month=9),
    _FinancialVariant(period_type="FinancialOct", suffix="Oct", start_month=10),
    _FinancialVariant(period_type="FinancialNov", suffix="Nov", start_month=11, year_offset=-1),
)


def parse_period(iso: str) -> PeriodValue:
    """Parse a DHIS2 ISO period string into its period type, start date, and end date."""
    if len(iso) < _MINIMUM_LENGTH or len(iso) > _MAXIMUM_LENGTH:
        raise ValueError(f"not a DHIS2 ISO period: {iso!r} (expected 4 to 11 characters)")
    year = _digits(iso, 0, 4)
    parsed = _parse_by_length(iso, year)
    if parsed is None:
        raise ValueError(f"not a DHIS2 ISO period: {iso!r}")
    return parsed


def _parse_by_length(iso: str, year: int) -> PeriodValue | None:
    """Dispatch on string length exactly as DHIS2's `Period.Input.of` does."""
    length = len(iso)
    if length == 4:
        return _yearly(iso, year)
    if length == 5:
        return None
    if length == 6:
        return _parse_short(iso, year)
    if length == 7:
        return _parse_medium(iso, year)
    if length == 8:
        return _parse_long(iso, year)
    if length == 9:
        return _parse_longer(iso, year)
    if length == 10:
        return _parse_longest(iso, year)
    return _six_monthly_april(iso, year) if iso[4:10] == "AprilS" else None


def _parse_short(iso: str, year: int) -> PeriodValue | None:
    """Length 6: `yyyyWn`, `yyyyMM`, `yyyyQn`, `yyyySn`."""
    marker = iso[4]
    if marker == "W":
        return _weekly(iso, year, _WEEKLY_VARIANTS[0], _digits(iso, 5, 1))
    if marker.isdigit():
        return _monthly(iso, year, _digits(iso, 4, 2))
    if marker == "Q":
        return _quarterly(iso, year, _digits(iso, 5, 1))
    if marker == "S":
        return _six_monthly(iso, year, _digits(iso, 5, 1))
    return None


def _parse_medium(iso: str, year: int) -> PeriodValue | None:
    """Length 7: the three-letter financial years, `yyyyMMB`, `yyyyWnn`, and `yyyy-MM`."""
    for variant in _FINANCIAL_VARIANTS:
        if len(variant.suffix) == 3 and iso.endswith(variant.suffix):
            return _financial(iso, year, variant)
    if iso.endswith("B"):
        return _bi_monthly(iso, year, _digits(iso, 4, 2))
    marker = iso[4]
    if marker == "W":
        return _weekly(iso, year, _WEEKLY_VARIANTS[0], _digits(iso, 5, 2))
    if marker == "-":
        return _monthly(iso, year, _digits(iso, 5, 2))
    return None


def _parse_long(iso: str, year: int) -> PeriodValue | None:
    """Length 8: `yyyyJuly`, `yyyyBiWn`, and otherwise `yyyyMMdd`."""
    if iso.endswith("July"):
        return _financial(iso, year, _financial_variant("FinancialJuly"))
    if iso[4:7] == "BiW":
        return _bi_weekly(iso, year, _digits(iso, 7, 1))
    return _daily(iso, year, _digits(iso, 4, 2), _digits(iso, 6, 2))


def _parse_longer(iso: str, year: int) -> PeriodValue | None:
    """Length 9: `yyyyApril`, `yyyyNovQn`, `yyyyBiWnn`, the named weeks, and `yyyyNovSn`."""
    if iso.endswith("April"):
        return _financial(iso, year, _financial_variant("FinancialApril"))
    if iso[4:8] == "NovQ":
        return _quarterly_november(iso, year, _digits(iso, 8, 1))
    if iso[4:7] == "BiW":
        return _bi_weekly(iso, year, _digits(iso, 7, 2))
    if iso[4:8] == "NovS":
        return _six_monthly_november(iso, year, _digits(iso, 8, 1))
    for variant in _NAMED_WEEKLY_VARIANTS:
        if iso[4:8] == variant.infix:
            return _weekly(iso, year, variant, _digits(iso, 8, 1))
    return None


def _parse_longest(iso: str, year: int) -> PeriodValue | None:
    """Length 10: `yyyy-MM-dd` and the two-digit named weeks."""
    if iso[4] == "-":
        if iso[7] != "-":
            return None
        return _daily(iso, year, _digits(iso, 5, 2), _digits(iso, 8, 2))
    for variant in _NAMED_WEEKLY_VARIANTS:
        if iso[4:8] == variant.infix:
            return _weekly(iso, year, variant, _digits(iso, 8, 2))
    return None


def _daily(iso: str, year: int, month: int, day: int) -> PeriodValue | None:
    """Daily: the given calendar day, start and end alike."""
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    day_date = datetime.date(year, month, day)
    return PeriodValue(iso=iso, period_type="Daily", start_date=day_date, end_date=day_date)


def _weekly(iso: str, year: int, variant: _WeeklyVariant, week: int) -> PeriodValue | None:
    """Weekly family: week `n` of the week-based year, seven days from that type's start weekday."""
    if week < 1:
        return None
    start = _first_week_start(year, variant.first_weekday) + datetime.timedelta(weeks=week - 1)
    if start >= _first_week_start(year + 1, variant.first_weekday):
        return None
    return PeriodValue(
        iso=iso,
        period_type=variant.period_type,
        start_date=start,
        end_date=start + datetime.timedelta(days=_DAYS_PER_WEEK - 1),
    )


def _bi_weekly(iso: str, year: int, bi_week: int) -> PeriodValue | None:
    """BiWeekly: bi-week `n` is the fortnight opening at Monday-aligned ISO week `2n - 1`."""
    week = bi_week * 2 - 1
    if week < 1 or week > _weeks_in_year(year):
        return None
    start = _first_week_start(year, 0) + datetime.timedelta(weeks=week - 1)
    return PeriodValue(
        iso=iso,
        period_type="BiWeekly",
        start_date=start,
        end_date=start + datetime.timedelta(days=2 * _DAYS_PER_WEEK - 1),
    )


def _monthly(iso: str, year: int, month: int) -> PeriodValue | None:
    """Monthly: the whole calendar month."""
    if not 1 <= month <= 12:
        return None
    start = datetime.date(year, month, 1)
    return PeriodValue(iso=iso, period_type="Monthly", start_date=start, end_date=_month_end(start))


def _bi_monthly(iso: str, year: int, bi_month: int) -> PeriodValue | None:
    """BiMonthly: `MM` is the bi-month ordinal 1..6, so the first calendar month is `2 * MM - 1`."""
    if not 1 <= bi_month <= 6:
        return None
    start = datetime.date(year, bi_month * 2 - 1, 1)
    return PeriodValue(iso=iso, period_type="BiMonthly", start_date=start, end_date=_span_end(start, months=2))


def _quarterly(iso: str, year: int, quarter: int) -> PeriodValue | None:
    """Quarterly: three months opening in January, April, July, or October."""
    if not 1 <= quarter <= 4:
        return None
    start = datetime.date(year, (quarter - 1) * 3 + 1, 1)
    return PeriodValue(iso=iso, period_type="Quarterly", start_date=start, end_date=_span_end(start, months=3))


def _quarterly_november(iso: str, year: int, quarter: int) -> PeriodValue | None:
    """QuarterlyNov: quarters of the November financial year, so Q1 opens in November of `yyyy - 1`."""
    if not 1 <= quarter <= 4:
        return None
    month = (quarter - 1) * 3 + 1 - 2
    start_year = year
    if month < 0:
        month += 12
        start_year -= 1
    start = datetime.date(start_year, month, 1)
    return PeriodValue(iso=iso, period_type="QuarterlyNov", start_date=start, end_date=_span_end(start, months=3))


def _six_monthly(iso: str, year: int, semester: int) -> PeriodValue | None:
    """SixMonthly: semesters opening in January and July."""
    if not 1 <= semester <= 2:
        return None
    start = datetime.date(year, 1 if semester == 1 else 7, 1)
    return PeriodValue(iso=iso, period_type="SixMonthly", start_date=start, end_date=_span_end(start, months=6))


def _six_monthly_april(iso: str, year: int) -> PeriodValue | None:
    """SixMonthlyApril: semesters opening in April and October of `yyyy`, so S2 runs into `yyyy + 1`."""
    semester = _digits(iso, 10, 1)
    if not 1 <= semester <= 2:
        return None
    start = datetime.date(year, 4 if semester == 1 else 10, 1)
    return PeriodValue(iso=iso, period_type="SixMonthlyApril", start_date=start, end_date=_span_end(start, months=6))


def _six_monthly_november(iso: str, year: int, semester: int) -> PeriodValue | None:
    """SixMonthlyNov: S1 opens in November of `yyyy - 1`, S2 in May of `yyyy`."""
    if not 1 <= semester <= 2:
        return None
    start = datetime.date(year - 1, 11, 1) if semester == 1 else datetime.date(year, 5, 1)
    return PeriodValue(iso=iso, period_type="SixMonthlyNov", start_date=start, end_date=_span_end(start, months=6))


def _yearly(iso: str, year: int) -> PeriodValue:
    """Yearly: the whole calendar year."""
    return PeriodValue(
        iso=iso,
        period_type="Yearly",
        start_date=datetime.date(year, 1, 1),
        end_date=datetime.date(year, 12, 31),
    )


def _financial(iso: str, year: int, variant: _FinancialVariant) -> PeriodValue:
    """Financial year: twelve months from the variant's start month, shifted back a year for November."""
    start = datetime.date(year + variant.year_offset, variant.start_month, 1)
    return PeriodValue(
        iso=iso,
        period_type=variant.period_type,
        start_date=start,
        end_date=_span_end(start, months=12),
    )


def _financial_variant(period_type: str) -> _FinancialVariant:
    """Look one financial variant up by its period-type name."""
    return next(variant for variant in _FINANCIAL_VARIANTS if variant.period_type == period_type)


def _digits(text: str, start: int, count: int) -> int:
    """Read `count` digits at `start`, rejecting anything else (DHIS2's `digitsN` helpers)."""
    fragment = text[start : start + count]
    if len(fragment) != count or not fragment.isdigit() or not fragment.isascii():
        raise ValueError(f"not a DHIS2 ISO period: {text!r} (expected {count} digit(s) at position {start})")
    return int(fragment)


def _first_week_start(year: int, first_weekday: int) -> datetime.date:
    """Start of week 1 of `year`: the earliest aligned week holding at least four days of the year."""
    january_first = datetime.date(year, 1, 1)
    offset = (january_first.weekday() - first_weekday) % _DAYS_PER_WEEK
    start = january_first - datetime.timedelta(days=offset)
    if _DAYS_PER_WEEK - offset < _MINIMAL_DAYS_IN_FIRST_WEEK:
        start += datetime.timedelta(days=_DAYS_PER_WEEK)
    return start


def _weeks_in_year(year: int) -> int:
    """Number of Monday-aligned ISO weeks in `year` (52 or 53)."""
    span = _first_week_start(year + 1, 0) - _first_week_start(year, 0)
    return span.days // _DAYS_PER_WEEK


def _month_end(start: datetime.date) -> datetime.date:
    """Last day of the month `start` falls in."""
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def _span_end(start: datetime.date, *, months: int) -> datetime.date:
    """Last day of a span of `months` whole months opening at `start`."""
    return _add_months(start, months) - datetime.timedelta(days=1)


def _add_months(start: datetime.date, months: int) -> datetime.date:
    """Advance a first-of-month date by whole months."""
    total = start.month - 1 + months
    return datetime.date(start.year + total // 12, total % 12 + 1, start.day)
