"""String functions."""

import base64
import html
import json
import re
from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry


def _unwrap_value(value: Any) -> Any:
    """Unwrap a potentially wrapped FHIR primitive value."""
    from ..visitor import _PrimitiveWithExtension

    if isinstance(value, _PrimitiveWithExtension):
        return value.value
    return value


@FunctionRegistry.register("startsWith")
def fn_starts_with(ctx: EvaluationContext, collection: list[Any], prefix: str) -> list[bool]:
    """Returns true if string starts with the given prefix."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.startswith(prefix)]


@FunctionRegistry.register("endsWith")
def fn_ends_with(ctx: EvaluationContext, collection: list[Any], suffix: str) -> list[bool]:
    """Returns true if string ends with the given suffix."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.endswith(suffix)]


@FunctionRegistry.register("contains")
def fn_contains(ctx: EvaluationContext, collection: list[Any], substring: str) -> list[bool]:
    """Returns true if string contains the given substring."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [substring in value]


@FunctionRegistry.register("matches")
def fn_matches(ctx: EvaluationContext, collection: list[Any], pattern: str | None = None) -> list[bool]:
    """Returns true if string matches the regex pattern (partial match)."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    # Empty pattern returns empty
    if pattern is None or pattern == "":
        return []
    try:
        # Use DOTALL so . matches newlines (FHIRPath single-line mode)
        return [bool(re.search(pattern, value, re.DOTALL))]
    except re.error:
        return [False]


@FunctionRegistry.register("matchesFull")
def fn_matches_full(ctx: EvaluationContext, collection: list[Any], pattern: str | None = None) -> list[bool]:
    """Returns true if string fully matches the regex pattern (entire string must match)."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    # Empty pattern returns empty
    if pattern is None or pattern == "":
        return []
    try:
        # Use DOTALL so . matches newlines
        return [bool(re.fullmatch(pattern, value, re.DOTALL))]
    except re.error:
        return [False]


@FunctionRegistry.register("replace")
def fn_replace(
    ctx: EvaluationContext, collection: list[Any], pattern: str | None, substitution: str | None
) -> list[str]:
    """Replaces all occurrences of pattern with substitution (simple string replacement).

    Per FHIRPath spec: if pattern or substitution is empty, returns empty.
    """
    if not collection:
        return []
    # If pattern or substitution is None/empty, return empty
    if pattern is None or substitution is None:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.replace(pattern, substitution)]


@FunctionRegistry.register("replaceMatches")
def fn_replace_matches(
    ctx: EvaluationContext, collection: list[Any], regex: str | None = None, substitution: str | None = None
) -> list[str]:
    """Replaces all matches of regex pattern with substitution."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    # Empty/null pattern or substitution returns empty
    if regex is None or substitution is None:
        return []
    # Empty regex pattern returns original unchanged
    if regex == "":
        return [value]
    try:
        return [re.sub(regex, substitution, value)]
    except re.error:
        return [value]


@FunctionRegistry.register("length")
def fn_length(ctx: EvaluationContext, collection: list[Any]) -> list[int]:
    """Returns the length of the string."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [len(value)]


@FunctionRegistry.register("substring")
def fn_substring(ctx: EvaluationContext, collection: list[Any], start: int, length: int | None = None) -> list[str]:
    """Returns a substring starting at start index.

    Per FHIRPath spec:
    - If start >= length of string, returns empty
    - If start < 0, it's treated as 0
    - If start + length goes past end of string, only returns what's there
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    start = int(start)
    # If start is negative or beyond the string length, return empty
    if start < 0 or start >= len(value):
        return []
    if length is not None:
        length = int(length)
        result = value[start : start + length]
    else:
        result = value[start:]
    return [result]


@FunctionRegistry.register("upper")
def fn_upper(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Returns the string in uppercase."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.upper()]


@FunctionRegistry.register("lower")
def fn_lower(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Returns the string in lowercase."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.lower()]


@FunctionRegistry.register("trim")
def fn_trim(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Returns the string with whitespace trimmed."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.strip()]


@FunctionRegistry.register("split")
def fn_split(ctx: EvaluationContext, collection: list[Any], separator: str) -> list[str]:
    """Splits the string by separator."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return value.split(separator)


@FunctionRegistry.register("join")
def fn_join(ctx: EvaluationContext, collection: list[Any], separator: str = "") -> list[str]:
    """Joins collection elements with separator."""
    if not collection:
        return []
    strings = [str(_unwrap_value(item)) for item in collection if item is not None]
    return [separator.join(strings)]


@FunctionRegistry.register("indexOf")
def fn_index_of(ctx: EvaluationContext, collection: list[Any], substring: str | None) -> list[int]:
    """Returns the index of substring, or -1 if not found.

    Per FHIRPath spec: if substring is empty, returns empty.
    """
    if not collection:
        return []
    # If substring is None/empty, return empty
    if substring is None:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return [value.find(substring)]


@FunctionRegistry.register("toChars")
def fn_to_chars(ctx: EvaluationContext, collection: list[Any]) -> list[str]:
    """Converts string to list of characters."""
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []
    return list(value)


@FunctionRegistry.register("encode")
def fn_encode(ctx: EvaluationContext, collection: list[Any], encoding: str) -> list[str]:
    """Encodes the string using the specified encoding.

    Supported encodings: 'base64', 'urlbase64', 'hex'
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []

    encoding = encoding.lower()
    data = value.encode("utf-8")

    if encoding == "base64":
        return [base64.b64encode(data).decode("ascii")]
    elif encoding == "urlbase64":
        return [base64.urlsafe_b64encode(data).decode("ascii")]
    elif encoding == "hex":
        return [data.hex()]
    else:
        return []


@FunctionRegistry.register("decode")
def fn_decode(ctx: EvaluationContext, collection: list[Any], encoding: str) -> list[str]:
    """Decodes the string using the specified encoding.

    Supported encodings: 'base64', 'urlbase64', 'hex'
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []

    encoding = encoding.lower()

    try:
        if encoding == "base64":
            return [base64.b64decode(value).decode("utf-8")]
        elif encoding == "urlbase64":
            return [base64.urlsafe_b64decode(value).decode("utf-8")]
        elif encoding == "hex":
            return [bytes.fromhex(value).decode("utf-8")]
        else:
            return []
    except Exception:
        return []


@FunctionRegistry.register("escape")
def fn_escape(ctx: EvaluationContext, collection: list[Any], mode: str) -> list[str]:
    """Escapes the string using the specified mode.

    Supported modes: 'html', 'json'
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []

    mode = mode.lower()

    if mode == "html":
        return [html.escape(value)]
    elif mode == "json":
        # JSON escape: escape quotes and backslashes
        escaped = json.dumps(value)
        # Remove the surrounding quotes from json.dumps output
        return [escaped[1:-1]]
    else:
        return []


@FunctionRegistry.register("unescape")
def fn_unescape(ctx: EvaluationContext, collection: list[Any], mode: str) -> list[str]:
    """Unescapes the string using the specified mode.

    Supported modes: 'html', 'json'
    """
    if not collection:
        return []
    value = _unwrap_value(collection[0])
    if not isinstance(value, str):
        return []

    mode = mode.lower()

    try:
        if mode == "html":
            return [html.unescape(value)]
        elif mode == "json":
            # JSON unescape: parse as JSON string
            return [json.loads(f'"{value}"')]
        else:
            return []
    except Exception:
        return []
