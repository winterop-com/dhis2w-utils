"""Unit tests for the bundled auth providers."""

from __future__ import annotations

import base64
import time

import httpx
import respx
from dhis2w_client.v42.auth.basic import BasicAuth
from dhis2w_client.v42.auth.oauth2 import OAuth2Auth, OAuth2Token
from dhis2w_client.v42.auth.pat import PatAuth


async def test_basic_auth_header() -> None:
    """Basic auth header."""
    provider = BasicAuth(username="admin", password="district")
    encoded = base64.b64encode(b"admin:district").decode()
    assert await provider.headers() == {"Authorization": f"Basic {encoded}"}


async def test_pat_auth_header() -> None:
    """Pat auth header."""
    provider = PatAuth(token="d2pat_example")
    assert await provider.headers() == {"Authorization": "ApiToken d2pat_example"}


async def test_basic_refresh_is_noop() -> None:
    """Basic refresh is noop."""
    await BasicAuth(username="a", password="b").refresh_if_needed()


async def test_pat_refresh_is_noop() -> None:
    """Pat refresh is noop."""
    await PatAuth(token="t").refresh_if_needed()


class _InMemoryTokenStore:
    """Minimal TokenStore implementation for unit tests."""

    def __init__(self) -> None:
        self._items: dict[str, OAuth2Token] = {}

    async def get(self, key: str) -> OAuth2Token | None:
        return self._items.get(key)

    async def set(self, key: str, token: OAuth2Token) -> None:
        self._items[key] = token


@respx.mock
async def test_oauth2_uses_cached_token_without_interactive_flow() -> None:
    """Oauth2 uses cached token without interactive flow."""
    token_store = _InMemoryTokenStore()
    cached = OAuth2Token(access_token="cached-access", refresh_token="cached-refresh", expires_at=time.time() + 3600)
    await token_store.set("profile:prod", cached)

    provider = OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
        client_secret="secret",
        scope="openid email",
        redirect_uri="http://localhost:8765",
        token_store=token_store,
        store_key="profile:prod",
    )
    headers = await provider.headers()
    assert headers == {"Authorization": "Bearer cached-access"}


@respx.mock
async def test_oauth2_refresh_on_near_expiry() -> None:
    """Oauth2 refresh on near expiry."""
    token_store = _InMemoryTokenStore()
    expiring = OAuth2Token(access_token="old", refresh_token="refresh-me", expires_at=time.time() + 5)
    await token_store.set("profile:prod", expiring)

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600},
        )
    )

    provider = OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
        client_secret="secret",
        scope="openid",
        redirect_uri="http://localhost:8765",
        token_store=token_store,
        store_key="profile:prod",
    )
    headers = await provider.headers()
    assert headers == {"Authorization": "Bearer new-access"}

    stored = await token_store.get("profile:prod")
    assert stored is not None
    assert stored.access_token == "new-access"
    assert stored.refresh_token == "new-refresh"


@respx.mock
async def test_oauth2_exchange_400_raises_oauth2_flow_error() -> None:
    """Bad-credential authorization-code exchange surfaces a clean OAuth2FlowError, not a raw httpx error.

    Authorization-code exchange used to call response.raise_for_status() which
    leaked a raw httpx.HTTPStatusError up. The wrapped message should include
    the HTTP status, the RFC 6749 `error` / `error_description` fields when
    DHIS2 returns them, and a hint about common causes.
    """
    from dhis2w_client.errors import OAuth2FlowError
    from dhis2w_client.v42.auth.oauth2 import OAuth2Auth as _OAuth2Auth

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            400,
            json={"error": "invalid_client", "error_description": "client secret rejected"},
        ),
    )

    provider = _OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
        client_secret="wrong-secret",
        scope="ALL",
        redirect_uri="http://localhost:8765",
        token_store=_InMemoryTokenStore(),
        store_key="profile:prod",
    )
    import pytest

    with pytest.raises(OAuth2FlowError) as exc:
        await provider._exchange_code(code="dummy-code", code_verifier="dummy-verifier")
    msg = str(exc.value)
    assert "400" in msg
    assert "invalid_client" in msg
    assert "client secret rejected" in msg
    assert "authorization-code exchange" in msg


@respx.mock
async def test_oauth2_refresh_400_raises_oauth2_flow_error() -> None:
    """When DHIS2 rejects the cached refresh_token (e.g. client rotated), surface a clean OAuth2FlowError.

    The error message must point at `d2w profile login <name>` so the
    user knows the recovery path. Raw httpx.HTTPStatusError tracebacks are
    not acceptable — this is a known recoverable failure mode and we
    own the UX.
    """
    from dhis2w_client.errors import OAuth2FlowError

    token_store = _InMemoryTokenStore()
    expiring = OAuth2Token(access_token="old", refresh_token="stale-refresh", expires_at=time.time() + 5)
    await token_store.set("profile:prod", expiring)

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"}),
    )

    provider = OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
        client_secret="secret",
        scope="ALL",
        redirect_uri="http://localhost:8765",
        token_store=token_store,
        store_key="profile:prod",
    )
    import pytest

    with pytest.raises(OAuth2FlowError, match=r"token refresh failed.*d2w profile login"):
        await provider.headers()


async def test_oauth2_expired_without_refresh_token_raises() -> None:
    """An expired token without a refresh_token can't be refreshed — must point at `profile login`."""
    from dhis2w_client.errors import OAuth2FlowError

    token_store = _InMemoryTokenStore()
    expiring = OAuth2Token(access_token="old", refresh_token=None, expires_at=time.time() + 5)
    await token_store.set("profile:prod", expiring)

    provider = OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
        client_secret="secret",
        scope="ALL",
        redirect_uri="http://localhost:8765",
        token_store=token_store,
        store_key="profile:prod",
    )
    import pytest

    with pytest.raises(OAuth2FlowError, match=r"no refresh_token.*d2w profile login"):
        await provider.headers()


@respx.mock
async def test_oauth2_full_authorization_flow_via_injected_capturer() -> None:
    """Fresh provider (no cached token) runs the full flow: capturer returns code, token endpoint exchanges it."""

    async def fake_capturer(_auth_url: str, _state: str) -> str:
        return "fake-auth-code"

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "first-access", "refresh_token": "first-refresh", "expires_in": 3600},
        ),
    )

    token_store = _InMemoryTokenStore()
    provider = OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils-local",
        client_secret="secret",
        scope="ALL",
        redirect_uri="http://localhost:8765",
        token_store=token_store,
        store_key="profile:prod",
        redirect_capturer=fake_capturer,
    )
    headers = await provider.headers()
    assert headers == {"Authorization": "Bearer first-access"}

    stored = await token_store.get("profile:prod")
    assert stored is not None
    assert stored.access_token == "first-access"
    assert stored.refresh_token == "first-refresh"
