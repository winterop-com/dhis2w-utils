"""CQL List Functions.

Implements: First, Last, Tail, Take, Skip, Length, Exists, Flatten, Distinct,
Sort, IndexOf, Singleton, SingletonFrom, Reverse, Slice, Combine, Union, Intersect, Except
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .registry import FunctionRegistry


def _first(args: list[Any]) -> Any:
    """Get first element of a list."""
    if args and isinstance(args[0], list) and len(args[0]) > 0:
        return args[0][0]
    return None


def _last(args: list[Any]) -> Any:
    """Get last element of a list."""
    if args and isinstance(args[0], list) and len(args[0]) > 0:
        return args[0][-1]
    return None


def _tail(args: list[Any]) -> list[Any] | None:
    """Get all elements except the first.

    Per CQL spec: If list is null, result is null.
    """
    if args:
        lst = args[0]
        if lst is None:
            return None
        if isinstance(lst, list) and len(lst) > 1:
            return lst[1:]
    return []


def _take(args: list[Any]) -> list[Any] | None:
    """Take first n elements from a list.

    Per CQL spec: If list is null, result is null.
    """
    if len(args) >= 2:
        lst = args[0]
        n = args[1]
        if lst is None:
            return None
        if isinstance(lst, list) and isinstance(n, int):
            return lst[:n]
    return []


def _skip(args: list[Any]) -> list[Any] | None:
    """Skip first n elements of a list.

    Per CQL spec: If list is null, result is null.
    """
    if len(args) >= 2:
        lst = args[0]
        n = args[1]
        if lst is None:
            return None
        if isinstance(lst, list) and isinstance(n, int):
            return lst[n:]
    return []


def _length(args: list[Any]) -> int:
    """Get length of a list or string.

    Per CQL spec: Length of null returns 0.
    """
    if args:
        val = args[0]
        if val is None:
            return 0
        if isinstance(val, (list, str)):
            return len(val)
    return 0


def _exists(args: list[Any]) -> bool:
    """Check if a value exists (not null/empty).

    Per CQL spec: Exists returns true if list has at least one non-null element.
    A list containing only null values returns false.
    """
    if args:
        val = args[0]
        if isinstance(val, list):
            # Check if any non-null elements exist
            return any(x is not None for x in val)
        return val is not None
    return False


def _flatten(args: list[Any]) -> list[Any]:
    """Flatten a list of lists."""
    if not args or not isinstance(args[0], list):
        return []
    result = []
    for item in args[0]:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def _distinct(args: list[Any]) -> list[Any]:
    """Get distinct values from a list.

    Per CQL spec: Null elements are ignored/removed.
    """
    if not args or not isinstance(args[0], list):
        return []
    seen = []
    for item in args[0]:
        # Skip null values per CQL spec
        if item is None:
            continue
        if item not in seen:
            seen.append(item)
    return seen


def _sort(args: list[Any]) -> list[Any]:
    """Sort a list."""
    if not args or not isinstance(args[0], list):
        return []
    values = args[0]
    try:
        return sorted(values)
    except TypeError:
        return values


def _index_of(args: list[Any]) -> int | None:
    """Find index of an element in a list or substring in a string.

    CQL signature: IndexOf(source List<T>, element T) returns Integer
    Returns the index of the element, or -1 if not found.
    Per CQL spec: If source is null, result is null.
    """
    if len(args) >= 2:
        source = args[0]  # list/string to search in
        element = args[1]  # element to find
        # If source is null, result is null
        if source is None:
            return None
        if isinstance(source, list):
            # List IndexOf - find element in list (including null)
            for i, item in enumerate(source):
                if item is element or item == element:
                    return i
            return -1
        if isinstance(source, str) and isinstance(element, str):
            # String IndexOf - find substring in string
            return source.find(element)
    return -1


def _singleton(args: list[Any]) -> Any:
    """Get single element from a list."""
    if args and isinstance(args[0], list):
        lst = args[0]
        if len(lst) == 1:
            return lst[0]
    return None


def _singleton_from(args: list[Any]) -> Any:
    """Get single element from a list, error if more than one."""
    from ...exceptions import CQLError

    if args and isinstance(args[0], list):
        lst = args[0]
        if len(lst) == 0:
            return None
        if len(lst) == 1:
            return lst[0]
        raise CQLError("singleton from requires a list with at most one element")
    return None


def _reverse(args: list[Any]) -> list[Any]:
    """Reverse a list."""
    if args and isinstance(args[0], list):
        return list(reversed(args[0]))
    return []


def _slice(args: list[Any]) -> list[Any]:
    """Get a slice of a list.

    Args: (list, startIndex, length)
    """
    if len(args) >= 3 and isinstance(args[0], list):
        start = args[1] if args[1] is not None else 0
        length = args[2] if args[2] is not None else len(args[0])
        return args[0][start : start + length]
    return []


def _combine(args: list[Any]) -> Any:
    """Combine elements (concatenate lists or join strings).

    Combine(list) - joins list elements with empty string
    Combine(list, separator) - joins list elements with separator
    Combine(list1, list2) - concatenates two lists
    """
    if not args:
        return None
    if len(args) >= 2 and isinstance(args[0], list) and isinstance(args[1], str):
        # Join list of strings with separator
        return args[1].join(str(x) for x in args[0] if x is not None)
    if len(args) == 1 and isinstance(args[0], list):
        # Join list with empty string (no separator)
        return "".join(str(x) for x in args[0] if x is not None)
    if len(args) >= 2 and isinstance(args[0], list) and isinstance(args[1], list):
        # Concatenate two lists
        result = list(args[0])
        result.extend(args[1])
        return result
    return None


def _union(args: list[Any]) -> list[Any]:
    """Union of two lists (concatenates all elements, preserves duplicates)."""
    if len(args) >= 2:
        left = list(args[0]) if isinstance(args[0], list) else [args[0]]
        right = list(args[1]) if isinstance(args[1], list) else [args[1]]
        return left + right
    return []


def _intersect(args: list[Any]) -> list[Any]:
    """Intersection of two lists."""
    if len(args) >= 2 and isinstance(args[0], list) and isinstance(args[1], list):
        return [x for x in args[0] if x in args[1]]
    return []


def _except(args: list[Any]) -> list[Any]:
    """Difference of two lists (elements in first but not second)."""
    if len(args) >= 2 and isinstance(args[0], list) and isinstance(args[1], list):
        return [x for x in args[0] if x not in args[1]]
    return []


def register(registry: "FunctionRegistry") -> None:
    """Register all list functions."""
    registry.register("First", _first, category="list", min_args=1, max_args=1)
    registry.register("Last", _last, category="list", min_args=1, max_args=1)
    registry.register("Tail", _tail, category="list", min_args=1, max_args=1)
    registry.register("Take", _take, category="list", min_args=2, max_args=2)
    registry.register("Skip", _skip, category="list", min_args=2, max_args=2)
    registry.register("Length", _length, category="list", min_args=1, max_args=1)
    registry.register("Exists", _exists, category="list", min_args=1, max_args=1)
    registry.register("Flatten", _flatten, category="list", min_args=1, max_args=1)
    registry.register("Distinct", _distinct, category="list", min_args=1, max_args=1)
    registry.register("Sort", _sort, category="list", min_args=1, max_args=1)
    registry.register("IndexOf", _index_of, category="list", min_args=2, max_args=2)
    registry.register("Singleton", _singleton, category="list", min_args=1, max_args=1)
    registry.register("SingletonFrom", _singleton_from, category="list", min_args=1, max_args=1)
    registry.register("Reverse", _reverse, category="list", min_args=1, max_args=1)
    registry.register("Slice", _slice, category="list", min_args=3, max_args=3)
    registry.register("Combine", _combine, category="list", min_args=1)
    registry.register("Union", _union, category="list", min_args=2, max_args=2)
    registry.register("Intersect", _intersect, category="list", min_args=2, max_args=2)
    registry.register("Except", _except, category="list", min_args=2, max_args=2)
