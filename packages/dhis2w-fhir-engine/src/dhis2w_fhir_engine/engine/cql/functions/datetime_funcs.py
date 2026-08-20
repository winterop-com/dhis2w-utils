"""CQL DateTime Functions.

Implements: Today, Now, TimeOfDay, Date, DateTime, Time, and component extractors
(Year, Month, Day, Hour, Minute, Second, Millisecond, Timezone, TimezoneOffset)
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ...types import FHIRDate, FHIRDateTime, FHIRTime

if TYPE_CHECKING:
    from .registry import FunctionRegistry


def _today(args: list[Any]) -> FHIRDate:
    """Get current date."""
    d = date.today()
    return FHIRDate(year=d.year, month=d.month, day=d.day)


def _now(args: list[Any]) -> FHIRDateTime:
    """Get current datetime."""
    dt = datetime.now(UTC)
    return FHIRDateTime(
        year=dt.year,
        month=dt.month,
        day=dt.day,
        hour=dt.hour,
        minute=dt.minute,
        second=dt.second,
        millisecond=dt.microsecond // 1000,
        tz_offset="Z",
    )


def _time_of_day(args: list[Any]) -> FHIRTime:
    """Get current time of day."""
    t = datetime.now().time()
    return FHIRTime(hour=t.hour, minute=t.minute, second=t.second, millisecond=t.microsecond // 1000)


def _date_constructor(args: list[Any]) -> FHIRDate | None:
    """Construct a Date from components."""
    if not args:
        return None
    year = args[0] if args else None
    month = args[1] if len(args) > 1 else None
    day = args[2] if len(args) > 2 else None
    if year is None:
        return None
    return FHIRDate(year=int(year), month=int(month) if month else None, day=int(day) if day else None)


def _datetime_constructor(args: list[Any]) -> FHIRDateTime | None:
    """Construct a DateTime from components."""
    from ...exceptions import CQLError

    if not args:
        return None
    year = args[0]
    if year is None:
        return None
    year_int = int(year)
    # Validate year range: 1-9999
    if year_int < 1 or year_int > 9999:
        raise CQLError(f"DateTime year {year_int} out of range (1-9999)")
    month = int(args[1]) if len(args) > 1 and args[1] is not None else None
    if month is not None and (month < 1 or month > 12):
        raise CQLError(f"DateTime month {month} out of range (1-12)")
    day = int(args[2]) if len(args) > 2 and args[2] is not None else None
    if day is not None and (day < 1 or day > 31):
        raise CQLError(f"DateTime day {day} out of range (1-31)")
    hour = int(args[3]) if len(args) > 3 and args[3] is not None else None
    if hour is not None and (hour < 0 or hour > 23):
        raise CQLError(f"DateTime hour {hour} out of range (0-23)")
    minute = int(args[4]) if len(args) > 4 and args[4] is not None else None
    if minute is not None and (minute < 0 or minute > 59):
        raise CQLError(f"DateTime minute {minute} out of range (0-59)")
    second = int(args[5]) if len(args) > 5 and args[5] is not None else None
    if second is not None and (second < 0 or second > 59):
        raise CQLError(f"DateTime second {second} out of range (0-59)")
    millisecond = int(args[6]) if len(args) > 6 and args[6] is not None else None
    if millisecond is not None and (millisecond < 0 or millisecond > 999):
        raise CQLError(f"DateTime millisecond {millisecond} out of range (0-999)")
    return FHIRDateTime(
        year=year_int,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        millisecond=millisecond,
        tz_offset=str(args[7]) if len(args) > 7 and args[7] is not None else None,
    )


def _time_constructor(args: list[Any]) -> FHIRTime | None:
    """Construct a Time from components."""
    from ...exceptions import CQLError

    if not args:
        return None
    hour = args[0]
    if hour is None:
        return None
    hour_int = int(hour)
    if hour_int < 0 or hour_int > 23:
        raise CQLError(f"Time hour {hour_int} out of range (0-23)")
    minute = int(args[1]) if len(args) > 1 and args[1] is not None else None
    if minute is not None and (minute < 0 or minute > 59):
        raise CQLError(f"Time minute {minute} out of range (0-59)")
    second = int(args[2]) if len(args) > 2 and args[2] is not None else None
    if second is not None and (second < 0 or second > 59):
        raise CQLError(f"Time second {second} out of range (0-59)")
    millisecond = int(args[3]) if len(args) > 3 and args[3] is not None else None
    if millisecond is not None and (millisecond < 0 or millisecond > 999):
        raise CQLError(f"Time millisecond {millisecond} out of range (0-999)")
    return FHIRTime(
        hour=hour_int,
        minute=minute,
        second=second,
        millisecond=millisecond,
    )


def _year(args: list[Any]) -> int | None:
    """Extract year component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDate, FHIRDateTime)):
            return val.year
        if isinstance(val, (date, datetime)):
            return val.year
    return None


def _month(args: list[Any]) -> int | None:
    """Extract month component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDate, FHIRDateTime)):
            return val.month
        if isinstance(val, (date, datetime)):
            return val.month
    return None


def _day(args: list[Any]) -> int | None:
    """Extract day component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDate, FHIRDateTime)):
            return val.day
        if isinstance(val, (date, datetime)):
            return val.day
    return None


def _hour(args: list[Any]) -> int | None:
    """Extract hour component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDateTime, FHIRTime)):
            return val.hour
        if isinstance(val, (datetime, time)):
            return val.hour
    return None


def _minute(args: list[Any]) -> int | None:
    """Extract minute component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDateTime, FHIRTime)):
            return val.minute
        if isinstance(val, (datetime, time)):
            return val.minute
    return None


def _second(args: list[Any]) -> int | None:
    """Extract second component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDateTime, FHIRTime)):
            return val.second
        if isinstance(val, (datetime, time)):
            return val.second
    return None


def _millisecond(args: list[Any]) -> int | None:
    """Extract millisecond component."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, (FHIRDateTime, FHIRTime)):
            return val.millisecond
        if isinstance(val, (datetime, time)):
            return val.microsecond // 1000
    return None


def _timezone_offset(args: list[Any]) -> Decimal | None:
    """Extract timezone offset in hours."""
    if args and args[0] is not None:
        val = args[0]
        if isinstance(val, FHIRDateTime) and val.tz_offset:
            offset = val.tz_offset
            if offset == "Z":
                return Decimal("0")
            if offset.startswith(("+", "-")):
                sign = 1 if offset[0] == "+" else -1
                hours = int(offset[1:3])
                minutes = int(offset[4:6]) if len(offset) > 4 else 0
                return Decimal(str(sign * (hours + minutes / 60)))
    return None


def _duration_between(args: list[Any]) -> int | None:
    """Calculate duration between two datetime values.

    This is a simplified implementation - the full version should consider precision.
    """
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        low = args[0]
        high = args[1]
        precision = args[2] if len(args) > 2 else "day"

        # Convert to Python datetime for calculation
        if isinstance(low, FHIRDateTime):
            low = low.to_datetime()
        elif isinstance(low, FHIRDate):
            low = low.to_date()

        if isinstance(high, FHIRDateTime):
            high = high.to_datetime()
        elif isinstance(high, FHIRDate):
            high = high.to_date()

        if low is None or high is None:
            return None

        # Convert to datetime for uniform handling
        low_dt: datetime
        high_dt: datetime
        if isinstance(low, datetime):
            low_dt = low
        elif isinstance(low, date):
            low_dt = datetime.combine(low, datetime.min.time())
        else:
            return None

        if isinstance(high, datetime):
            high_dt = high
        elif isinstance(high, date):
            high_dt = datetime.combine(high, datetime.min.time())
        else:
            return None

        delta = high_dt - low_dt
        if precision in ("day", "days"):
            return delta.days
        if precision in ("hour", "hours"):
            return int(delta.total_seconds() // 3600)
        if precision in ("minute", "minutes"):
            return int(delta.total_seconds() // 60)
        if precision in ("second", "seconds"):
            return int(delta.total_seconds())

    return None


def register(registry: "FunctionRegistry") -> None:
    """Register all datetime functions."""
    registry.register("Today", _today, category="datetime", min_args=0, max_args=0)
    registry.register("Now", _now, category="datetime", min_args=0, max_args=0)
    registry.register("TimeOfDay", _time_of_day, category="datetime", min_args=0, max_args=0)
    registry.register("Date", _date_constructor, category="datetime", min_args=1, max_args=3)
    registry.register("DateTime", _datetime_constructor, category="datetime", min_args=1, max_args=8)
    registry.register("Time", _time_constructor, category="datetime", min_args=1, max_args=4)

    # Component extractors
    registry.register("Year", _year, category="datetime", min_args=1, max_args=1)
    registry.register("Month", _month, category="datetime", min_args=1, max_args=1)
    registry.register("Day", _day, category="datetime", min_args=1, max_args=1)
    registry.register("Hour", _hour, category="datetime", min_args=1, max_args=1)
    registry.register("Minute", _minute, category="datetime", min_args=1, max_args=1)
    registry.register("Second", _second, category="datetime", min_args=1, max_args=1)
    registry.register("Millisecond", _millisecond, category="datetime", min_args=1, max_args=1)
    registry.register("TimezoneOffset", _timezone_offset, category="datetime", min_args=1, max_args=1)
    registry.register("DurationBetween", _duration_between, category="datetime", min_args=2, max_args=3)
