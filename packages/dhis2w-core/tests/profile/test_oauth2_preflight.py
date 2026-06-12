"""Unit tests for the OAuth2 Authorization Server preflight probe."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.oauth2_preflight import DISCOVERY_PATH, check_oauth2_server

BASE_URL = "http://localhost:8080"


@pytest.mark.asyncio
@respx.mock
async def test_ok_when_discovery_doc_returns_json() -> None:
    """Ok when discovery doc returns json."""
    respx.get(f"{BASE_URL}{DISCOVERY_PATH}").mock(
        return_value=httpx.Response(200, json={"issuer": BASE_URL}, headers={"content-type": "application/json"}),
    )
    assert await check_oauth2_server(BASE_URL) is None


@pytest.mark.asyncio
@respx.mock
async def test_404_hints_at_dhis_conf_flag() -> None:
    """404 hints at dhis conf flag."""
    respx.get(f"{BASE_URL}{DISCOVERY_PATH}").mock(return_value=httpx.Response(404))
    error = await check_oauth2_server(BASE_URL)
    assert error is not None
    assert "oauth2.server.enabled = on" in error
    assert BASE_URL in error


@pytest.mark.asyncio
@respx.mock
async def test_500_surfaces_misconfiguration_hint() -> None:
    """500 surfaces misconfiguration hint."""
    respx.get(f"{BASE_URL}{DISCOVERY_PATH}").mock(return_value=httpx.Response(500))
    error = await check_oauth2_server(BASE_URL)
    assert error is not None
    assert "HTTP 500" in error
    assert "misconfigured" in error


@pytest.mark.asyncio
@respx.mock
async def test_non_json_response_flagged() -> None:
    """Non json response flagged."""
    respx.get(f"{BASE_URL}{DISCOVERY_PATH}").mock(
        return_value=httpx.Response(200, text="<html>hello</html>", headers={"content-type": "text/html"}),
    )
    error = await check_oauth2_server(BASE_URL)
    assert error is not None
    assert "content-type" in error


@pytest.mark.asyncio
@respx.mock
async def test_connect_error_is_clean() -> None:
    """Connect error is clean."""
    respx.get(f"{BASE_URL}{DISCOVERY_PATH}").mock(side_effect=httpx.ConnectError("boom"))
    error = await check_oauth2_server(BASE_URL)
    assert error is not None
    assert "cannot reach" in error
