"""Typer sub-app for the `browser` plugin — mounts `d2w browser ...`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import is_json_output


def register(app: Any) -> None:
    """Mount `d2w browser` on the root CLI."""
    browser_app = typer.Typer(
        help="Playwright-driven DHIS2 UI automation.",
        no_args_is_help=True,
    )
    browser_app.command("pat")(pat_command)

    dashboard_app = typer.Typer(
        help="Dashboard capture workflows.",
        no_args_is_help=True,
    )
    dashboard_app.command("screenshot")(dashboard_screenshot_command)
    browser_app.add_typer(dashboard_app, name="dashboard")

    viz_app = typer.Typer(
        help="Visualization capture workflows.",
        no_args_is_help=True,
    )
    viz_app.command("screenshot")(viz_screenshot_command)
    browser_app.add_typer(viz_app, name="viz")

    map_app = typer.Typer(
        help="Map capture workflows.",
        no_args_is_help=True,
    )
    map_app.command("screenshot")(map_screenshot_command)
    browser_app.add_typer(map_app, name="map")

    app.add_typer(browser_app, name="browser")


def pat_command(
    url: Annotated[str, typer.Option("--url", help="Base URL of the DHIS2 instance.")],
    username: Annotated[str, typer.Option("--username", help="Login username.")],
    password: Annotated[str, typer.Option("--password", help="Login password.")],
    name: Annotated[str | None, typer.Option("--name", help="Friendly display name for the token.")] = None,
    expires_in_days: Annotated[
        int | None,
        typer.Option("--expires-in-days", help="Token lifetime in days; omit for no expiry."),
    ] = None,
    allowed_ip: Annotated[
        list[str] | None,
        typer.Option("--allowed-ip", help="CIDR/IP allowlist entry; repeat for multiple."),
    ] = None,
    allowed_method: Annotated[
        list[str] | None,
        typer.Option("--allowed-method", help="HTTP method allowlist; repeat for each method."),
    ] = None,
    allowed_referrer: Annotated[
        list[str] | None,
        typer.Option("--allowed-referrer", help="Referer URL allowlist; repeat for each."),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headful",
            help="Run browser headlessly (default: visible, so you can watch the flow).",
        ),
    ] = False,
) -> None:
    """Mint a Personal Access Token V2 via Playwright and print the token value to stdout.

    DHIS2 only returns the token value once, at creation — store it somewhere
    persistent immediately. Subsequent `GET /api/apiToken/{id}` calls return
    metadata but not the secret.
    """
    from dhis2w_core.v41.plugins.browser import service

    service.require_browser()
    from dhis2w_browser import PatOptions

    options = PatOptions(
        name=name,
        expires_in_days=expires_in_days,
        allowed_ips=allowed_ip,
        allowed_methods=allowed_method,
        allowed_referrers=allowed_referrer,
    )
    token = asyncio.run(service.create_pat(url, username, password, options=options, headless=headless))
    if is_json_output():
        typer.echo(json.dumps({"token": token}, indent=2))
    else:
        typer.echo(token)


def dashboard_screenshot_command(
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help=(
                "Directory for the PNG output. Defaults to `./screenshots`. "
                "Each run auto-creates an `{instance-slug}/` subdirectory keyed on "
                "the profile's base URL so multi-stack captures don't overwrite."
            ),
        ),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Capture only these dashboard UIDs; repeat for multiple."),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headful",
            help="Run browser headlessly (default: yes — automation-friendly).",
        ),
    ] = True,
    banner: Annotated[
        bool,
        typer.Option(
            "--banner/--no-banner",
            help="Prepend an info banner (instance / user / timestamp) to each PNG.",
        ),
    ] = True,
    trim: Annotated[
        bool,
        typer.Option(
            "--trim/--no-trim",
            help="Crop uniform-colour edges off the bottom + right of each PNG.",
        ),
    ] = True,
) -> None:
    """Capture full-page PNGs of every DHIS2 dashboard (or just the ones named via --only).

    Shares a single Playwright context across dashboards — one login, one
    dashboard-app load, then hash-only navigation between dashboards. The
    capture loop waits for each item's plugin iframe to render substantial
    content (canvas / svg / leaflet / highcharts / img / long text) with
    a plateau detector so one stuck item doesn't stall the batch.
    """
    from dhis2w_core.v41.plugins.browser import service

    profile = profile_from_env()
    resolved_output_dir = output_dir if output_dir is not None else Path.cwd() / "screenshots"
    results = asyncio.run(
        service.capture_dashboards(
            profile,
            output_dir=resolved_output_dir,
            only=only,
            headless=headless,
            banner=banner,
            trim=trim,
        )
    )
    if is_json_output():
        typer.echo(json.dumps([r.model_dump(mode="json", exclude_none=True) for r in results], indent=2))
        return
    if not results:
        typer.echo("no dashboards captured.")
        return
    for result in results:
        suffix = ""
        if result.items_expected and result.items_rendered < result.items_expected:
            suffix = f"  ({result.items_rendered}/{result.items_expected} items rendered)"
        typer.echo(f"  {result.output_path}  {result.display_name}{suffix}")


def viz_screenshot_command(
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help=(
                "Directory for the PNG output. Defaults to `./screenshots`. "
                "Each run auto-creates an `{instance-slug}/` subdirectory keyed on "
                "the profile's base URL so multi-stack captures don't overwrite."
            ),
        ),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Capture only these Visualization UIDs; repeat for multiple."),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headful",
            help="Run browser headlessly (default: yes — automation-friendly).",
        ),
    ] = True,
    banner: Annotated[
        bool,
        typer.Option(
            "--banner/--no-banner",
            help="Prepend an info banner (name / type / instance / user / timestamp) to each PNG.",
        ),
    ] = True,
    trim: Annotated[
        bool,
        typer.Option(
            "--trim/--no-trim",
            help="Crop uniform-colour edges off the bottom + right of each PNG.",
        ),
    ] = True,
) -> None:
    """Capture a PNG of each Visualization (or just the UIDs named via --only).

    Each capture navigates the DHIS2 Data Visualizer app
    (`/dhis-web-data-visualizer/#/<uid>`) inside a shared Playwright
    context — one login, one app-shell load, hash-only navigation
    between vizes. Renders wait for the chart to materialise (SVG /
    canvas / pivot table / long text) with a plateau detector so one
    stuck viz doesn't stall the batch.

    DHIS2 has no native `/api/visualizations/{uid}.png` endpoint, so
    every PNG goes through Chromium. Install the extra via
    `uv add 'dhis2w-cli[browser]'` + `playwright install
    chromium` first.
    """
    from dhis2w_core.v41.plugins.browser import service

    service.require_browser()
    profile = profile_from_env()
    resolved_output_dir = output_dir if output_dir is not None else Path.cwd() / "screenshots"
    results = asyncio.run(
        service.capture_visualizations(
            profile,
            output_dir=resolved_output_dir,
            only=only,
            headless=headless,
            banner=banner,
            trim=trim,
        ),
    )
    if is_json_output():
        typer.echo(json.dumps([dict(r) for r in results], indent=2, default=str))
        return
    if not results:
        typer.echo("no visualizations captured.")
        return
    for result in results:
        suffix = "" if result.get("rendered") else "  (plateau — chart may be blank)"
        typer.echo(f"  {result['output_path']}  {result['display_name']}{suffix}")


def map_screenshot_command(
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help=(
                "Directory for the PNG output. Defaults to `./screenshots`. "
                "Each run auto-creates an `{instance-slug}/` subdirectory keyed on "
                "the profile's base URL so multi-stack captures don't overwrite."
            ),
        ),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Capture only these Map UIDs; repeat for multiple."),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headful",
            help="Run browser headlessly (default: yes — automation-friendly).",
        ),
    ] = True,
    banner: Annotated[
        bool,
        typer.Option(
            "--banner/--no-banner",
            help="Prepend an info banner (name / layer count / instance / user / timestamp) to each PNG.",
        ),
    ] = True,
    trim: Annotated[
        bool,
        typer.Option(
            "--trim/--no-trim",
            help="Crop uniform-colour edges off the bottom + right of each PNG.",
        ),
    ] = True,
) -> None:
    """Capture a PNG of each Map (or the UIDs named via --only).

    Navigates the DHIS2 Maps app (`/dhis-web-maps/#/<uid>`) in a shared
    Playwright context — one login, one app-shell load, hash-nav between
    maps. Waits for MapLibre canvas + vector overlays to render before
    snapping. Requires the `[browser]` extra (install with
    `uv add 'dhis2w-cli[browser]'` + `playwright install chromium`).
    """
    from dhis2w_core.v41.plugins.browser import service

    service.require_browser()
    profile = profile_from_env()
    resolved_output_dir = output_dir if output_dir is not None else Path.cwd() / "screenshots"
    results = asyncio.run(
        service.capture_maps(
            profile,
            output_dir=resolved_output_dir,
            only=only,
            headless=headless,
            banner=banner,
            trim=trim,
        ),
    )
    if is_json_output():
        typer.echo(json.dumps([dict(r) for r in results], indent=2, default=str))
        return
    if not results:
        typer.echo("no maps captured.")
        return
    for result in results:
        suffix = "" if result.get("rendered") else "  (plateau — map may be blank)"
        typer.echo(f"  {result['output_path']}  {result['display_name']}{suffix}")
