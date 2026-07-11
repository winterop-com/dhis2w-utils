"""Tests for the per-version accessor dispatch + version-mismatch guards."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway BasicAuth for connect tests."""
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_top_level_error_class_catches_a_v41_bound_client_error() -> None:
    """Errors are shared across trees: the top-level Dhis2ApiError catches a v41-bound client's error.

    Regression for the per-version-exception-class footgun — each tree used to define its own
    Dhis2ClientError, so `except dhis2w_client.Dhis2ApiError` silently missed v41/v43 errors.
    """
    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.41.0"})
    )
    respx.get("https://dhis2.example/api/dataElements/MISSING").mock(
        return_value=httpx.Response(404, json={"httpStatus": "Not Found", "message": "nope"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        assert client.version_key == "v41"
        with pytest.raises(Dhis2ApiError) as exc_info:  # top-level (v42-baseline) class
            await client.data_elements.get("MISSING")
    assert exc_info.value.status_code == 404


def _mock_redirect_probe() -> None:
    """Mock the unauthenticated canonical-URL resolution probe."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))


@respx.mock
async def test_top_level_client_against_v42_keeps_v42_accessors() -> None:
    """Default Dhis2Client (== v42 class) talking to a v42 server keeps its v42 accessors."""
    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        assert client.version_key == "v42"
        assert client.category_combos.__class__.__module__ == "dhis2w_client.v42.category_combos"
        assert client.maintenance.__class__.__module__ == "dhis2w_client.v42.maintenance"


@respx.mock
async def test_top_level_client_against_v43_dispatches_to_v43_accessors() -> None:
    """Default Dhis2Client talking to a v43 server gets its accessors swapped to v43 classes."""
    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        assert client.version_key == "v43"
        assert client.category_combos.__class__.__module__ == "dhis2w_client.v43.category_combos"
        assert client.maintenance.__class__.__module__ == "dhis2w_client.v43.maintenance"


@respx.mock
async def test_top_level_client_against_v41_dispatches_to_v41_accessors() -> None:
    """Default Dhis2Client talking to a v41 server gets its accessors swapped to v41 classes."""
    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.41.0"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth(), allow_version_fallback=True) as client:
        assert client.version_key == "v41"
        assert client.category_combos.__class__.__module__ == "dhis2w_client.v41.category_combos"


@respx.mock
async def test_connect_primes_system_cache_with_bound_tree_model() -> None:
    """After a rebind to v43, the primed system-info cache holds v43's SystemInfo, not the v42 baseline's."""
    _mock_redirect_probe()
    info_route = respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        info = await client.system.info()
    assert info_route.call_count == 1  # connect's fetch primed the cache; info() was a free read
    assert type(info).__module__.startswith("dhis2w_client.generated.v43")


@respx.mock
async def test_connect_primes_system_cache_with_v41_tree_model() -> None:
    """Same priming guarantee for a v41 rebind."""
    _mock_redirect_probe()
    info_route = respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.41.0"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        info = await client.system.info()
    assert info_route.call_count == 1
    assert type(info).__module__.startswith("dhis2w_client.generated.v41")


@respx.mock
async def test_v43_client_class_against_v42_server_raises() -> None:
    """Direct use of `dhis2w_client.v43.client.Dhis2Client` against a v42 server is a hard error."""
    from dhis2w_client.v43.client import Dhis2Client as V43Client

    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"})
    )
    with pytest.raises(RuntimeError, match="v43.client.Dhis2Client connected to"):
        async with V43Client("https://dhis2.example", auth=_auth(), version=None):
            pass


@respx.mock
async def test_v41_client_class_against_v42_server_raises() -> None:
    """Direct use of `dhis2w_client.v41.client.Dhis2Client` against a v42 server is a hard error."""
    from dhis2w_client.v41.client import Dhis2Client as V41Client

    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"})
    )
    with pytest.raises(RuntimeError, match="v41.client.Dhis2Client connected to"):
        async with V41Client("https://dhis2.example", auth=_auth(), version=None):
            pass


@respx.mock
async def test_v43_wait_for_coc_fires_maintenance_trigger() -> None:
    """v43 servers: wait_for_coc_generation calls /api/maintenance/categoryOptionComboUpdate (BUGS.md #33)."""
    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0"})
    )
    maintenance_route = respx.post("https://dhis2.example/api/maintenance/categoryOptionComboUpdate").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"})
    )
    respx.get("https://dhis2.example/api/categoryOptionCombos").mock(
        return_value=httpx.Response(200, json={"categoryOptionCombos": [{"id": "COC_1"}, {"id": "COC_2"}]})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        landed = await client.category_combos.wait_for_coc_generation(
            "CC_X", expected_count=2, timeout_seconds=2.0, poll_interval_seconds=0.01
        )
    assert landed == 2
    assert maintenance_route.called


@respx.mock
async def test_v42_wait_for_coc_skips_maintenance_trigger() -> None:
    """v42 servers auto-regenerate COCs at save time — no maintenance round-trip needed."""
    _mock_redirect_probe()
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"})
    )
    maintenance_route = respx.post("https://dhis2.example/api/maintenance/categoryOptionComboUpdate").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"})
    )
    respx.get("https://dhis2.example/api/categoryOptionCombos").mock(
        return_value=httpx.Response(200, json={"categoryOptionCombos": [{"id": "COC_1"}, {"id": "COC_2"}]})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        landed = await client.category_combos.wait_for_coc_generation(
            "CC_X", expected_count=2, timeout_seconds=2.0, poll_interval_seconds=0.01
        )
    assert landed == 2
    assert not maintenance_route.called
