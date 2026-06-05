"""Typer sub-app for the `user-group` plugin (mounted under `dhis2 user-group`)."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import typer
from dhis2w_client.v43 import ACCESS_READ_METADATA, ACCESS_READ_WRITE_METADATA, SharingBuilder

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import (
    ColumnSpec,
    DetailRow,
    format_access_string,
    format_ref,
    format_reflist,
    is_json_output,
    render_detail,
    render_list,
)
from dhis2w_core.v43.plugins.user_group import service

app = typer.Typer(
    help="Inspect + administer DHIS2 user groups (list, members, sharing).",
    no_args_is_help=True,
)

_DEFAULT_FIELDS = "id,name,displayName,users"


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    fields: Annotated[str, typer.Option("--fields", help="DHIS2 field selector.")] = _DEFAULT_FIELDS,
    filters: Annotated[
        list[str] | None,
        typer.Option("--filter", help="Filter 'property:operator:value' (repeatable)."),
    ] = None,
    order: Annotated[
        list[str] | None,
        typer.Option("--order", help="Sort clause 'property:asc|desc' (repeatable)."),
    ] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Server-side page size.")] = None,
) -> None:
    """List user groups."""
    groups = asyncio.run(
        service.list_user_groups(
            profile_from_env(),
            fields=fields,
            filters=filters,
            order=order,
            page_size=page_size,
        )
    )
    dumped = [g.model_dump(by_alias=True, exclude_none=True, mode="json") for g in groups]
    if is_json_output():
        typer.echo(json.dumps(dumped, indent=2))
        return
    render_list(
        "user groups",
        dumped,
        [
            ColumnSpec("id", "id", style="cyan", no_wrap=True),
            ColumnSpec("name", "displayName"),
            ColumnSpec("members", "users", formatter=lambda v: str(len(v or []))),
        ],
    )


@app.command("get")
def get_command(
    uid: Annotated[str, typer.Argument(help="User-group UID.")],
    fields: Annotated[str | None, typer.Option("--fields", help="DHIS2 field selector.")] = None,
) -> None:
    """Fetch one user group by UID. Prints a concise summary; `--json` for full payload."""
    group = asyncio.run(service.get_user_group(profile_from_env(), uid, fields=fields))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    members = group.users or []
    managed_groups = getattr(group, "managedGroups", None) or []
    managed_by_groups = getattr(group, "managedByGroups", None) or []
    rows = [
        DetailRow("id", str(group.id or "-")),
        DetailRow("name", str(group.name or "-")),
        DetailRow("displayName", str(group.displayName or "-")),
        DetailRow("code", str(group.code or "-")),
        DetailRow("created", str(group.created or "-")),
        DetailRow("lastUpdated", str(group.lastUpdated or "-")),
        DetailRow(f"members ({len(members)})", format_reflist(members)),
    ]
    if managed_groups:
        rows.append(DetailRow(f"managedGroups ({len(managed_groups)})", format_reflist(managed_groups)))
    if managed_by_groups:
        rows.append(DetailRow(f"managedBy ({len(managed_by_groups)})", format_reflist(managed_by_groups)))
    render_detail(f"user-group {group.name or group.id or '?'}", rows)


@app.command("create")
def create_command(
    name: Annotated[str, typer.Option("--name", help="User-group name.")],
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a user group (then add members with `add-member`)."""
    from dhis2w_core.v43.cli_output import render_webmessage  # noqa: PLC0415

    response = asyncio.run(service.create_user_group(profile_from_env(), name=name, code=code, uid=uid))
    render_webmessage(response, action="created")


@app.command("delete")
def delete_command(
    uid: Annotated[str, typer.Argument(help="User-group UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete a user group by UID."""
    if not yes and not typer.confirm(f"Delete userGroup {uid}?"):
        raise typer.Abort()
    asyncio.run(service.delete_user_group(profile_from_env(), uid))
    typer.echo(f"deleted userGroup {uid}")


@app.command("add-member")
def add_member_command(
    group_uid: Annotated[str, typer.Argument(help="User-group UID.")],
    user_uid: Annotated[str, typer.Argument(help="User UID to add.")],
) -> None:
    """Add a user to a group (POST /api/userGroups/<gid>/users/<uid>)."""
    envelope = asyncio.run(service.add_member(profile_from_env(), group_uid, user_uid))
    typer.echo(f"added {user_uid} -> {group_uid}: {envelope.httpStatus or envelope.status or 'OK'}")


@app.command("remove-member")
def remove_member_command(
    group_uid: Annotated[str, typer.Argument(help="User-group UID.")],
    user_uid: Annotated[str, typer.Argument(help="User UID to remove.")],
) -> None:
    """Remove a user from a group (DELETE /api/userGroups/<gid>/users/<uid>)."""
    envelope = asyncio.run(service.remove_member(profile_from_env(), group_uid, user_uid))
    typer.echo(f"removed {user_uid} from {group_uid}: {envelope.httpStatus or envelope.status or 'OK'}")


@app.command("sharing-get")
def sharing_get_command(
    uid: Annotated[str, typer.Argument(help="User-group UID.")],
) -> None:
    """Print the current sharing block for one user group. `--json` for full payload."""
    sharing = asyncio.run(service.get_group_sharing(profile_from_env(), uid))
    if is_json_output():
        typer.echo(sharing.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    user_accesses = sharing.userAccesses or []
    group_accesses = sharing.userGroupAccesses or []
    # v43 dropped the `externalAccess` field on SharingObject.
    rows = [
        DetailRow("id", str(sharing.id or "-")),
        DetailRow("publicAccess", format_access_string(sharing.publicAccess)),
        DetailRow("owner", format_ref(sharing.user) if sharing.user else "-"),
        DetailRow(f"userAccesses ({len(user_accesses)})", "" if user_accesses else "-"),
    ]
    for ua in user_accesses:
        label = ua.displayName or ua.username or ua.name or ua.id or "?"
        rows.append(DetailRow(f"  {label}", f"{format_access_string(ua.access)}  [dim]({ua.id})[/dim]"))
    rows.append(DetailRow(f"userGroupAccesses ({len(group_accesses)})", "" if group_accesses else "-"))
    for ga in group_accesses:
        label = ga.displayName or ga.name or ga.id or "?"
        rows.append(DetailRow(f"  {label}", f"{format_access_string(ga.access)}  [dim]({ga.id})[/dim]"))
    render_detail(f"sharing — userGroup {sharing.name or sharing.id or '?'}", rows)


@app.command("sharing-grant-user")
def sharing_grant_user_command(
    group_uid: Annotated[str, typer.Argument(help="User-group UID.")],
    user_uid: Annotated[str, typer.Argument(help="User UID to grant.")],
    metadata_write: Annotated[
        bool,
        typer.Option("--metadata-write/--metadata-read", help="Grant metadata write (default) or read-only."),
    ] = True,
) -> None:
    """Grant one user access to a group (shortcut over `/api/sharing`).

    Preserves existing userAccesses/userGroupAccesses by fetching the current
    sharing block first, then appending the new grant.
    """
    profile = profile_from_env()
    current = asyncio.run(service.get_group_sharing(profile, group_uid))
    # v43's SharingBuilder doesn't accept external_access (the field was dropped).
    builder = SharingBuilder(
        public_access=current.publicAccess or ACCESS_READ_METADATA,
        owner_user_id=current.user.id if current.user else None,
    )
    for user_access in current.userAccesses or []:
        if user_access.id and user_access.access:
            builder = builder.grant_user(user_access.id, user_access.access)
    for group_access in current.userGroupAccesses or []:
        if group_access.id and group_access.access:
            builder = builder.grant_user_group(group_access.id, group_access.access)
    access = ACCESS_READ_WRITE_METADATA if metadata_write else ACCESS_READ_METADATA
    builder = builder.grant_user(user_uid, access)
    envelope = asyncio.run(service.apply_group_sharing(profile, group_uid, builder))
    typer.echo(f"granted {user_uid}:{access} on {group_uid}: {envelope.httpStatus or envelope.status or 'OK'}")


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `dhis2 user-group`."""
    root_app.add_typer(app, name="user-group", help="DHIS2 user-group administration.")
