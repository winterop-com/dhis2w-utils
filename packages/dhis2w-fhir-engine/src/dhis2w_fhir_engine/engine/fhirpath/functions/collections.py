"""Collection functions."""

from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry


@FunctionRegistry.register("distinct")
def fn_distinct(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns collection with duplicates removed."""
    seen: list[Any] = []
    for item in collection:
        # Use custom equality check for complex types
        found = False
        for s in seen:
            if _deep_equals(item, s):
                found = True
                break
        if not found:
            seen.append(item)
    return seen


@FunctionRegistry.register("isDistinct")
def fn_is_distinct(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Returns true if all elements in collection are distinct."""
    distinct = fn_distinct(ctx, collection)
    return [len(distinct) == len(collection)]


def _ensure_list(val: Any) -> list[Any]:
    """Ensure a value is a list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


@FunctionRegistry.register("union")
def fn_union(ctx: EvaluationContext, left: list[Any], right: Any) -> list[Any]:
    """Returns union of two collections (with duplicates removed)."""
    right_list = _ensure_list(right)
    combined = left + right_list
    distinct: list[Any] = fn_distinct(ctx, combined)
    return distinct


@FunctionRegistry.register("intersect")
def fn_intersect(ctx: EvaluationContext, left: list[Any], right: Any) -> list[Any]:
    """Returns intersection of two collections."""
    right_list = _ensure_list(right)
    result = []
    for item in left:
        for r_item in right_list:
            if _deep_equals(item, r_item):
                result.append(item)
                break
    distinct: list[Any] = fn_distinct(ctx, result)
    return distinct


@FunctionRegistry.register("exclude")
def fn_exclude(ctx: EvaluationContext, left: list[Any], right: Any) -> list[Any]:
    """Returns elements in left that are not in right."""
    right_list = _ensure_list(right)
    result = []
    for item in left:
        found = False
        for r_item in right_list:
            if _deep_equals(item, r_item):
                found = True
                break
        if not found:
            result.append(item)
    return result


@FunctionRegistry.register("combine")
def fn_combine(ctx: EvaluationContext, left: list[Any], right: Any) -> list[Any]:
    """Combines two collections (preserves duplicates)."""
    right_list = _ensure_list(right)
    return left + right_list


@FunctionRegistry.register("flatten")
def fn_flatten(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Flattens nested collections one level."""
    result = []
    for item in collection:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


@FunctionRegistry.register("subsetOf")
def fn_subset_of(ctx: EvaluationContext, left: list[Any], right: Any) -> list[bool]:
    """Returns true if left is a subset of right."""
    right_list = _ensure_list(right)
    for item in left:
        found = False
        for r_item in right_list:
            if _deep_equals(item, r_item):
                found = True
                break
        if not found:
            return [False]
    return [True]


@FunctionRegistry.register("supersetOf")
def fn_superset_of(ctx: EvaluationContext, left: list[Any], right: Any) -> list[bool]:
    """Returns true if left is a superset of right."""
    right_list = _ensure_list(right)
    is_subset: list[bool] = fn_subset_of(ctx, right_list, left)
    return is_subset


@FunctionRegistry.register("sort")
def fn_sort(ctx: EvaluationContext, collection: list[Any], *args: Any) -> list[Any]:
    """Sorts the collection.

    If no criteria is provided, sorts by natural ordering.
    If criteria is provided, it's evaluated for each item to get the sort key.
    A negative polarity on the criteria means descending order.
    """
    if not collection:
        return []

    if not args:
        # Sort by natural ordering
        try:
            return sorted(collection, key=lambda x: (x is None, x))
        except TypeError:
            # Can't compare mixed types, return as-is
            return collection

    # With criteria, we need to evaluate it for each item
    # This is handled specially in the visitor for lazy evaluation
    # For now, just return the collection (will be handled by visitor)
    return collection


def _unwrap_value(value: Any) -> Any:
    """Unwrap a potentially wrapped FHIR primitive value."""
    from ..visitor import _PrimitiveWithExtension

    if isinstance(value, _PrimitiveWithExtension):
        return value.value
    return value


def _deep_equals(a: Any, b: Any) -> bool:
    """Deep equality check for FHIRPath values."""
    # Unwrap primitive wrappers
    a = _unwrap_value(a)
    b = _unwrap_value(b)

    if type(a) is not type(b):
        # Special case for int/float comparison
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        return False

    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equals(a[k], b[k]) for k in a)

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_deep_equals(a[i], b[i]) for i in range(len(a)))

    equal: bool = a == b
    return equal
