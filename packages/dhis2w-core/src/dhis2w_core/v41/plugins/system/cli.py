"""Typer sub-app for the `system` plugin (mounted under `dhis2 system`)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_client.v41 import DhisCalendar, DisplayRef

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import DetailRow, is_json_output, render_detail
from dhis2w_core.v41.plugins.system import service

app = typer.Typer(help="DHIS2 system info and current-user access.", no_args_is_help=True)


def _format_refs(refs: list[DisplayRef] | None) -> str:
    """Render a ref list as `name (uid)` entries, joined by commas; `(none)` when empty."""
    items = refs or []
    if not items:
        return "(none)"
    return ", ".join(f"{ref.displayName} ({ref.id})" if ref.displayName else (ref.id or "?") for ref in items)


@app.command("whoami")
def whoami_command() -> None:
    """Print the authenticated DHIS2 user for the current environment profile."""
    me = asyncio.run(service.whoami(profile_from_env()))
    if is_json_output():
        typer.echo(me.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    authorities = me.authorities or []
    superuser = "  (incl. ALL — superuser)" if "ALL" in authorities else ""
    rows = [
        DetailRow("username", me.username or "-"),
        DetailRow("displayName", me.displayName or "-"),
        DetailRow("email", me.email or "-"),
        DetailRow("id", me.id or "-"),
        DetailRow("last login", me.lastLogin or "-"),
        DetailRow("authorities", f"{len(authorities)}{superuser}"),
        DetailRow("roles", _format_refs(me.userRoles)),
        DetailRow("groups", _format_refs(me.userGroups)),
        DetailRow("org units", _format_refs(me.organisationUnits)),
    ]
    render_detail(f"whoami — {me.username or '?'}", rows)


@app.command("info")
def info_command() -> None:
    """Print DHIS2 system info (version, build, analytics state, env)."""
    info = asyncio.run(service.system_info(profile_from_env()))
    if is_json_output():
        typer.echo(info.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    rows = [
        DetailRow("version", str(info.version or "-")),
        DetailRow("revision", str(info.revision or "-")),
        DetailRow("systemName", str(info.systemName or "-")),
        DetailRow("systemId", str(info.systemId or "-")),
        DetailRow("serverDate", str(info.serverDate or "-")),
        DetailRow("buildTime", str(info.buildTime or "-")),
        DetailRow("calendar", str(info.calendar or "-")),
        DetailRow("dateFormat", str(info.dateFormat or "-")),
        DetailRow("instanceBaseUrl", str(getattr(info, "instanceBaseUrl", None) or "-")),
        DetailRow("contextPath", str(info.contextPath or "-")),
        DetailRow("environment", str(getattr(info, "environmentVariable", None) or "-")),
        DetailRow("lastAnalyticsSuccess", str(getattr(info, "lastAnalyticsTableSuccess", None) or "-")),
        DetailRow("lastAnalyticsRuntime", str(getattr(info, "lastAnalyticsTableRuntime", None) or "-")),
        DetailRow("javaVersion", str(getattr(info, "javaVersion", None) or "-")),
        DetailRow("cpuCores", str(getattr(info, "cpuCores", None) or "-")),
    ]
    render_detail(f"system info — {info.systemName or info.systemId or '?'}", rows)


@app.command("calendar")
def calendar_command(
    value: Annotated[
        DhisCalendar | None,
        typer.Argument(
            help="When supplied, write `keyCalendar` (one of: coptic, ethiopian, "
            "gregorian, islamic, iso8601, julian, nepali, persian, thai). "
            "Omit to print the current calendar.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip the interactive confirmation. Required for non-interactive callers (CI, scripts).",
        ),
    ] = False,
) -> None:
    """Print the active DHIS2 calendar, or change it when a value is supplied.

    `keyCalendar` is the system-wide calendar DHIS2 uses to interpret periods.
    The default is `iso8601`. Changing it is rare and risky — most instances
    pick a calendar at deploy time and never touch it again. Switching the
    calendar after data collection has started can leave existing periods
    unreadable and break analytics, so this command requires interactive
    confirmation (or `--yes`).
    """
    profile = profile_from_env()
    if value is None:
        current = asyncio.run(service.get_calendar(profile))
        typer.echo(current)
        return
    current = asyncio.run(service.get_calendar(profile))
    if current == value.value:
        typer.echo(f"keyCalendar already {value.value}")
        return
    if not yes:
        typer.echo(f"Current calendar: {current}")
        typer.echo(f"New calendar:     {value.value}")
        typer.echo(
            "WARNING: only change the calendar when it is genuinely required. "
            "If data collection has already started on this instance, switching "
            "the calendar can leave existing periods unreadable and break "
            "analytics. Confirm only after taking a backup."
        )
        if not typer.confirm("Change calendar?", default=False):
            typer.echo("Aborted — keyCalendar unchanged.")
            raise typer.Exit(code=1)
    asyncio.run(service.set_calendar(profile, value))
    typer.echo(f"keyCalendar set to {value.value} (was {current})")


settings_app = typer.Typer(help="Read/write DHIS2 system settings.", no_args_is_help=True)
app.add_typer(settings_app, name="settings")


@settings_app.command("set")
def settings_set_command(
    key: Annotated[str, typer.Argument(help="System setting key (e.g. applicationTitle, keyApplicationFooter).")],
    value: Annotated[str, typer.Argument(help="New value.")],
) -> None:
    """Set a single system setting."""
    asyncio.run(service.set_system_setting(profile_from_env(), key, value))
    typer.echo(f"set {key}")


@settings_app.command("set-many")
def settings_set_many_command(
    file: Annotated[Path, typer.Argument(help="JSON file containing a {key: value} object.")],
) -> None:
    """Bulk-set system settings from a JSON file."""
    loaded: Any = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise typer.BadParameter(f"{file} must contain a {{key: value}} object")
    applied = asyncio.run(service.set_system_settings(profile_from_env(), {str(k): str(v) for k, v in loaded.items()}))
    for key in applied:
        typer.echo(f"set {key}")


@settings_app.command("get")
def settings_get_command(
    key: Annotated[str, typer.Argument(help="System setting key (e.g. applicationTitle).")],
) -> None:
    """Print one system setting's value; exit 1 if it is unset."""
    value = asyncio.run(service.get_setting(profile_from_env(), key))
    if value is None:
        typer.echo(f"{key} is not set", err=True)
        raise typer.Exit(code=1)
    typer.echo(value)


@settings_app.command("list")
@settings_app.command("ls", hidden=True)
def settings_list_command() -> None:
    """List every system setting (key = value)."""
    snapshot = asyncio.run(service.list_settings(profile_from_env()))
    if is_json_output():
        typer.echo(snapshot.model_dump_json(indent=2))
        return
    for key, value in snapshot.pairs():
        typer.echo(f"{key} = {value}")


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `dhis2 system`."""
    root_app.add_typer(app, name="system", help="DHIS2 system info.")
