"""Service layer for the `apps` plugin — thin orchestration + update-logic.

The only non-trivial logic is picking the "latest" App Hub version for a
given installed app: we match installed apps to hub catalog entries via
`App.app_hub_id`, then pick the version with the highest numeric semver.
If the installed version already matches (or is greater), the app is
reported as `UP_TO_DATE`. Apps without an `app_hub_id` (side-loaded zips)
are reported as `SKIPPED`; the App Hub has no copy of them.

Bundled core apps (`bundled=True`) keep their `app_hub_id` — DHIS2 lets
the App Hub overwrite the bundled copy in place, and the DHIS2 App
Management UI surfaces hub updates for those apps alongside non-bundled
ones, so the service treats them the same.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dhis2w_client.v43 import App, AppHubApp, AppsSnapshot, RestoreSummary

from dhis2w_core.profile import Profile
from dhis2w_core.v43.client_context import open_client
from dhis2w_core.v43.plugins.apps.models import InstallTarget, UpdateOutcome, UpdateSummary

if TYPE_CHECKING:
    from dhis2w_client.v43 import Dhis2Client


class InstallTargetError(LookupError):
    """Raised when `apps add` cannot resolve an id to an App Hub version (handled cleanly by the CLI)."""


async def list_apps(profile: Profile) -> list[App]:
    """Return every installed app — typed list of generated `App` records."""
    async with open_client(profile) as client:
        return await client.apps.list_apps()


async def get_app(profile: Profile, key: str) -> App | None:
    """Return one installed app by `key` (folder name); None if not installed."""
    async with open_client(profile) as client:
        return await client.apps.get(key)


async def install_from_file(profile: Profile, path: Path | str) -> None:
    """Install / update an app from a local `.zip`."""
    async with open_client(profile) as client:
        await client.apps.install_from_file(path)


async def install_from_hub(profile: Profile, app_or_version_id: str) -> InstallTarget:
    """Install an App Hub app by version id, or by app id (latest version is resolved).

    DHIS2's `POST /api/appHub/{versionId}` only accepts a version id; handing it
    an app id 404s through the server's App Hub proxy (BUGS.md #46). App ids and
    version ids are both bare UUIDs, so this resolves the given id against the
    configured catalog (`GET /api/appHub`): a version id installs directly; an
    app id resolves to that app's latest version. Raises `InstallTargetError`
    when the id matches neither.
    """
    async with open_client(profile) as client:
        catalog = await client.apps.hub_list()
        target = _resolve_install_target(catalog, app_or_version_id)
        await client.apps.install_from_hub(target.version_id)
        return target


def _resolve_install_target(catalog: list[AppHubApp], app_or_version_id: str) -> InstallTarget:
    """Classify an id against the hub catalog: a version id installs as-is; an app id picks its latest version."""
    for app in catalog:
        for version in app.versions:
            if version.id == app_or_version_id:
                return InstallTarget(
                    version_id=app_or_version_id,
                    app_name=app.name,
                    version=version.version,
                    resolved_from="version-id",
                )
    for app in catalog:
        if app.id == app_or_version_id:
            if not app.versions:
                raise InstallTargetError(f"App Hub app {app.name or app_or_version_id!r} has no published versions")
            latest = max(app.versions, key=lambda v: _version_key(v.version))
            if not latest.id:
                raise InstallTargetError(
                    f"App Hub app {app.name or app_or_version_id!r} latest version record is missing its id",
                )
            return InstallTarget(
                version_id=latest.id,
                app_name=app.name,
                version=latest.version,
                resolved_from="app-id",
            )
    raise InstallTargetError(
        f"{app_or_version_id!r} is neither an App Hub version id nor an app id in the configured "
        "catalog (GET /api/appHub) - run `d2w apps hub-list` to find a valid version id",
    )


async def uninstall(profile: Profile, key: str) -> None:
    """Remove an installed app by `key`."""
    async with open_client(profile) as client:
        await client.apps.uninstall(key)


async def reload_apps(profile: Profile) -> None:
    """Trigger DHIS2 to re-read every app from disk (no new versions fetched)."""
    async with open_client(profile) as client:
        await client.apps.reload()


async def hub_list(profile: Profile, *, query: str | None = None) -> list[AppHubApp]:
    """List every app in the configured App Hub (proxied server-side).

    `query` applies a case-insensitive substring filter on `name` + `description`.
    """
    async with open_client(profile) as client:
        return await client.apps.hub_list(query=query)


async def hub_versions(profile: Profile, app_id: str) -> AppHubApp:
    """Return one App Hub app by its app id, versions sorted newest-first.

    The catalog (`GET /api/appHub`) carries each app's full version list; this
    finds the app by `app_id` and returns it with versions ordered by descending
    semver. Each version's `id` is a `d2w apps add <id>` target (pins that exact
    version). Raises `InstallTargetError` when `app_id` is not an app id in the
    catalog.
    """
    async with open_client(profile) as client:
        catalog = await client.apps.hub_list()
    app = next((entry for entry in catalog if entry.id == app_id), None)
    if app is None:
        raise InstallTargetError(
            f"{app_id!r} is not an App Hub app id in the configured catalog (GET /api/appHub) "
            "- run `d2w apps hub-list` to find an app id",
        )
    ordered = sorted(app.versions, key=lambda version: _version_key(version.version), reverse=True)
    return app.model_copy(update={"versions": ordered})


async def snapshot(profile: Profile) -> AppsSnapshot:
    """Return a typed `AppsSnapshot` of every installed app (for backup / transfer)."""
    async with open_client(profile) as client:
        return await client.apps.snapshot()


async def restore(profile: Profile, snapshot: AppsSnapshot, *, dry_run: bool = False) -> RestoreSummary:
    """Reinstall every hub-backed entry in `snapshot` via `install_from_hub`.

    `dry_run=True` reports `AVAILABLE` without calling the install
    endpoint. Side-loaded entries + entries already at the snapshot's
    version are reported but not acted on.
    """
    async with open_client(profile) as client:
        return await client.apps.restore(snapshot, dry_run=dry_run)


async def get_hub_url(profile: Profile) -> str | None:
    """Return the DHIS2 `keyAppHubUrl` system setting (or None when server default)."""
    async with open_client(profile) as client:
        return await client.apps.get_hub_url()


async def set_hub_url(profile: Profile, url: str | None) -> None:
    """Point DHIS2 at a different App Hub by writing the `keyAppHubUrl` system setting.

    Pass `url=None` to clear the setting; DHIS2 falls back to its default hub.
    """
    async with open_client(profile) as client:
        await client.apps.set_hub_url(url)


async def update_one(profile: Profile, key: str, *, dry_run: bool = False) -> UpdateOutcome:
    """Update a single installed app to its latest App Hub version.

    Resolves the installed app, matches it to the hub catalog, picks the
    latest version, and POSTs `/api/appHub/{versionId}` if newer.
    `dry_run=True` reports what would happen (status `AVAILABLE`) without
    calling the install endpoint.
    """
    async with open_client(profile) as client:
        app = await client.apps.get(key)
        if app is None:
            return UpdateOutcome(
                key=key,
                name=key,
                status="FAILED",
                reason=f"no installed app with key {key!r}",
            )
        hub = await client.apps.hub_list()
        return await _apply_update(client, app, hub, dry_run=dry_run)


async def update_all(profile: Profile, *, dry_run: bool = False) -> UpdateSummary:
    """Walk every installed app and update each one to the latest hub version.

    One App Hub query up front (`GET /api/appHub`), then an install call per
    app that has a newer version. Apps without an `app_hub_id` are reported
    as `SKIPPED` (they're side-loaded zips; only their owner can push a new
    version). `bundled=True` apps still carry an `app_hub_id` — DHIS2 lets
    the App Hub overwrite the bundled copy in place, so they update like
    any other hub-backed app. `dry_run=True` walks the same matching logic
    but tags available updates as `AVAILABLE` and skips every install POST
    — useful for "what would change?" previews ahead of a real run.
    """
    outcomes: list[UpdateOutcome] = []
    async with open_client(profile) as client:
        installed = await client.apps.list_apps()
        hub = await client.apps.hub_list()
        for app in installed:
            outcomes.append(await _apply_update(client, app, hub, dry_run=dry_run))
    return UpdateSummary(outcomes=outcomes)


async def _apply_update(
    client: Dhis2Client,
    app: App,
    hub: list[AppHubApp],
    *,
    dry_run: bool = False,
) -> UpdateOutcome:
    """Figure out the right action for one installed app + hit the install endpoint if needed."""
    key = app.key or app.folderName or app.name or "?"
    display = app.displayName or app.name or key
    current = app.version
    # `bundled=True` only means the app shipped inside DHIS2's WAR — it still
    # carries an `app_hub_id` and the App Hub can ship a newer version of
    # `reports`, `cache-cleaner`, etc. Overwriting the bundled copy is the
    # same POST /api/appHub/{versionId} as any other install. The only signal
    # that an app isn't hub-updatable is a missing `app_hub_id` (side-loaded
    # zip).
    if not app.app_hub_id:
        return UpdateOutcome(
            key=key,
            name=display,
            from_version=current,
            status="SKIPPED",
            reason="no app_hub_id on this installed app (side-loaded zip?)",
        )
    catalog = next((h for h in hub if h.id == app.app_hub_id), None)
    if catalog is None or not catalog.versions:
        return UpdateOutcome(
            key=key,
            name=display,
            from_version=current,
            status="SKIPPED",
            reason=f"App Hub has no versions for id {app.app_hub_id!r}",
        )
    # Pick the hub version with the highest semver. Sort by `version` string
    # descending — DHIS2 App Hub versions look like "1.2.3" so a plain-string
    # compare over tuple(int parts) handles the common case; fall back to
    # lexicographic when parts aren't numeric.
    latest = max(catalog.versions, key=lambda v: _version_key(v.version))
    if latest.version == current or _version_key(latest.version) <= _version_key(current):
        return UpdateOutcome(
            key=key,
            name=display,
            from_version=current,
            to_version=latest.version,
            status="UP_TO_DATE",
        )
    if not latest.id:
        return UpdateOutcome(
            key=key,
            name=display,
            from_version=current,
            to_version=latest.version,
            status="FAILED",
            reason="hub version record missing its id",
        )
    if dry_run:
        return UpdateOutcome(
            key=key,
            name=display,
            from_version=current,
            to_version=latest.version,
            status="AVAILABLE",
        )
    try:
        await client.apps.install_from_hub(latest.id)
    except Exception as exc:  # noqa: BLE001 — capture the reason for the summary row
        return UpdateOutcome(
            key=key,
            name=display,
            from_version=current,
            to_version=latest.version,
            status="FAILED",
            reason=f"{type(exc).__name__}: {exc}",
        )
    return UpdateOutcome(
        key=key,
        name=display,
        from_version=current,
        to_version=latest.version,
        status="UPDATED",
    )


def _version_key(value: str | None) -> tuple[int, ...]:
    """Parse `'1.2.3'` → `(1, 2, 3)` for comparison; `(0, 0, 0)` on missing / non-numeric."""
    if not value:
        return (0, 0, 0)
    parts: list[int] = []
    for token in value.split("."):
        try:
            parts.append(int(token))
        except ValueError:
            return (0, 0, 0)
    return tuple(parts)
