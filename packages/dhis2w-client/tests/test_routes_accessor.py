"""Tests for `Dhis2Client.routes` — code -> uid resolve + /run proxy wiring."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


_ROUTE_LOOKUP_BODY = {
    "pager": {"page": 1, "pageSize": 1, "total": 1, "pageCount": 1},
    "routes": [{"id": "Rabcdef1234", "code": "health-upstream"}],
}


@respx.mock
async def test_run_resolves_code_to_uid_then_proxies_get(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """run(code, path) does one /api/routes lookup, then GETs /api/routes/<uid>/run/<path>."""
    mock_system_info(server_version)
    lookup_route = respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(200, json=_ROUTE_LOOKUP_BODY),
    )
    run_route = respx.get("https://dhis2.example/api/routes/Rabcdef1234/run/status").mock(
        return_value=httpx.Response(200, json={"ok": True}),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        response = await client.routes.run("health-upstream", "status")
    assert lookup_route.call_count == 1
    assert run_route.call_count == 1
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@respx.mock
async def test_run_caches_uid_across_calls(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Second run() against the same code skips the /api/routes lookup."""
    mock_system_info(server_version)
    lookup_route = respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(200, json=_ROUTE_LOOKUP_BODY),
    )
    respx.get("https://dhis2.example/api/routes/Rabcdef1234/run").mock(
        return_value=httpx.Response(200, text="up"),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.routes.run("health-upstream")
        await client.routes.run("health-upstream")
    assert lookup_route.call_count == 1


@respx.mock
async def test_run_use_cache_false_refetches_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Passing use_cache=False forces a fresh /api/routes lookup even when cached."""
    mock_system_info(server_version)
    lookup_route = respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(200, json=_ROUTE_LOOKUP_BODY),
    )
    respx.get("https://dhis2.example/api/routes/Rabcdef1234/run").mock(
        return_value=httpx.Response(200, text="up"),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.routes.run("health-upstream")
        await client.routes.run("health-upstream", use_cache=False)
    assert lookup_route.call_count == 2


@respx.mock
async def test_run_surfaces_non_2xx_without_raising(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """502 from the proxy lands as response.status_code, not a Dhis2ApiError."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(200, json=_ROUTE_LOOKUP_BODY),
    )
    respx.get("https://dhis2.example/api/routes/Rabcdef1234/run/probe").mock(
        return_value=httpx.Response(502, text="upstream down"),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        response = await client.routes.run("health-upstream", "probe")
    assert response.status_code == 502
    assert response.text == "upstream down"


@respx.mock
async def test_run_raises_lookup_error_when_code_unknown(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """No matching Route -> LookupError, no /run call attempted."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(
            200,
            json={"pager": {"page": 1, "pageSize": 1, "total": 0, "pageCount": 0}, "routes": []},
        ),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        with pytest.raises(LookupError):
            await client.routes.run("does-not-exist")


@respx.mock
async def test_invalidate_cache_drops_one_entry(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """invalidate_cache(code) forces re-lookup for that code only."""
    mock_system_info(server_version)
    lookup_route = respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(200, json=_ROUTE_LOOKUP_BODY),
    )
    respx.get("https://dhis2.example/api/routes/Rabcdef1234/run").mock(
        return_value=httpx.Response(200, text="up"),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.routes.run("health-upstream")
        client.routes.invalidate_cache("health-upstream")
        await client.routes.run("health-upstream")
    assert lookup_route.call_count == 2


@respx.mock
async def test_run_forwards_params_and_extra_headers(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """params=... lands on the query string; extra_headers lands on the request."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/routes").mock(
        return_value=httpx.Response(200, json=_ROUTE_LOOKUP_BODY),
    )
    seen: dict[str, httpx.Request] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        """Snapshot the request so the test can assert on params + headers."""
        seen["request"] = request
        return httpx.Response(200, text="ok")

    respx.get("https://dhis2.example/api/routes/Rabcdef1234/run/q").mock(side_effect=_capture)
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.routes.run(
            "health-upstream",
            "q",
            params={"q": "alpha"},
            extra_headers={"X-Probe": "1"},
        )
    request = seen["request"]
    assert request.url.params["q"] == "alpha"
    assert request.headers["x-probe"] == "1"
