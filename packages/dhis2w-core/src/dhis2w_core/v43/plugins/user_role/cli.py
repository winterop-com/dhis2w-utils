"""Typer sub-app for the `user-role` plugin (mounted under `d2w user-role`)."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import (
    ColumnSpec,
    DetailRow,
    format_reflist,
    is_json_output,
    render_detail,
    render_list,
)

app = typer.Typer(
    help="Inspect + administer DHIS2 user roles (list, authority-list, grant/revoke users).",
    no_args_is_help=True,
)

_DEFAULT_FIELDS = "id,name,displayName,authorities,users"


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    fields: Annotated[str, typer.Option("--fields", help="DHIS2 field selector.")] = _DEFAULT_FIELDS,
    filters: Annotated[list[str] | None, typer.Option("--filter", help="Filter (repeatable).")] = None,
    order: Annotated[list[str] | None, typer.Option("--order", help="Sort clause (repeatable).")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Server-side page size.")] = None,
) -> None:
    """List user roles."""
    from dhis2w_core.v43.plugins.user_role import service

    roles = asyncio.run(
        service.list_user_roles(
            profile_from_env(),
            fields=fields,
            filters=filters,
            order=order,
            page_size=page_size,
        )
    )
    dumped = [r.model_dump(by_alias=True, exclude_none=True, mode="json") for r in roles]
    if is_json_output():
        typer.echo(json.dumps(dumped, indent=2))
        return
    render_list(
        "user roles",
        dumped,
        [
            ColumnSpec("id", "id", style="cyan", no_wrap=True),
            ColumnSpec("name", "displayName"),
            ColumnSpec("authorities", "authorities", formatter=lambda v: str(len(v or []))),
            ColumnSpec("users", "users", formatter=lambda v: str(len(v or []))),
        ],
    )


@app.command("get")
def get_command(
    uid: Annotated[str, typer.Argument(help="User-role UID.")],
    fields: Annotated[str | None, typer.Option("--fields", help="DHIS2 field selector.")] = None,
) -> None:
    """Fetch one user role by UID. Prints a concise summary; `--json` for full payload."""
    from dhis2w_core.v43.plugins.user_role import service

    role = asyncio.run(service.get_user_role(profile_from_env(), uid, fields=fields))
    if is_json_output():
        typer.echo(role.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    authorities = role.authorities or []
    users = role.users or []
    preview = ", ".join(sorted(authorities)[:10])
    auths_cell = (
        preview
        + (
            f" [dim]+{len(authorities) - 10} more (run `d2w user-role authority-list {role.id}` for all)[/dim]"
            if len(authorities) > 10
            else ""
        )
        if authorities
        else "-"
    )
    rows = [
        DetailRow("id", str(role.id or "-")),
        DetailRow("name", str(role.name or "-")),
        DetailRow("displayName", str(role.displayName or "-")),
        DetailRow("code", str(role.code or "-")),
        DetailRow("description", str(role.description or "-")),
        DetailRow(f"authorities ({len(authorities)})", auths_cell),
        DetailRow(f"users ({len(users)})", format_reflist(users)),
    ]
    render_detail(f"user-role {role.name or role.id or '?'}", rows)


@app.command("authority-list")
def authority_list_command(
    uid: Annotated[str, typer.Argument(help="User-role UID.")],
) -> None:
    """Print the sorted authorities carried by one role, one per line."""
    from dhis2w_core.v43.plugins.user_role import service

    auths = asyncio.run(service.list_authorities(profile_from_env(), uid))
    for auth in auths:
        typer.echo(auth)


@app.command("add-user")
def add_user_command(
    role_uid: Annotated[str, typer.Argument(help="User-role UID.")],
    user_uid: Annotated[str, typer.Argument(help="User UID to grant the role to.")],
) -> None:
    """Grant a user a role (POST /api/userRoles/<rid>/users/<uid>)."""
    from dhis2w_core.v43.plugins.user_role import service

    envelope = asyncio.run(service.add_user(profile_from_env(), role_uid, user_uid))
    typer.echo(f"granted role {role_uid} to {user_uid}: {envelope.httpStatus or envelope.status or 'OK'}")


@app.command("remove-user")
def remove_user_command(
    role_uid: Annotated[str, typer.Argument(help="User-role UID.")],
    user_uid: Annotated[str, typer.Argument(help="User UID to revoke the role from.")],
) -> None:
    """Revoke a role from a user (DELETE /api/userRoles/<rid>/users/<uid>)."""
    from dhis2w_core.v43.plugins.user_role import service

    envelope = asyncio.run(service.remove_user(profile_from_env(), role_uid, user_uid))
    typer.echo(f"revoked role {role_uid} from {user_uid}: {envelope.httpStatus or envelope.status or 'OK'}")


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w user-role`."""
    root_app.add_typer(app, name="user-role", help="DHIS2 user-role administration.")
