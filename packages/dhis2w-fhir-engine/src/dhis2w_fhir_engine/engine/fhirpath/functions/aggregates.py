"""Aggregate functions: sum, min, max, avg.

FHIRPath section 7 (Aggregates) defines `aggregate()` and, beside it, four named short-cuts for the
aggregations people actually write. `aggregate()` lives in the visitor because it evaluates an
expression per item; these four read the collection they are handed and so belong here.

Section 7 states three rules for all four, and each one is implemented literally:

- an empty input collection answers with the empty collection,
- every item is the same type, or an exception is thrown,
- `avg()` answers in Decimal, converting Integer and Long on the way in.

The one place the code reads the type rule more widely than the letter of the spec is the numeric
family: Integer, Long and Decimal count as one type here, because FHIRPath converts Integer to
Decimal implicitly everywhere else and `avg()` names that conversion outright. Mixing a number with
a String, a Boolean, a Quantity, or a date is what the rule refuses.
"""

from decimal import Decimal
from typing import Any

from ...context import EvaluationContext
from ...exceptions import FHIRPathError
from ...functions import FunctionRegistry
from ...types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

_NUMBER = "number"
_QUANTITY = "Quantity"

_ADDABLE_KINDS = frozenset({_NUMBER, _QUANTITY})
"""What `sum()` and `avg()` take: the numeric family and Quantity."""

_ORDERED_KINDS = frozenset({_NUMBER, _QUANTITY, "String", "Date", "DateTime", "Time"})
"""What `min()` and `max()` take: everything section 7 lists comparison semantics for."""


def _unwrap_value(value: Any) -> Any:
    """Read the number out of a FHIR primitive that carries its own extensions."""
    from ..visitor import _underlying_value

    return _underlying_value(value)


def _kind_of(value: Any) -> str:
    """Name the type family an aggregate groups a value under.

    Booleans are tested before the numeric family because `bool` is a subclass of `int` in Python
    and `(true | false).sum()` is not an aggregation any of these four accept.
    """
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, (int, float, Decimal)):
        return _NUMBER
    if isinstance(value, Quantity):
        return _QUANTITY
    if isinstance(value, str):
        return "String"
    if isinstance(value, FHIRDate):
        return "Date"
    if isinstance(value, FHIRDateTime):
        return "DateTime"
    if isinstance(value, FHIRTime):
        return "Time"
    return type(value).__name__


def _checked_values(function_name: str, collection: list[Any], accepted_kinds: frozenset[str]) -> list[Any]:
    """Unwrap a non-empty collection and refuse a mixed one, or one of a type this aggregate has no rule for."""
    values = [_unwrap_value(item) for item in collection]
    kinds = sorted({_kind_of(value) for value in values})
    if len(kinds) > 1:
        raise FHIRPathError(f"{function_name}() takes one type across the collection, and this one mixes {kinds}")
    if kinds[0] not in accepted_kinds:
        raise FHIRPathError(f"{function_name}() has no rule for {kinds[0]}; it takes {sorted(accepted_kinds)}")
    return values


def _one_unit(function_name: str, quantities: list[Quantity]) -> str:
    """Return the single unit the quantities share, refusing a collection that carries more than one.

    Adding two quantities is the `+` operator's rule - same unit or nothing - and these two functions
    are that operator applied down a collection, so they hold to the same rule rather than converting
    silently. `min()` and `max()` compare instead of add, and comparison does convert.
    """
    units = sorted({quantity.unit for quantity in quantities})
    if len(units) > 1:
        raise FHIRPathError(f"{function_name}() adds quantities in one unit, and this collection carries {units}")
    return units[0]


def _numeric_total(values: list[Any]) -> Any:
    """Add a numeric collection, keeping Integer arithmetic exact and lifting anything else to Decimal or float."""
    if all(isinstance(value, int) for value in values):
        return sum(values)
    if any(isinstance(value, Decimal) for value in values):
        return sum((Decimal(str(value)) for value in values), Decimal(0))
    return sum(float(value) for value in values)


def _decimal_total(values: list[Any]) -> Decimal:
    """Add a numeric collection in Decimal, which is the type `avg()` answers in."""
    return sum((Decimal(str(value)) for value in values), Decimal(0))


@FunctionRegistry.register("sum")
def fn_sum(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the sum of a numeric or Quantity collection, and the empty collection for an empty one."""
    if not collection:
        return []
    values = _checked_values("sum", collection, _ADDABLE_KINDS)
    if isinstance(values[0], Quantity):
        quantities: list[Quantity] = values
        unit = _one_unit("sum", quantities)
        return [Quantity(value=sum((quantity.value for quantity in quantities), Decimal(0)), unit=unit)]
    return [_numeric_total(values)]


@FunctionRegistry.register("avg")
def fn_avg(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the average of a numeric or Quantity collection in Decimal, and empty for an empty one."""
    if not collection:
        return []
    values = _checked_values("avg", collection, _ADDABLE_KINDS)
    count = Decimal(len(values))
    if isinstance(values[0], Quantity):
        quantities: list[Quantity] = values
        unit = _one_unit("avg", quantities)
        total = sum((quantity.value for quantity in quantities), Decimal(0))
        return [Quantity(value=total / count, unit=unit)]
    return [_decimal_total(values) / count]


@FunctionRegistry.register("min")
def fn_min(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the smallest item under the comparison rules for its type, and empty for an empty collection."""
    if not collection:
        return []
    values = _checked_values("min", collection, _ORDERED_KINDS)
    try:
        return [min(values)]
    except TypeError as error:
        raise FHIRPathError(f"min() cannot order this collection: {error}") from error


@FunctionRegistry.register("max")
def fn_max(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the largest item under the comparison rules for its type, and empty for an empty collection."""
    if not collection:
        return []
    values = _checked_values("max", collection, _ORDERED_KINDS)
    try:
        return [max(values)]
    except TypeError as error:
        raise FHIRPathError(f"max() cannot order this collection: {error}") from error
