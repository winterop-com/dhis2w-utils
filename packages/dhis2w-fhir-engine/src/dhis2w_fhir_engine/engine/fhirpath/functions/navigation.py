"""Tree navigation functions: children, descendants."""

from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry


def _get_children(item: Any) -> list[Any]:
    """Get immediate children of an item."""
    if isinstance(item, dict):
        result = []
        for key, value in item.items():
            if key.startswith("_"):
                continue  # Skip FHIR primitive extensions
            if isinstance(value, list):
                result.extend(value)
            else:
                result.append(value)
        return result
    return []


def _get_descendants(item: Any) -> list[Any]:
    """Get all descendants of an item recursively."""
    result = []
    children = _get_children(item)
    for child in children:
        result.append(child)
        result.extend(_get_descendants(child))
    return result


@FunctionRegistry.register("children")
def fn_children(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns a collection with all immediate child nodes of all items in the input collection.

    Note: This function is FHIR-aware and skips primitive extension elements (prefixed with _).
    """
    result = []
    for item in collection:
        result.extend(_get_children(item))
    return result


@FunctionRegistry.register("descendants")
def fn_descendants(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns a collection with all descendant nodes of all items in the input collection.

    Descendants include all child nodes, recursively.
    """
    result = []
    for item in collection:
        result.extend(_get_descendants(item))
    return result
