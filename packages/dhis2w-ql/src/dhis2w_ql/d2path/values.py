"""Low-level value helpers shared by the evaluator and the function registry.

Values flow through the evaluator as plain Python objects (str/int/float/bool/None, list, dict,
or pydantic `BaseModel`). Collections are Python lists; "single" values are length-1 lists.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_MISSING = object()


def collapse(items: list[Any]) -> Any:
    """Collapse a collection to a scalar for object/array construction: []→None, [x]→x, else the list."""
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return items


def truthy(items: list[Any]) -> bool:
    """FHIRPath-style truthiness: empty is false, a singleton boolean is itself, else non-empty is true."""
    if not items:
        return False
    if len(items) == 1 and isinstance(items[0], bool):
        return items[0]
    return True


def member(item: Any, name: str) -> Any:
    """Read property `name` from a dict or pydantic model; return a sentinel when absent.

    For FHIR resources a leading type name (`Patient.name`) resolves to the resource itself when
    the node's `resourceType` matches, so type-prefixed paths navigate as written.
    """
    if isinstance(item, BaseModel):
        if name in type(item).model_fields:
            return getattr(item, name)
        extra = item.model_extra or {}
        if name in extra:
            return extra[name]
        return _MISSING
    if isinstance(item, dict):
        if name in item:
            return item[name]
        if item.get("resourceType") == name:
            return item
        return _MISSING
    return _MISSING


def is_missing(value: Any) -> bool:
    """Report whether `member` returned its absent sentinel."""
    return value is _MISSING


def flatten_member(items: list[Any], name: str) -> list[Any]:
    """Navigate `name` across a collection, flattening list-valued results and dropping absent nodes."""
    result: list[Any] = []
    for item in items:
        value = member(item, name)
        if value is _MISSING or value is None:
            continue
        if isinstance(value, list):
            result.extend(v for v in value if v is not None)
        else:
            result.append(value)
    return result


def to_number(value: Any) -> float | None:
    """Coerce a value to a float for arithmetic/comparison, or None when it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def loose_equal(left: Any, right: Any) -> bool:
    """Equality used by `=`: numeric-aware, otherwise Python equality."""
    left_number, right_number = to_number(left), to_number(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return bool(left == right)


def like(left: Any, right: Any) -> bool:
    """The `~` operator: case-insensitive substring match for strings, loose equality otherwise."""
    if isinstance(left, str) and isinstance(right, str):
        return right.casefold() in left.casefold()
    return loose_equal(left, right)


def compare(left: Any, right: Any) -> int | None:
    """Three-way compare for `< <= > >=`; returns None when the operands are not comparable."""
    left_number, right_number = to_number(left), to_number(right)
    if left_number is not None and right_number is not None:
        return (left_number > right_number) - (left_number < right_number)
    if isinstance(left, str) and isinstance(right, str):
        return (left > right) - (left < right)
    return None
