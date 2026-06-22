"""Per-version parity for the `apps` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/apps/test_apps_plugin.py` routes + payloads, but resolves the service per
`core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.

`install_from_file` is skipped: it reads a local `.zip` off disk and POSTs multipart, which needs a real
file on the filesystem rather than a respx route — out of scope for a wire-parity sweep.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"

_INSTALLED = [
    {
        "key": "widget",
        "name": "Dashboard Widget",
        "displayName": "Dashboard Widget",
        "version": "1.0.0",
        "bundled": False,
        "app_hub_id": "hub-widget",
    },
    {
        "key": "reports",
        "name": "Reports (bundled, hub-updatable)",
        "version": "100.2.0",
        "bundled": True,
        "app_hub_id": "hub-reports",
    },
    {
        "key": "side-loaded",
        "name": "Side-Loaded",
        "version": "0.1.0",
        "bundled": False,
    },
]

_HUB = [
    {
        "id": "hub-widget",
        "name": "Dashboard Widget",
        "versions": [
            {"id": "ver-100", "version": "1.0.0"},
            {"id": "ver-200", "version": "2.0.0"},
        ],
    },
    {
        "id": "hub-reports",
        "name": "Reports",
        "versions": [
            {"id": "ver-reports-1002", "version": "100.2.0"},
            {"id": "ver-reports-1003", "version": "100.3.0"},
        ],
    },
]


@respx.mock
async def test_list_apps_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_apps` parses `GET /api/apps` into typed `App` rows, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    route = respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))

    apps = await service.list_apps(resolve_profile("probe"))

    assert [app.key for app in apps] == ["widget", "reports", "side-loaded"]
    assert route.called


@respx.mock
async def test_get_app_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_app` returns one installed app by key, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))

    app = await service.get_app(resolve_profile("probe"), "widget")

    assert app is not None
    assert app.key == "widget"
    assert app.version == "1.0.0"


@respx.mock
async def test_install_from_hub_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`install_from_hub` resolves a version id and POSTs `/api/appHub/{id}`, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post(f"{_HOST}/api/appHub/ver-200").mock(return_value=httpx.Response(201))

    target = await service.install_from_hub(resolve_profile("probe"), "ver-200")

    assert install_route.called
    assert target.version_id == "ver-200"
    assert target.version == "2.0.0"
    assert target.resolved_from == "version-id"


@respx.mock
async def test_uninstall_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`uninstall` DELETEs `/api/apps/{key}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    route = respx.delete(f"{_HOST}/api/apps/widget").mock(return_value=httpx.Response(204))

    await service.uninstall(resolve_profile("probe"), "widget")

    assert route.called


@respx.mock
async def test_reload_apps_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`reload_apps` PUTs `/api/apps`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    route = respx.put(f"{_HOST}/api/apps").mock(return_value=httpx.Response(204))

    await service.reload_apps(resolve_profile("probe"))

    assert route.called


@respx.mock
async def test_hub_list_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`hub_list` parses `GET /api/appHub` into typed `AppHubApp` rows, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    route = respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))

    catalog = await service.hub_list(resolve_profile("probe"))

    assert [app.id for app in catalog] == ["hub-widget", "hub-reports"]
    assert route.called


@respx.mock
async def test_hub_list_with_query_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`hub_list(query=...)` filters the catalog client-side by name substring, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))

    catalog = await service.hub_list(resolve_profile("probe"), query="widget")

    assert [app.id for app in catalog] == ["hub-widget"]


@respx.mock
async def test_hub_versions_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`hub_versions` returns one hub app with versions sorted newest-first, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))

    record = await service.hub_versions(resolve_profile("probe"), "hub-widget")

    assert record.name == "Dashboard Widget"
    assert [v.version for v in record.versions] == ["2.0.0", "1.0.0"]
    assert [v.id for v in record.versions] == ["ver-200", "ver-100"]


@respx.mock
async def test_snapshot_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`snapshot` inventories installed apps, tagging hub-backed vs side-loaded, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))

    snap = await service.snapshot(resolve_profile("probe"))

    by_key = {entry.key: entry for entry in snap.entries}
    assert by_key["widget"].source == "app-hub"
    assert by_key["widget"].hub_version_id == "ver-100"
    assert by_key["side-loaded"].source == "side-loaded"
    assert by_key["side-loaded"].hub_version_id is None


@respx.mock
async def test_restore_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`restore` reinstalls hub-backed entries and skips side-loaded ones, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post(f"{_HOST}/api/appHub/ver-200").mock(return_value=httpx.Response(201))

    snap = await service.snapshot(resolve_profile("probe"))
    # Re-point the widget entry at a newer hub version so restore performs a real install POST.
    bumped = snap.model_copy(
        update={
            "entries": [
                entry.model_copy(update={"hub_version_id": "ver-200", "version": "2.0.0"})
                if entry.key == "widget"
                else entry
                for entry in snap.entries
            ],
        },
    )

    summary = await service.restore(resolve_profile("probe"), bumped)

    assert install_route.called
    by_key = {outcome.key: outcome for outcome in summary.outcomes}
    assert by_key["widget"].status == "RESTORED"
    assert by_key["side-loaded"].status == "SKIPPED"


@respx.mock
async def test_restore_dry_run_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`restore(dry_run=True)` reports AVAILABLE without POSTing, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post(f"{_HOST}/api/appHub/ver-200").mock(return_value=httpx.Response(201))

    snap = await service.snapshot(resolve_profile("probe"))
    bumped = snap.model_copy(
        update={
            "entries": [
                entry.model_copy(update={"hub_version_id": "ver-200", "version": "2.0.0"})
                if entry.key == "widget"
                else entry
                for entry in snap.entries
            ],
        },
    )

    summary = await service.restore(resolve_profile("probe"), bumped, dry_run=True)

    assert not install_route.called
    by_key = {outcome.key: outcome for outcome in summary.outcomes}
    assert by_key["widget"].status == "AVAILABLE"


@respx.mock
async def test_get_hub_url_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_hub_url` reads the `keyAppHubUrl` system setting, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/systemSettings/keyAppHubUrl").mock(
        return_value=httpx.Response(200, json={"keyAppHubUrl": "https://apps.example.org/api"}),
    )

    url = await service.get_hub_url(resolve_profile("probe"))

    assert url == "https://apps.example.org/api"


@respx.mock
async def test_set_hub_url_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_hub_url` POSTs the new value to the `keyAppHubUrl` system setting, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    route = respx.post(f"{_HOST}/api/systemSettings/keyAppHubUrl").mock(return_value=httpx.Response(200))

    await service.set_hub_url(resolve_profile("probe"), "https://apps.example.org/api")

    assert route.called
    assert route.calls.last.request.read() == b"https://apps.example.org/api"


@respx.mock
async def test_update_one_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`update_one` installs the latest hub version for one app, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=[_INSTALLED[0]]))
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post(f"{_HOST}/api/appHub/ver-200").mock(return_value=httpx.Response(201))

    outcome = await service.update_one(resolve_profile("probe"), "widget")

    assert install_route.called
    assert outcome.status == "UPDATED"
    assert outcome.from_version == "1.0.0"
    assert outcome.to_version == "2.0.0"


@respx.mock
async def test_update_all_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`update_all` updates hub-backed apps and skips side-loaded ones, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("apps")
    respx.get(f"{_HOST}/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))
    respx.get(f"{_HOST}/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    respx.post(f"{_HOST}/api/appHub/ver-200").mock(return_value=httpx.Response(201))
    respx.post(f"{_HOST}/api/appHub/ver-reports-1003").mock(return_value=httpx.Response(201))

    summary = await service.update_all(resolve_profile("probe"))

    assert summary.updated == 2
    assert summary.skipped == 1
    assert summary.failed == 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
