"""Comparison functions and operators."""

from decimal import Decimal
from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry
from ...types import FHIRDate, FHIRDateTime, FHIRTime, Quantity


def _normalize_for_comparison(value: Any) -> Any:
    """Normalize a value for comparison.

    Converts date strings to FHIRDate/FHIRDateTime for proper comparison.
    Also unwraps _PrimitiveWithExtension wrappers.
    Converts FHIR Quantity dicts to Quantity objects.
    """
    # Import here to avoid circular imports
    from ..visitor import _PrimitiveWithExtension

    # Unwrap primitive wrappers
    if isinstance(value, _PrimitiveWithExtension):
        value = value.value

    # Convert FHIR Quantity dict to Quantity object
    if isinstance(value, dict) and "value" in value and ("unit" in value or "code" in value):
        qty_value = value.get("value")
        # Prefer 'code' (UCUM code) over 'unit' (human-readable)
        qty_unit = value.get("code") or value.get("unit") or "1"
        if qty_value is not None:
            return Quantity(value=Decimal(str(qty_value)), unit=qty_unit)

    if isinstance(value, str):
        # Try to parse as date or datetime
        if "T" in value or len(value) > 10:
            # Might be a datetime
            try:
                result = FHIRDateTime.parse(value)
                if result is not None:
                    return result
            except (ValueError, AttributeError):
                pass
        # Try as date (only if looks like a date pattern: YYYY or YYYY-MM or YYYY-MM-DD)
        if len(value) >= 4 and value[:4].isdigit():
            try:
                date_result = FHIRDate.parse(value)
                if date_result is not None:
                    return date_result
            except (ValueError, AttributeError):
                pass
    return value


def equals(left: Any, right: Any) -> bool | None:
    """FHIRPath equality comparison.

    Returns None if either operand is empty/null.
    Collections must be singletons for comparison - different sizes = False.
    """
    if left is None or right is None:
        return None

    # Handle lists
    if isinstance(left, list):
        if not left:
            return None
        if len(left) > 1:
            # Multi-element collection on left side
            if isinstance(right, list):
                if not right:
                    return None
                if len(right) != len(left):
                    return False
                # Compare element by element; the length check above guarantees equal lengths
                for l_item, r_item in zip(left, right, strict=True):
                    result = _equals_single(l_item, r_item)
                    if result is None:
                        return None  # Incomparable items
                    if not result:
                        return False
                return True
            return False  # Can't compare multi-element with singleton
        left = left[0]

    if isinstance(right, list):
        if not right:
            return None
        if len(right) > 1:
            return False  # Can't compare singleton with multi-element
        right = right[0]

    return _equals_single(left, right)


def _equals_single(left: Any, right: Any) -> bool | None:
    """Compare two single values for equality.

    Returns:
        True if equal, False if not equal, None if incomparable (different precision).
    """
    # Normalize date strings to FHIRDate/FHIRDateTime
    left = _normalize_for_comparison(left)
    right = _normalize_for_comparison(right)

    # Handle date/datetime cross-comparison with precision check
    if isinstance(left, FHIRDate) and isinstance(right, FHIRDateTime):
        # Date has precision only to day, datetime may have time components
        # If datetime has time components, they have different precision → None
        if right.hour is not None:
            return None  # Incomparable precision
        # Compare date parts only
        return left.year == right.year and left.month == right.month and left.day == right.day

    if isinstance(left, FHIRDateTime) and isinstance(right, FHIRDate):
        # Same as above, reversed
        if left.hour is not None:
            return None  # Incomparable precision
        return left.year == right.year and left.month == right.month and left.day == right.day

    # Type-specific comparison
    if type(left) is not type(right):
        # Different types are not equal (with some exceptions)
        # int, float, and Decimal can be compared
        if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
            return float(left) == float(right)
        return False

    # Special handling for FHIRDateTime precision and timezone
    if isinstance(left, FHIRDateTime) and isinstance(right, FHIRDateTime):
        # Check timezone compatibility - one has tz, other doesn't = incomparable
        left_has_tz = left.tz_offset is not None
        right_has_tz = right.tz_offset is not None
        if left_has_tz != right_has_tz:
            return None  # Incomparable

        # If both have timezones, compare normalized UTC tuples
        if left_has_tz and right_has_tz:
            return left._to_utc_tuple() == right._to_utc_tuple()

        # Check time precision compatibility
        # second=None vs second=explicit is incomparable (different precision)
        # But millisecond=None vs millisecond=0 is comparable (same moment)
        left_has_second = left.second is not None
        right_has_second = right.second is not None
        if left_has_second != right_has_second:
            return None  # Incomparable - different time precision

        # Compare with millisecond normalization (None == 0 for semantic equivalence)
        return (
            left.year == right.year
            and left.month == right.month
            and left.day == right.day
            and left.hour == right.hour
            and left.minute == right.minute
            and left.second == right.second
            and (left.millisecond or 0) == (right.millisecond or 0)
        )

    # Special handling for FHIRTime precision
    if isinstance(left, FHIRTime) and isinstance(right, FHIRTime):
        # Check time precision compatibility
        # second=None vs second=explicit is incomparable
        # But millisecond=None vs millisecond=0 is comparable
        left_has_second = left.second is not None
        right_has_second = right.second is not None
        if left_has_second != right_has_second:
            return None  # Incomparable - different time precision

        # Compare with millisecond normalization (None == 0 for semantic equivalence)
        return (
            left.hour == right.hour
            and (left.minute or 0) == (right.minute or 0)
            and left.second == right.second
            and (left.millisecond or 0) == (right.millisecond or 0)
        )

    # Special handling for FHIRDate precision
    if isinstance(left, FHIRDate) and isinstance(right, FHIRDate):
        # Different precision levels are incomparable
        left_has_month = left.month is not None
        right_has_month = right.month is not None
        left_has_day = left.day is not None
        right_has_day = right.day is not None

        if left_has_month != right_has_month or left_has_day != right_has_day:
            return None  # Incomparable precision

        return left == right

    # Special handling for Quantity - incompatible units return None (incomparable)
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        result = left._convert_for_comparison(right)
        if result is None:
            return None  # Incomparable units
        return result[0] == result[1]

    equal: bool = left == right
    return equal


def equivalent(left: Any, right: Any) -> bool:
    """FHIRPath equivalence comparison (~).

    Empty collections are equivalent to empty collections.
    Comparison is case-insensitive for strings.
    For quantities, uses precision-based comparison after unit conversion.
    For collections, order does not matter (set-based comparison).
    """
    # Handle lists - compare as sets (order doesn't matter)
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False
        if not left and not right:
            return True  # Both empty
        # For each element in left, find a matching element in right
        # This is O(n^2) but collections are typically small
        right_matched = [False] * len(right)
        for l_item in left:
            found = False
            for i, r_item in enumerate(right):
                if not right_matched[i] and equivalent(l_item, r_item):
                    right_matched[i] = True
                    found = True
                    break
            if not found:
                return False
        return True

    # Unwrap single-element lists
    if isinstance(left, list):
        left = left[0] if len(left) == 1 else (left if left else None)
    if isinstance(right, list):
        right = right[0] if len(right) == 1 else (right if right else None)

    # If one is still a list (multi-element) and other is not, they're not equivalent
    if isinstance(left, list) or isinstance(right, list):
        return False

    # Both empty/null are equivalent
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False

    # Normalize values (convert FHIR quantity dicts to Quantity objects)
    left = _normalize_for_comparison(left)
    right = _normalize_for_comparison(right)

    # String comparison is case-insensitive
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower()

    # Decimal equivalence with precision-based comparison
    if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
        return _decimal_equivalent(left, right)

    # Quantity equivalence with precision-based comparison
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return _quantity_equivalent(left, right)

    # DateTime equivalence with timezone and precision handling
    if isinstance(left, FHIRDateTime) and isinstance(right, FHIRDateTime):
        return _datetime_equivalent(left, right)

    # Time equivalence with precision handling
    if isinstance(left, FHIRTime) and isinstance(right, FHIRTime):
        return _time_equivalent(left, right)

    equivalent_values: bool = left == right
    return equivalent_values


def _decimal_equivalent(left: int | float | Decimal, right: int | float | Decimal) -> bool:
    """Check if two decimal values are equivalent using precision-based comparison."""
    left_dec = Decimal(str(left))
    right_dec = Decimal(str(right))

    # Get precision of both values
    left_precision = _get_quantity_precision(left_dec)
    right_precision = _get_quantity_precision(right_dec)

    # Use the minimum precision (least precise value determines tolerance)
    min_precision = min(left_precision, right_precision)

    # Calculate tolerance based on precision
    tolerance = Decimal("0.5") * (Decimal(10) ** (-min_precision))

    return abs(left_dec - right_dec) <= tolerance


def _datetime_equivalent(left: FHIRDateTime, right: FHIRDateTime) -> bool:
    """Check if two FHIRDateTime values are equivalent."""
    left_has_tz = left.tz_offset is not None
    right_has_tz = right.tz_offset is not None

    # Mixed timezone awareness - not equivalent
    if left_has_tz != right_has_tz:
        return False

    # Both have timezones - compare in UTC
    if left_has_tz and right_has_tz:
        return left._to_utc_tuple() == right._to_utc_tuple()

    # Neither has timezone - compare with millisecond normalization
    return (
        left.year == right.year
        and left.month == right.month
        and left.day == right.day
        and left.hour == right.hour
        and left.minute == right.minute
        and left.second == right.second
        and (left.millisecond or 0) == (right.millisecond or 0)
    )


def _time_equivalent(left: FHIRTime, right: FHIRTime) -> bool:
    """Check if two FHIRTime values are equivalent."""
    return (
        left.hour == right.hour
        and (left.minute or 0) == (right.minute or 0)
        and (left.second or 0) == (right.second or 0)
        and (left.millisecond or 0) == (right.millisecond or 0)
    )


def _quantity_equivalent(left: Quantity, right: Quantity) -> bool:
    """Check if two quantities are equivalent using precision-based comparison."""
    from dhis2w_fhir_engine.engine.units import convert_quantity

    # Try to convert right to left's unit
    converted = convert_quantity(right.value, right.unit, left.unit)
    if converted is None:
        # Try the other direction
        converted_left = convert_quantity(left.value, left.unit, right.unit)
        if converted_left is None:
            return False
        # Compare in right's unit
        left_val = Decimal(str(converted_left))
        right_val = right.value
    else:
        # Compare in left's unit
        left_val = left.value
        right_val = Decimal(str(converted))

    # Get precision of both values (number of decimal places)
    left_precision = _get_quantity_precision(left.value)
    right_precision = _get_quantity_precision(right.value)

    # Use the minimum precision (least precise value determines tolerance)
    min_precision = min(left_precision, right_precision)

    # Calculate tolerance based on precision
    # For precision 0 (integer), tolerance is 0.5
    # For precision 1 (1 decimal), tolerance is 0.05
    tolerance = Decimal("0.5") * (Decimal(10) ** (-min_precision))

    return abs(left_val - right_val) <= tolerance


def _get_quantity_precision(value: Decimal) -> int:
    """Get the precision (number of decimal places) of a Decimal value."""
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        return 0  # Handle NaN/Infinity
    if exponent >= 0:
        return 0
    return -exponent


def compare(left: Any, right: Any) -> int | None:
    """Compare two values.

    Returns:
        -1 if left < right
        0 if left == right
        1 if left > right
        None if not comparable
    """
    if left is None or right is None:
        return None

    # Handle lists (should be singletons)
    if isinstance(left, list):
        if not left:
            return None
        left = left[0]
    if isinstance(right, list):
        if not right:
            return None
        right = right[0]

    # Normalize date strings to FHIRDate/FHIRDateTime
    left = _normalize_for_comparison(left)
    right = _normalize_for_comparison(right)

    # Handle date/datetime cross-comparison with precision check
    if isinstance(left, FHIRDate) and isinstance(right, FHIRDateTime):
        # If datetime has time components AND dates are equal, precision matters
        if right.hour is not None:
            # Only return None if date parts are equal (time would determine result)
            if left.year == right.year and left.month == right.month and left.day == right.day:
                return None  # Incomparable precision (same date, different time precision)
            # Otherwise, compare date parts only
            if left.year < right.year:
                return -1
            if left.year > right.year:
                return 1
            if left.month is not None and right.month is not None:
                if left.month < right.month:
                    return -1
                if left.month > right.month:
                    return 1
            if left.day is not None and right.day is not None:
                if left.day < right.day:
                    return -1
                if left.day > right.day:
                    return 1
            return 0
    elif isinstance(left, FHIRDateTime) and isinstance(right, FHIRDate) and left.hour is not None:
        # Only return None if date parts are equal
        if left.year == right.year and left.month == right.month and left.day == right.day:
            return None  # Incomparable precision
        # Otherwise, compare date parts only
        if left.year < right.year:
            return -1
        if left.year > right.year:
            return 1
        if left.month is not None and right.month is not None:
            if left.month < right.month:
                return -1
            if left.month > right.month:
                return 1
        if left.day is not None and right.day is not None:
            if left.day < right.day:
                return -1
            if left.day > right.day:
                return 1
        return 0

    # Handle FHIRDateTime precision differences
    if isinstance(left, FHIRDateTime) and isinstance(right, FHIRDateTime):
        # Check timezone compatibility first
        left_has_tz = left.tz_offset is not None
        right_has_tz = right.tz_offset is not None
        if left_has_tz != right_has_tz:
            return None  # Incomparable - mixed timezone awareness

        left_precision = _get_datetime_precision(left)
        right_precision = _get_datetime_precision(right)

        # If date precision differs (missing month or day), that's incomparable
        left_date_precision = min(left_precision, 3)  # Cap at day level
        right_date_precision = min(right_precision, 3)
        if left_date_precision != right_date_precision:
            # Different date precision - compare what we can
            min_precision = min(left_date_precision, right_date_precision)
            cmp_result = _compare_datetime_to_precision(left, right, min_precision)
            if cmp_result == 0:
                return None  # Equal at common date precision = incomparable
            return cmp_result

        # Check time precision compatibility
        # second=None vs second=explicit is incomparable (different precision)
        # But millisecond=None vs millisecond=0 is comparable (same moment)
        left_has_second = left.second is not None
        right_has_second = right.second is not None
        if left_has_second != right_has_second:
            # Different time precision at second level
            # Compare up to minute level
            cmp_result = _compare_datetime_to_precision(left, right, 5)  # minute level
            if cmp_result == 0:
                return None  # Equal at minute level = incomparable
            return cmp_result

        # Same time precision (both have or both lack seconds)
        # If both have timezones, use FHIRDateTime's built-in comparison which normalizes to UTC
        if left_has_tz and right_has_tz:
            if left < right:
                return -1
            elif left > right:
                return 1
            else:
                return 0

        # No timezones - compare raw values with millisecond normalization (None == 0)
        return _compare_datetime_to_precision(left, right, 7)

    # Handle FHIRTime precision differences
    if isinstance(left, FHIRTime) and isinstance(right, FHIRTime):
        # Check time precision compatibility
        # second=None vs second=explicit is incomparable
        # But millisecond=None vs millisecond=0 is comparable
        left_has_second = left.second is not None
        right_has_second = right.second is not None
        if left_has_second != right_has_second:
            # Different precision at second level
            # Compare up to minute level
            cmp_result = _compare_time_to_precision(left, right, 2)  # minute level
            if cmp_result == 0:
                return None  # Equal at minute level = incomparable
            return cmp_result

        # Same precision - compare with millisecond normalization
        return _compare_time_to_precision(left, right, 4)

    # Handle FHIRDate precision differences
    if isinstance(left, FHIRDate) and isinstance(right, FHIRDate):
        left_has_month = left.month is not None
        right_has_month = right.month is not None
        left_has_day = left.day is not None
        right_has_day = right.day is not None

        # Different precision levels - compare at common precision
        if left_has_month != right_has_month or left_has_day != right_has_day:
            # Compare year first
            if left.year != right.year:
                return -1 if left.year < right.year else 1
            # Compare month if both have it
            if left_has_month and right_has_month:
                left_month = left.month
                right_month = right.month
                if left_month is not None and right_month is not None and left_month != right_month:
                    return -1 if left_month < right_month else 1
            # Equal at common precision = incomparable
            return None

    # After handling cross-type comparisons, remaining comparisons should be same-type
    try:
        if left < right:
            return -1
        elif left > right:
            return 1
        else:
            return 0
    except TypeError:
        return None


def _get_datetime_precision(dt: FHIRDateTime) -> int:
    """Get the precision level of a FHIRDateTime.

    Returns:
        1: year only
        2: year-month
        3: year-month-day
        4: year-month-day hour
        5: year-month-day hour:minute
        6: year-month-day hour:minute:second
        7: year-month-day hour:minute:second.millisecond
    """
    if dt.millisecond is not None:
        return 7
    if dt.second is not None:
        return 6
    if dt.minute is not None:
        return 5
    if dt.hour is not None:
        return 4
    if dt.day is not None:
        return 3
    if dt.month is not None:
        return 2
    return 1


def _compare_datetime_to_precision(left: FHIRDateTime, right: FHIRDateTime, precision: int) -> int:
    """Compare two FHIRDateTimes up to the specified precision level."""
    # Year
    if left.year < right.year:
        return -1
    if left.year > right.year:
        return 1
    if precision == 1:
        return 0

    # Month
    l_month = left.month or 1
    r_month = right.month or 1
    if l_month < r_month:
        return -1
    if l_month > r_month:
        return 1
    if precision == 2:
        return 0

    # Day
    l_day = left.day or 1
    r_day = right.day or 1
    if l_day < r_day:
        return -1
    if l_day > r_day:
        return 1
    if precision == 3:
        return 0

    # Hour
    l_hour = left.hour or 0
    r_hour = right.hour or 0
    if l_hour < r_hour:
        return -1
    if l_hour > r_hour:
        return 1
    if precision == 4:
        return 0

    # Minute
    l_min = left.minute or 0
    r_min = right.minute or 0
    if l_min < r_min:
        return -1
    if l_min > r_min:
        return 1
    if precision == 5:
        return 0

    # Second
    l_sec = left.second or 0
    r_sec = right.second or 0
    if l_sec < r_sec:
        return -1
    if l_sec > r_sec:
        return 1
    if precision == 6:
        return 0

    # Millisecond
    l_ms = left.millisecond or 0
    r_ms = right.millisecond or 0
    if l_ms < r_ms:
        return -1
    if l_ms > r_ms:
        return 1
    return 0


def _get_time_precision(t: FHIRTime) -> int:
    """Get the precision level of a FHIRTime.

    Returns:
        1: hour only
        2: hour:minute
        3: hour:minute:second
        4: hour:minute:second.millisecond
    """
    if t.millisecond is not None:
        return 4
    if t.second is not None:
        return 3
    if t.minute is not None:
        return 2
    return 1


def _compare_time_to_precision(left: FHIRTime, right: FHIRTime, precision: int) -> int:
    """Compare two FHIRTimes up to the specified precision level."""
    # Hour
    if left.hour < right.hour:
        return -1
    if left.hour > right.hour:
        return 1
    if precision == 1:
        return 0

    # Minute
    l_min = left.minute or 0
    r_min = right.minute or 0
    if l_min < r_min:
        return -1
    if l_min > r_min:
        return 1
    if precision == 2:
        return 0

    # Second
    l_sec = left.second or 0
    r_sec = right.second or 0
    if l_sec < r_sec:
        return -1
    if l_sec > r_sec:
        return 1
    if precision == 3:
        return 0

    # Millisecond
    l_ms = left.millisecond or 0
    r_ms = right.millisecond or 0
    if l_ms < r_ms:
        return -1
    if l_ms > r_ms:
        return 1
    return 0


@FunctionRegistry.register("=")
def fn_equals(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Equality operator."""
    result = equals(left, right)
    if result is None:
        return []
    return [result]


@FunctionRegistry.register("!=")
def fn_not_equals(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Inequality operator."""
    result = equals(left, right)
    if result is None:
        return []
    return [not result]


@FunctionRegistry.register("~")
def fn_equivalent(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Equivalence operator."""
    return [equivalent(left, right)]


@FunctionRegistry.register("!~")
def fn_not_equivalent(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Not equivalent operator."""
    return [not equivalent(left, right)]


@FunctionRegistry.register("<")
def fn_less_than(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Less than operator."""
    result = compare(left, right)
    if result is None:
        return []
    return [result < 0]


@FunctionRegistry.register(">")
def fn_greater_than(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Greater than operator."""
    result = compare(left, right)
    if result is None:
        return []
    return [result > 0]


@FunctionRegistry.register("<=")
def fn_less_or_equal(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Less than or equal operator."""
    result = compare(left, right)
    if result is None:
        return []
    return [result <= 0]


@FunctionRegistry.register(">=")
def fn_greater_or_equal(ctx: EvaluationContext, left: list[Any], right: list[Any]) -> list[bool]:
    """Greater than or equal operator."""
    result = compare(left, right)
    if result is None:
        return []
    return [result >= 0]


@FunctionRegistry.register("comparable")
def fn_comparable(ctx: EvaluationContext, collection: list[Any], other: Any) -> list[bool]:
    """Returns true if the quantities are comparable (have compatible units).

    This function checks if two Quantity values can be compared by determining
    if their units can be converted to a common unit.
    """
    if not collection:
        return []

    left = collection[0]
    if not isinstance(left, Quantity):
        return []

    # Handle list argument
    if isinstance(other, list):
        if not other:
            return []
        other = other[0]

    if not isinstance(other, Quantity):
        return []

    # Check if the quantities can be converted for comparison
    result = left._convert_for_comparison(other)
    return [result is not None]
