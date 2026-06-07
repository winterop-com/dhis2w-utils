"""Typer sub-app for the `user` plugin (mounted under `dhis2 user`)."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import (
    ColumnSpec,
    DetailRow,
    format_disabled,
    format_reflist,
    is_json_output,
    render_detail,
    render_list,
)
from dhis2w_core.v43.plugins.user import service
from dhis2w_core.v43.plugins.user.service import UserInvite, UserNotFoundError

app = typer.Typer(help="Inspect + administer DHIS2 users (list, get, invite, reset-password).", no_args_is_help=True)

_DEFAULT_FIELDS = "id,username,displayName,email,disabled,lastLogin"


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    fields: Annotated[
        str,
        typer.Option(
            "--fields",
            help=(
                "DHIS2 field selector. Supports plain lists ('id,username,email'), presets "
                "(':identifiable', ':nameable', ':owner', ':all'), and exclusions (':all,!password')."
            ),
        ),
    ] = _DEFAULT_FIELDS,
    filters: Annotated[
        list[str] | None,
        typer.Option("--filter", help="Filter 'property:operator:value' (repeatable)."),
    ] = None,
    root_junction: Annotated[
        str,
        typer.Option("--root-junction", help="Combine repeated --filter as AND (default) or OR."),
    ] = "AND",
    order: Annotated[
        list[str] | None,
        typer.Option("--order", help="Sort clause 'property:asc|desc' (repeatable)."),
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="Server-side page number (1-based).")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Server-side page size (default 50).")] = None,
) -> None:
    """List users.

    Examples:
      dhis2 user list
      dhis2 user list --filter 'disabled:eq:true' --order 'username:asc'
      dhis2 user list --filter 'username:like:admin'
    """
    rj = root_junction if filters and len(filters) > 1 else None
    users = asyncio.run(
        service.list_users(
            profile_from_env(),
            fields=fields,
            filters=filters,
            root_junction=rj,
            order=order,
            page=page,
            page_size=page_size,
        )
    )
    dumped = [u.model_dump(by_alias=True, exclude_none=True, mode="json") for u in users]
    if is_json_output():
        typer.echo(json.dumps(dumped, indent=2))
        return
    render_list(
        "users",
        dumped,
        [
            ColumnSpec("id", "id", style="cyan", no_wrap=True),
            ColumnSpec("username", "username", formatter=lambda v: str(v or "-")),
            ColumnSpec("name", "displayName", formatter=lambda v: str(v or "-")),
            ColumnSpec("email", "email", formatter=lambda v: str(v or "-")),
            ColumnSpec("disabled", "disabled", formatter=format_disabled),
            ColumnSpec("lastLogin", "lastLogin", formatter=lambda v: str(v or "-"), style="dim"),
        ],
    )


@app.command("get")
def get_command(
    uid_or_username: Annotated[str, typer.Argument(help="User UID (11 chars) or username.")],
    fields: Annotated[str | None, typer.Option("--fields", help="DHIS2 field selector.")] = None,
) -> None:
    """Fetch one user by UID or username. Prints a concise summary; `--json` for full payload."""
    try:
        user = asyncio.run(service.get_user(profile_from_env(), uid_or_username, fields=fields))
    except UserNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if is_json_output():
        typer.echo(user.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    full_name = user.displayName or f"{user.firstName or ''} {user.surname or ''}".strip() or "-"
    authorities = getattr(user, "authorities", None) or []
    rows = [
        DetailRow("id", str(user.id or "-")),
        DetailRow("username", str(user.username or "-")),
        DetailRow("name", full_name),
        DetailRow("email", str(user.email or "-")),
        DetailRow("disabled", format_disabled(user.disabled)),
        DetailRow("lastLogin", str(user.lastLogin or "-")),
        DetailRow("created", str(user.created or "-")),
        DetailRow("twoFactor", str(getattr(user, "twoFactorType", None) or "-")),
        DetailRow(f"userRoles ({len(user.userRoles or [])})", format_reflist(user.userRoles or [])),
        DetailRow(f"userGroups ({len(user.userGroups or [])})", format_reflist(user.userGroups or [])),
        DetailRow(
            f"organisationUnits ({len(user.organisationUnits or [])})",
            format_reflist(user.organisationUnits or []),
        ),
        DetailRow(
            f"authorities ({len(authorities)})",
            _authorities_preview(authorities, hint_cmd=f"dhis2 --json user get {user.username or user.id}"),
        ),
    ]
    render_detail(f"user {user.username or user.id or '?'}", rows)


@app.command("invite")
def invite_command(
    email: Annotated[str, typer.Argument(help="Email address for the new user (receives the invitation link).")],
    first_name: Annotated[str, typer.Option("--first-name", help="User's given name.")],
    surname: Annotated[str, typer.Option("--surname", help="User's surname.")],
    username: Annotated[
        str | None,
        typer.Option(
            "--username",
            help="Desired username. Omit to let DHIS2 derive from the email prefix.",
        ),
    ] = None,
    user_role: Annotated[
        list[str] | None,
        typer.Option("--user-role", help="User-role UID (repeatable). Grants the role on accept."),
    ] = None,
    org_unit: Annotated[
        list[str] | None,
        typer.Option("--org-unit", "--ou", help="Organisation-unit UID for capture scope (repeatable)."),
    ] = None,
) -> None:
    """Create a user and send the invitation email.

    Hits POST /api/users/invite. DHIS2's configured mailer sends the link;
    the new user sets their password on accept. Prints the new user's UID.
    """
    invite = UserInvite(
        email=email,
        firstName=first_name,
        surname=surname,
        username=username,
        userRoles=[{"id": uid} for uid in (user_role or [])],
        organisationUnits=[{"id": uid} for uid in (org_unit or [])],
    )
    envelope = asyncio.run(service.invite_user(profile_from_env(), invite))
    created = envelope.created_uid
    if created:
        typer.echo(f"invited {email} -> user {created}")
    else:
        typer.echo(envelope.model_dump_json(indent=2, exclude_none=True, by_alias=True))


@app.command("reinvite")
def reinvite_command(
    uid: Annotated[str, typer.Argument(help="UID of a user who hasn't yet completed their invite.")],
) -> None:
    """Re-send the invitation email for a pending user (POST /api/users/{uid}/invite)."""
    envelope = asyncio.run(service.reinvite_user(profile_from_env(), uid))
    status = envelope.httpStatus or envelope.status or "OK"
    typer.echo(f"reinvite queued for {uid}: {status}")


@app.command("reset-password")
def reset_password_command(
    uid: Annotated[str, typer.Argument(help="UID of the user to reset.")],
) -> None:
    """Trigger DHIS2's password-reset email (POST /api/users/{uid}/reset)."""
    envelope = asyncio.run(service.reset_password(profile_from_env(), uid))
    status = envelope.httpStatus or envelope.status or "OK"
    typer.echo(f"reset link mailed for {uid}: {status}")


def _authorities_preview(authorities: list[str], *, hint_cmd: str, limit: int = 10) -> str:
    """Render the authorities list as a comma-separated preview + overflow hint."""
    if not authorities:
        return "-"
    sorted_auths = sorted(authorities)
    preview = ", ".join(sorted_auths[:limit])
    if len(sorted_auths) > limit:
        preview += f" [dim]+{len(sorted_auths) - limit} more (run `{hint_cmd}` for all)[/dim]"
    return preview


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `dhis2 user`."""
    root_app.add_typer(app, name="user", help="DHIS2 user administration.")
