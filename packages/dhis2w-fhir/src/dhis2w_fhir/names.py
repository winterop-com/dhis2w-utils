"""Slug and escaping helpers for FSH names, ids, codes, and string literals."""

from __future__ import annotations

import re

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


def quote(value: str) -> str:
    """Render a double-quoted FSH string literal, escaping backslashes/quotes and flattening newlines."""
    flattened = " ".join((value or "").split())
    return '"' + flattened.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fsh_code(value: str) -> str:
    """Render a `#code` token, using the quoted `#"..."` form when the code contains spaces."""
    return f'#"{value}"' if " " in value else f"#{value}"


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def join_id_tokens(*tokens: str) -> str:
    """Join non-empty naming tokens into a FHIR id fragment, splitting camel case (`OrgUnit` -> `org-unit`)."""
    return "-".join(_CAMEL_BOUNDARY.sub("-", token).lower() for token in tokens if token)


def is_valid_fhir_code(value: str | None) -> bool:
    """Check `value` against the R4 `code` datatype: non-empty, single internal spaces only."""
    return bool(value) and _FHIR_CODE_PATTERN.match(value or "") is not None


def is_valid_fhir_id(value: str) -> bool:
    """Check `value` against the R4 `id` datatype: ASCII letters/digits/hyphen/dot, 1-64 characters."""
    return _FHIR_ID_PATTERN.match(value) is not None
