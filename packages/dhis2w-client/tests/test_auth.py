"""Unit tests for the bundled auth providers."""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client.v42.auth.basic import BasicAuth
from dhis2w_client.v42.auth.oauth2 import OAuth2Auth, OAuth2Token
from dhis2w_client.v42.auth.pat import PatAuth
from dhis2w_client.v42.auth.session import SessionCookieAuth


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


async def test_session_cookie_auth_header() -> None:
    """Session cookie auth header — the raw Cookie value is sent verbatim, name included."""
    provider = SessionCookieAuth(cookie="JSESSIONID=abc123")
    assert await provider.headers() == {"Cookie": "JSESSIONID=abc123"}


async def test_session_cookie_auth_header_includes_xsrf_when_set() -> None:
    """When an xsrf token is set, headers() echoes it as X-XSRF-TOKEN alongside the Cookie."""
    provider = SessionCookieAuth(cookie="JSESSIONID=abc123", xsrf_token="xsrf-tok-1")
    assert await provider.headers() == {"Cookie": "JSESSIONID=abc123", "X-XSRF-TOKEN": "xsrf-tok-1"}


async def test_session_cookie_auth_header_omits_xsrf_when_none() -> None:
    """With no xsrf token (the default), headers() carries only the Cookie header."""
    provider = SessionCookieAuth(cookie="JSESSIONID=abc123")
    assert provider.xsrf_token is None
    assert await provider.headers() == {"Cookie": "JSESSIONID=abc123"}


async def test_session_cookie_auth_empty_xsrf_normalizes_to_none() -> None:
    """An empty xsrf token is inert — it normalizes to None so headers() omits X-XSRF-TOKEN."""
    provider = SessionCookieAuth(cookie="JSESSIONID=abc123", xsrf_token="")
    assert provider.xsrf_token is None
    assert await provider.headers() == {"Cookie": "JSESSIONID=abc123"}


async def test_session_cookie_auth_whitespace_xsrf_normalizes_to_none() -> None:
    """A whitespace-only xsrf token normalizes to None (header omitted), never a literal empty header."""
    provider = SessionCookieAuth(cookie="JSESSIONID=abc123", xsrf_token="   \n")
    assert provider.xsrf_token is None
    assert "X-XSRF-TOKEN" not in await provider.headers()


async def test_session_cookie_auth_xsrf_surrounding_whitespace_is_stripped() -> None:
    """Surrounding whitespace on the xsrf token is trimmed while the inner value is preserved."""
    provider = SessionCookieAuth(cookie="JSESSIONID=abc123", xsrf_token="  xsrf-tok-9\n")
    assert provider.xsrf_token == "xsrf-tok-9"
    assert (await provider.headers())["X-XSRF-TOKEN"] == "xsrf-tok-9"


async def test_session_cookie_auth_xsrf_control_char_is_rejected() -> None:
    """A CRLF/control-char xsrf token fails fast at construction, not with a cryptic error at send time."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        SessionCookieAuth(cookie="JSESSIONID=abc123", xsrf_token="xsrf\r\ntok")
    assert "control characters" in str(excinfo.value)


async def test_session_cookie_masks_xsrf_token_in_repr_and_dump() -> None:
    """The xsrf token stays out of repr() and is masked in model_dump(); reveal returns the real value."""
    session = SessionCookieAuth(cookie="JSESSIONID=xyz789", xsrf_token="xsrf-secret")
    assert "xsrf-secret" not in repr(session)
    assert "xsrf-secret" not in str(session.model_dump())
    assert "xsrf-secret" not in session.model_dump_json()
    assert session.model_dump()["xsrf_token"] == "**********"
    assert session.model_dump(context={"reveal": True})["xsrf_token"] == "xsrf-secret"
    # The plain attribute is still readable for headers().
    assert session.xsrf_token == "xsrf-secret"
    assert (await session.headers())["X-XSRF-TOKEN"] == "xsrf-secret"


async def test_auth_providers_mask_secrets_in_repr_and_dump() -> None:
    """Credential fields stay out of repr() and are masked in model_dump() by default."""
    basic = BasicAuth(username="admin", password="hunter2pw")
    pat = PatAuth(token="d2pat_zzz")
    session = SessionCookieAuth(cookie="JSESSIONID=xyz789")
    token = OAuth2Token(access_token="ax-9931", refresh_token="rx-8842", expires_at=1.0)
    for model, leaked in (
        (basic, "hunter2pw"),
        (pat, "d2pat_zzz"),
        (session, "JSESSIONID=xyz789"),
        (token, "ax-9931"),
    ):
        assert leaked not in repr(model)
        assert leaked not in str(model.model_dump())
        assert leaked not in model.model_dump_json()
        assert "**********" in str(model.model_dump())
    # The reveal context returns the real value for persistence.
    assert basic.model_dump(context={"reveal": True})["password"] == "hunter2pw"
    assert token.model_dump(context={"reveal": True})["access_token"] == "ax-9931"
    assert token.model_dump(context={"reveal": True})["refresh_token"] == "rx-8842"
    # The plain attribute is still readable for the code that needs it.
    assert basic.password == "hunter2pw"
    assert token.access_token == "ax-9931"
    # headers() carry the real secret (attribute read, not the mask).
    assert (await basic.headers())["Authorization"].endswith(base64.b64encode(b"admin:hunter2pw").decode("ascii"))
    assert (await pat.headers())["Authorization"] == "ApiToken d2pat_zzz"
    assert (await session.headers())["Cookie"] == "JSESSIONID=xyz789"


async def test_session_cookie_refresh_is_noop() -> None:
    """Session cookie refresh is noop."""
    await SessionCookieAuth(cookie="JSESSIONID=abc123").refresh_if_needed()


class _InMemoryTokenStore:
    """Minimal TokenStore implementation for unit tests."""

    def __init__(self) -> None:
        self._items: dict[str, OAuth2Token] = {}

    async def get(self, key: str) -> OAuth2Token | None:
        return self._items.get(key)

    async def set(self, key: str, token: OAuth2Token) -> None:
        self._items[key] = token


class _CountingTokenStore(_InMemoryTokenStore):
    """TokenStore that counts `set` calls — asserts persistence frequency."""

    def __init__(self) -> None:
        super().__init__()
        self.set_calls = 0

    async def set(self, key: str, token: OAuth2Token) -> None:
        self.set_calls += 1
        await super().set(key, token)


@respx.mock
async def test_oauth2_uses_cached_token_without_interactive_flow() -> None:
    """Oauth2 uses cached token without interactive flow."""
    token_store = _InMemoryTokenStore()
    cached = OAuth2Token(
        access_token="cached-access",
        refresh_token="cached-refresh",
        expires_at=time.time() + 3600,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
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


@pytest.mark.parametrize(
    ("stored_base_url", "stored_client_id"),
    [
        ("https://other.example", "dhis2-utils"),
        ("https://dhis2.example", "other-client"),
        (None, None),
    ],
)
@respx.mock
async def test_oauth2_discards_cached_token_minted_for_another_identity(
    stored_base_url: str | None,
    stored_client_id: str | None,
) -> None:
    """A cached token whose recorded origin or client id is not this provider's is never sent."""
    token_store = _InMemoryTokenStore()
    await token_store.set(
        "profile:prod",
        OAuth2Token(
            access_token="foreign-access",
            refresh_token="foreign-refresh",
            expires_at=time.time() + 3600,
            base_url=stored_base_url,
            client_id=stored_client_id,
        ),
    )

    async def capture(auth_url: str, expected_state: str) -> str:
        return "fresh-code"

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "fresh-access", "expires_in": 3600}),
    )

    provider = OAuth2Auth(
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
        client_secret="secret",
        scope="openid email",
        redirect_uri="http://localhost:8765",
        token_store=token_store,
        store_key="profile:prod",
        redirect_capturer=capture,
    )
    headers = await provider.headers()
    assert headers == {"Authorization": "Bearer fresh-access"}
    reissued = await token_store.get("profile:prod")
    assert reissued is not None
    assert reissued.base_url == "https://dhis2.example"
    assert reissued.client_id == "dhis2-utils"


@respx.mock
async def test_oauth2_refresh_on_near_expiry() -> None:
    """Oauth2 refresh on near expiry."""
    token_store = _InMemoryTokenStore()
    expiring = OAuth2Token(
        access_token="old",
        refresh_token="refresh-me",
        expires_at=time.time() + 5,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
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
    expiring = OAuth2Token(
        access_token="old",
        refresh_token="stale-refresh",
        expires_at=time.time() + 5,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
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
    expiring = OAuth2Token(
        access_token="old",
        refresh_token=None,
        expires_at=time.time() + 5,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
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


def _provider(token_store: _InMemoryTokenStore, **kwargs: Any) -> OAuth2Auth:
    """Build an OAuth2Auth against dhis2.example with test defaults."""
    defaults: dict[str, Any] = {
        "base_url": "https://dhis2.example",
        "client_id": "dhis2-utils",
        "client_secret": "secret",
        "scope": "ALL",
        "redirect_uri": "http://localhost:8765",
        "token_store": token_store,
        "store_key": "profile:prod",
    }
    defaults.update(kwargs)
    return OAuth2Auth(**defaults)


async def test_oauth2_fresh_cached_token_is_not_rewritten_to_store() -> None:
    """A valid cached token costs zero store writes per request — no SQLite upsert per API call."""
    token_store = _CountingTokenStore()
    cached = OAuth2Token(
        access_token="cached",
        refresh_token="r",
        expires_at=time.time() + 3600,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
    await token_store.set("profile:prod", cached)
    token_store.set_calls = 0

    provider = _provider(token_store)
    for _ in range(5):
        await provider.headers()
    assert token_store.set_calls == 0


@respx.mock
async def test_oauth2_refresh_persists_exactly_once() -> None:
    """A refresh writes the new token to the store once; later fresh-token requests write nothing."""
    token_store = _CountingTokenStore()
    expiring = OAuth2Token(
        access_token="old",
        refresh_token="refresh-me",
        expires_at=time.time() + 5,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
    await token_store.set("profile:prod", expiring)
    token_store.set_calls = 0

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new", "refresh_token": "new-r", "expires_in": 3600},
        ),
    )

    provider = _provider(token_store)
    await provider.headers()
    await provider.headers()
    assert token_store.set_calls == 1


@respx.mock
async def test_oauth2_concurrent_requests_refresh_exactly_once() -> None:
    """N concurrent requests on an expired token trigger one refresh — rotation-safe."""
    token_store = _CountingTokenStore()
    expiring = OAuth2Token(
        access_token="old",
        refresh_token="rotate-me",
        expires_at=time.time() + 5,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
    await token_store.set("profile:prod", expiring)
    token_store.set_calls = 0

    route = respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fresh", "refresh_token": "rotated", "expires_in": 3600},
        ),
    )

    provider = _provider(token_store)
    all_headers = await asyncio.gather(*(provider.headers() for _ in range(10)))
    assert route.call_count == 1
    assert token_store.set_calls == 1
    assert all(headers == {"Authorization": "Bearer fresh"} for headers in all_headers)


@respx.mock
async def test_oauth2_concurrent_first_time_requests_run_one_interactive_flow() -> None:
    """Concurrent first-time requests launch the interactive flow once, not once per request."""
    capturer_calls = 0

    async def counting_capturer(_auth_url: str, _state: str) -> str:
        nonlocal capturer_calls
        capturer_calls += 1
        await asyncio.sleep(0)  # yield so waiters pile up on the lock
        return "one-code"

    route = respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "flow-access", "refresh_token": "flow-r", "expires_in": 3600},
        ),
    )

    provider = _provider(_CountingTokenStore(), redirect_capturer=counting_capturer)
    all_headers = await asyncio.gather(*(provider.headers() for _ in range(5)))
    assert capturer_calls == 1
    assert route.call_count == 1
    assert all(headers == {"Authorization": "Bearer flow-access"} for headers in all_headers)


@respx.mock
async def test_oauth2_verify_threads_into_token_endpoint_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """`verify=False` reaches the httpx client used for `/oauth2/token` — self-signed refresh works."""
    recorded_verify: list[Any] = []

    class _RecordingAsyncClient(httpx.AsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            recorded_verify.append(kwargs.get("verify", True))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)

    token_store = _InMemoryTokenStore()
    expiring = OAuth2Token(
        access_token="old",
        refresh_token="r",
        expires_at=time.time() + 5,
        base_url="https://dhis2.example",
        client_id="dhis2-utils",
    )
    await token_store.set("profile:prod", expiring)

    respx.post("https://dhis2.example/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new", "refresh_token": "new-r", "expires_in": 3600},
        ),
    )

    provider = _provider(token_store, verify=False)
    await provider.headers()
    assert recorded_verify == [False]
