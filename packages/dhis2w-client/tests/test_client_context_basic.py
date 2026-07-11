"""Unit tests for the lightweight open_client + build_auth_for_basic in dhis2w-client."""

from __future__ import annotations

import pytest
import respx
from dhis2w_client import (
    BasicAuth,
    PatAuth,
    Profile,
    SessionCookieAuth,
    build_auth_for_basic,
    open_client,
)
from httpx import Response


def test_build_auth_for_basic_pat() -> None:
    """Build auth for basic pat."""
    provider = build_auth_for_basic(Profile(base_url="http://x", auth="pat", token="d2p_x"))
    assert isinstance(provider, PatAuth)
    assert provider.token == "d2p_x"


def test_build_auth_for_basic_basic() -> None:
    """Build auth for basic basic."""
    provider = build_auth_for_basic(Profile(base_url="http://x", auth="basic", username="admin", password="district"))
    assert isinstance(provider, BasicAuth)
    assert provider.username == "admin"


def test_build_auth_for_basic_session() -> None:
    """Build auth for basic session."""
    provider = build_auth_for_basic(Profile(base_url="http://x", auth="session", cookie="JSESSIONID=abc123"))
    assert isinstance(provider, SessionCookieAuth)
    assert provider.cookie == "JSESSIONID=abc123"


def test_build_auth_for_basic_session_requires_cookie() -> None:
    """Build auth for basic session requires cookie."""
    with pytest.raises(ValueError):
        build_auth_for_basic(Profile(base_url="http://x", auth="session"))


def test_build_auth_for_basic_oauth2_raises_with_install_hint() -> None:
    """Build auth for basic oauth2 raises with install hint."""
    profile = Profile(
        base_url="http://x",
        auth="oauth2",
        client_id="cid",
        client_secret="cs",
        scope="ALL",
        redirect_uri="http://localhost/callback",
    )
    with pytest.raises(NotImplementedError) as exc:
        build_auth_for_basic(profile)
    assert "dhis2w-core" in str(exc.value)


def test_build_auth_for_basic_pat_requires_token() -> None:
    """Build auth for basic pat requires token."""
    with pytest.raises(ValueError):
        build_auth_for_basic(Profile(base_url="http://x", auth="pat"))


def test_build_auth_for_basic_basic_requires_credentials() -> None:
    """Build auth for basic basic requires credentials."""
    with pytest.raises(ValueError):
        build_auth_for_basic(Profile(base_url="http://x", auth="basic"))


@respx.mock
async def test_open_client_pat_opens_against_mocked_dhis2() -> None:
    """Open client pat opens against mocked dhis2."""
    base_url = "http://mocked.dhis2.example"
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=Response(200, json={"version": "2.42.4", "revision": "abc"})
    )
    respx.get(f"{base_url}/api/me").mock(
        return_value=Response(200, json={"id": "u1", "username": "admin", "displayName": "Admin"})
    )
    profile = Profile(base_url=base_url, auth="pat", token="d2p_test")
    async with open_client(profile, system_cache_ttl=None) as client:
        me = await client.system.me()
        assert me.username == "admin"


async def test_open_client_oauth2_raises_with_install_hint() -> None:
    """Open client oauth2 raises with install hint."""
    profile = Profile(
        base_url="http://x",
        auth="oauth2",
        client_id="cid",
        client_secret="cs",
        scope="ALL",
        redirect_uri="http://localhost/callback",
    )
    with pytest.raises(NotImplementedError) as exc:
        async with open_client(profile):
            pass
    assert "dhis2w-core" in str(exc.value)
