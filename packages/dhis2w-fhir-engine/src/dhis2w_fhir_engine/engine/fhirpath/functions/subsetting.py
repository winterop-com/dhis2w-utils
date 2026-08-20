"""Subsetting functions: first, last, tail, take, skip, single."""

from typing import Any

from ...context import EvaluationContext
from ...exceptions import FHIRPathError
from ...functions import FunctionRegistry


@FunctionRegistry.register("first")
def fn_first(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the first element of the collection, or empty if none."""
    if not collection:
        return []
    return [collection[0]]


@FunctionRegistry.register("last")
def fn_last(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the last element of the collection, or empty if none."""
    if not collection:
        return []
    return [collection[-1]]


@FunctionRegistry.register("tail")
def fn_tail(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns all elements except the first."""
    if len(collection) <= 1:
        return []
    return collection[1:]


@FunctionRegistry.register("take")
def fn_take(ctx: EvaluationContext, collection: list[Any], num: int | float | None) -> list[Any]:
    """Returns the first num elements of the collection."""
    n = int(num) if num is not None else 0
    return collection[:n]


@FunctionRegistry.register("skip")
def fn_skip(ctx: EvaluationContext, collection: list[Any], num: int | float | None) -> list[Any]:
    """Returns all elements after skipping the first num."""
    n = int(num) if num is not None else 0
    return collection[n:]


@FunctionRegistry.register("single")
def fn_single(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the single element, or empty if none.

    Raises error if more than one element.
    """
    if not collection:
        return []
    if len(collection) > 1:
        raise FHIRPathError(f"single() expected 0 or 1 elements, got {len(collection)}")
    return collection


@FunctionRegistry.register("not")
def fn_not(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns the boolean negation of the input."""
    if not collection:
        return []
    if len(collection) == 1 and isinstance(collection[0], bool):
        return [not collection[0]]
    # For non-boolean, return negation of "exists"
    return [not bool(collection)]
