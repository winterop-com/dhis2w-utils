"""Typer sub-app for `d2w apps` — install / uninstall / update DHIS2 apps."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_client.v43 import RestoreSummary
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import is_json_output
from dhis2w_core.v43.plugins.apps import service
from dhis2w_core.v43.plugins.apps.models import UpdateOutcome, UpdateSummary

app = typer.Typer(
    help="DHIS2 apps — install / uninstall / update via /api/apps + /api/appHub.",
    no_args_is_help=True,
)
_console = Console()


@app.command("list")
@app.command("ls", hidden=True)
def list_command() -> None:
    """List every installed app (`GET /api/apps`)."""
    apps = asyncio.run(service.list_apps(profile_from_env()))
    if is_json_output():
        typer.echo("[" + ",".join(a.model_dump_json(exclude_none=True) for a in apps) + "]")
        return
    if not apps:
        typer.echo("no apps installed")
        return
    table = Table(title=f"DHIS2 apps ({len(apps)})")
    table.add_column("key", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("version", justify="right")
    table.add_column("type")
    table.add_column("bundled", justify="center")
    table.add_column("hub id", style="dim", overflow="fold")
    for row in apps:
        table.add_row(
            row.key or "-",
            row.displayName or row.name or "-",
            row.version or "-",
            str(row.appType or "-"),
            "[green]yes[/green]" if row.bundled else "[dim]no[/dim]",
            row.app_hub_id or "-",
        )
    _console.print(table)


@app.command("add")
def add_command(
    source: Annotated[
        str,
        typer.Argument(
            help=(
                "A path to a local `.zip` (installs via /api/apps), an App Hub "
                "version id, or an App Hub app id (the latest version is resolved)."
            ),
        ),
    ],
) -> None:
    """Install an app from a local zip, an App Hub version id, or an App Hub app id.

    Auto-dispatches on `source`: an existing file on disk → multipart upload to
    `/api/apps`; otherwise the id is resolved against the configured App Hub
    catalog and installed via `POST /api/appHub/{versionId}`. A version id
    installs directly; an app id resolves to that app's latest version (App Hub
    app ids and version ids are both bare UUIDs and easy to confuse — see
    BUGS.md #46). DHIS2 overwrites an existing install of the same app.
    """
    candidate = Path(source)
    profile = profile_from_env()
    if candidate.is_file():
        asyncio.run(service.install_from_file(profile, candidate))
        typer.echo(f"installed from file: {candidate.name}")
    else:
        target = asyncio.run(service.install_from_hub(profile, source))
        label = f"{target.app_name or 'app'} {target.version or ''}".strip()
        if target.resolved_from == "app-id":
            typer.echo(f"installed {label} (resolved app id to App Hub version {target.version_id})")
        else:
            typer.echo(f"installed {label} (App Hub version {target.version_id})")


@app.command("remove")
@app.command("rm", hidden=True)
def remove_command(
    key: Annotated[str, typer.Argument(help="App key (folder name) from `apps list`.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Uninstall an app by key (`DELETE /api/apps/{key}`)."""
    if not yes and not typer.confirm(f"remove installed app {key!r}?", default=False):
        raise typer.Exit(0)
    asyncio.run(service.uninstall(profile_from_env(), key))
    typer.echo(f"removed {key}")


@app.command("update")
def update_command(
    key: Annotated[str | None, typer.Argument(help="App key; omit with --all to update every app.")] = None,
    all_apps: Annotated[bool, typer.Option("--all", help="Update every installed app.")] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Show what would change without installing — report the newer hub "
                "version for every app with an update available, tagged AVAILABLE."
            ),
        ),
    ] = False,
) -> None:
    """Update one app or every installed app to its latest App Hub version.

    Apps without an `app_hub_id` (typically side-loaded zips) are reported
    as `SKIPPED` — they're not installable via the hub. Bundled core apps
    (`bundled=True`) still carry an `app_hub_id` and can be updated in
    place, so they're treated like any other hub-updatable app. With
    `--dry-run`, every available update prints as
    `AVAILABLE` and no install call is made, so you can preview the delta
    first.
    """
    profile = profile_from_env()
    if all_apps and key:
        raise typer.BadParameter("pass either a key or --all, not both")
    if not all_apps and not key:
        raise typer.BadParameter("pass a key, or use --all to update every app")
    if all_apps:
        summary = asyncio.run(service.update_all(profile, dry_run=dry_run))
        if is_json_output():
            typer.echo(summary.model_dump_json(exclude_none=True))
            return
        _render_summary(summary, dry_run=dry_run)
        return
    assert key is not None  # guarded above
    outcome = asyncio.run(service.update_one(profile, key, dry_run=dry_run))
    if is_json_output():
        typer.echo(outcome.model_dump_json(exclude_none=True))
        return
    _render_summary(UpdateSummary(outcomes=[outcome]), dry_run=dry_run)


@app.command("reload")
def reload_command() -> None:
    """Ask DHIS2 to re-read every app from disk (`PUT /api/apps`)."""
    asyncio.run(service.reload_apps(profile_from_env()))
    typer.echo("apps reloaded from disk")


@app.command("restore")
def restore_command(
    manifest: Annotated[
        Path,
        typer.Argument(
            help="Path to a snapshot JSON file produced by `d2w apps snapshot`.",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Show what would install without running the /api/appHub POSTs — "
                "entries that would install are tagged AVAILABLE."
            ),
        ),
    ] = False,
) -> None:
    """Reinstall every hub-backed entry from a snapshot JSON.

    The flip side of `d2w apps snapshot`. Reads the JSON produced by
    `snapshot`, walks each entry, and calls `/api/appHub/{versionId}`
    for every app whose `hub_version_id` is set and whose currently
    installed version differs from the snapshot's. Side-loaded entries
    (no `hub_version_id`) report as `SKIPPED` — the snapshot doesn't
    carry their zips.
    """
    from dhis2w_client.v43 import AppsSnapshot

    if not manifest.is_file():
        raise typer.BadParameter(f"no such manifest: {manifest}")
    payload = manifest.read_text(encoding="utf-8")
    loaded = AppsSnapshot.model_validate_json(payload)
    summary = asyncio.run(service.restore(profile_from_env(), loaded, dry_run=dry_run))
    if is_json_output():
        typer.echo(summary.model_dump_json(exclude_none=True))
        return
    _render_restore_summary(summary, dry_run=dry_run)


def _render_restore_summary(summary: RestoreSummary, *, dry_run: bool) -> None:
    """Print a restore-outcome table + totals footer."""
    if not summary.outcomes:
        typer.echo("empty snapshot")
        return
    title = "restore preview (dry run)" if dry_run else "restore summary"
    table = Table(title=title)
    table.add_column("key", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("from", justify="right")
    table.add_column("to", justify="right")
    table.add_column("status")
    table.add_column("reason", style="dim", overflow="fold")
    for outcome in summary.outcomes:
        table.add_row(
            outcome.key,
            outcome.name,
            outcome.from_version or "-",
            outcome.to_version or "-",
            _color_restore_status(outcome.status),
            outcome.reason or "",
        )
    _console.print(table)
    if dry_run:
        typer.echo(
            f"totals: available={summary.available} up-to-date={summary.up_to_date} "
            f"skipped={summary.skipped} failed={summary.failed}  "
            "(re-run without --dry-run to restore)",
        )
    else:
        typer.echo(
            f"totals: restored={summary.restored} up-to-date={summary.up_to_date} "
            f"skipped={summary.skipped} failed={summary.failed}",
        )


def _color_restore_status(status: str) -> str:
    """Colourize the status column for readable terminal output."""
    return {
        "RESTORED": f"[green bold]{status}[/green bold]",
        "AVAILABLE": f"[green]{status}[/green]",
        "UP_TO_DATE": f"[dim]{status}[/dim]",
        "SKIPPED": f"[yellow]{status}[/yellow]",
        "FAILED": f"[red bold]{status}[/red bold]",
    }.get(status, status)


@app.command("snapshot")
def snapshot_command(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the snapshot JSON to this file. Omit to print to stdout.",
        ),
    ] = None,
) -> None:
    """Capture every installed app into a portable JSON snapshot.

    One entry per installed app — key, name, version, `app_hub_id`, and
    (when the app came from the App Hub) the hub `versionId` +
    `downloadUrl` needed to re-install it on another instance. Apps
    without an `app_hub_id` are captured as `source=side-loaded`; they
    appear in the snapshot but can't be rehydrated without their zip.

    Useful as a "pin my apps catalog at this point in time" operation —
    diff two snapshots to see drift, or re-apply on staging after a
    bulk-install on production.
    """
    result = asyncio.run(service.snapshot(profile_from_env()))
    payload = result.model_dump_json(indent=2, exclude_none=True)
    if output is not None:
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(
            f"wrote {output} ({len(result.entries)} apps; "
            f"{result.hub_backed} hub-backed, {result.side_loaded} side-loaded)",
        )
    else:
        typer.echo(payload)


@app.command("hub-list")
def hub_list_command(
    search: Annotated[
        str | None,
        typer.Option(
            "--search",
            "-s",
            help="Case-insensitive substring filter on name + description (client-side).",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Cap the number of rows shown.")] = 50,
) -> None:
    """List apps available in the configured App Hub (`GET /api/appHub`).

    Pass `--search <query>` to filter the catalog by app name or
    description substring. The filter runs client-side — DHIS2's
    `/api/appHub` proxy doesn't expose a server-side query parameter
    on v42, so the full catalog is fetched and filtered after.
    """
    hub = asyncio.run(service.hub_list(profile_from_env(), query=search))
    hub = hub[:limit]
    if is_json_output():
        typer.echo("[" + ",".join(a.model_dump_json(exclude_none=True) for a in hub) + "]")
        return
    if not hub:
        suffix = f" matching {search!r}" if search else ""
        typer.echo(f"App Hub returned no apps{suffix}")
        return
    title_suffix = f" matching {search!r}" if search else ""
    table = Table(title=f"DHIS2 App Hub ({len(hub)} shown{title_suffix})")
    table.add_column("id", style="cyan", overflow="fold")
    table.add_column("name", overflow="fold")
    table.add_column("type")
    table.add_column("versions", justify="right")
    for row in hub:
        table.add_row(
            row.id or "-",
            row.name or "-",
            row.app_type or "-",
            str(len(row.versions)),
        )
    _console.print(table)


@app.command("hub-versions")
def hub_versions_command(
    app_id: Annotated[str, typer.Argument(help="App Hub app id (the `id` column from `apps hub-list`).")],
) -> None:
    """List every published version of one App Hub app (`GET /api/appHub`).

    Prints `version / id / channel / DHIS2 min->max` for each version, newest
    first. The `id` values are the version ids `d2w apps add <id>` installs
    directly (pinning that exact version) — use this to pick a version instead
    of letting `apps add <app-id>` resolve to the latest.
    """
    record = asyncio.run(service.hub_versions(profile_from_env(), app_id))
    if is_json_output():
        typer.echo(record.model_dump_json(exclude_none=True))
        return
    table = Table(title=f"{record.name or app_id} — {len(record.versions)} versions")
    table.add_column("version", justify="right")
    table.add_column("id", style="cyan", overflow="fold")
    table.add_column("channel")
    table.add_column("DHIS2", justify="center")
    for version in record.versions:
        span = f"{version.min_dhis2_version or '?'}->{version.max_dhis2_version or ''}"
        table.add_row(version.version or "-", version.id or "-", version.channel or "-", span)
    _console.print(table)


@app.command("hub-url")
def hub_url_command(
    set_url: Annotated[
        str | None,
        typer.Option(
            "--set",
            help="Point this DHIS2 instance at a different App Hub (writes the `keyAppHubUrl` system setting).",
        ),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            help="Clear the `keyAppHubUrl` setting so DHIS2 reverts to its default hub.",
        ),
    ] = False,
) -> None:
    """Read or write DHIS2's configured App Hub URL (`keyAppHubUrl` system setting).

    The App Hub is open source (https://github.com/dhis2/app-hub); teams
    running a self-hosted hub can point DHIS2 at it by setting this.
    Pass `--set <url>` to update, `--clear` to revert to DHIS2's
    hard-coded default (typically `https://apps.dhis2.org/api`).
    """
    if set_url and clear:
        raise typer.BadParameter("--set and --clear are mutually exclusive")
    profile = profile_from_env()
    if clear:
        asyncio.run(service.set_hub_url(profile, None))
        typer.echo("cleared keyAppHubUrl — DHIS2 will use its default App Hub")
        return
    if set_url:
        asyncio.run(service.set_hub_url(profile, set_url))
        typer.echo(f"keyAppHubUrl -> {set_url}")
        return
    current = asyncio.run(service.get_hub_url(profile))
    if current is None:
        typer.echo("keyAppHubUrl: <not set>  (DHIS2 is using its default App Hub)")
    else:
        typer.echo(f"keyAppHubUrl: {current}")


def _render_summary(summary: UpdateSummary, *, dry_run: bool = False) -> None:
    """Print an update-outcome table + totals footer."""
    if not summary.outcomes:
        typer.echo("no apps to update")
        return
    title = "available updates (dry run)" if dry_run else "update summary"
    table = Table(title=title)
    table.add_column("key", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("from", justify="right")
    table.add_column("to", justify="right")
    table.add_column("status")
    table.add_column("reason", style="dim", overflow="fold")
    for outcome in summary.outcomes:
        table.add_row(
            outcome.key,
            outcome.name,
            outcome.from_version or "-",
            outcome.to_version or "-",
            _color_status(outcome.status),
            outcome.reason or "",
        )
    _console.print(table)
    if dry_run:
        typer.echo(
            f"totals: available={summary.available} up-to-date={summary.up_to_date} "
            f"skipped={summary.skipped} failed={summary.failed}  "
            "(re-run without --dry-run to install)",
        )
    else:
        typer.echo(
            f"totals: updated={summary.updated} up-to-date={summary.up_to_date} "
            f"skipped={summary.skipped} failed={summary.failed}",
        )


def _color_status(status: str) -> str:
    """Colourize the status column for readable terminal output."""
    return {
        "UPDATED": f"[green bold]{status}[/green bold]",
        "AVAILABLE": f"[green]{status}[/green]",
        "UP_TO_DATE": f"[dim]{status}[/dim]",
        "SKIPPED": f"[yellow]{status}[/yellow]",
        "FAILED": f"[red bold]{status}[/red bold]",
    }.get(status, status)


def register(parent_app: Any) -> None:
    """Mount `d2w apps` on the root CLI."""
    parent_app.add_typer(app, name="apps", help="DHIS2 apps — /api/apps + /api/appHub.")


__all__ = ["register", "UpdateOutcome"]
