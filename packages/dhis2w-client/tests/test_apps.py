"""Tests for `Dhis2Client.apps` — /api/apps + /api/appHub wiring."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


_INSTALLED_APPS_PAYLOAD = [
    {
        "key": "dashboard-widget",
        "name": "Dashboard Widget",
        "displayName": "Dashboard Widget",
        "version": "1.0.0",
        "appType": "DASHBOARD_WIDGET",
        "bundled": False,
        "app_hub_id": "hub-widget-001",
    },
    {
        "key": "core-import-export",
        "name": "Import/Export",
        "version": "42.0.0",
        "bundled": True,
    },
]

_HUB_PAYLOAD = [
    {
        "id": "hub-widget-001",
        "name": "Dashboard Widget",
        "versions": [
            {"id": "ver-100", "version": "1.0.0"},
            {"id": "ver-200", "version": "2.0.0"},
        ],
    },
]


@respx.mock
async def test_list_apps_parses_installed_rows(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """GET /api/apps → typed list[App]; bundled + non-bundled both land."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/apps").mock(
        return_value=httpx.Response(200, json=_INSTALLED_APPS_PAYLOAD),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        apps = await client.apps.list_apps()
    assert len(apps) == 2
    widget = next(a for a in apps if a.key == "dashboard-widget")
    assert widget.version == "1.0.0"
    assert widget.app_hub_id == "hub-widget-001"
    assert widget.bundled is False
    core = next(a for a in apps if a.key == "core-import-export")
    assert core.bundled is True


@respx.mock
async def test_get_returns_none_when_key_not_installed(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`apps.get('missing')` falls through to None rather than raising."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED_APPS_PAYLOAD))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        assert await client.apps.get("missing") is None
        hit = await client.apps.get("dashboard-widget")
        assert hit is not None
        assert hit.version == "1.0.0"


@respx.mock
async def test_install_from_file_posts_multipart(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`install_from_file` uploads the zip as `file=` in multipart/form-data."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/apps").mock(return_value=httpx.Response(204))
    zip_path = tmp_path / "widget.zip"
    zip_path.write_bytes(b"fake-zip-bytes")
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.apps.install_from_file(zip_path)
    assert route.called
    body = route.calls.last.request.content
    # multipart bodies contain the filename + content-type headers; spot-check them.
    assert b'filename="widget.zip"' in body
    assert b"application/zip" in body
    assert b"fake-zip-bytes" in body


@respx.mock
async def test_install_from_hub_posts_to_versioned_path(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`install_from_hub('abc')` → POST /api/appHub/abc."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/appHub/abc-123").mock(return_value=httpx.Response(201))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.apps.install_from_hub("abc-123")
    assert route.called


@respx.mock
async def test_uninstall_calls_delete_on_app_key(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`uninstall('k')` → DELETE /api/apps/k."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/apps/my-app").mock(return_value=httpx.Response(204))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.apps.uninstall("my-app")
    assert route.called


@respx.mock
async def test_reload_calls_put_on_apps(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`reload()` → PUT /api/apps (reload from disk; no payload)."""
    mock_system_info(server_version)
    route = respx.put("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.apps.reload()
    assert route.called


@respx.mock
async def test_hub_list_parses_catalog_rows(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """GET /api/appHub → typed list[AppHubApp] with nested version records."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB_PAYLOAD))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        hub = await client.apps.hub_list()
    assert len(hub) == 1
    assert hub[0].id == "hub-widget-001"
    assert len(hub[0].versions) == 2
    assert hub[0].versions[0].version == "1.0.0"


@respx.mock
async def test_hub_list_applies_client_side_query_filter(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`hub_list(query=...)` narrows the catalog by case-insensitive name / description substring."""
    mock_system_info(server_version)
    payload = [
        {"id": "a", "name": "Dashboard Widget"},
        {"id": "b", "name": "Reports App", "description": "Aggregated Dashboard insights"},
        {"id": "c", "name": "Something else"},
    ]
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=payload))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        hits = await client.apps.hub_list(query="DASHBOARD")
    ids = {h.id for h in hits}
    assert ids == {"a", "b"}


@respx.mock
async def test_hub_list_ingests_epoch_millis_created_field(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Per BUGS.md #30, `versions[*].created` is an int on the wire — the model absorbs it."""
    mock_system_info(server_version)
    payload = [
        {
            "id": "hub-x",
            "name": "X",
            "versions": [{"id": "v1", "version": "1.0.0", "created": 1_747_820_526_374}],
        },
    ]
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=payload))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        hub = await client.apps.hub_list()
    assert hub[0].versions[0].created == 1_747_820_526_374


@respx.mock
async def test_get_hub_url_reads_system_setting(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`get_hub_url` unwraps DHIS2's `{keyAppHubUrl: "..."}` envelope."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/systemSettings/keyAppHubUrl").mock(
        return_value=httpx.Response(200, json={"keyAppHubUrl": "https://custom.hub.example/api"}),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        url = await client.apps.get_hub_url()
    assert url == "https://custom.hub.example/api"


@respx.mock
async def test_set_hub_url_posts_text_plain_body(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`set_hub_url('https://x/api')` POSTs the raw URL as text/plain."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/systemSettings/keyAppHubUrl").mock(
        return_value=httpx.Response(200),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.apps.set_hub_url("https://custom.hub.example/api")
    assert route.called
    assert route.calls.last.request.content == b"https://custom.hub.example/api"
    assert route.calls.last.request.headers.get("content-type") == "text/plain"


@respx.mock
async def test_restore_reinstalls_hub_backed_entries_and_skips_side_loaded(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """restore() posts /api/appHub/{versionId} for hub entries with a version drift + SKIPs the rest."""
    from dhis2w_client import AppsSnapshot

    mock_system_info(server_version)
    installed_now = [
        {
            "key": "hub-app",
            "name": "Hub App",
            "displayName": "Hub App",
            "version": "1.0.0",
            "bundled": False,
            "app_hub_id": "hub-widget-001",
        },
        {
            "key": "matches",
            "name": "Already At Snapshot Version",
            "version": "3.0.0",
            "bundled": False,
            "app_hub_id": "hub-matches",
        },
    ]
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=installed_now))
    install_hub = respx.post("https://dhis2.example/api/appHub/ver-200").mock(return_value=httpx.Response(201))
    install_matches = respx.post("https://dhis2.example/api/appHub/ver-300").mock(return_value=httpx.Response(201))

    snapshot = AppsSnapshot.model_validate(
        {
            "entries": [
                {
                    "key": "hub-app",
                    "name": "Hub App",
                    "version": "2.0.0",
                    "app_hub_id": "hub-widget-001",
                    "source": "app-hub",
                    "hub_version_id": "ver-200",
                },
                {
                    "key": "matches",
                    "name": "Already At Snapshot Version",
                    "version": "3.0.0",
                    "app_hub_id": "hub-matches",
                    "source": "app-hub",
                    "hub_version_id": "ver-300",
                },
                {
                    "key": "side-loaded",
                    "name": "Side Loaded",
                    "version": "0.1.0",
                    "source": "side-loaded",
                },
            ],
        },
    )

    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        summary = await client.apps.restore(snapshot)

    assert summary.restored == 1
    assert summary.up_to_date == 1
    assert summary.skipped == 1
    assert summary.failed == 0
    assert install_hub.called
    assert not install_matches.called

    hub_outcome = next(o for o in summary.outcomes if o.key == "hub-app")
    assert hub_outcome.status == "RESTORED"
    assert hub_outcome.from_version == "1.0.0"
    assert hub_outcome.to_version == "2.0.0"

    match_outcome = next(o for o in summary.outcomes if o.key == "matches")
    assert match_outcome.status == "UP_TO_DATE"

    side = next(o for o in summary.outcomes if o.key == "side-loaded")
    assert side.status == "SKIPPED"
    assert side.reason is not None
    assert "hub_version_id" in side.reason


@respx.mock
async def test_restore_dry_run_reports_available_without_posting(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`dry_run=True` tags would-install entries as AVAILABLE; no install POSTs."""
    from dhis2w_client import AppsSnapshot

    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=[]))
    install_route = respx.post("https://dhis2.example/api/appHub/ver-xyz").mock(return_value=httpx.Response(201))

    snapshot = AppsSnapshot.model_validate(
        {
            "entries": [
                {
                    "key": "new-app",
                    "name": "New App",
                    "version": "1.2.3",
                    "app_hub_id": "hub-new",
                    "source": "app-hub",
                    "hub_version_id": "ver-xyz",
                },
            ],
        },
    )

    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        summary = await client.apps.restore(snapshot, dry_run=True)

    assert summary.restored == 0
    assert summary.available == 1
    assert not install_route.called


@respx.mock
async def test_snapshot_captures_installed_apps_with_hub_version_id(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """snapshot() cross-references installed apps with the hub catalog to find a rehydration target."""
    mock_system_info(server_version)
    installed = [
        {
            "key": "hub-app",
            "name": "Hub App",
            "displayName": "Hub App",
            "version": "2.0.0",
            "bundled": False,
            "app_hub_id": "hub-widget-001",
        },
        {
            "key": "side-loaded",
            "name": "Side Loaded",
            "version": "0.1.0",
            "bundled": False,
        },
    ]
    hub = [
        {
            "id": "hub-widget-001",
            "name": "Hub App",
            "versions": [
                {"id": "ver-100", "version": "1.0.0", "download_url": "https://hub/v1.zip"},
                {"id": "ver-200", "version": "2.0.0", "download_url": "https://hub/v2.zip"},
            ],
        },
    ]
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=installed))
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=hub))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        snap = await client.apps.snapshot()
    assert len(snap.entries) == 2
    assert snap.hub_backed == 1
    assert snap.side_loaded == 1
    hub_entry = next(e for e in snap.entries if e.key == "hub-app")
    assert hub_entry.source == "app-hub"
    assert hub_entry.hub_version_id == "ver-200"
    assert hub_entry.hub_download_url == "https://hub/v2.zip"
    side_entry = next(e for e in snap.entries if e.key == "side-loaded")
    assert side_entry.source == "side-loaded"
    assert side_entry.hub_version_id is None


@respx.mock
async def test_set_hub_url_none_deletes_setting(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`set_hub_url(None)` sends a DELETE so DHIS2 reverts to its default hub."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/systemSettings/keyAppHubUrl").mock(
        return_value=httpx.Response(204),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.apps.set_hub_url(None)
    assert route.called
