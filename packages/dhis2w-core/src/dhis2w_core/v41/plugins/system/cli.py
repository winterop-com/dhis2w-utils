"""Typer sub-app for the `system` plugin (mounted under `d2w system`)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer

# DhisCalendar stays at module scope: a Typer enum param annotation on the calendar
# command, which Typer resolves at command-registration time (import) — not deferrable.
from dhis2w_client.v41 import DhisCalendar

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import DetailRow, is_json_output, render_detail

app = typer.Typer(help="DHIS2 system info and current-user access.", no_args_is_help=True)


_WHOAMI_HIDE = frozenset(
    {"access", "sharing", "href", "translations", "favorites", "favorite", "name", "attributeValues", "user"}
)
_WHOAMI_LABELS = {
    "displayName": "display name",
    "firstName": "first name",
    "lastLogin": "last login",
    "lastUpdated": "last updated",
    "passwordLastUpdated": "password set",
    "organisationUnits": "org units",
    "dataViewOrganisationUnits": "data-view OUs",
    "teiSearchOrganisationUnits": "TEI-search OUs",
    "userRoles": "roles",
    "userGroups": "groups",
    "twoFactorType": "2FA",
    "externalAuth": "external auth",
    "emailVerified": "email verified",
    "selfRegistered": "self-registered",
    "createdBy": "created by",
    "lastUpdatedBy": "updated by",
    "catDimensionConstraints": "category constraints",
    "cogsDimensionConstraints": "cat-option-group constraints",
}


def _ref_label(item: dict[str, Any]) -> str:
    """Render a single ref as `name (uid)`, or just the uid / name when one is missing."""
    name = item.get("displayName") or item.get("name")
    uid = item.get("id")
    if name and uid:
        return f"{name} ({uid})"
    return str(uid or name or item)


def _whoami_value(value: Any) -> str:
    """Render one /api/me value for the table: refs as `name (uid)`, lists joined, scalars as text."""
    if isinstance(value, list):
        if not value:
            return "(none)"
        if isinstance(value[0], dict):
            return ", ".join(_ref_label(item) for item in value)
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return _ref_label(value)
    return str(value)


@app.command("whoami")
def whoami_command() -> None:
    """Expose everything DHIS2 reports about the authenticated user. `--json` for the raw object."""
    from dhis2w_core.v41.plugins.system import service

    me = asyncio.run(service.whoami(profile_from_env()))
    if is_json_output():
        typer.echo(me.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        return
    data = me.model_dump(exclude_none=True)
    authorities = data.get("authorities") or []
    superuser = "  (incl. ALL — superuser)" if "ALL" in authorities else ""
    rows: list[DetailRow] = []
    for key, value in data.items():
        if key in _WHOAMI_HIDE:
            continue
        rendered = f"{len(authorities)}{superuser}" if key == "authorities" else _whoami_value(value)
        rows.append(DetailRow(_WHOAMI_LABELS.get(key, key), rendered))
    render_detail(f"whoami — {me.username or '?'}", rows)
    if authorities:
        typer.echo(f"\nauthorities ({len(authorities)}):")
        typer.echo("  " + ", ".join(sorted(authorities)))


@app.command("info")
def info_command() -> None:
    """Print DHIS2 system info (version, build, analytics state, env)."""
    from dhis2w_core.v41.plugins.system import service

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
    from dhis2w_core.v41.plugins.system import service

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
    from dhis2w_core.v41.plugins.system import service

    asyncio.run(service.set_system_setting(profile_from_env(), key, value))
    typer.echo(f"set {key}")


@settings_app.command("set-many")
def settings_set_many_command(
    file: Annotated[Path, typer.Argument(help="JSON file containing a {key: value} object.")],
) -> None:
    """Bulk-set system settings from a JSON file."""
    from dhis2w_core.v41.plugins.system import service

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
    from dhis2w_core.v41.plugins.system import service

    value = asyncio.run(service.get_setting(profile_from_env(), key))
    if value is None:
        typer.echo(f"{key} is not set", err=True)
        raise typer.Exit(code=1)
    typer.echo(value)


@settings_app.command("list")
@settings_app.command("ls", hidden=True)
def settings_list_command() -> None:
    """List every system setting (key = value)."""
    from dhis2w_core.v41.plugins.system import service

    snapshot = asyncio.run(service.list_settings(profile_from_env()))
    if is_json_output():
        typer.echo(snapshot.model_dump_json(indent=2))
        return
    for key, value in snapshot.pairs():
        typer.echo(f"{key} = {value}")


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w system`."""
    root_app.add_typer(app, name="system", help="DHIS2 system info.")
