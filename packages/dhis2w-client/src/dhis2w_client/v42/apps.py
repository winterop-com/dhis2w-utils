"""DHIS2 apps + App Hub — `/api/apps` and `/api/appHub`.

Covers the installed-apps surface (list / install from zip / install from App
Hub / uninstall / reload-from-disk) plus read-only App Hub queries used by
the `update` verbs in the `apps` plugin.

Terminology:

- An **installed app** is a row DHIS2 returns from `GET /api/apps`. Its
  identifier is the folder name (`key`); that's what the DELETE endpoint
  takes. `app_hub_id` on the installed record matches the App Hub's own
  `id` so an `update` verb can locate the latest version.
- An **App Hub app** is a catalog entry under `GET /api/appHub`. Each has
  a list of `versions`, each with a unique `id` (the `versionId` the
  install endpoint takes).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from dhis2w_client.generated.v42.oas import App
from dhis2w_client.generated.v42.oas._enums import AppStatus, AppType
from dhis2w_client.v42._collection import parse_rows

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client


class AppHubVersion(BaseModel):
    """One version of an App Hub app — the install target for `POST /api/appHub/{versionId}`."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=False)

    id: str | None = None
    version: str | None = None
    # Wire keys are camelCase `minDhisVersion` / `maxDhisVersion` (note: "Dhis", not "Dhis2").
    min_dhis2_version: str | None = Field(
        default=None, validation_alias=AliasChoices("min_dhis2_version", "minDhisVersion")
    )
    max_dhis2_version: str | None = Field(
        default=None, validation_alias=AliasChoices("max_dhis2_version", "maxDhisVersion")
    )
    # DHIS2's App Hub returns epoch-millis integers here (e.g. 1747820526374);
    # the type is lax to absorb both shapes without a custom validator.
    created: int | str | None = None
    last_updated: int | str | None = None
    download_url: str | None = None
    channel: str | None = None


class AppSnapshotEntry(BaseModel):
    """One row of an `AppsSnapshot` — a single installed app captured for later restore."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    version: str | None = None
    app_hub_id: str | None = None
    bundled: bool = False
    source: str  # "app-hub" | "side-loaded"
    hub_version_id: str | None = None
    hub_download_url: str | None = None


class RestoreOutcome(BaseModel):
    """Per-app result of an `apps.restore(snapshot)` call."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    from_version: str | None = None
    to_version: str | None = None
    status: str  # RESTORED / AVAILABLE / UP_TO_DATE / SKIPPED / FAILED
    reason: str | None = None


class RestoreSummary(BaseModel):
    """Aggregate of `apps.restore(...)` — rows plus totals for the table footer."""

    model_config = ConfigDict(frozen=True)

    outcomes: list[RestoreOutcome]

    @property
    def restored(self) -> int:
        """Count of apps successfully installed from their snapshot version."""
        return sum(1 for o in self.outcomes if o.status == "RESTORED")

    @property
    def available(self) -> int:
        """Count of apps that *would* restore under `dry_run=True`."""
        return sum(1 for o in self.outcomes if o.status == "AVAILABLE")

    @property
    def up_to_date(self) -> int:
        """Count of apps already at the snapshot's version (no-op)."""
        return sum(1 for o in self.outcomes if o.status == "UP_TO_DATE")

    @property
    def skipped(self) -> int:
        """Count of side-loaded entries with no hub version to restore from."""
        return sum(1 for o in self.outcomes if o.status == "SKIPPED")

    @property
    def failed(self) -> int:
        """Count of install calls that raised."""
        return sum(1 for o in self.outcomes if o.status == "FAILED")


class AppsSnapshot(BaseModel):
    """Typed inventory of every installed app — portable across instances."""

    model_config = ConfigDict(frozen=True)

    entries: list[AppSnapshotEntry]

    @property
    def hub_backed(self) -> int:
        """Count of entries that can be rehydrated via `install_from_hub`."""
        return sum(1 for e in self.entries if e.hub_version_id)

    @property
    def side_loaded(self) -> int:
        """Count of entries that have no hub match (need an external zip to restore)."""
        return sum(1 for e in self.entries if not e.hub_version_id)


class AppHubApp(BaseModel):
    """One catalog entry from `GET /api/appHub` — the App Hub's view of an app."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=False)

    id: str | None = None
    name: str | None = None
    app_type: str | None = None
    description: str | None = None
    developer: dict[str, Any] | None = None
    icons: dict[str, Any] | None = None
    versions: list[AppHubVersion] = []


class AppsAccessor:
    """`Dhis2Client.apps` — list / install / uninstall / reload + App Hub queries."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def list_apps(self) -> list[App]:
        """Return every installed app — `GET /api/apps`.

        The response body is a bare JSON array (no envelope key), so
        `get_raw` wraps it under `"data"` — unwrapping is a one-liner.
        Every row becomes a typed `App`; extra fields DHIS2 tacks on in
        minor versions ride through via `model_config = extra="allow"`.
        """
        raw = await self._client.get_raw("/api/apps")
        rows = _unwrap_array(raw)
        return parse_rows(rows, App)

    async def get(self, key: str) -> App | None:
        """Find one installed app by `key` (folder name). Returns None if not installed."""
        for app in await self.list_apps():
            if app.key == key:
                return app
        return None

    async def install_from_file(self, path: Path | str, *, filename: str | None = None) -> None:
        """Upload an `.zip` to `POST /api/apps` — installs or updates in place.

        DHIS2 accepts multipart/form-data with a single `file` field. On
        success the endpoint returns 204 No Content (or a thin JSON body);
        the caller then calls `list()` again to see the new row.
        `filename` overrides the on-the-wire filename (defaults to the
        local path's basename).
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"no such app zip: {file_path}")
        data = file_path.read_bytes()
        resolved_filename = filename or file_path.name
        await self._client._request(  # noqa: SLF001 — accessor is tight with the client
            "POST",
            "/api/apps",
            files={"file": (resolved_filename, data, "application/zip")},
        )

    async def install_from_hub(self, version_id: str) -> None:
        """Install a specific App Hub version — `POST /api/appHub/{versionId}`.

        DHIS2 streams the app zip from the App Hub server-side, so the
        local caller only supplies the `versionId` (usually a UUID the
        App Hub hands out). On success the installed row is returned
        from the next `list()` call.
        """
        if not version_id:
            raise ValueError("install_from_hub requires a non-empty version_id")
        await self._client.post_raw(f"/api/appHub/{version_id}")

    async def uninstall(self, key: str) -> None:
        """Remove an installed app by `key` — `DELETE /api/apps/{key}`."""
        if not key:
            raise ValueError("uninstall requires a non-empty app key")
        await self._client.delete_raw(f"/api/apps/{key}")

    async def reload(self) -> None:
        """Re-read every app from disk — `PUT /api/apps`. No new versions are fetched."""
        await self._client.put_raw("/api/apps")

    async def hub_list(self, *, query: str | None = None) -> list[AppHubApp]:
        """List every app in the configured App Hub — `GET /api/appHub`.

        DHIS2 proxies this call to the App Hub server the instance is
        pointed at (typically `apps.dhis2.org`, configurable via the
        `keyAppHubUrl` system setting). The response is a JSON array of
        hub-app records; each has a `versions` list whose `id` fields
        are install targets for `install_from_hub(version_id)`.

        `query` applies a case-insensitive substring filter on `name` +
        `description` after the full catalog lands — the App Hub proxy
        doesn't expose a server-side query parameter in v42, so the
        filter is client-side.
        """
        raw = await self._client.get_raw("/api/appHub")
        rows = _unwrap_array(raw)
        catalog = parse_rows(rows, AppHubApp)
        if not query:
            return catalog
        needle = query.lower()
        return [
            app
            for app in catalog
            if (app.name and needle in app.name.lower()) or (app.description and needle in app.description.lower())
        ]

    async def snapshot(self) -> AppsSnapshot:
        """Capture an inventory of every installed app into a typed snapshot.

        Each entry records the app's `key`, human name, installed
        `version`, and — when the app was installed from the App Hub —
        its `app_hub_id` plus the matching hub `version_id` +
        `download_url` so the snapshot is sufficient to rehydrate the
        same catalog on another instance via `install_from_hub`.

        Apps without an `app_hub_id` (side-loaded zips uploaded via the
        legacy UI or `install_from_file`) are captured too, but with
        `source="side-loaded"` + no reinstall target. A restore step
        would have to source those zips externally.
        """
        installed = await self.list_apps()
        hub = await self.hub_list()
        hub_by_id = {app.id: app for app in hub if app.id}
        entries: list[AppSnapshotEntry] = []
        for app in installed:
            hub_entry = hub_by_id.get(app.app_hub_id) if app.app_hub_id else None
            hub_version: AppHubVersion | None = None
            if hub_entry is not None and app.version is not None:
                hub_version = next(
                    (v for v in hub_entry.versions if v.version == app.version),
                    None,
                )
            entries.append(
                AppSnapshotEntry(
                    key=app.key or app.folderName or app.name or "?",
                    name=app.displayName or app.name or app.key or "?",
                    version=app.version,
                    app_hub_id=app.app_hub_id,
                    bundled=bool(app.bundled),
                    source="app-hub" if app.app_hub_id else "side-loaded",
                    hub_version_id=hub_version.id if hub_version else None,
                    hub_download_url=hub_version.download_url if hub_version else None,
                ),
            )
        return AppsSnapshot(entries=entries)

    async def restore(self, snapshot: AppsSnapshot, *, dry_run: bool = False) -> RestoreSummary:
        """Reinstall every hub-backed entry in `snapshot` via `install_from_hub`.

        For each entry:

        - Side-loaded apps (no `hub_version_id`) → `SKIPPED` with a reason.
        - App already installed at the same version → `UP_TO_DATE`, no POST.
        - `dry_run=True` + install would happen → `AVAILABLE`, no POST.
        - Otherwise → `POST /api/appHub/{hub_version_id}`, outcome
          `RESTORED` on 2xx or `FAILED` with the exception string.

        The flip side of `snapshot()` — same data model, opposite
        direction. Use to rehydrate a pinned app catalog on another
        instance or recover a known-good state after an upgrade.
        """
        installed_by_key = {app.key: app for app in await self.list_apps() if app.key}
        outcomes: list[RestoreOutcome] = []
        for entry in snapshot.entries:
            outcomes.append(await self._apply_restore(entry, installed_by_key, dry_run=dry_run))
        return RestoreSummary(outcomes=outcomes)

    async def _apply_restore(
        self,
        entry: AppSnapshotEntry,
        installed_by_key: dict[str, App],
        *,
        dry_run: bool,
    ) -> RestoreOutcome:
        """Classify one snapshot entry + install if needed; returns a `RestoreOutcome`."""
        installed = installed_by_key.get(entry.key)
        from_version = installed.version if installed else None
        if not entry.hub_version_id:
            return RestoreOutcome(
                key=entry.key,
                name=entry.name,
                from_version=from_version,
                to_version=entry.version,
                status="SKIPPED",
                reason="no hub_version_id in snapshot (side-loaded zip — needs external source)",
            )
        if from_version == entry.version:
            return RestoreOutcome(
                key=entry.key,
                name=entry.name,
                from_version=from_version,
                to_version=entry.version,
                status="UP_TO_DATE",
            )
        if dry_run:
            return RestoreOutcome(
                key=entry.key,
                name=entry.name,
                from_version=from_version,
                to_version=entry.version,
                status="AVAILABLE",
            )
        try:
            await self.install_from_hub(entry.hub_version_id)
        except Exception as exc:  # noqa: BLE001 — capture the reason for the summary row
            return RestoreOutcome(
                key=entry.key,
                name=entry.name,
                from_version=from_version,
                to_version=entry.version,
                status="FAILED",
                reason=f"{type(exc).__name__}: {exc}",
            )
        return RestoreOutcome(
            key=entry.key,
            name=entry.name,
            from_version=from_version,
            to_version=entry.version,
            status="RESTORED",
        )

    async def get_hub_url(self) -> str | None:
        """Return the configured App Hub URL (`keyAppHubUrl` system setting) or None if unset.

        When None, DHIS2 falls back to its hard-coded default
        (`https://apps.dhis2.org/api` on v42). The App Hub is open
        source (https://github.com/dhis2/app-hub); self-hosters can
        point their instance at a private catalog by setting this.
        """
        return await self._client.system.setting("keyAppHubUrl", use_cache=False)

    async def set_hub_url(self, url: str | None) -> None:
        """Set the `keyAppHubUrl` system setting — points DHIS2 at a different App Hub.

        Passing `None` clears the setting (server reverts to its
        hard-coded default). Any HTTP call that hits `/api/appHub` on
        this instance after this write uses the new URL.
        """
        await self._client.system.set_setting("keyAppHubUrl", url)


def _unwrap_array(raw: Any) -> list[Any]:
    """Unwrap a bare-array JSON response that `get_raw` wrapped as `{"data": [...]}`."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, list):
            return data
    return []


__all__ = [
    "App",
    "AppHubApp",
    "AppHubVersion",
    "AppSnapshotEntry",
    "AppStatus",
    "AppType",
    "AppsAccessor",
    "AppsSnapshot",
    "RestoreOutcome",
    "RestoreSummary",
]
