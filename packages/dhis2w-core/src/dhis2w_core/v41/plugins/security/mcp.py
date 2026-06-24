"""FastMCP tool registration for the `security` plugin (cheap read-only posture tools).

Exposes only the cheap, single-request reads that mirror the CLI's `settings`,
`authorities`, and `version` checks. The long-running `d2w security audit` (and its
credential probe, guest probe, sharing scan, and per-check subcommands) stays
CLI-only -- it is multi-request, makes one external release-feed call, and may issue
the single default-credential login attempt, none of which belong in an MCP tool.

Every tool here is one read-only GET against an already-allowlisted path
(`/api/systemSettings`, `/api/me/authorization`, `/api/system/info`).
"""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from dhis2w_core.profile import resolve_profile
from dhis2w_core.security_core import AccountAuthorities, VersionPosture
from dhis2w_core.v41.plugins.security import service
from dhis2w_core.v41.plugins.security.models import SecuritySettings

_READ = ToolAnnotations(readOnlyHint=True)


def register(mcp: Any) -> None:
    """Register the read-only `security_settings`, `security_authorities`, and `security_version` tools."""

    @mcp.tool(annotations=_READ)
    async def security_settings(profile: str | None = None) -> SecuritySettings:
        """Read the security slice of /api/systemSettings (one GET).

        Returns the typed security-relevant settings projection: password policy,
        failed-login lockout, self-registration, account recovery, and email
        verification. `profile` selects a named profile from the project or global
        `profiles.toml`. Omit to use the default (from `DHIS2_PROFILE` env, raw
        `DHIS2_URL/PAT` env, or the TOML `default`).
        """
        return await service.get_security_settings(resolve_profile(profile))

    @mcp.tool(annotations=_READ)
    async def security_authorities(profile: str | None = None) -> AccountAuthorities:
        """Read the authenticated account's effective authorities, risk-categorised (one GET).

        Reads /api/me/authorization and groups the account's authorities into the
        dangerous-authority taxonomy with a superuser flag. `profile` selects a
        named profile (see `security_settings` for precedence).
        """
        return await service.get_account_authorities(resolve_profile(profile))

    @mcp.tool(annotations=_READ)
    async def security_version(profile: str | None = None) -> VersionPosture:
        """Read the DHIS2 version and classify its EOL/advisory posture (one GET, no external egress).

        Reads /api/system/info once and classifies the reported version against the
        static advisory patch floor and end-of-life line rules, returning the raw
        version, its parsed parts, and the findings. It deliberately skips the
        external releases.dhis2.org feed, so this tool stays a single DHIS2 request
        with no external egress; the feed-based behind-latest-patch refinement is
        audit-only. `profile` selects a named profile (see `security_settings` for
        precedence).
        """
        return await service.get_version_posture(resolve_profile(profile))
