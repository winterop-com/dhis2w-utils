"""Typer sub-app for the `datastore` plugin (mounted under `dhis2 datastore`)."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import is_json_output
from dhis2w_core.v43.plugins.datastore import service

app = typer.Typer(
    help="DHIS2 key-value data store (/api/dataStore + per-user /api/userDataStore).",
    no_args_is_help=True,
)

_UserOpt = Annotated[
    bool,
    typer.Option("--user", help="Target the per-user store (/api/userDataStore) instead of the shared one."),
]
_YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="Skip the interactive confirmation.")]


@app.command("namespaces")
def namespaces_command(user: _UserOpt = False) -> None:
    """List every namespace in the store."""
    names = asyncio.run(service.list_namespaces(profile_from_env(), user=user))
    if is_json_output():
        typer.echo(json.dumps(names, indent=2))
        return
    for name in names:
        typer.echo(name)


@app.command("keys")
def keys_command(
    namespace: Annotated[str, typer.Argument(help="Namespace to list keys in.")],
    user: _UserOpt = False,
) -> None:
    """List every key in a namespace."""
    keys = asyncio.run(service.list_keys(profile_from_env(), namespace, user=user))
    if is_json_output():
        typer.echo(json.dumps(keys, indent=2))
        return
    for key in keys:
        typer.echo(key)


@app.command("get")
def get_command(
    namespace: Annotated[str, typer.Argument(help="Namespace.")],
    key: Annotated[str, typer.Argument(help="Key.")],
    user: _UserOpt = False,
) -> None:
    """Print the value stored at `namespace/key` (JSON)."""
    value = asyncio.run(service.get_value(profile_from_env(), namespace, key, user=user))
    typer.echo(json.dumps(value, indent=2))


@app.command("set")
def set_command(
    namespace: Annotated[str, typer.Argument(help="Namespace.")],
    key: Annotated[str, typer.Argument(help="Key.")],
    value: Annotated[str, typer.Argument(help="Value — parsed as JSON, or stored as a string if not valid JSON.")],
    user: _UserOpt = False,
) -> None:
    """Create or update `namespace/key`."""
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    asyncio.run(service.set_value(profile_from_env(), namespace, key, parsed, user=user))
    typer.echo(f"set {namespace}/{key}")


@app.command("delete")
def delete_command(
    namespace: Annotated[str, typer.Argument(help="Namespace.")],
    key: Annotated[str, typer.Argument(help="Key.")],
    user: _UserOpt = False,
    yes: _YesOpt = False,
) -> None:
    """Delete `namespace/key`."""
    if not yes and not typer.confirm(f"Delete {namespace}/{key}?", default=False):
        typer.echo("Aborted.")
        raise typer.Exit(code=1)
    asyncio.run(service.delete_key(profile_from_env(), namespace, key, user=user))
    typer.echo(f"deleted {namespace}/{key}")


@app.command("delete-namespace")
def delete_namespace_command(
    namespace: Annotated[str, typer.Argument(help="Namespace to delete (all its keys go with it).")],
    user: _UserOpt = False,
    yes: _YesOpt = False,
) -> None:
    """Delete an entire namespace and every key in it."""
    if not yes and not typer.confirm(f"Delete the whole {namespace!r} namespace?", default=False):
        typer.echo("Aborted.")
        raise typer.Exit(code=1)
    asyncio.run(service.delete_namespace(profile_from_env(), namespace, user=user))
    typer.echo(f"deleted namespace {namespace}")


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `dhis2 datastore`."""
    root_app.add_typer(app, name="datastore", help="DHIS2 key-value data store.")
