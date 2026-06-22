"""Per-version parity for the `datastore` plugin service — exercise every public function on all trees.

Resolves the service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed
and counted, not just smoke-imported. The three service trees are byte-identical copies (only the import
version differs), so the assertions are the same on every tree. Mocked (respx); no live stack. Endpoints
derive from the `DatastoreAccessor`: `/api/dataStore`, `/api/dataStore/{namespace}`, and
`/api/dataStore/{namespace}/{key}` (the per-user store swaps in `/api/userDataStore`).
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_namespaces_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_namespaces` GETs /api/dataStore and returns the namespace list, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    route = respx.get(f"{_HOST}/api/dataStore").mock(
        return_value=httpx.Response(200, json=["capture", "analytics"]),
    )

    result = await service.list_namespaces(resolve_profile("probe"))

    assert result == ["capture", "analytics"]
    assert route.called


@respx.mock
async def test_list_keys_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_keys` GETs /api/dataStore/{namespace} and returns the key list, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    route = respx.get(f"{_HOST}/api/dataStore/capture").mock(
        return_value=httpx.Response(200, json=["key1", "key2"]),
    )

    result = await service.list_keys(resolve_profile("probe"), "capture")

    assert result == ["key1", "key2"]
    assert route.called


@respx.mock
async def test_get_value_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_value` GETs /api/dataStore/{namespace}/{key} and returns the opaque JSON, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    route = respx.get(f"{_HOST}/api/dataStore/capture/settings").mock(
        return_value=httpx.Response(200, json={"enabled": True, "items": ["abc"]}),
    )

    result = await service.get_value(resolve_profile("probe"), "capture", "settings")

    assert result == {"enabled": True, "items": ["abc"]}
    assert route.called


@respx.mock
async def test_set_value_creates_with_post_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_value` POSTs the body when the key is absent (existence GET 404s), on every tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    respx.get(f"{_HOST}/api/dataStore/capture/settings").mock(
        return_value=httpx.Response(404, json={"message": "not found"}),
    )
    create = respx.post(f"{_HOST}/api/dataStore/capture/settings").mock(
        return_value=httpx.Response(201, json={"status": "OK"}),
    )

    await service.set_value(resolve_profile("probe"), "capture", "settings", {"a": 1})

    assert create.called
    assert create.calls.last.request.read() == b'{"a":1}'


@respx.mock
async def test_set_value_updates_with_put_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_value` PUTs the body when the key already exists (existence GET 200s), on every tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    respx.get(f"{_HOST}/api/dataStore/capture/settings").mock(
        return_value=httpx.Response(200, json={"a": 0}),
    )
    update = respx.put(f"{_HOST}/api/dataStore/capture/settings").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.set_value(resolve_profile("probe"), "capture", "settings", {"a": 1})

    assert update.called
    assert update.calls.last.request.read() == b'{"a":1}'


@respx.mock
async def test_delete_key_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_key` DELETEs /api/dataStore/{namespace}/{key}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    route = respx.delete(f"{_HOST}/api/dataStore/capture/settings").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.delete_key(resolve_profile("probe"), "capture", "settings")

    assert route.called


@respx.mock
async def test_delete_namespace_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_namespace` DELETEs /api/dataStore/{namespace}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("datastore")
    route = respx.delete(f"{_HOST}/api/dataStore/capture").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.delete_namespace(resolve_profile("probe"), "capture")

    assert route.called
