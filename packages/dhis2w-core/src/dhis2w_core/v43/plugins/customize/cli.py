"""Typer sub-app for the `customize` plugin (mounted under `d2w dev customize`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import is_json_output

app = typer.Typer(
    help="DHIS2 branding — login-page logos, copy, theme.",
    no_args_is_help=True,
)


@app.command("logo-front")
def logo_front_command(
    file: Annotated[Path, typer.Argument(help="PNG/JPG/SVG to upload as the login splash logo.")],
) -> None:
    """Upload the login-page splash / upper-right logo."""
    from dhis2w_core.v43.plugins.customize import service

    asyncio.run(service.upload_logo_front(profile_from_env(), file))
    typer.echo(f"uploaded {file.name} as logo_front (keyUseCustomLogoFront=true)")


@app.command("logo-banner")
def logo_banner_command(
    file: Annotated[Path, typer.Argument(help="PNG/JPG/SVG to upload as the top-menu banner.")],
) -> None:
    """Upload the top-menu banner logo (appears on every authenticated page)."""
    from dhis2w_core.v43.plugins.customize import service

    asyncio.run(service.upload_logo_banner(profile_from_env(), file))
    typer.echo(f"uploaded {file.name} as logo_banner (keyUseCustomLogoBanner=true)")


@app.command("style")
def style_command(
    file: Annotated[Path, typer.Argument(help="CSS file to upload as `/api/files/style`.")],
) -> None:
    """Upload a CSS stylesheet that DHIS2 serves on every authenticated page.

    NOTE: DHIS2's standalone login app (`/dhis-web-login/`) does NOT include this
    stylesheet. Post-auth pages do.
    """
    from dhis2w_core.v43.plugins.customize import service

    asyncio.run(service.upload_style(profile_from_env(), file))
    typer.echo(f"uploaded {file.name} as /api/files/style (keyStyle=style)")


@app.command("apply")
def apply_command(
    directory: Annotated[
        Path,
        typer.Argument(
            help="Directory containing optional logo_front.png, logo_banner.png, style.css, preset.json.",
        ),
    ],
) -> None:
    """Apply a committed preset directory in one call (skips files that don't exist)."""
    from dhis2w_core.v43.plugins.customize import service

    if not directory.is_dir():
        raise typer.BadParameter(f"{directory} is not a directory")
    result = asyncio.run(service.apply_preset_dir(profile_from_env(), directory))
    if result.logo_front_uploaded:
        typer.echo("uploaded logo_front")
    if result.logo_banner_uploaded:
        typer.echo("uploaded logo_banner")
    if result.style_uploaded:
        typer.echo("uploaded style.css")
    for key in result.settings_applied:
        typer.echo(f"set {key}")


@app.command("show")
def show_command() -> None:
    """Show DHIS2's current `/api/loginConfig` snapshot (what the login app sees)."""
    from dhis2w_core.v43.plugins.customize import service

    config = asyncio.run(service.get_login_config(profile_from_env()))
    if is_json_output():
        typer.echo(config.model_dump_json(indent=2, exclude_none=True))
        return
    for key in (
        "applicationTitle",
        "applicationDescription",
        "applicationNotification",
        "applicationLeftSideFooter",
        "applicationRightSideFooter",
        "useCustomLogoFront",
        "loginPageLayout",
    ):
        value = getattr(config, key, None)
        if value not in (None, ""):
            typer.echo(f"{key}: {value}")


def register(parent_app: Any) -> None:
    """Mount under `d2w dev customize` (called from `plugins/dev/cli.py`)."""
    parent_app.add_typer(app, name="customize", help="Brand + theme a DHIS2 instance (logos, copy, CSS).")
