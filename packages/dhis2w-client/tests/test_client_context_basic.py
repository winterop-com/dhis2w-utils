"""Unit tests for the lightweight open_client + build_auth_provider in dhis2w-client."""

from __future__ import annotations

import pytest
import respx
from dhis2w_client import (
    BasicAuth,
    Dhis2,
    PatAuth,
    Profile,
    SessionCookieAuth,
    VersionPinMismatchError,
    build_auth_provider,
    open_client,
)
from httpx import Response


def test_build_auth_provider_pat() -> None:
    """Build auth for basic pat."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="pat", token="d2p_x"))
    assert isinstance(provider, PatAuth)
    assert provider.token == "d2p_x"


def test_build_auth_provider_basic() -> None:
    """Build auth for basic basic."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="basic", username="admin", password="district"))
    assert isinstance(provider, BasicAuth)
    assert provider.username == "admin"


def test_build_auth_provider_session() -> None:
    """Build auth for basic session."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="session", cookie="JSESSIONID=abc123"))
    assert isinstance(provider, SessionCookieAuth)
    assert provider.cookie == "JSESSIONID=abc123"


def test_build_auth_provider_session_threads_xsrf_token() -> None:
    """build_auth_provider passes profile.xsrf_token into the SessionCookieAuth provider."""
    profile = Profile(base_url="http://x", auth="session", cookie="JSESSIONID=abc123", xsrf_token="xsrf-tok")
    provider = build_auth_provider(profile)
    assert isinstance(provider, SessionCookieAuth)
    assert provider.xsrf_token == "xsrf-tok"


def test_build_auth_provider_session_defaults_xsrf_to_none() -> None:
    """Without a profile xsrf token, the session provider's xsrf_token stays None."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="session", cookie="JSESSIONID=abc123"))
    assert isinstance(provider, SessionCookieAuth)
    assert provider.xsrf_token is None


@pytest.mark.parametrize("version", ["v41", "v42", "v43"])
def test_build_auth_provider_session_threads_xsrf_parity(version: str) -> None:
    """v41/v42/v43 build_auth_provider all thread profile.xsrf_token into their SessionCookieAuth."""
    import importlib

    ctx = importlib.import_module(f"dhis2w_client.{version}.client_context")
    session_mod = importlib.import_module(f"dhis2w_client.{version}.auth.session")
    profile = Profile(base_url="http://x", auth="session", cookie="JSESSIONID=abc123", xsrf_token="xsrf-tok")
    provider = ctx.build_auth_provider(profile)
    assert isinstance(provider, session_mod.SessionCookieAuth)
    assert provider.xsrf_token == "xsrf-tok"


def test_build_auth_provider_session_requires_cookie() -> None:
    """Build auth for basic session requires cookie."""
    with pytest.raises(ValueError):
        build_auth_provider(Profile(base_url="http://x", auth="session"))


def test_build_auth_provider_oauth2_raises_with_install_hint() -> None:
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
        build_auth_provider(profile)
    assert "dhis2w-core" in str(exc.value)


def test_build_auth_provider_pat_requires_token() -> None:
    """Build auth for basic pat requires token."""
    with pytest.raises(ValueError):
        build_auth_provider(Profile(base_url="http://x", auth="pat"))


def test_build_auth_provider_basic_requires_credentials() -> None:
    """Build auth for basic basic requires credentials."""
    with pytest.raises(ValueError):
        build_auth_provider(Profile(base_url="http://x", auth="basic"))


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


@respx.mock
async def test_open_client_passes_verify_through() -> None:
    """`open_client(verify=False)` reaches the underlying Dhis2Client so private-CA hosts work."""
    base_url = "http://mocked.dhis2.example"
    respx.get(f"{base_url}/api/system/info").mock(return_value=Response(200, json={"version": "2.42.4"}))
    profile = Profile(base_url=base_url, auth="pat", token="d2p_test")
    async with open_client(profile, system_cache_ttl=None, verify=False) as client:
        assert client._verify is False


@respx.mock
async def test_open_client_passes_version_pin_through() -> None:
    """`open_client(version=...)` reaches Dhis2Client and raises on a server-major mismatch."""
    base_url = "http://mocked.dhis2.example"
    respx.get(f"{base_url}/api/system/info").mock(return_value=Response(200, json={"version": "2.42.4"}))
    profile = Profile(base_url=base_url, auth="pat", token="d2p_test")
    with pytest.raises(VersionPinMismatchError):
        async with open_client(profile, system_cache_ttl=None, version=Dhis2.V43):
            pass


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
