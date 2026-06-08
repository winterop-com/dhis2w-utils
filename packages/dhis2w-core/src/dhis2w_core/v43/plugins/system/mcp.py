"""FastMCP tool registration for the `system` plugin."""

from __future__ import annotations

from typing import Any

from dhis2w_client.v43 import DhisCalendar, Me, SystemInfo

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v43.plugins.system import service
from dhis2w_core.v43.plugins.system.models import SystemSettingsSnapshot
from dhis2w_core.v43.plugins.system.service import ServerInfo


def register(mcp: Any) -> None:
    """Register `system_whoami`, `system_info`, `system_server_info`, and calendar tools on `mcp`."""

    @mcp.tool()
    async def system_whoami(profile: str | None = None) -> Me:
        """Return the authenticated DHIS2 user.

        `profile` selects a named profile from the project or global
        `profiles.toml`. Omit to use the default (from `DHIS2_PROFILE` env,
        raw `DHIS2_URL/PAT` env, or the TOML `default`).
        """
        return await service.whoami(resolve_profile(profile))

    @mcp.tool()
    async def system_info(profile: str | None = None) -> SystemInfo:
        """Return /api/system/info for the given profile (see `system_whoami` for precedence)."""
        return await service.system_info(resolve_profile(profile))

    @mcp.tool()
    async def system_settings_set(key: str, value: str, profile: str | None = None) -> dict[str, str]:
        """Set a single DHIS2 system setting.

        Login-page relevant keys: `applicationTitle` (no `key` prefix!), `keyApplicationIntro`,
        `keyApplicationNotification`, `keyApplicationFooter`, `keyApplicationRightFooter`, `keyStyle`.
        """
        await service.set_system_setting(resolve_profile(profile), key, value)
        return {"status": "set", "key": key}

    @mcp.tool()
    async def system_settings_set_many(settings: dict[str, str], profile: str | None = None) -> list[str]:
        """Bulk-set DHIS2 system settings from a `{key: value}` mapping; returns keys applied."""
        return await service.set_system_settings(resolve_profile(profile), settings)

    @mcp.tool()
    async def system_settings_get(key: str, profile: str | None = None) -> str | None:
        """Read a single DHIS2 system setting (null when unset)."""
        return await service.get_setting(resolve_profile(profile), key)

    @mcp.tool()
    async def system_settings_list(profile: str | None = None) -> SystemSettingsSnapshot:
        """Return every DHIS2 system setting as a key->value snapshot."""
        return await service.list_settings(resolve_profile(profile))

    @mcp.tool()
    async def system_server_info() -> ServerInfo:
        """Return the MCP server's active plugin tree + bound package versions.

        Process-local introspection — no DHIS2 client is opened. Tells the
        caller which plugin tree (`v41` / `v42` / `v43`) was selected at
        startup, where that selection came from (`profile.version`,
        `DHIS2_VERSION` env, or default fallback), and which `dhis2w-*`
        packages are installed. Useful for MCP clients that want to
        detect version mismatch before issuing version-sensitive calls.
        """
        return await service.server_info()

    @mcp.tool()
    async def system_calendar_get(profile: str | None = None) -> str:
        """Return the active DHIS2 calendar (`keyCalendar`) — `iso8601` by default."""
        return await service.get_calendar(resolve_profile(profile))

    @mcp.tool()
    async def system_calendar_set(calendar: DhisCalendar, profile: str | None = None) -> str:
        """Set the DHIS2 calendar setting and return the value written.

        `calendar` must be one of the canonical DHIS2 calendar names —
        coptic, ethiopian, gregorian, islamic, iso8601, julian, nepali,
        persian, thai. Rarely needs to be changed.
        """
        await service.set_calendar(resolve_profile(profile), calendar)
        return calendar.value
