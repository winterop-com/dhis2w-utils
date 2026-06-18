"""Per-version parity for the `route` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/route/test_route_*.py` routes + assertions, but resolves the service per
`core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_client import ReplaceOp
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_routes_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_routes` unwraps the `{pager, routes: [...]}` envelope from /api/routes, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    route = respx.get(f"{_HOST}/api/routes").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "routes": [
                    {"id": "E8OPcc45A22", "code": "chap", "name": "chap", "url": "http://upstream.example/get"},
                    {"id": "yt4aUhoQOqH", "code": "mrc", "name": "mrc", "url": "http://other.example/api/"},
                ],
            },
        ),
    )

    result = await service.list_routes(resolve_profile("probe"))

    assert [r.id for r in result] == ["E8OPcc45A22", "yt4aUhoQOqH"]
    assert route.calls.last.request.url.params["fields"] == "id,code,name,url,disabled"


@respx.mock
async def test_get_route_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_route` fetches a UID-shaped ref directly via /api/routes/{uid}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    route = respx.get(f"{_HOST}/api/routes/E8OPcc45A22").mock(
        return_value=httpx.Response(
            200,
            json={"id": "E8OPcc45A22", "code": "chap", "name": "chap", "url": "http://upstream.example/get"},
        ),
    )

    result = await service.get_route(resolve_profile("probe"), "E8OPcc45A22")

    assert result.id == "E8OPcc45A22"
    assert result.code == "chap"
    assert route.called


@respx.mock
async def test_add_route_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_route` serialises the typed payload as the POST /api/routes body, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    route = respx.post(f"{_HOST}/api/routes").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 201}),
    )

    response = await service.add_route(
        resolve_profile("probe"),
        service.RoutePayload(code="X", name="X route", url="https://u", authorities=["A", "B"]),
    )

    assert response.status == "OK"
    body = json.loads(route.calls.last.request.content)
    assert body == {"code": "X", "name": "X route", "url": "https://u", "authorities": ["A", "B"]}


@respx.mock
async def test_update_route_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`update_route` PUTs the full payload to /api/routes/{uid} for a UID-shaped ref, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    route = respx.put(f"{_HOST}/api/routes/E8OPcc45A22").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.update_route(
        resolve_profile("probe"),
        "E8OPcc45A22",
        service.RoutePayload(code="X", name="X renamed", url="https://u"),
    )

    assert response.status == "OK"
    body = json.loads(route.calls.last.request.content)
    assert body == {"code": "X", "name": "X renamed", "url": "https://u"}


@respx.mock
async def test_patch_route_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`patch_route` sends typed ops as a plain RFC 6902 JSON Patch array, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    route = respx.patch(f"{_HOST}/api/routes/E8OPcc45A22").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.patch_route(
        resolve_profile("probe"),
        "E8OPcc45A22",
        [ReplaceOp(path="/name", value="renamed")],
    )

    assert response.status == "OK"
    body = json.loads(route.calls.last.request.content)
    assert body == [{"op": "replace", "path": "/name", "value": "renamed"}]


@respx.mock
async def test_delete_route_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_route` DELETEs /api/routes/{uid} for a UID-shaped ref, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    route = respx.delete(f"{_HOST}/api/routes/E8OPcc45A22").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.delete_route(resolve_profile("probe"), "E8OPcc45A22")

    assert response.status == "OK"
    assert route.called


@respx.mock
async def test_run_route_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_route` pre-fetches the route then executes /api/routes/{uid}/run, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("route")
    fetch = respx.get(f"{_HOST}/api/routes/E8OPcc45A22").mock(
        return_value=httpx.Response(
            200,
            json={"id": "E8OPcc45A22", "url": "https://upstream.example/get-risk-map/"},
        ),
    )
    run = respx.get(f"{_HOST}/api/routes/E8OPcc45A22/run").mock(
        return_value=httpx.Response(200, json={"ok": True}),
    )

    result = await service.run_route(resolve_profile("probe"), "E8OPcc45A22")

    assert result == {"ok": True}
    assert fetch.called
    assert run.called
