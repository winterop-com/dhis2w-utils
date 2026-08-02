"""Slug, escaping, and URI helpers shared by every component: FSH names, ids, codes, and string literals."""

from __future__ import annotations

import re


def strip_trailing_slash(value: str) -> str:
    """Drop trailing slashes - SUSHI and the IG publisher append path segments to the canonical."""
    return value.rstrip("/")


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
# R4 `code` (https://hl7.org/fhir/R4/datatypes.html#primitive): the prose constraint is stricter
# than the published regex - no whitespace other than SINGLE SPACES in the contents.
_FHIR_CODE_PATTERN = re.compile(r"^[^\s]+( [^\s]+)*$")
# R4 `id`: [A-Za-z0-9\-\.]{1,64}
_FHIR_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-\.]{1,64}$")


def pascal(value: str, fallback: str = "Generated") -> str:
    """Collapse free text into a PascalCase FSH name (never empty, never digit-leading)."""
    parts = _TOKEN_PATTERN.findall(value or "")
    text = "".join(part[:1].upper() + part[1:] for part in parts)
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"{fallback}{text}"
    return text


def kebab(value: str, fallback: str = "generated") -> str:
    """Collapse free text into a kebab-case slug for FSH ids and file names."""
    parts = _TOKEN_PATTERN.findall(value or "")
    return "-".join(part.lower() for part in parts) or fallback


def escape_fsh_string(value: str) -> str:
    r"""Escape the two characters a double-quoted FSH string literal cannot carry raw: `\` and `"`."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def quote(value: str) -> str:
    """Render a double-quoted FSH string literal, escaping backslashes/quotes and flattening newlines."""
    flattened = " ".join((value or "").split())
    return f'"{escape_fsh_string(flattened)}"'


def fsh_code(value: str) -> str:
    """Render a `#code` token, using the escaped, quoted `#"..."` form when the code contains spaces."""
    return f'#"{escape_fsh_string(value)}"' if " " in value else f"#{value}"


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def join_id_tokens(*tokens: str) -> str:
    """Join non-empty naming tokens into a FHIR id fragment, splitting camel case (`OrgUnit` -> `org-unit`)."""
    return "-".join(_CAMEL_BOUNDARY.sub("-", token).lower() for token in tokens if token)


def join_name_segments(*segments: str) -> str:
    """Join non-empty FSH name segments with underscores (`D2OS` + `BirthType` -> `D2OS_BirthType`).

    Dropping the empty segments is what keeps a name cnl-0 valid when a naming token is
    configured empty: an absent prefix yields `BirthType`, never a leading `_BirthType`.
    """
    return "_".join(segment for segment in segments if segment)


def is_valid_fhir_code(value: str | None) -> bool:
    """Check `value` against the R4 `code` datatype: non-empty, single internal spaces only."""
    return bool(value) and _FHIR_CODE_PATTERN.match(value or "") is not None


def describe_code_defect(code: str) -> str | None:
    r"""Name the first R4 `code` defect the value carries, or None when it is a valid code.

    The checks run in a fixed order, so a code carrying several defects reports the one that
    explains the invisible character best: a line break beats the leading space it sits behind.
    A code that is invalid for whitespace outside this list (a form feed, a non-breaking space)
    falls through to the generic phrase.
    """
    if is_valid_fhir_code(code):
        return None
    if not code:
        return "code is empty"
    if "\n" in code or "\r" in code:
        return "code contains a line break"
    if "\t" in code:
        return "code contains a tab"
    if code != code.lstrip():
        return "code has leading whitespace"
    if code != code.rstrip():
        return "code has trailing whitespace"
    if "  " in code:
        return "code contains consecutive spaces"
    return "code contains whitespace"


def is_valid_fhir_id(value: str) -> bool:
    """Check `value` against the R4 `id` datatype: ASCII letters/digits/hyphen/dot, 1-64 characters."""
    return _FHIR_ID_PATTERN.match(value) is not None


def code_or_uid(code: str | None, uid: str) -> str:
    """The DHIS2 code when it is a usable FHIR code, else the UID.

    Every generated artifact exposes both DHIS2 identifiers, so the code slot is never empty:
    until an instance carries a real code on every object, the code slot repeats the UID.
    """
    return code if code is not None and is_valid_fhir_code(code) else uid
