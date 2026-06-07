"""Service layer for the `system` plugin — wraps /api/system/info and /api/me."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

from dhis2w_client.v42 import DhisCalendar, Me, SystemInfo
from pydantic import BaseModel, ConfigDict

from dhis2w_core.plugin import DEFAULT_VERSION_KEY, resolve_startup_version
from dhis2w_core.profile import Profile
from dhis2w_core.v42.client_context import open_client


class _SystemIdResponse(BaseModel):
    """Envelope for `GET /api/system/id` — returns `{codes: ["UID", ...]}`."""

    model_config = ConfigDict(extra="allow")

    codes: list[str] = []


class ServerInfo(BaseModel):
    """Metadata about the running `dhis2w-mcp` / `dhis2w-cli` process itself.

    Distinct from `SystemInfo`, which is about the *DHIS2* the process talks
    to. This model surfaces the active plugin tree (v41 / v42 / v43) + the
    chain element that selected it (`profile.version` / `DHIS2_VERSION` env
    / default fallback), plus the bound package versions.
    """

    model_config = ConfigDict(frozen=True)

    active_plugin_tree: str
    """Plugin tree the server booted with — `v41` / `v42` / `v43`."""

    active_plugin_tree_source: str
    """Where the selection came from: `profile.version`, `DHIS2_VERSION env`, or `default`."""

    dhis2w_core_version: str
    """Version of the installed `dhis2w-core` package, or `unknown` when not pip-installed."""

    dhis2w_mcp_version: str | None = None
    """Version of the installed `dhis2w-mcp` package (None when running as CLI / library)."""

    dhis2w_cli_version: str | None = None
    """Version of the installed `dhis2w-cli` package (None when running as MCP / library)."""


def _package_version(name: str) -> str | None:
    """Return the installed package version, or None if not pip-installed."""
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _active_plugin_tree_source(active: str) -> str:
    """Describe which step of the resolution chain picked the active plugin tree."""
    env_version = os.environ.get("DHIS2_VERSION", "").strip()
    if env_version in {"41", "42", "43"} and f"v{env_version}" == active:
        return f"DHIS2_VERSION={env_version!r} env"
    if env_version in {"v41", "v42", "v43"} and env_version == active:
        return f"DHIS2_VERSION={env_version!r} env"
    if active == DEFAULT_VERSION_KEY:
        return "default (no profile.version, no DHIS2_VERSION env)"
    return "profile.version"


async def server_info() -> ServerInfo:
    """Return the process-local plugin tree + package version envelope.

    Doesn't open a DHIS2 client — purely introspects the running
    `dhis2w-mcp` / `dhis2w-cli` / library process. Useful for MCP clients
    that want to detect what plugin tree they're talking to before
    issuing version-sensitive tool calls.
    """
    active = resolve_startup_version()
    core_version = _package_version("dhis2w-core") or "unknown"
    return ServerInfo(
        active_plugin_tree=active,
        active_plugin_tree_source=_active_plugin_tree_source(active),
        dhis2w_core_version=core_version,
        dhis2w_mcp_version=_package_version("dhis2w-mcp"),
        dhis2w_cli_version=_package_version("dhis2w-cli"),
    )


async def whoami(profile: Profile) -> Me:
    """Return the authenticated user for the given profile."""
    async with open_client(profile) as client:
        return await client.system.me()


async def system_info(profile: Profile) -> SystemInfo:
    """Return the DHIS2 system info for the given profile."""
    async with open_client(profile) as client:
        return await client.system.info()


async def get_calendar(profile: Profile) -> str:
    """Return the active DHIS2 calendar (`keyCalendar`) for the given profile."""
    async with open_client(profile) as client:
        return await client.system.calendar()


async def set_calendar(profile: Profile, calendar: DhisCalendar | str) -> None:
    """Write the DHIS2 calendar setting for the given profile."""
    async with open_client(profile) as client:
        await client.system.set_calendar(calendar)


async def generate_uids(profile: Profile, *, limit: int = 1) -> list[str]:
    """Generate `limit` fresh DHIS2 UIDs via `/api/system/id`.

    Returns the raw 11-char UIDs — useful for creating metadata with
    caller-chosen ids without writing your own UID generator.
    """
    async with open_client(profile) as client:
        response = await client.get("/api/system/id", model=_SystemIdResponse, params={"limit": limit})
    return response.codes


async def set_system_setting(profile: Profile, key: str, value: str) -> None:
    """Set a single DHIS2 system setting."""
    async with open_client(profile) as client:
        await client.customize.set_system_setting(key, value)


async def set_system_settings(profile: Profile, settings: dict[str, str]) -> list[str]:
    """Bulk-set DHIS2 system settings from a `{key: value}` mapping; return keys applied."""
    async with open_client(profile) as client:
        return await client.customize.set_system_settings(settings)
