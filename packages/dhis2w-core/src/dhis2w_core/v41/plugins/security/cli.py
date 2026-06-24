"""Typer sub-app for the `security` plugin (mounted under `d2w security`)."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import ColumnSpec, DetailRow, format_bool, is_json_output, render_detail, render_list

app = typer.Typer(
    help="Inspect DHIS2 security posture (settings, account authorities).",
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
    from dhis2w_core.v41.plugins.security import service

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


@app.command("authorities")
def authorities_command() -> None:
    """Show my effective authorities, categorised by security risk. `--json` for the full payload."""
    from dhis2w_core.v41.plugins.security import service

    account = asyncio.run(service.get_account_authorities(profile_from_env()))
    if is_json_output():
        typer.echo(account.model_dump_json(indent=2))
        return
    rows = [
        DetailRow("authorities", str(len(account.authorities))),
        DetailRow("superuser (ALL)", format_bool(account.is_superuser)),
        DetailRow("risk categories", str(len(account.categories))),
    ]
    render_detail("security authorities", rows)
    if account.categories:
        render_list(
            "risk categories",
            [
                {
                    "category": match.label,
                    "matched": ", ".join(match.matched),
                    "description": match.description,
                }
                for match in account.categories
            ],
            [
                ColumnSpec("Category", "category", style="cyan", no_wrap=True),
                ColumnSpec("Matched authorities", "matched"),
                ColumnSpec("Why it matters", "description"),
            ],
        )


def _parse_csv(value: str | None) -> list[str] | None:
    """Split a comma-separated option into a list of keys, or None when unset."""
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _run_folder(output_dir: Path | None, profile_name: str, timestamp: str) -> Path:
    """Build the per-run output folder under `output_dir` (default: current directory)."""
    parent = output_dir or Path.cwd()
    return parent / f"dhis2-security-{profile_name}-{timestamp}"


@app.command("audit")
def audit_command(
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir", file_okay=False, help="Parent directory for the run folder (default: current dir)."
        ),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Comma-separated formats: md,txt,csv,html (default: all).")
    ] = None,
    checks: Annotated[
        str | None, typer.Option("--checks", help="Comma-separated check keys to run (default: all).")
    ] = None,
    skip: Annotated[str | None, typer.Option("--skip", help="Comma-separated check keys to skip.")] = None,
    progress: Annotated[
        bool, typer.Option("--progress/--no-progress", help="Animate step-by-step progress on a TTY.")
    ] = True,
    credential_probe: Annotated[
        bool,
        typer.Option(
            "--credential-probe/--no-credential-probe",
            help="Actively test the default admin/district login against /api/me (on by default).",
        ),
    ] = True,
    stale_days: Annotated[
        int, typer.Option("--stale-days", min=1, help="Days without login before a privileged account is stale.")
    ] = 90,
    max_password_age: Annotated[
        int,
        typer.Option("--max-password-age", min=1, help="Days before an unchanged password is treated as stale."),
    ] = 365,
    two_factor_detail: Annotated[
        bool,
        typer.Option(
            "--two-factor-detail/--no-two-factor-detail",
            help="On v41+, also list each superuser lacking 2FA (per-user /api/users/twoFactor read).",
        ),
    ] = False,
    max_objects: Annotated[
        int | None,
        typer.Option(
            "--max-objects",
            min=1,
            show_default=False,
            help="Max objects the sharing scan inspects across all types before stopping "
            "(default 5000; truncation is loud).",
        ),
    ] = None,
    sharing_graph: Annotated[
        bool,
        typer.Option(
            "--sharing-graph",
            "--visualize",
            help="Also write the interactive d3 sharing explorer (sharing-explorer.html) into the run folder.",
        ),
    ] = False,
    resume: Annotated[
        Path | None, typer.Option("--resume", file_okay=False, exists=True, help="Resume an interrupted run folder.")
    ] = None,
    dhis_conf: Annotated[
        Path | None,
        typer.Option(
            "--dhis-conf",
            envvar="DHIS2_CONF_LOCATION",
            show_envvar=True,
            dir_okay=False,
            exists=True,
            help=(
                "Path to a local COPY of the server's dhis.conf for the audit-config check. The audit "
                "posture is not API-readable; secrets are reported set/not-set only and never echoed."
            ),
        ),
    ] = None,
) -> None:
    """Run the security checks step by step and stream a report to a folder. `--json` prints the report."""
    from dhis2w_core.security_core import AuditOptions
    from dhis2w_core.v41.plugins.security import audit

    profile = profile_from_env()
    profile_name = os.environ.get("DHIS2_PROFILE") or "default"
    formats = _parse_csv(output_format) or list(audit.DEFAULT_FORMATS)
    animated = progress and sys.stderr.isatty() and not is_json_output()
    options = AuditOptions(
        stale_days=stale_days,
        max_password_age_days=max_password_age,
        two_factor_detail=two_factor_detail,
        max_objects=max_objects if max_objects is not None else audit.DEFAULT_SHARING_MAX_OBJECTS,
        dhis_conf_path=dhis_conf,
    )

    try:
        if resume is not None:
            report = asyncio.run(
                audit.resume_security_audit(
                    profile,
                    folder=resume,
                    profile_name=profile_name,
                    options=options,
                    formats=formats,
                    visualize=sharing_graph,
                    animated=animated,
                )
            )
            folder = resume
        else:
            skip_keys = _parse_csv(skip) or []
            if not credential_probe:
                skip_keys = [*skip_keys, "credential-probe"]
            now = datetime.now(UTC)
            folder = _run_folder(output_dir, profile_name, now.strftime("%Y%m%dT%H%M%S%fZ"))
            report = asyncio.run(
                audit.run_security_audit(
                    profile,
                    output_dir=folder,
                    profile_name=profile_name,
                    started_at=now.isoformat(),
                    options=options,
                    only=_parse_csv(checks),
                    skip=skip_keys or None,
                    formats=formats,
                    visualize=sharing_graph,
                    animated=animated,
                )
            )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if is_json_output():
        typer.echo(report.model_dump_json(indent=2, exclude_none=True))
        return
    worst = report.summary.worst
    typer.echo(f"report written to {folder}")
    typer.echo(f"{report.summary.total_findings} finding(s); worst severity: {worst.value if worst else 'none'}")
    if sharing_graph and (folder / "sharing-explorer.html").exists():
        typer.echo(f"sharing explorer: {folder / 'sharing-explorer.html'}")


@app.command("report")
def report_command(
    folder: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="An existing run folder to re-render.")],
    output_format: Annotated[
        str | None, typer.Option("--format", help="Comma-separated formats (default: all).")
    ] = None,
) -> None:
    """Re-render an existing run's report files from its JSONL spine, without re-scanning."""
    from dhis2w_core.v41.plugins.security import audit

    formats = _parse_csv(output_format) or list(audit.DEFAULT_FORMATS)
    try:
        audit.rerender_report(folder, formats=formats)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"re-rendered {', '.join(formats)} in {folder}")


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w security`."""
    root_app.add_typer(app, name="security", help="DHIS2 security posture (read-only).")
