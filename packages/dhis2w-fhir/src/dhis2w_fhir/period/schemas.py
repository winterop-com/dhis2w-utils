"""Period schemas: the parsed period value plus the catalogue of DHIS2 period types."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class PeriodValue(BaseModel):
    """One DHIS2 reporting period: its ISO identifier, its period type, and the dates it covers."""

    model_config = ConfigDict(frozen=True)

    iso: str
    period_type: str
    start_date: datetime.date
    end_date: datetime.date


class PeriodTypeDefinition(BaseModel):
    """One DHIS2 period type as terminology: its name, its ISO format, and a display phrase."""

    model_config = ConfigDict(frozen=True)

    name: str
    iso_format: str
    display: str


def _definition(name: str, iso_format: str) -> PeriodTypeDefinition:
    """Build a period-type definition whose display is the name followed by its ISO format."""
    return PeriodTypeDefinition(name=name, iso_format=iso_format, display=f"{name} ({iso_format})")


#: Every period type DHIS2 registers in `PeriodType.PERIOD_TYPES`, in that order. The names are the
#: exact `getName()` strings, which abbreviate the month for several types (`QuarterlyNov`, not
#: `QuarterlyNovember`). `TwoYearly` and `FinancialYearly` are deliberately absent: they exist as
#: enum constants but are neither registered nor reachable from an ISO string.
PERIOD_TYPE_DEFINITIONS: tuple[PeriodTypeDefinition, ...] = (
    _definition("Daily", "yyyyMMdd"),
    _definition("Weekly", "yyyyWn"),
    _definition("WeeklyWednesday", "yyyyWedWn"),
    _definition("WeeklyThursday", "yyyyThuWn"),
    _definition("WeeklyFriday", "yyyyFriWn"),
    _definition("WeeklySaturday", "yyyySatWn"),
    _definition("WeeklySunday", "yyyySunWn"),
    _definition("BiWeekly", "yyyyBiWn"),
    _definition("Monthly", "yyyyMM"),
    _definition("BiMonthly", "yyyyMMB"),
    _definition("Quarterly", "yyyyQn"),
    _definition("QuarterlyNov", "yyyyNovQn"),
    _definition("SixMonthly", "yyyySn"),
    _definition("SixMonthlyApril", "yyyyAprilSn"),
    _definition("SixMonthlyNov", "yyyyNovSn"),
    _definition("Yearly", "yyyy"),
    _definition("FinancialFeb", "yyyyFeb"),
    _definition("FinancialApril", "yyyyApril"),
    _definition("FinancialJuly", "yyyyJuly"),
    _definition("FinancialAug", "yyyyAug"),
    _definition("FinancialSep", "yyyySep"),
    _definition("FinancialOct", "yyyyOct"),
    _definition("FinancialNov", "yyyyNov"),
)

#: The period-type names, in registration order.
PERIOD_TYPE_NAMES: tuple[str, ...] = tuple(definition.name for definition in PERIOD_TYPE_DEFINITIONS)
