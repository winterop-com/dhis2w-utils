"""CQL Interval Timing Functions.

Implements interval comparison operations for CQL timing relationships:
- before/after
- meets before/after
- overlaps before/after
- starts/ends
- during/included in/includes
"""

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..types import CQLInterval


def get_successor(value: Any) -> Any:
    """Get the successor of a value for interval adjacency checks."""
    if value is None:
        return None
    if isinstance(value, int):
        return value + 1
    if isinstance(value, Decimal):
        return value + Decimal("0.00000001")  # CQL uses 8 decimal places
    if hasattr(value, "day") and hasattr(value, "year"):
        # FHIRDateTime or FHIRDate - add 1 millisecond or 1 day depending on precision
        from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime

        if isinstance(value, FHIRDateTime) and value.hour is not None:
            # Has time component - add 1 millisecond
            ms = (value.millisecond or 0) + 1
            sec = value.second or 0
            minute = value.minute or 0
            hour = value.hour or 0
            day = value.day or 1
            month = value.month or 1
            year = value.year
            if ms >= 1000:
                ms = 0
                sec += 1
            if sec >= 60:
                sec = 0
                minute += 1
            if minute >= 60:
                minute = 0
                hour += 1
            if hour >= 24:
                hour = 0
                day += 1
            return FHIRDateTime(year=year, month=month, day=day, hour=hour, minute=minute, second=sec, millisecond=ms)
        elif isinstance(value, FHIRDate) or (isinstance(value, FHIRDateTime) and value.hour is None):
            # Date precision - add 1 day
            day = (value.day or 1) + 1
            month = value.month or 1
            year = value.year
            if day > 28:  # Simplified - just roll over
                day = 1
                month += 1
            if month > 12:
                month = 1
                year += 1
            return type(value)(year=year, month=month, day=day)
    if hasattr(value, "hour") and hasattr(value, "minute"):
        # FHIRTime - add 1 millisecond
        from dhis2w_fhir_engine.engine.types import FHIRTime

        ms = (value.millisecond or 0) + 1
        sec = value.second or 0
        minute = value.minute or 0
        hour = value.hour or 0
        if ms >= 1000:
            ms = 0
            sec += 1
        if sec >= 60:
            sec = 0
            minute += 1
        if minute >= 60:
            minute = 0
            hour += 1
        if hour >= 24:
            hour = 0  # Wrap around
        return FHIRTime(hour=hour, minute=minute, second=sec, millisecond=ms)
    if hasattr(value, "value") and hasattr(value, "unit"):
        # Quantity - add smallest step
        from ...types import Quantity

        if isinstance(value, Quantity):
            return Quantity(value=value.value + Decimal("0.00000001"), unit=value.unit)
    return value


def interval_timing(left: "CQLInterval[Any]", right: "CQLInterval[Any]", op: str) -> bool | None:
    """Handle interval-to-interval timing comparisons.

    CQL interval timing operators:
    - before/after: intervals don't overlap and one is entirely before/after the other
    - meets before/after: intervals touch at exactly one point
    - overlaps before: left overlaps right AND left starts before right
    - overlaps after: left overlaps right AND left ends after right
    - starts: left and right have same start AND left ends before or at right's end
    - ends: left and right have same end AND left starts at or after right's start
    - during/included in: left is entirely within right
    - includes: right is entirely within left
    """
    # Handle compound 'overlaps before/after' first (before 'before'/'after' checks)
    if "overlaps" in op:
        if "before" in op:
            # overlaps before: left overlaps right AND left starts before right starts
            if left.low is None or right.low is None:
                return None
            return left.overlaps(right) and left.low < right.low
        elif "after" in op:
            # overlaps after: left overlaps right AND left ends after right ends
            if left.high is None or right.high is None:
                return None
            return left.overlaps(right) and left.high > right.high
        else:
            # Simple overlaps
            return left.overlaps(right)

    # Handle compound 'meets before/after'
    # Two intervals meet if the successor of one's end equals the other's start
    if "meets" in op:
        if left.high is None or right.low is None:
            return None
        if "before" in op:
            # left meets before right: successor(left.high) == right.low
            meets_before: bool = get_successor(left.high) == right.low
            return meets_before
        elif "after" in op:
            # left meets after right: left.low == successor(right.high)
            if right.high is None or left.low is None:
                return None
            meets_after: bool = left.low == get_successor(right.high)
            return meets_after
        else:
            # Simple meets: either meets before or meets after
            simple_meets_after: bool = (
                left.low == get_successor(right.high) if right.high is not None and left.low is not None else False
            )
            simple_meets_before: bool = get_successor(left.high) == right.low
            return simple_meets_before or simple_meets_after

    # Handle simple before/after (intervals don't overlap)
    if "before" in op:
        if left.high is None or right.low is None:
            return None
        left_ends_before_right_starts: bool = left.high < right.low
        return left_ends_before_right_starts
    elif "after" in op:
        if left.low is None or right.high is None:
            return None
        left_starts_after_right_ends: bool = left.low > right.high
        return left_starts_after_right_ends

    # Handle 'starts': same start AND left is contained within or equal to right
    elif "starts" in op:
        if left.low is None or right.low is None:
            return None
        if left.low != right.low:
            return False
        # Also check low_closed matches
        if left.low_closed != right.low_closed:
            return False
        # left must end before or at right's end
        if left.high is None and right.high is None:
            return True
        if left.high is None or right.high is None:
            return left.high is None  # left unbounded ends after right
        left_ends_within_right: bool = left.high <= right.high
        return left_ends_within_right

    # Handle 'ends': same end AND left is contained within or equal to right
    elif "ends" in op:
        if left.high is None or right.high is None:
            return None
        if left.high != right.high:
            return False
        # Also check high_closed matches
        if left.high_closed != right.high_closed:
            return False
        # left must start at or after right's start
        if left.low is None and right.low is None:
            return True
        if left.low is None or right.low is None:
            return right.low is None  # right unbounded starts before left
        left_starts_within_right: bool = left.low >= right.low
        return left_starts_within_right

    elif "during" in op or "included in" in op:
        return right.includes(left)
    elif "includes" in op:
        return left.includes(right)
    elif "same" in op:
        return left == right
    return None


def interval_point_timing(interval: "CQLInterval[Any]", point: Any, op: str) -> bool | None:
    """Handle interval-to-point timing comparisons."""
    # Handle "on or before/after" patterns
    if "on" in op or "same" in op:
        if "orbefore" in op or "or before" in op:
            # Interval on or before point: interval.high <= point
            return interval.high is not None and interval.high <= point
        elif "orafter" in op or "or after" in op:
            # Interval on or after point: interval.low >= point
            return interval.low is not None and interval.low >= point

    if "before" in op:
        return interval.high is not None and interval.high < point
    elif "after" in op:
        return interval.low is not None and interval.low > point
    elif "contains" in op or "includes" in op:
        if "properly" in op:
            return interval.properly_contains(point)
        return interval.contains(point)
    return None


def point_interval_timing(point: Any, interval: "CQLInterval[Any]", op: str) -> bool | None:
    """Handle point-to-interval timing comparisons."""
    # Handle "on or before/after" patterns
    # "P on or before I" means P is at or before the START of interval (P <= I.low)
    # "P on or after I" means P is at or after the END of interval (P >= I.high)
    if "on" in op or "same" in op:
        if "orbefore" in op or "or before" in op:
            # Point on or before interval: point <= interval.low
            return interval.low is not None and point <= interval.low
        elif "orafter" in op or "or after" in op:
            # Point on or after interval: point >= interval.high
            return interval.high is not None and point >= interval.high

    if "before" in op:
        return interval.low is not None and point < interval.low
    elif "after" in op:
        return interval.high is not None and point > interval.high
    elif "during" in op or "in" in op or "included in" in op:
        if "properly" in op:
            return interval.properly_contains(point)
        return interval.contains(point)
    return None


def _are_adjacent(high: Any, low: Any) -> bool:
    """Check if two values are adjacent (successor of high equals low).

    For integers: high + 1 == low
    For dates: next day
    For times: next millisecond
    """
    from datetime import date, datetime
    from decimal import Decimal

    from ...types import FHIRDate, FHIRDateTime, FHIRTime

    # Integer adjacency
    if isinstance(high, int) and isinstance(low, int):
        return high + 1 == low

    # Decimal adjacency - for CQL, decimals with step 0.00000001
    if isinstance(high, Decimal) and isinstance(low, Decimal):
        # For decimals, check if difference is minimal (within precision)
        diff = low - high
        # Adjacent if the difference equals the smallest decimal step
        return diff > 0 and diff <= Decimal("0.00000001")

    # Date adjacency - next day
    if isinstance(high, date) and isinstance(low, date):
        return high + timedelta(days=1) == low
    if isinstance(high, FHIRDate) and isinstance(low, FHIRDate):
        if high.day is not None and low.day is not None:
            h_date = high.to_date()
            l_date = low.to_date()
            if h_date and l_date:
                return h_date + timedelta(days=1) == l_date
        return False

    # DateTime adjacency - next day (for day precision) or next ms (for time precision)
    if isinstance(high, FHIRDateTime) and isinstance(low, FHIRDateTime):
        # Check if both have same precision level
        if high.day is not None and low.day is not None:
            if high.hour is None and low.hour is None:
                # Day precision - check if adjacent days
                h_date = high.to_datetime()
                l_date = low.to_datetime()
                if h_date and l_date:
                    return h_date + timedelta(days=1) == l_date
            elif high.millisecond is not None and low.millisecond is not None:
                # Full precision - check millisecond adjacency
                h_dt = high.to_datetime()
                l_dt = low.to_datetime()
                if h_dt and l_dt:
                    return h_dt + timedelta(milliseconds=1) == l_dt
        return False

    # Time adjacency - next millisecond
    if isinstance(high, FHIRTime) and isinstance(low, FHIRTime):
        h_time = high.to_time()
        l_time = low.to_time()
        if h_time and l_time:
            # Convert to datetime for calculation
            h_dt = datetime.combine(date.today(), h_time)
            l_dt = datetime.combine(date.today(), l_time)
            return h_dt + timedelta(milliseconds=1) == l_dt
        return False

    return False


def collapse_intervals(
    intervals: list["CQLInterval[Any]"],
    interval_class: type,
) -> list["CQLInterval[Any]"]:
    """Collapse overlapping/adjacent intervals into merged intervals.

    Args:
        intervals: List of intervals to collapse
        interval_class: The CQLInterval class to use for creating new intervals
    """
    if not intervals:
        return []

    # Sort by low bound - we filter to only intervals with non-None low
    filtered = [i for i in intervals if i.low is not None]
    sorted_intervals = sorted(filtered, key=lambda x: x.low)  # type: ignore[arg-type,return-value]

    if not sorted_intervals:
        return []

    result = [sorted_intervals[0]]
    for current in sorted_intervals[1:]:
        last = result[-1]
        # Check if intervals overlap, touch, or are adjacent
        if last.high is not None and current.low is not None:
            # Overlapping: last.high >= current.low
            # Touching: last.high == current.low and one side is closed
            # Adjacent: successor(last.high) == current.low (for closed intervals)
            should_merge = False
            if (
                last.high >= current.low
                or (last.high == current.low and (last.high_closed or current.low_closed))
                or (last.high_closed and current.low_closed and _are_adjacent(last.high, current.low))
            ):
                should_merge = True

            if should_merge:
                # Merge intervals
                new_high = max(last.high, current.high) if current.high is not None else current.high
                result[-1] = interval_class(
                    low=last.low,
                    high=new_high,
                    low_closed=last.low_closed,
                    high_closed=current.high_closed if new_high == current.high else last.high_closed,
                )
            else:
                result.append(current)
        else:
            result.append(current)

    return result
