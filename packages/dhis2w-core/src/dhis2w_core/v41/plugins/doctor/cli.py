"""Typer sub-app for the `doctor` plugin — mounted as `d2w doctor`.

Three sub-commands map to three probe categories:

    d2w doctor metadata     # workspace metadata-health probes (default)
    d2w doctor integrity    # DHIS2's own /api/dataIntegrity summary
    d2w doctor bugs         # BUGS.md workaround drift detection

    d2w doctor              # no sub-command → runs metadata + integrity
    d2w doctor --all        # runs every category

Non-zero exit when any probe lands on `fail`. `warn` doesn't change exit
code — bugs drifting upstream or metadata issues are informational, not
build-blocking.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import is_json_output
from dhis2w_core.v41.plugins.doctor._models import DoctorReport, ProbeCategory

app = typer.Typer(
    help="Diagnose a DHIS2 instance — metadata health, DHIS2 data-integrity, workspace requirements.",
    no_args_is_help=False,
    invoke_without_command=True,
)
_console = Console()

_STATUS_STYLES: dict[str, str] = {
    "pass": "green",
    "warn": "yellow",
    "fail": "red",
    "skip": "dim",
}
_STATUS_MARKS: dict[str, str] = {
    "pass": "PASS",
    "warn": "WARN",
    "fail": "FAIL",
    "skip": "SKIP",
}


def _render(report: DoctorReport) -> int:
    """Print the report (Rich table or JSON) and return the intended exit code."""
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2, exclude_none=True))
        return 1 if report.fail_count else 0

    table = Table(title=f"d2w doctor — {report.base_url} (DHIS2 {report.dhis2_version or '?'})")
    table.add_column("probe", overflow="fold")
    table.add_column("category", no_wrap=True, style="dim")
    table.add_column("status", justify="center", no_wrap=True)
    table.add_column("message", overflow="fold")
    table.add_column("offending / ref", overflow="fold", style="dim")
    for probe in report.probes:
        mark = _STATUS_MARKS.get(probe.status, probe.status)
        style = _STATUS_STYLES.get(probe.status, "white")
        extra = probe.bugs_ref or ""
        if probe.offending_uids:
            shown = ", ".join(probe.offending_uids[:5])
            extra = f"{shown}{'...' if len(probe.offending_uids) > 5 else ''}"
        table.add_row(probe.name, probe.category, f"[{style}]{mark}[/{style}]", probe.message, extra)
    _console.print(table)

    summary = (
        f"[green]{report.pass_count} pass[/green] / "
        f"[yellow]{report.warn_count} warn[/yellow] / "
        f"[red]{report.fail_count} fail[/red] / "
        f"[dim]{report.skip_count} skip[/dim] "
        f"({len(report.probes)} probes)"
    )
    _console.print(summary)
    return 1 if report.fail_count else 0


def _run(categories: tuple[ProbeCategory, ...]) -> None:
    """Run the requested probe categories and render the report (table or JSON)."""
    from dhis2w_core.v41.plugins.doctor import service

    report = asyncio.run(service.run_doctor(profile_from_env(), categories=categories))
    exit_code = _render(report)
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.callback(invoke_without_command=True)
def root_command(
    ctx: typer.Context,
    run_all: Annotated[
        bool,
        typer.Option("--all", help="Run every category (metadata + integrity + bugs)."),
    ] = False,
) -> None:
    """Default: run metadata + integrity probes. Pass `--all` for bugs too."""
    if ctx.invoked_subcommand is not None:
        return
    categories: tuple[ProbeCategory, ...] = ("metadata", "integrity", "bugs") if run_all else ("metadata", "integrity")
    _run(categories)


@app.command("metadata")
def metadata_command() -> None:
    """Run workspace metadata-health probes only (data sets without DEs, programs without stages, ...)."""
    _run(("metadata",))


@app.command("integrity")
def integrity_command() -> None:
    """Run DHIS2's own `/api/dataIntegrity/summary` and surface each check as a probe."""
    _run(("integrity",))


@app.command("bugs")
def bugs_command() -> None:
    """Run BUGS.md workaround drift detection (workspace maintenance, not operator-facing)."""
    _run(("bugs",))


def register(root_app: Any) -> None:
    """Mount under `d2w doctor`."""
    root_app.add_typer(app, name="doctor", help="Probe a DHIS2 instance for known gotchas + requirements.")
