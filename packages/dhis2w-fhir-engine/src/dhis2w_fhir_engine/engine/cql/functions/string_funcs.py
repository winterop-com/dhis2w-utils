"""CQL String Functions.

Implements: Concatenate, Combine, Split, Upper, Lower, StartsWith, EndsWith,
Substring, PositionOf, LastPositionOf, Matches, ReplaceMatches, Length
"""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .registry import FunctionRegistry


def _concatenate(args: list[Any]) -> str | None:
    """Concatenate strings.

    Per CQL spec: If any argument is null, the result is null.
    Note: This differs from the & operator which treats null as empty string.
    """
    # If any argument is null, return null
    for arg in args:
        if arg is None:
            return None
    # All arguments are non-null, concatenate them
    return "".join(str(arg) for arg in args)


def _split(args: list[Any]) -> list[str] | None:
    """Split a string by separator.

    Per CQL spec: If separator is null, returns a list with the original string.
    """
    if len(args) >= 2:
        s = args[0]
        sep = args[1]
        if s is None:
            return None
        if sep is None:
            # Null separator returns list with original string
            return [str(s)]
        return str(s).split(str(sep))
    return None


def _upper(args: list[Any]) -> str | None:
    """Convert string to uppercase."""
    if args and args[0] is not None:
        return str(args[0]).upper()
    return None


def _lower(args: list[Any]) -> str | None:
    """Convert string to lowercase."""
    if args and args[0] is not None:
        return str(args[0]).lower()
    return None


def _starts_with(args: list[Any]) -> bool | None:
    """Check if string starts with prefix."""
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        return str(args[0]).startswith(str(args[1]))
    return None


def _ends_with(args: list[Any]) -> bool | None:
    """Check if string ends with suffix."""
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        return str(args[0]).endswith(str(args[1]))
    return None


def _substring(args: list[Any]) -> str | None:
    """Get substring from start index with optional length.

    Per CQL spec:
    - Negative start index returns null
    - Start index beyond string length returns null
    """
    if len(args) >= 2 and args[0] is not None:
        s = str(args[0])
        start = args[1]
        if start is None:
            return None
        start = int(start)
        # Negative index is invalid in CQL
        if start < 0:
            return None
        # Start beyond string length returns null
        if start >= len(s):
            return None
        if len(args) >= 3 and args[2] is not None:
            length = int(args[2])
            return s[start : start + length]
        return s[start:]
    return None


def _position_of(args: list[Any]) -> int | None:
    """Find position of pattern in string.

    Per CQL spec: Returns -1 if pattern is not found, null if either arg is null.
    """
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        pattern = str(args[0])
        s = str(args[1])
        return s.find(pattern)  # Returns -1 if not found
    return None


def _last_position_of(args: list[Any]) -> int | None:
    """Find last position of pattern in string.

    Per CQL spec: Returns -1 if pattern is not found, null if either arg is null.
    """
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        pattern = str(args[0])
        s = str(args[1])
        return s.rfind(pattern)  # Returns -1 if not found
    return None


def _matches(args: list[Any]) -> bool | None:
    """Check if string matches regex pattern.

    Per CQL spec: Returns true if the entire string matches the pattern.
    """
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        s = str(args[0])
        pattern = str(args[1])
        try:
            return bool(re.fullmatch(pattern, s))
        except re.error:
            return None
    return None


def _replace_matches(args: list[Any]) -> str | None:
    r"""Replace regex matches in string.

    Per CQL spec: The replacement string follows regex replacement rules
    where \$ becomes literal $, etc.
    """
    if len(args) >= 3 and args[0] is not None:
        s = str(args[0])
        pattern = args[1]
        replacement = args[2]
        if pattern is None or replacement is None:
            return None
        try:
            # Process CQL escape sequences in replacement:
            # \\$ -> $ (literal dollar sign)
            # \\\ -> \ (literal backslash)
            repl = str(replacement)
            # First unescape CQL-style escapes to actual characters
            repl = repl.replace("\\$", "$")
            repl = repl.replace("\\\\", "\\")
            return re.sub(str(pattern), repl, s)
        except re.error:
            return None
    return None


def _replace(args: list[Any]) -> str | None:
    """Simple string replace (not regex)."""
    if len(args) >= 3 and args[0] is not None:
        s = str(args[0])
        find = args[1]
        replace_with = args[2]
        if find is None or replace_with is None:
            return None
        return s.replace(str(find), str(replace_with))
    return None


def _string_length(args: list[Any]) -> int | None:
    """Get length of a string.

    Per HL7 tests: Length(null) = 0.
    """
    if args:
        if args[0] is None:
            return 0
        return len(str(args[0]))
    return None


def _trim(args: list[Any]) -> str | None:
    """Trim whitespace from string."""
    if args and args[0] is not None:
        return str(args[0]).strip()
    return None


def _indexer(args: list[Any]) -> str | None:
    """Get character at index (CQL Indexer for strings)."""
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        s = str(args[0])
        idx = int(args[1])
        if 0 <= idx < len(s):
            return s[idx]
    return None


def _contains_string(args: list[Any]) -> bool | None:
    """Check if string contains substring."""
    if len(args) >= 2 and args[0] is not None and args[1] is not None:
        return str(args[1]) in str(args[0])
    return None


def register(registry: "FunctionRegistry") -> None:
    """Register all string functions."""
    registry.register("Concatenate", _concatenate, aliases=["Concat"], category="string", min_args=1)
    registry.register("Split", _split, category="string", min_args=2, max_args=2)
    registry.register("Upper", _upper, category="string", min_args=1, max_args=1)
    registry.register("Lower", _lower, category="string", min_args=1, max_args=1)
    registry.register("StartsWith", _starts_with, category="string", min_args=2, max_args=2)
    registry.register("EndsWith", _ends_with, category="string", min_args=2, max_args=2)
    registry.register("Substring", _substring, category="string", min_args=2, max_args=3)
    registry.register("PositionOf", _position_of, category="string", min_args=2, max_args=2)
    registry.register("LastPositionOf", _last_position_of, category="string", min_args=2, max_args=2)
    registry.register("Matches", _matches, category="string", min_args=2, max_args=2)
    registry.register("ReplaceMatches", _replace_matches, category="string", min_args=3, max_args=3)
    registry.register("Replace", _replace, category="string", min_args=3, max_args=3)
    registry.register("Trim", _trim, category="string", min_args=1, max_args=1)
    registry.register("Indexer", _indexer, category="string", min_args=2, max_args=2)
