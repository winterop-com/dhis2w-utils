"""Unit tests for the DHIS2 ISO period grammar: every registered period type, both ends of its range.

Expected dates are derived from the dhis2-core rules transcribed in `dhis2w_fhir.period.parser`
(`Period.Input.of` for tokenizing, `DateUnitPeriodTypeParser` for the intervals).
"""

from __future__ import annotations

import datetime

import pytest
from dhis2w_fhir.period import PERIOD_TYPE_DEFINITIONS, PERIOD_TYPE_NAMES, parse_period, recent_periods

#: (iso, period type, start, end) for every registered type, at least two cases each.
_CASES = [
    # Daily - both accepted spellings, and a leap day.
    ("20240229", "Daily", "2024-02-29", "2024-02-29"),
    ("2024-02-29", "Daily", "2024-02-29", "2024-02-29"),
    ("20251231", "Daily", "2025-12-31", "2025-12-31"),
    # Weekly - Monday start, week 1 holds at least four days of the year.
    ("2024W1", "Weekly", "2024-01-01", "2024-01-07"),
    ("2024W01", "Weekly", "2024-01-01", "2024-01-07"),
    ("2011W1", "Weekly", "2011-01-03", "2011-01-09"),
    ("2026W1", "Weekly", "2025-12-29", "2026-01-04"),
    ("2025W30", "Weekly", "2025-07-21", "2025-07-27"),
    ("2020W53", "Weekly", "2020-12-28", "2021-01-03"),
    # The named weekday variants shift the alignment day, not the four-day rule.
    ("2024WedW1", "WeeklyWednesday", "2024-01-03", "2024-01-09"),
    ("2026WedW1", "WeeklyWednesday", "2025-12-31", "2026-01-06"),
    ("2024ThuW1", "WeeklyThursday", "2024-01-04", "2024-01-10"),
    ("2026ThuW1", "WeeklyThursday", "2026-01-01", "2026-01-07"),
    ("2024FriW1", "WeeklyFriday", "2023-12-29", "2024-01-04"),
    ("2026FriW1", "WeeklyFriday", "2026-01-02", "2026-01-08"),
    ("2024SatW1", "WeeklySaturday", "2023-12-30", "2024-01-05"),
    ("2026SatW1", "WeeklySaturday", "2026-01-03", "2026-01-09"),
    ("2024SunW1", "WeeklySunday", "2023-12-31", "2024-01-06"),
    ("2026SunW1", "WeeklySunday", "2026-01-04", "2026-01-10"),
    ("2024WedW52", "WeeklyWednesday", "2024-12-25", "2024-12-31"),
    # BiWeekly - bi-week n opens at ISO week 2n-1, always Monday aligned.
    ("2024BiW1", "BiWeekly", "2024-01-01", "2024-01-14"),
    ("2024BiW2", "BiWeekly", "2024-01-15", "2024-01-28"),
    ("2026BiW1", "BiWeekly", "2025-12-29", "2026-01-11"),
    ("2025BiW26", "BiWeekly", "2025-12-15", "2025-12-28"),
    # Monthly - both accepted spellings, leap February.
    ("202402", "Monthly", "2024-02-01", "2024-02-29"),
    ("2024-02", "Monthly", "2024-02-01", "2024-02-29"),
    ("202511", "Monthly", "2025-11-01", "2025-11-30"),
    # BiMonthly - MM is the bi-month ordinal 1..6, so the first month is 2*MM-1.
    ("202401B", "BiMonthly", "2024-01-01", "2024-02-29"),
    ("202403B", "BiMonthly", "2024-05-01", "2024-06-30"),
    ("202506B", "BiMonthly", "2025-11-01", "2025-12-31"),
    # Quarterly.
    ("2024Q1", "Quarterly", "2024-01-01", "2024-03-31"),
    ("2024Q4", "Quarterly", "2024-10-01", "2024-12-31"),
    ("2025Q2", "Quarterly", "2025-04-01", "2025-06-30"),
    # QuarterlyNov - yyyy names the ending financial year, so Q1 sits in the previous year.
    ("2024NovQ1", "QuarterlyNov", "2023-11-01", "2024-01-31"),
    ("2024NovQ2", "QuarterlyNov", "2024-02-01", "2024-04-30"),
    ("2024NovQ4", "QuarterlyNov", "2024-08-01", "2024-10-31"),
    # SixMonthly and its offset variants.
    ("2024S1", "SixMonthly", "2024-01-01", "2024-06-30"),
    ("2024S2", "SixMonthly", "2024-07-01", "2024-12-31"),
    ("2024AprilS1", "SixMonthlyApril", "2024-04-01", "2024-09-30"),
    ("2024AprilS2", "SixMonthlyApril", "2024-10-01", "2025-03-31"),
    ("2024NovS1", "SixMonthlyNov", "2023-11-01", "2024-04-30"),
    ("2024NovS2", "SixMonthlyNov", "2024-05-01", "2024-10-31"),
    ("2025NovS1", "SixMonthlyNov", "2024-11-01", "2025-04-30"),
    # Yearly.
    ("2024", "Yearly", "2024-01-01", "2024-12-31"),
    ("2025", "Yearly", "2025-01-01", "2025-12-31"),
    # Financial years - all label by the starting year except November.
    ("2024Feb", "FinancialFeb", "2024-02-01", "2025-01-31"),
    ("2025Feb", "FinancialFeb", "2025-02-01", "2026-01-31"),
    ("2024April", "FinancialApril", "2024-04-01", "2025-03-31"),
    ("2025April", "FinancialApril", "2025-04-01", "2026-03-31"),
    ("2024July", "FinancialJuly", "2024-07-01", "2025-06-30"),
    ("2025July", "FinancialJuly", "2025-07-01", "2026-06-30"),
    ("2024Aug", "FinancialAug", "2024-08-01", "2025-07-31"),
    ("2025Aug", "FinancialAug", "2025-08-01", "2026-07-31"),
    ("2024Sep", "FinancialSep", "2024-09-01", "2025-08-31"),
    ("2025Sep", "FinancialSep", "2025-09-01", "2026-08-31"),
    ("2024Oct", "FinancialOct", "2024-10-01", "2025-09-30"),
    ("2025Oct", "FinancialOct", "2025-10-01", "2026-09-30"),
    ("2024Nov", "FinancialNov", "2023-11-01", "2024-10-31"),
    ("2025Nov", "FinancialNov", "2024-11-01", "2025-10-31"),
]


@pytest.mark.parametrize(("iso", "period_type", "start", "end"), _CASES)
def test_parse_period(iso: str, period_type: str, start: str, end: str) -> None:
    """Each ISO period resolves to its DHIS2 period type and the dates DHIS2 assigns it."""
    parsed = parse_period(iso)
    assert parsed.iso == iso
    assert parsed.period_type == period_type
    assert parsed.start_date == datetime.date.fromisoformat(start)
    assert parsed.end_date == datetime.date.fromisoformat(end)


def test_every_registered_type_is_covered() -> None:
    """The case table exercises every period type the CodeSystem publishes."""
    assert {case[1] for case in _CASES} == set(PERIOD_TYPE_NAMES)
    assert len(PERIOD_TYPE_DEFINITIONS) == 23


@pytest.mark.parametrize(
    "iso",
    [
        "",
        "20",
        "202",
        "abcd",
        "2024X1",
        "2024Q0",
        "2024Q5",
        "2024Q01",  # quarter ordinals are single-digit: length 7 is not the Quarterly branch
        "2024S3",
        "202400B",
        "202407B",  # bi-month ordinals stop at 6
        "2024W0",
        "2021W53",  # 2021 has 52 ISO weeks, so week 53 overflows into 2022
        "2025BiW27",  # 2025 has 52 ISO weeks, so bi-week 27 needs a week 53
        "2024NovQ5",
        "2024NovS0",
        "2024AprilS3",
        "20241301",
        "20240230",
        "2024-13-01",
        "2024-01x01",
        "2024XyzW1",
        "2024Marc",
        "202401234567",
    ],
)
def test_rejects_unrecognised_input(iso: str) -> None:
    """Malformed or out-of-range period strings raise ValueError naming the input."""
    with pytest.raises(ValueError, match="DHIS2 ISO period"):
        parse_period(iso)


def test_period_value_is_frozen() -> None:
    """The parsed period is an immutable value."""
    parsed = parse_period("202402")
    with pytest.raises(ValueError, match="frozen"):
        parsed.iso = "202403"


def test_definitions_carry_the_iso_format_in_the_display() -> None:
    """Each period-type concept displays its ISO format, the phrase the DHIS2 docs use."""
    by_name = {definition.name: definition for definition in PERIOD_TYPE_DEFINITIONS}
    assert by_name["Monthly"].display == "Monthly (yyyyMM)"
    assert by_name["FinancialApril"].iso_format == "yyyyApril"
    assert by_name["BiMonthly"].display == "BiMonthly (yyyyMMB)"


@pytest.mark.parametrize("period_type", PERIOD_TYPE_NAMES)
def test_recent_periods_round_trips_through_the_parser(period_type: str) -> None:
    """Every ISO the enumerator emits parses back to its own type, ends before today, and is newest-first."""
    today = datetime.date(2026, 8, 2)
    isos = recent_periods(period_type, 3, today)
    assert len(isos) == 3
    parsed = [parse_period(iso) for iso in isos]
    assert [value.period_type for value in parsed] == [period_type] * 3
    assert all(value.end_date < today for value in parsed)
    assert [value.end_date for value in parsed] == sorted((value.end_date for value in parsed), reverse=True)
    assert len(set(isos)) == 3


@pytest.mark.parametrize(
    ("period_type", "today", "expected"),
    [
        ("Monthly", datetime.date(2026, 8, 2), ["202607", "202606", "202605"]),
        ("Monthly", datetime.date(2026, 1, 1), ["202512", "202511", "202510"]),
        ("Quarterly", datetime.date(2026, 8, 2), ["2026Q2", "2026Q1", "2025Q4"]),
        ("Yearly", datetime.date(2026, 8, 2), ["2025", "2024", "2023"]),
        ("Daily", datetime.date(2026, 3, 2), ["20260301", "20260228", "20260227"]),
        ("Weekly", datetime.date(2026, 1, 8), ["2026W1", "2025W52", "2025W51"]),
        ("BiWeekly", datetime.date(2026, 8, 2), ["2026BiW15", "2026BiW14", "2026BiW13"]),
        ("BiMonthly", datetime.date(2026, 8, 2), ["202603B", "202602B", "202601B"]),
        ("SixMonthly", datetime.date(2026, 8, 2), ["2026S1", "2025S2", "2025S1"]),
        ("SixMonthlyApril", datetime.date(2026, 8, 2), ["2025AprilS2", "2025AprilS1", "2024AprilS2"]),
        ("SixMonthlyNov", datetime.date(2026, 8, 2), ["2026NovS1", "2025NovS2", "2025NovS1"]),
        ("QuarterlyNov", datetime.date(2026, 8, 2), ["2026NovQ3", "2026NovQ2", "2026NovQ1"]),
        ("FinancialApril", datetime.date(2026, 8, 2), ["2025April", "2024April", "2023April"]),
        ("FinancialNov", datetime.date(2026, 8, 2), ["2025Nov", "2024Nov", "2023Nov"]),
    ],
)
def test_recent_periods_names_the_newest_completed_periods(
    period_type: str, today: datetime.date, expected: list[str]
) -> None:
    """The enumerator answers the three newest periods whose end date is already past."""
    assert recent_periods(period_type, 3, today) == expected


@pytest.mark.parametrize(("period_type", "count"), [("Monthly", 0), ("Monthly", -1), ("NotAPeriodType", 3), ("", 3)])
def test_recent_periods_answers_nothing_it_cannot_enumerate(period_type: str, count: int) -> None:
    """An unregistered period type or a non-positive count yields nothing rather than raising."""
    assert recent_periods(period_type, count, datetime.date(2026, 8, 2)) == []
