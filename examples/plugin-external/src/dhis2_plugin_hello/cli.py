"""Typer sub-app mounted as `d2w hello`."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer
from dhis2w_core.profile import profile_from_env

from dhis2_plugin_hello import service

app = typer.Typer(help="External plugin example — greet the authenticated DHIS2 user.", no_args_is_help=True)


@app.command("say")
def say_command(
    greeting: Annotated[str, typer.Option("--greeting", help="Prefix the name with this.")] = "Hello",
) -> None:
    """Call /api/me and print a greeting with the user's displayName."""
    message = asyncio.run(service.greet(profile_from_env(), greeting=greeting))
    typer.echo(message)


def register(root_app: Any) -> None:
    """Mount under `d2w hello` — called by dhis2w-core's plugin loader."""
    root_app.add_typer(app, name="hello", help="External plugin example.")
