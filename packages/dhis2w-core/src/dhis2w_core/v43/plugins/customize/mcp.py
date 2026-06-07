"""FastMCP tool registration for the `customize` plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dhis2w_client.generated.v43.oas import LoginConfigResponse
from dhis2w_client.v43 import CustomizationResult

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v43.plugins.customize import service


def register(mcp: Any) -> None:
    """Register customize tools on the MCP server."""

    @mcp.tool()
    async def customize_logo_front(path: str, profile: str | None = None) -> dict[str, str]:
        """Upload an image file as the DHIS2 login-page splash / upper-right logo.

        Also flips `keyUseCustomLogoFront=true` so DHIS2 serves the uploaded
        bytes instead of redirecting to the built-in default.
        """
        await service.upload_logo_front(resolve_profile(profile), Path(path))
        return {"status": "uploaded", "key": "logo_front"}

    @mcp.tool()
    async def customize_logo_banner(path: str, profile: str | None = None) -> dict[str, str]:
        """Upload an image file as the DHIS2 top-menu banner logo (authenticated pages).

        Also flips `keyUseCustomLogoBanner=true`.
        """
        await service.upload_logo_banner(resolve_profile(profile), Path(path))
        return {"status": "uploaded", "key": "logo_banner"}

    @mcp.tool()
    async def customize_style(path: str, profile: str | None = None) -> dict[str, str]:
        """Upload a CSS file served as `/api/files/style` on every authenticated page.

        DHIS2's standalone login app does NOT load this stylesheet — it only
        affects post-authentication pages.
        """
        await service.upload_style(resolve_profile(profile), Path(path))
        return {"status": "uploaded", "key": "style"}

    @mcp.tool()
    async def customize_show(profile: str | None = None) -> LoginConfigResponse:
        """Return DHIS2's read-only `/api/loginConfig` summary (what the login app renders)."""
        return await service.get_login_config(resolve_profile(profile))

    @mcp.tool()
    async def customize_apply(directory: str, profile: str | None = None) -> CustomizationResult:
        """Apply a committed preset directory in one call.

        Expected files (all optional; missing are skipped):
        - `logo_front.png`     — upper-right / login splash logo
        - `logo_banner.png`    — top-menu banner
        - `style.css`          — stylesheet served on authenticated pages
        - `preset.json`        — `{system-setting-key: value}` map
        """
        return await service.apply_preset_dir(resolve_profile(profile), Path(directory))
