"""Existence functions: exists, empty, count, all, any."""

from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry


@FunctionRegistry.register("exists")
def fn_exists(ctx: EvaluationContext, collection: list[Any], *args: Any) -> list[bool]:
    """Returns true if the collection has any elements.

    If criteria is provided, returns true if any element matches.

    Note: When called with a criteria argument, the visitor handles evaluation
    via _evaluate_exists() method. This function only handles the no-criteria case.
    """
    return [len(collection) > 0]


@FunctionRegistry.register("empty")
def fn_empty(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the collection is empty."""
    return [len(collection) == 0]


@FunctionRegistry.register("count")
def fn_count(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Returns the number of elements in the collection."""
    return [len(collection)]


@FunctionRegistry.register("all")
def fn_all(ctx: EvaluationContext, collection: list[Any], criteria: Any = None) -> list[bool]:
    """Returns true if all elements in the collection match the criteria.

    If collection is empty, returns true.
    """
    if not collection:
        return [True]

    # criteria is evaluated by the visitor for each item
    # This function receives pre-evaluated boolean results
    if criteria is None:
        # No criteria means check if all items are truthy
        return [all(bool(item) for item in collection)]

    # With criteria, we expect it to be evaluated per-item by visitor
    return [all(bool(item) for item in collection)]


@FunctionRegistry.register("allTrue")
def fn_all_true(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if all elements are true."""
    if not collection:
        return [True]
    return [all(item is True for item in collection)]


@FunctionRegistry.register("anyTrue")
def fn_any_true(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if any element is true."""
    return [any(item is True for item in collection)]


@FunctionRegistry.register("allFalse")
def fn_all_false(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if all elements are false."""
    if not collection:
        return [True]
    return [all(item is False for item in collection)]


@FunctionRegistry.register("anyFalse")
def fn_any_false(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if any element is false."""
    return [any(item is False for item in collection)]


@FunctionRegistry.register("hasValue")
def fn_has_value(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if the input has a value (is not empty and not null)."""
    # Import here to avoid circular imports
    from ..visitor import _PrimitiveWithExtension

    if not collection:
        return [False]

    item = collection[0]
    # Handle primitives with extensions - check the underlying value
    if isinstance(item, _PrimitiveWithExtension):
        return [item.value is not None]
    return [item is not None]
