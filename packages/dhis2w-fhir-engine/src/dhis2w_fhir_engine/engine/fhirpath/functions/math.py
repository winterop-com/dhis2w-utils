"""Math functions."""

import math
from decimal import Decimal
from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry
from ...types import Quantity


def _unwrap_value(value: Any) -> Any:
    """Unwrap a FHIR primitive carrying extensions so arithmetic reads the number, not the wrapper.

    Navigation hands `Observation.value.value` on as a primitive paired with its `_value` extensions, and
    the wrapper is neither an int nor a Decimal, so every math function takes its input through here before
    testing what kind of number it holds.
    """
    from ..visitor import _underlying_value

    return _underlying_value(value)


@FunctionRegistry.register("abs")
def fn_abs(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the absolute value."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        return [abs(value)]
    if isinstance(value, Quantity):
        return [Quantity(value=abs(value.value), unit=value.unit)]
    return []


@FunctionRegistry.register("ceiling")
def fn_ceiling(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Returns the smallest integer >= value."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        return [math.ceil(value)]
    return []


@FunctionRegistry.register("floor")
def fn_floor(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Returns the largest integer <= value."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        return [math.floor(value)]
    return []


@FunctionRegistry.register("round")
def fn_round(ctx: EvaluationContext, collection: list[Any], precision: int = 0) -> list[Any]:
    """Rounds to the specified precision."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        return [round(float(value), int(precision))]
    return []


@FunctionRegistry.register("truncate")
def fn_truncate(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Truncates to integer by removing decimal portion."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        return [int(value)]
    return []


@FunctionRegistry.register("sqrt")
def fn_sqrt(ctx: EvaluationContext, collection: list[Any]) -> list[float]:
    """Returns the square root."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)) and value >= 0:
        return [math.sqrt(float(value))]
    return []


@FunctionRegistry.register("ln")
def fn_ln(ctx: EvaluationContext, collection: list[Any]) -> list[float]:
    """Returns the natural logarithm."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)) and value > 0:
        return [math.log(float(value))]
    return []


@FunctionRegistry.register("log")
def fn_log(ctx: EvaluationContext, collection: list[Any], base: float) -> list[float]:
    """Returns the logarithm with given base."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)) and value > 0:
        return [math.log(float(value), float(base))]
    return []


@FunctionRegistry.register("power")
def fn_power(ctx: EvaluationContext, collection: list[Any], exponent: float) -> list[float]:
    """Returns value raised to the exponent.

    Per FHIRPath spec: returns empty if the result would be a complex number
    (e.g., square root of a negative number).
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        try:
            result = math.pow(float(value), float(exponent))
            return [result]
        except ValueError:
            # Math domain error (e.g., sqrt of negative number) returns empty
            return []
    return []


@FunctionRegistry.register("exp")
def fn_exp(ctx: EvaluationContext, collection: list[Any]) -> list[float]:
    """Returns e raised to the power of value."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if isinstance(value, (int, float, Decimal)):
        return [math.exp(float(value))]
    return []


def _get_decimal_precision(value: Decimal) -> int:
    """Get the precision (number of significant decimal places) of a Decimal value."""
    exponent = value.as_tuple().exponent
    # Handle special values (NaN, Infinity) which have string exponents
    if not isinstance(exponent, int):
        return 0
    if exponent >= 0:
        return 0
    return -exponent


def _decimal_low_boundary(value: Decimal, input_precision: int, output_precision: int | None = None) -> Decimal | None:
    """Calculate the low boundary for a decimal value."""
    from decimal import ROUND_FLOOR, ROUND_HALF_UP, InvalidOperation

    # Default output precision is 8 per FHIRPath spec
    if output_precision is None:
        output_precision = 8
    elif output_precision < 0:
        return None  # Negative precision returns empty

    # If precision is too high for the system, return None (empty)
    # Python's Decimal has default precision of 28 digits
    if output_precision > 28:
        return None

    try:
        # The uncertainty is half the smallest increment at the input precision
        increment = Decimal(10) ** (-input_precision)
        half_increment = increment / 2

        # Low boundary is value minus half increment
        low = value - half_increment

        # Format to output precision
        quantizer = Decimal(10) ** (-output_precision)
        prec_diff = input_precision - output_precision

        # Use ROUND_HALF_UP when value is small (near zero) AND precision difference is large.
        # This avoids artificially large jumps for values close to zero.
        # Otherwise use ROUND_FLOOR (towards -infinity) for true low boundary.
        if abs(value) < 1 and prec_diff > 2:
            return low.quantize(quantizer, rounding=ROUND_HALF_UP)
        else:
            return low.quantize(quantizer, rounding=ROUND_FLOOR)
    except InvalidOperation:
        # Precision overflow - return empty
        return None


def _decimal_high_boundary(value: Decimal, input_precision: int, output_precision: int | None = None) -> Decimal | None:
    """Calculate the high boundary for a decimal value."""
    from decimal import ROUND_CEILING, ROUND_HALF_UP, InvalidOperation

    # Default output precision is 8 per FHIRPath spec
    if output_precision is None:
        output_precision = 8
    elif output_precision < 0:
        return None  # Negative precision returns empty

    # If precision is too high for the system, return None (empty)
    if output_precision > 28:
        return None

    try:
        # The uncertainty is half the smallest increment at the input precision
        increment = Decimal(10) ** (-input_precision)
        half_increment = increment / 2

        # High boundary is value plus half increment
        high = value + half_increment

        # Format to output precision
        quantizer = Decimal(10) ** (-output_precision)
        prec_diff = input_precision - output_precision

        # Use ROUND_HALF_UP when value is small (near zero) AND precision difference is large.
        # This avoids artificially large jumps for values close to zero.
        # Otherwise use ROUND_CEILING (towards +infinity) for true high boundary.
        if abs(value) < 1 and prec_diff > 2:
            return high.quantize(quantizer, rounding=ROUND_HALF_UP)
        else:
            return high.quantize(quantizer, rounding=ROUND_CEILING)
    except InvalidOperation:
        # Precision overflow - return empty
        return None


@FunctionRegistry.register("lowBoundary")
def fn_low_boundary(ctx: EvaluationContext, collection: list[Any], precision: int | None = None) -> list[Decimal | Any]:
    """Returns the lowest possible value for the input to the specified precision.

    For decimals: calculates the low boundary based on the implicit precision
    of the input value. The precision parameter specifies the number of decimal
    places in the output (default is 8).
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])

    from ...types import FHIRDate, FHIRDateTime, FHIRTime

    # Parse date/datetime strings into their date/time types
    if isinstance(value, str):
        # Try parsing as datetime first (contains 'T')
        if "T" in value:
            parsed_dt = FHIRDateTime.parse(value)
            if parsed_dt:
                value = parsed_dt
        else:
            # Try as date
            parsed_date = FHIRDate.parse(value)
            if parsed_date:
                value = parsed_date

    if isinstance(value, (int, float, Decimal)):
        decimal_value = Decimal(str(value))
        input_precision = _get_decimal_precision(decimal_value)
        # Pass precision as-is; _decimal_low_boundary handles the default
        result = _decimal_low_boundary(decimal_value, input_precision, precision)
        return [result] if result is not None else []

    if isinstance(value, Quantity):
        decimal_value = value.value
        input_precision = _get_decimal_precision(decimal_value)
        new_value = _decimal_low_boundary(decimal_value, input_precision, precision)
        if new_value is None:
            return []
        return [Quantity(value=new_value, unit=value.unit)]

    # Handle date/time types
    from ...types import FHIRDate, FHIRDateTime

    if isinstance(value, FHIRDate):
        # For lowBoundary, fill in minimum values for unspecified components
        # Per FHIRPath spec, when no precision is specified, return DateTime with full precision
        # This enables proper comparison between Date and DateTime values
        # Precision: 4=YYYY, 6=YYYY-MM, 8=YYYY-MM-DD, 10+=DateTime
        if precision is None:
            precision = 17  # Default to full DateTime precision for comparison
        year = value.year
        month = value.month if value.month is not None else 1
        day = value.day if value.day is not None else 1
        if precision <= 4:
            return [FHIRDate(year=year, month=None, day=None)]
        elif precision <= 6:
            return [FHIRDate(year=year, month=month, day=None)]
        elif precision <= 8:
            return [FHIRDate(year=year, month=month, day=day)]
        else:
            # Return DateTime for time-level precision
            # For lowBoundary: use +14:00 for earliest UTC
            return [
                FHIRDateTime(
                    year=year,
                    month=month,
                    day=day,
                    hour=0,
                    minute=0,
                    second=0,
                    millisecond=0,
                    tz_offset="+14:00",
                )
            ]

    if isinstance(value, FHIRDateTime):
        # For lowBoundary datetime, fill in minimum values for unspecified components
        # Keep existing timezone if present, else use +14:00 for earliest UTC at precision 17+
        # Precision: 4=YYYY, 6=YYYY-MM, 8=YYYY-MM-DD, 10=Thh, 12=Thh:mm, 14=Thh:mm:ss, 17=Thh:mm:ss.fff
        if precision is None:
            precision = 17
        year = value.year
        month = value.month if value.month is not None else 1
        day = value.day if value.day is not None else 1
        hour = value.hour if value.hour is not None else 0
        minute = value.minute if value.minute is not None else 0
        second = value.second if value.second is not None else 0
        millisecond = value.millisecond if value.millisecond is not None else 0
        # For lowBoundary: use existing tz or +14:00 for earliest UTC
        tz = value.tz_offset if value.tz_offset is not None else "+14:00"

        if precision <= 4:
            return [FHIRDate(year=year, month=None, day=None)]
        elif precision <= 6:
            return [FHIRDate(year=year, month=month, day=None)]
        elif precision <= 8:
            return [FHIRDate(year=year, month=month, day=day)]
        elif precision <= 10:
            return [FHIRDateTime(year=year, month=month, day=day, hour=hour)]
        elif precision <= 12:
            return [FHIRDateTime(year=year, month=month, day=day, hour=hour, minute=minute)]
        elif precision <= 14:
            return [FHIRDateTime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)]
        else:
            return [
                FHIRDateTime(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    second=second,
                    millisecond=millisecond,
                    tz_offset=tz,
                )
            ]

    if isinstance(value, FHIRTime):
        # For lowBoundary time, fill in minimum values for unspecified components
        if precision is None:
            precision = 9
        hour = value.hour
        minute = value.minute if value.minute is not None else 0
        second = value.second if value.second is not None else 0
        millisecond = value.millisecond if value.millisecond is not None else 0

        if precision <= 2:
            return [FHIRTime(hour=hour)]
        elif precision <= 4:
            return [FHIRTime(hour=hour, minute=minute)]
        elif precision <= 6:
            return [FHIRTime(hour=hour, minute=minute, second=second)]
        else:
            return [FHIRTime(hour=hour, minute=minute, second=second, millisecond=millisecond)]

    return []


@FunctionRegistry.register("highBoundary")
def fn_high_boundary(
    ctx: EvaluationContext, collection: list[Any], precision: int | None = None
) -> list[Decimal | Any]:
    """Returns the highest possible value for the input to the specified precision.

    For decimals: calculates the high boundary based on the implicit precision
    of the input value. The precision parameter specifies the number of decimal
    places in the output (default is 8).
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])

    from ...types import FHIRDate, FHIRDateTime, FHIRTime

    # Parse date/datetime strings into their date/time types
    if isinstance(value, str):
        # Try parsing as datetime first (contains 'T')
        if "T" in value:
            parsed_dt = FHIRDateTime.parse(value)
            if parsed_dt:
                value = parsed_dt
        else:
            # Try as date
            parsed_date = FHIRDate.parse(value)
            if parsed_date:
                value = parsed_date

    if isinstance(value, (int, float, Decimal)):
        decimal_value = Decimal(str(value))
        input_precision = _get_decimal_precision(decimal_value)
        # Pass precision as-is; _decimal_high_boundary handles the default
        result = _decimal_high_boundary(decimal_value, input_precision, precision)
        return [result] if result is not None else []

    if isinstance(value, Quantity):
        decimal_value = value.value
        input_precision = _get_decimal_precision(decimal_value)
        new_value = _decimal_high_boundary(decimal_value, input_precision, precision)
        if new_value is None:
            return []
        return [Quantity(value=new_value, unit=value.unit)]

    # Handle date/time types
    from ...types import FHIRDate, FHIRDateTime

    if isinstance(value, FHIRDate):
        import calendar

        # For highBoundary, fill in maximum values for unspecified components
        # Per FHIRPath spec, when no precision is specified, return DateTime with full precision
        # This enables proper comparison between Date and DateTime values
        if precision is None:
            precision = 17  # Default to full DateTime precision for comparison
        year = value.year
        month = value.month if value.month is not None else 12
        day = value.day if value.day is not None else calendar.monthrange(year, month)[1]
        if precision <= 4:
            return [FHIRDate(year=year, month=None, day=None)]
        elif precision <= 6:
            return [FHIRDate(year=year, month=month, day=None)]
        elif precision <= 8:
            return [FHIRDate(year=year, month=month, day=day)]
        else:
            # Return DateTime for time-level precision
            # For highBoundary: use -12:00 for latest UTC
            return [
                FHIRDateTime(
                    year=year,
                    month=month,
                    day=day,
                    hour=23,
                    minute=59,
                    second=59,
                    millisecond=999,
                    tz_offset="-12:00",
                )
            ]

    if isinstance(value, FHIRDateTime):
        import calendar

        # For highBoundary datetime, fill in maximum values for unspecified components
        # Keep existing timezone if present, else use -12:00 for latest UTC at precision 17+
        if precision is None:
            precision = 17
        year = value.year
        month = value.month if value.month is not None else 12
        day = value.day if value.day is not None else calendar.monthrange(year, month)[1]
        hour = value.hour if value.hour is not None else 23
        # If hour is specified but minute is not, FHIR rules say minute is implicitly 0 (T08 = T08:00)
        # If neither hour nor minute is specified, use 59 for highBoundary
        minute = value.minute if value.minute is not None else (0 if value.hour is not None else 59)
        second = value.second if value.second is not None else 59
        millisecond = value.millisecond if value.millisecond is not None else 999
        # For highBoundary: use existing tz or -12:00 for latest UTC
        tz = value.tz_offset if value.tz_offset is not None else "-12:00"

        if precision <= 4:
            return [FHIRDate(year=year, month=None, day=None)]
        elif precision <= 6:
            return [FHIRDate(year=year, month=month, day=None)]
        elif precision <= 8:
            return [FHIRDate(year=year, month=month, day=day)]
        elif precision <= 10:
            return [FHIRDateTime(year=year, month=month, day=day, hour=hour)]
        elif precision <= 12:
            return [FHIRDateTime(year=year, month=month, day=day, hour=hour, minute=minute)]
        elif precision <= 14:
            return [FHIRDateTime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)]
        else:
            return [
                FHIRDateTime(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    second=second,
                    millisecond=millisecond,
                    tz_offset=tz,
                )
            ]

    if isinstance(value, FHIRTime):
        # For highBoundary time, fill in maximum values for unspecified components
        if precision is None:
            precision = 9
        hour = value.hour
        minute = value.minute if value.minute is not None else 59
        second = value.second if value.second is not None else 59
        millisecond = value.millisecond if value.millisecond is not None else 999

        if precision <= 2:
            return [FHIRTime(hour=hour)]
        elif precision <= 4:
            return [FHIRTime(hour=hour, minute=minute)]
        elif precision <= 6:
            return [FHIRTime(hour=hour, minute=minute, second=second)]
        else:
            return [FHIRTime(hour=hour, minute=minute, second=second, millisecond=millisecond)]

    return []


@FunctionRegistry.register("precision")
def fn_precision(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Returns the precision of a decimal, date, dateTime, or time value.

    For decimals: returns the number of decimal places.
    For dates: returns the number of significant date digits (year=4, month=6, day=8).
    For times: returns the number of significant time digits (hour=2, minute=4, second=6, millisecond=9).
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])

    if isinstance(value, (int, float, Decimal)):
        decimal_value = Decimal(str(value))
        return [_get_decimal_precision(decimal_value)]

    # Handle date/time types
    from ...types import FHIRDate, FHIRDateTime, FHIRTime

    if isinstance(value, FHIRDate):
        if value.day is not None:
            return [8]  # YYYY-MM-DD
        if value.month is not None:
            return [6]  # YYYY-MM
        return [4]  # YYYY

    if isinstance(value, FHIRDateTime):
        if value.millisecond is not None:
            return [17]  # YYYY-MM-DDThh:mm:ss.fff
        if value.second is not None:
            return [14]  # YYYY-MM-DDThh:mm:ss
        if value.minute is not None:
            return [12]  # YYYY-MM-DDThh:mm
        if value.hour is not None:
            return [10]  # YYYY-MM-DDThh
        if value.day is not None:
            return [8]
        if value.month is not None:
            return [6]
        return [4]

    if isinstance(value, FHIRTime):
        if value.millisecond is not None:
            return [9]  # hh:mm:ss.fff
        if value.second is not None:
            return [6]  # hh:mm:ss
        if value.minute is not None:
            return [4]  # hh:mm
        return [2]  # hh

    return []
