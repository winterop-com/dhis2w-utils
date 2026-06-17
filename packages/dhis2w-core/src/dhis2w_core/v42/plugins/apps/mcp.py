"""FastMCP tool registration for the `apps` plugin."""

from __future__ import annotations

from typing import Any

from dhis2w_client.v42 import App, AppHubApp, AppsSnapshot, RestoreSummary

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v42.plugins.apps import service
from dhis2w_core.v42.plugins.apps.models import InstallTarget, UpdateOutcome, UpdateSummary


def register(mcp: Any) -> None:
    """Register `apps_*` tools on the MCP server."""

    @mcp.tool()
    async def apps_list(profile: str | None = None) -> list[App]:
        """List every installed DHIS2 app (`GET /api/apps`). Returns typed App records."""
        return await service.list_apps(resolve_profile(profile))

    @mcp.tool()
    async def apps_get(key: str, profile: str | None = None) -> App | None:
        """Return one installed app by `key`; None if not installed."""
        return await service.get_app(resolve_profile(profile), key)

    @mcp.tool()
    async def apps_install_from_file(path: str, profile: str | None = None) -> None:
        """Install / update an app from a local `.zip` at `path` (`POST /api/apps`)."""
        await service.install_from_file(resolve_profile(profile), path)

    @mcp.tool()
    async def apps_install_from_hub(app_or_version_id: str, profile: str | None = None) -> InstallTarget:
        """Install an App Hub app by version id or app id; returns the resolved install target.

        A version id installs directly (`POST /api/appHub/{versionId}`); an app id
        resolves to that app's latest version first (App Hub app ids and version
        ids are both bare UUIDs - see BUGS.md #46).
        """
        return await service.install_from_hub(resolve_profile(profile), app_or_version_id)

    @mcp.tool()
    async def apps_uninstall(key: str, profile: str | None = None) -> None:
        """Remove an installed app by `key` (`DELETE /api/apps/{key}`)."""
        await service.uninstall(resolve_profile(profile), key)

    @mcp.tool()
    async def apps_reload(profile: str | None = None) -> None:
        """Re-read every app from disk (`PUT /api/apps`). No new versions fetched."""
        await service.reload_apps(resolve_profile(profile))

    @mcp.tool()
    async def apps_hub_list(query: str | None = None, profile: str | None = None) -> list[AppHubApp]:
        """List apps available in the configured App Hub (`GET /api/appHub`).

        `query` applies a case-insensitive substring filter on name +
        description; the filter runs client-side because DHIS2's
        `/api/appHub` proxy doesn't expose a server-side query
        parameter on v42.
        """
        return await service.hub_list(resolve_profile(profile), query=query)

    @mcp.tool()
    async def apps_hub_versions(app_id: str, profile: str | None = None) -> AppHubApp:
        """List every published version of one App Hub app by app id (newest first).

        Returns the catalog `AppHubApp` with its `versions` sorted by descending
        semver; each version's `id` is an `apps_install_from_hub` target that
        pins that exact version.
        """
        return await service.hub_versions(resolve_profile(profile), app_id)

    @mcp.tool()
    async def apps_restore(
        snapshot: AppsSnapshot,
        dry_run: bool = False,
        profile: str | None = None,
    ) -> RestoreSummary:
        """Reinstall every hub-backed entry in the given snapshot.

        Takes a typed `AppsSnapshot` (previously produced by
        `apps_snapshot`) and calls `install_from_hub` for each entry
        whose `hub_version_id` is set and whose currently installed
        version differs. Returns a per-app `RestoreSummary` matching
        the `apps_update_all` shape. `dry_run=True` tags would-install
        entries as `AVAILABLE` and skips every POST.
        """
        return await service.restore(resolve_profile(profile), snapshot, dry_run=dry_run)

    @mcp.tool()
    async def apps_snapshot(profile: str | None = None) -> AppsSnapshot:
        """Capture a portable inventory of every installed app.

        Each entry records the app's key / name / version / app_hub_id plus
        (when installed from the App Hub) the version_id + download_url
        needed to rehydrate it on another instance via
        `apps_install_from_hub(version_id)`. Side-loaded apps appear
        with `source='side-loaded'` and no reinstall target.
        """
        return await service.snapshot(resolve_profile(profile))

    @mcp.tool()
    async def apps_hub_url_get(profile: str | None = None) -> str | None:
        """Read DHIS2's configured App Hub URL (`keyAppHubUrl` system setting).

        Returns None when unset (DHIS2 uses its hard-coded default).
        """
        return await service.get_hub_url(resolve_profile(profile))

    @mcp.tool()
    async def apps_hub_url_set(url: str | None, profile: str | None = None) -> None:
        """Point DHIS2 at a different App Hub by writing the `keyAppHubUrl` system setting.

        Pass `url=None` to clear the setting; DHIS2 reverts to its
        default hub. The App Hub is open source
        (https://github.com/dhis2/app-hub), so self-hosted catalogs are
        supported.
        """
        await service.set_hub_url(resolve_profile(profile), url)

    @mcp.tool()
    async def apps_update(key: str, dry_run: bool = False, profile: str | None = None) -> UpdateOutcome:
        """Update a single installed app to its latest App Hub version.

        Pass `dry_run=True` to report whether a newer version exists without
        calling the install endpoint — outcome status is `AVAILABLE` when a
        newer hub version is present, `UP_TO_DATE` otherwise.
        """
        return await service.update_one(resolve_profile(profile), key, dry_run=dry_run)

    @mcp.tool()
    async def apps_update_all(dry_run: bool = False, profile: str | None = None) -> UpdateSummary:
        """Walk every installed app; install the latest App Hub version where available.

        Apps without an `app_hub_id` (side-loaded zips) are reported as
        `SKIPPED` in the returned summary. Bundled core apps with a hub id
        still update in place. `dry_run=True` tags available updates as
        `AVAILABLE` and skips every install POST.
        """
        return await service.update_all(resolve_profile(profile), dry_run=dry_run)
