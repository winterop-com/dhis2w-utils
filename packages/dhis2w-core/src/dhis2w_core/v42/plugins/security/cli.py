"""Typer sub-app for the `security` plugin (mounted under `dhis2 security`)."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v42.cli_output import DetailRow, format_bool, is_json_output, render_detail
from dhis2w_core.v42.plugins.security import service

app = typer.Typer(
    help="Inspect DHIS2 security posture (password policy, registration, lockout).",
    no_args_is_help=True,
)


def _months(value: int | None) -> str:
    """Render a credentials-expiry month count, calling out the never-expire default."""
    if value is None:
        return "-"
    return "0 (never)" if value == 0 else f"{value} months"


def _number(value: int | None) -> str:
    """Render an int setting, or a dash when the server didn't return it."""
    return "-" if value is None else str(value)


def _flag(value: bool | None) -> str:
    """Render a security toggle as enabled/disabled."""
    return format_bool(value, true_label="enabled", false_label="disabled")


@app.command("settings")
def settings_command() -> None:
    """Show the server's security-relevant system settings. `--json` for the full payload."""
    settings = asyncio.run(service.get_security_settings(profile_from_env()))
    if is_json_output():
        typer.echo(settings.model_dump_json(indent=2, exclude_none=True))
        return
    rows = [
        DetailRow("minPasswordLength", _number(settings.minPasswordLength)),
        DetailRow("maxPasswordLength", _number(settings.maxPasswordLength)),
        DetailRow("credentialsExpires", _months(settings.credentialsExpires)),
        DetailRow("credentialsExpiresReminderInDays", _number(settings.credentialsExpiresReminderInDays)),
        DetailRow("credentialsExpiryAlert", format_bool(settings.credentialsExpiryAlert)),
        DetailRow("accountRecovery", _flag(settings.keyAccountRecovery)),
        DetailRow("selfRegistrationNoRecaptcha", _flag(settings.keySelfRegistrationNoRecaptcha)),
        DetailRow("lockMultipleFailedLogins", _flag(settings.keyLockMultipleFailedLogins)),
        DetailRow("enforceVerifiedEmail", _flag(settings.enforceVerifiedEmail)),
    ]
    render_detail("security settings", rows)


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `dhis2 security`."""
    root_app.add_typer(app, name="security", help="DHIS2 security posture (read-only).")
