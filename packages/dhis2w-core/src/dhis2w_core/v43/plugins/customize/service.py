"""Service layer for the `customize` plugin — thin orchestration over `Dhis2Client.customize`."""

from __future__ import annotations

import json
from pathlib import Path

from dhis2w_client.generated.v43.oas import LoginConfigResponse
from dhis2w_client.v43 import CustomizationResult, LoginCustomization

from dhis2w_core.profile import Profile
from dhis2w_core.v43.client_context import open_client


async def upload_logo_front(profile: Profile, path: Path) -> None:
    """Upload an image as the login-page splash / upper-right logo."""
    data = path.read_bytes()
    async with open_client(profile) as client:
        await client.customize.upload_logo_front(data, filename=path.name)


async def upload_logo_banner(profile: Profile, path: Path) -> None:
    """Upload an image as the top-menu banner logo (shown on every authenticated page)."""
    data = path.read_bytes()
    async with open_client(profile) as client:
        await client.customize.upload_logo_banner(data, filename=path.name)


async def upload_style(profile: Profile, path: Path) -> None:
    """Upload a CSS file served on every authenticated page (`/api/files/style`)."""
    css = path.read_text(encoding="utf-8")
    async with open_client(profile) as client:
        await client.customize.upload_style(css)


async def get_login_config(profile: Profile) -> LoginConfigResponse:
    """Return DHIS2's read-only `/api/loginConfig` summary."""
    async with open_client(profile) as client:
        return await client.customize.get_login_config()


async def apply_preset_dir(profile: Profile, directory: Path) -> CustomizationResult:
    """Apply a committed preset directory — optional `logo_front.png`, `logo_banner.png`, `style.css`, `preset.json`.

    Missing files are skipped (no error). `preset.json` is a flat `{key: value}` map of
    DHIS2 system-setting keys (`applicationTitle`, `keyApplicationIntro`, ...).
    """
    preset = LoginCustomization()
    logo_front = directory / "logo_front.png"
    if logo_front.exists():
        preset.logo_front = logo_front.read_bytes()
    logo_banner = directory / "logo_banner.png"
    if logo_banner.exists():
        preset.logo_banner = logo_banner.read_bytes()
    style = directory / "style.css"
    if style.exists():
        preset.style_css = style.read_text(encoding="utf-8")
    settings_file = directory / "preset.json"
    if settings_file.exists():
        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{settings_file} must contain a {{key: value}} object")
        preset.system_settings = {str(k): str(v) for k, v in loaded.items()}
    async with open_client(profile) as client:
        return await client.customize.apply_preset(preset)
