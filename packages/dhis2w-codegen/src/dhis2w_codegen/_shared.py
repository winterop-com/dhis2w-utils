"""Helpers shared between the /api/schemas emitter and the OpenAPI emitter."""

from __future__ import annotations

import contextlib
import keyword
import subprocess
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape


def python_string_literal(value: object) -> str:
    """Serialise `value` as Python source for a string literal, escaping via `repr`."""
    return repr(str(value))


def docstring_body(value: object) -> str:
    """Escape text so it is safe between the `\"\"\"` delimiters of a generated docstring."""
    text = str(value).replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if text.endswith('"'):
        text = f'{text[:-1]}\\"'
    return text


def build_template_environment() -> Environment:
    """Build the Jinja environment shared by the schemas emitter and the OpenAPI emitter.

    `trim_blocks` / `lstrip_blocks` keep `{% ... %}` control tags from leaving
    blank lines behind, which is what makes rebuilds byte-deterministic.
    """
    environment = Environment(
        loader=PackageLoader("dhis2w_codegen", "templates"),
        autoescape=select_autoescape(default=False),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["python_string_literal"] = python_string_literal
    environment.filters["docstring_body"] = docstring_body
    return environment


def sanitize_identifier(wire_name: str) -> tuple[str, str | None]:
    """Return `(python_name, alias_or_none)` for a wire field name.

    Pydantic keyword collisions (`from`, `class`, etc.) take a `_` suffix plus
    `Field(alias=...)` so the wire form still serialises.
    """
    if not wire_name:
        return wire_name, None
    if keyword.iskeyword(wire_name):
        return f"{wire_name}_", wire_name
    return wire_name, None


def format_output(output_dir: Path) -> None:
    """Run `ruff check --fix` then `ruff format` on the emitted files (best-effort).

    Selects `I` (import sort), `W` (whitespace), and `B033` (duplicate-value
    in set literal) — the last catches the `_submodule_names` duplicates
    multi-class modules would otherwise produce if the emitter forgets to
    dedupe. Avoid `F` — `ruff` flags `Any` as unused import when annotations
    are stringified via `from __future__ import annotations`, even though
    pydantic still evaluates them at model-schema time.
    """
    with contextlib.suppress(FileNotFoundError):
        subprocess.run(
            ["ruff", "check", "--fix", "--select", "I,W,B033", str(output_dir)],
            check=False,
            capture_output=True,
        )
        subprocess.run(["ruff", "format", str(output_dir)], check=False, capture_output=True)
