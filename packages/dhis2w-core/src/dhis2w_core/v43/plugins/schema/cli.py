"""Root `d2w schema <type>` command — describe a generated type's fields."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import ColumnSpec, is_json_output, render_list
from dhis2w_core.v43.plugins.schema import service

_SOURCES = ("auto", "oas", "schemas")


def schema_command(
    type_name: Annotated[
        str,
        typer.Argument(help="Type name, e.g. dataElement or TrackedEntity (case-insensitive; plural wire names ok)."),
    ],
    source: Annotated[
        str,
        typer.Option(help="Which generated tree to read: auto (prefer oas), oas, or schemas."),
    ] = "auto",
) -> None:
    """Describe a type's fields from the locally generated models (not the server's live schema).

    Only the DHIS2 major is read live (auto-detected via /api/system/info, SNAPSHOT-safe); the field
    shapes come from the generated trees, so the output reflects what this client parses/accepts.
    """
    if source not in _SOURCES:
        raise typer.BadParameter(f"source must be one of {', '.join(_SOURCES)}")
    version = asyncio.run(service.detect_version(profile_from_env()))
    result = service.describe_type(version, type_name, source=source)
    if result is None:
        message = f"unknown type {type_name!r} for {version}"
        candidates = service.search_types(version, type_name)
        if candidates:
            message += f". Did you mean: {', '.join(candidates)}?"
        typer.echo(message, err=True)
        raise typer.Exit(2)
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2))
        return
    render_list(
        f"{result.name} ({result.source}, {result.version})",
        [field.model_dump() for field in result.fields],
        [
            ColumnSpec("field", "name", formatter=str, style="cyan", no_wrap=True),
            ColumnSpec("type", "type", formatter=str),
            ColumnSpec("req", "required", formatter=lambda value: "yes" if value else ""),
            ColumnSpec("description", "description", formatter=lambda value: value or ""),
        ],
    )


def register(root_app: Any) -> None:
    """Mount `schema` as a top-level command on the root CLI."""
    root_app.command(
        "schema",
        help="Describe a generated type's fields (metadata or instance-side; prefers the OpenAPI tree).",
    )(schema_command)
