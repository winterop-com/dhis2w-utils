"""Boolean and logic functions."""

from decimal import Decimal
from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry


def _unwrap_value(value: Any) -> Any:
    """Unwrap a FHIR primitive carrying extensions so a conversion reads the value, not the wrapper.

    Navigation hands `Patient.active` on as a primitive paired with its `_active` extensions, so every
    conversion in this module takes its single input through here before the FHIRPath conversion table
    (FHIRPath 2.0.0 section 5.6) decides what the value converts to.
    """
    from ..visitor import _underlying_value

    return _underlying_value(value)


@FunctionRegistry.register("not")
def fn_not(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns the boolean negation of the input, reading the input under the singleton evaluation rule."""
    from ..visitor import singleton_boolean

    condition = singleton_boolean(collection)
    if condition is None:
        return []
    return [not condition]


@FunctionRegistry.register("iif")
def fn_iif(
    ctx: EvaluationContext,
    collection: list[Any],
    true_result: Any = None,
    otherwise_result: Any = None,
) -> list[Any]:
    """If-then-else function.

    Note: This is handled specially by the visitor because the branches
    should only be evaluated based on the condition.
    """
    # Simple implementation - visitor may override for lazy evaluation
    if not collection:
        if otherwise_result is not None:
            return [otherwise_result] if not isinstance(otherwise_result, list) else otherwise_result
        return []

    condition = collection[0]
    if isinstance(condition, bool) and condition:
        if true_result is not None:
            return [true_result] if not isinstance(true_result, list) else true_result
        return []
    else:
        if otherwise_result is not None:
            return [otherwise_result] if not isinstance(otherwise_result, list) else otherwise_result
        return []


@FunctionRegistry.register("trace")
def fn_trace(ctx: EvaluationContext, collection: list[Any], name: str = "", *args: Any) -> list[Any]:
    """Logs the collection for debugging and returns it unchanged.

    In production, this is typically a no-op.
    """
    # In debug mode, this could log to a handler
    return collection


@FunctionRegistry.register("toBoolean")
def fn_to_boolean(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Converts the input to a boolean."""
    from decimal import Decimal

    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, bool):
        return [value]

    if isinstance(value, str):
        lower = value.lower()
        if lower in ("true", "t", "yes", "y", "1", "1.0"):
            return [True]
        if lower in ("false", "f", "no", "n", "0", "0.0"):
            return [False]
        return []

    if isinstance(value, int):
        if value == 1:
            return [True]
        if value == 0:
            return [False]
        return []

    if isinstance(value, (float, Decimal)):
        if value == 1 or value == Decimal("1") or value == Decimal("1.0"):
            return [True]
        if value == 0 or value == Decimal("0") or value == Decimal("0.0"):
            return [False]
        return []

    return []


@FunctionRegistry.register("convertsToBoolean")
def fn_converts_to_boolean(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to a boolean."""
    result = fn_to_boolean(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toInteger")
def fn_to_integer(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Converts the input to an integer."""
    from decimal import Decimal

    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, bool):
        return [1 if value else 0]

    if isinstance(value, int):
        return [value]

    if isinstance(value, Decimal):
        int_val = int(value)
        if value == Decimal(int_val):
            return [int_val]
        return []

    if isinstance(value, float):
        int_val = int(value)
        if value == float(int_val):
            return [int_val]
        return []

    if isinstance(value, str):
        try:
            # String must NOT contain a decimal point to convert to integer
            # Even '1.0' does not convert to integer per FHIRPath spec
            if "." in value:
                return []
            return [int(value)]
        except ValueError:
            return []

    return []


@FunctionRegistry.register("convertsToInteger")
def fn_converts_to_integer(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to an integer."""
    result = fn_to_integer(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toDecimal")
def fn_to_decimal(ctx: EvaluationContext, collection: list[Any]) -> list[Decimal]:
    """Converts the input to a decimal.

    Returns Decimal to preserve precision for lowBoundary/highBoundary.
    """
    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, bool):
        return [Decimal(1 if value else 0)]

    if isinstance(value, Decimal):
        return [value]

    if isinstance(value, int):
        # Preserve integer precision (no decimal places)
        return [Decimal(value)]

    if isinstance(value, float):
        # Convert float, keeping its precision
        return [Decimal(str(value))]

    if isinstance(value, str):
        try:
            return [Decimal(value)]
        except (ValueError, ArithmeticError):
            return []

    return []


@FunctionRegistry.register("convertsToDecimal")
def fn_converts_to_decimal(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to a decimal."""
    result = fn_to_decimal(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toString")
def fn_to_string(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Converts the input to a string."""
    from decimal import Decimal as PyDecimal

    from ...types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, bool):
        return ["true" if value else "false"]

    if isinstance(value, int):
        return [str(value)]

    if isinstance(value, (float, PyDecimal)):
        # Format decimal: FHIRPath requires preserving trailing zeros
        return [str(value)]

    if isinstance(value, str):
        return [value]

    if isinstance(value, Quantity):
        # Format value preserving precision
        val_str = str(value.value)
        # Use original_unit for calendar durations (e.g., "week" instead of "wk")
        if value.original_unit:
            return [f"{val_str} {value.original_unit}"]
        unit = value.unit
        if unit == "1":
            return [val_str]
        return [f"{val_str} '{unit}'"]

    if isinstance(value, FHIRDateTime):
        return [str(value)]

    if isinstance(value, FHIRDate):
        return [str(value)]

    if isinstance(value, FHIRTime):
        return [str(value)]

    return []


@FunctionRegistry.register("convertsToString")
def fn_converts_to_string(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to a string."""
    result = fn_to_string(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toDate")
def fn_to_date(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Converts the input to a date."""
    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, str):
        # Basic date validation - YYYY-MM-DD format
        import re

        if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", value):
            return [value]
        # Handle datetime by extracting date part
        if "T" in value:
            date_part = value.split("T")[0]
            if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", date_part):
                return [date_part]
    return []


@FunctionRegistry.register("convertsToDate")
def fn_converts_to_date(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to a date."""
    result = fn_to_date(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toDateTime")
def fn_to_datetime(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Converts the input to a datetime."""
    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, str):
        import re

        # Full datetime or date-only (which implicitly becomes datetime)
        # Timezone can be Z, or +/-HH:MM
        if re.match(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?$", value):
            return [value]
    return []


@FunctionRegistry.register("convertsToDateTime")
def fn_converts_to_datetime(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to a datetime."""
    result = fn_to_datetime(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toTime")
def fn_to_time(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Converts the input to a time."""
    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, str):
        import re

        # Time format HH:MM:SS.fff
        if re.match(r"^\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?$", value):
            return [value]
        # Handle T prefix
        if value.startswith("T") and re.match(r"^T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?$", value):
            return [value[1:]]
    return []


@FunctionRegistry.register("convertsToTime")
def fn_converts_to_time(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input can be converted to a time."""
    result = fn_to_time(ctx, collection)
    return [len(result) > 0]


@FunctionRegistry.register("toQuantity")
def fn_to_quantity(ctx: EvaluationContext, collection: list[Any], unit: str | None = None) -> list[Any]:
    """Converts the input to a quantity."""
    from decimal import Decimal

    from ...types import Quantity

    if not collection:
        return []

    value = _unwrap_value(collection[0])

    if isinstance(value, Quantity):
        return [value]

    # Handle boolean first (before int check since bool is subclass of int)
    if isinstance(value, bool):
        return [Quantity(value=Decimal(1 if value else 0), unit=unit or "1")]

    if isinstance(value, (int, float, Decimal)):
        return [Quantity(value=Decimal(str(value)), unit=unit or "1")]

    if isinstance(value, str):
        import re

        # Parse "number unit" format
        # Number must be: integer OR decimal with digits after the point
        match = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(.*)$", value.strip())
        if match:
            num_str, unit_str = match.groups()
            unit_str = unit_str.strip()

            # Valid units are:
            # - Calendar duration keywords (year, month, week, day, hour, minute, second, millisecond and plurals)
            # - UCUM units in single quotes (e.g., 'kg', 'wk')
            # - Empty (defaults to '1')
            # Calendar units map to UCUM equivalents
            calendar_to_ucum = {
                "year": "a",
                "years": "a",
                "month": "mo",
                "months": "mo",
                "week": "wk",
                "weeks": "wk",
                "day": "d",
                "days": "d",
                "hour": "h",
                "hours": "h",
                "minute": "min",
                "minutes": "min",
                "second": "s",
                "seconds": "s",
                "millisecond": "ms",
                "milliseconds": "ms",
            }
            is_valid_unit = (
                not unit_str  # Empty is OK
                or unit_str in calendar_to_ucum  # Calendar duration
                or (unit_str.startswith("'") and unit_str.endswith("'"))  # UCUM in quotes
            )

            if not is_valid_unit:
                return []

            # Convert calendar units to UCUM, or remove quotes from UCUM units
            if unit_str in calendar_to_ucum:
                unit_str = calendar_to_ucum[unit_str]
            elif unit_str.startswith("'") and unit_str.endswith("'"):
                unit_str = unit_str[1:-1]

            try:
                return [Quantity(value=Decimal(num_str), unit=unit_str or unit or "1")]
            except (ValueError, ArithmeticError):
                pass
    return []


@FunctionRegistry.register("convertsToQuantity")
def fn_converts_to_quantity(ctx: EvaluationContext, collection: list[Any], unit: str | None = None) -> list[bool]:
    """Returns true if the input can be converted to a quantity."""
    result = fn_to_quantity(ctx, collection, unit)
    return [len(result) > 0]
