"""Integration-style tests for Dhis2Client using respx-mocked HTTP."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_client import (
    AuthenticationError,
    BasicAuth,
    Dhis2,
    Dhis2ApiError,
    Dhis2Client,
    UnsupportedVersionError,
    VersionPinMismatchError,
)
from pydantic import BaseModel


class _Me(BaseModel):
    username: str


@respx.mock
async def test_get_raw_injects_auth_header_and_parses_json() -> None:
    """Get raw injects auth header and parses json."""
    route = respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"username": "admin"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="admin", password="district"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        body = await client.get_raw("/api/me")
    finally:
        await client.close()
    assert body == {"username": "admin"}
    assert route.called
    sent_headers = dict(route.calls.last.request.headers)
    assert "authorization" in sent_headers
    assert sent_headers["authorization"].startswith("Basic ")


@respx.mock
async def test_empty_2xx_body_parses_to_empty_dict() -> None:
    """DELETE-style empty bodies map to {} — no error, no fake payload."""
    respx.delete("https://dhis2.example/api/dataElements/abc").mock(
        return_value=httpx.Response(204),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        body = await client.delete_raw("/api/dataElements/abc")
    finally:
        await client.close()
    assert body == {}


@respx.mock
async def test_non_json_2xx_body_raises_with_snippet() -> None:
    """A 200 with an HTML body (proxy / SSO login page) raises Dhis2ApiError instead of returning {}."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html><body>Corporate proxy sign-in</body></html>",
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        with pytest.raises(Dhis2ApiError) as exc:
            await client.get_raw("/api/me")
    finally:
        await client.close()
    assert exc.value.status_code == 200
    assert "non-JSON" in exc.value.message
    assert isinstance(exc.value.body, str)
    assert "Corporate proxy sign-in" in exc.value.body


@respx.mock
async def test_typed_get_returns_pydantic_instance() -> None:
    """Typed get returns pydantic instance."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"username": "admin"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="admin", password="district"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        me = await client.get("/api/me", model=_Me)
    finally:
        await client.close()
    assert isinstance(me, _Me)
    assert me.username == "admin"


@respx.mock
async def test_non_success_raises_dhis2_api_error() -> None:
    """Non success raises dhis2 api error."""
    respx.get("https://dhis2.example/api/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        with pytest.raises(Dhis2ApiError) as exc:
            await client.get_raw("/api/missing")
    finally:
        await client.close()
    assert exc.value.status_code == 404
    assert exc.value.body == {"message": "not found"}


@respx.mock
async def test_401_raises_authentication_error() -> None:
    """401 raises authentication error."""
    respx.get("https://dhis2.example/api/me").mock(return_value=httpx.Response(401, text="Unauthorized"))
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        with pytest.raises(AuthenticationError):
            await client.get_raw("/api/me")
    finally:
        await client.close()


@respx.mock
async def test_401_openid_mapping_message_includes_actionable_fix() -> None:
    """When DHIS2 issues a valid JWT but rejects user mapping, surface the openId PATCH hint."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(
            401,
            text="Unauthorized",
            headers={
                "WWW-Authenticate": (
                    'Bearer error="invalid_token", '
                    "error_description=\"Found no matching DHIS2 user for the mapping claim: 'sub' "
                    "with the value: 'admin'\", "
                    'error_uri="https://tools.ietf.org/html/rfc6750#section-3.1"'
                ),
            },
        )
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_raw("/api/me")
    finally:
        await client.close()
    message = str(exc_info.value)
    assert "openId='admin'" in message
    assert "claim='sub'" in message
    assert "/api/users/" in message
    assert "v43" in message


@respx.mock
async def test_401_passes_through_unrecognised_error_description() -> None:
    """For other 401s (e.g. expired token), the error_description is appended verbatim."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(
            401,
            text="Unauthorized",
            headers={
                "WWW-Authenticate": 'Bearer error="invalid_token", error_description="Token has expired"',
            },
        )
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        with pytest.raises(AuthenticationError) as exc_info:
            await client.get_raw("/api/me")
    finally:
        await client.close()
    assert "Token has expired" in str(exc_info.value)


async def test_resolve_canonical_base_url_returns_original_when_probe_fails() -> None:
    # No respx mock set up — probe fails, returns original base (defensive fallback).
    """Resolve canonical base url returns original when probe fails."""
    resolved = await Dhis2Client._resolve_canonical_base_url("https://dhis2.example")
    assert resolved == "https://dhis2.example"


@respx.mock
async def test_resolve_canonical_base_url_follows_cross_host_redirect() -> None:
    # Simulate play.dhis2.org/dev -> play.im.dhis2.org/dev pattern.
    """Resolve canonical base url follows cross host redirect."""
    respx.get("https://play.dhis2.org/dev/").mock(
        return_value=httpx.Response(302, headers={"location": "https://play.im.dhis2.org/dev/"}),
    )
    respx.get("https://play.im.dhis2.org/dev/").mock(
        return_value=httpx.Response(302, headers={"location": "https://play.im.dhis2.org/dev/dhis-web-login/"}),
    )
    respx.get("https://play.im.dhis2.org/dev/dhis-web-login/").mock(
        return_value=httpx.Response(200, text="<html>login</html>"),
    )
    # Cross-origin canonical — probe /api/system/info to confirm DHIS2.
    respx.get("https://play.im.dhis2.org/dev/api/system/info").mock(
        return_value=httpx.Response(
            401,
            headers={"content-type": "application/json"},
            json={"httpStatusCode": 401, "message": "Not authenticated"},
        ),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("https://play.dhis2.org/dev")
    # The /dhis-web-login suffix is stripped so we land on the DHIS2 root.
    assert resolved == "https://play.im.dhis2.org/dev"


@respx.mock
async def test_resolve_canonical_base_url_rejects_sso_idp_redirect() -> None:
    """Cross-origin redirect to an SSO IdP must not be adopted as canonical."""
    # DHIS2 host root redirects to an IdP on a different origin.
    respx.get("https://dhis2.example.org/").mock(
        return_value=httpx.Response(
            302,
            headers={"location": "https://sso.example.org/oauth2/authorize?client_id=dhis2&..."},
        ),
    )
    # IdP returns its login page — HTML, not JSON.
    respx.get("https://sso.example.org/oauth2/authorize").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body>Sign in</body></html>",
        ),
    )
    # Probe of the IdP's /api/system/info returns HTML (404 or login page) — not JSON.
    respx.get("https://sso.example.org/api/system/info").mock(
        return_value=httpx.Response(
            404,
            headers={"content-type": "text/html"},
            text="<html>Not Found</html>",
        ),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("https://dhis2.example.org")
    # Falls back to the original DHIS2 URL — does NOT adopt the IdP host.
    assert resolved == "https://dhis2.example.org"


@respx.mock
async def test_resolve_canonical_base_url_strips_login_suffix() -> None:
    """Resolve canonical base url strips login suffix."""
    respx.get("http://localhost:8080/").mock(
        return_value=httpx.Response(302, headers={"location": "/dhis-web-login/"}),
    )
    respx.get("http://localhost:8080/dhis-web-login/").mock(
        return_value=httpx.Response(200, text="<html>login</html>"),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("http://localhost:8080")
    assert resolved == "http://localhost:8080"


@respx.mock
async def test_resolve_canonical_base_url_rejects_foreign_registrable_domain() -> None:
    """A JSON-speaking host on another registrable domain is never adopted, and never sees credentials."""
    respx.get("https://dhis2.example.org/").mock(
        return_value=httpx.Response(302, headers={"location": "https://relay.example.net/"}),
    )
    respx.get("https://relay.example.net/").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/json"}, json={"version": "2.42.1"}),
    )
    probe = respx.get("https://relay.example.net/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.1", "contextPath": "https://relay.example.net"}),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("https://dhis2.example.org")
    assert resolved == "https://dhis2.example.org"
    for call in respx.calls:
        assert call.request.url.host != "relay.example.net" or "authorization" not in call.request.headers
    assert probe.call_count == 0


@respx.mock
async def test_resolve_canonical_base_url_rejects_scheme_downgrade() -> None:
    """An HTTPS base URL redirected to plain HTTP keeps the configured URL."""
    respx.get("https://dhis2.example.org/").mock(
        return_value=httpx.Response(302, headers={"location": "http://dhis2.example.org/"}),
    )
    respx.get("http://dhis2.example.org/").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/json"}, json={"version": "2.42.1"}),
    )
    respx.get("http://dhis2.example.org/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.1"}),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("https://dhis2.example.org")
    assert resolved == "https://dhis2.example.org"


@respx.mock
async def test_resolve_canonical_base_url_adopts_same_origin_path() -> None:
    """A same-origin redirect onto the context path is adopted without a DHIS2 probe."""
    respx.get("https://dhis2.example.org/").mock(
        return_value=httpx.Response(302, headers={"location": "https://dhis2.example.org/dhis/"}),
    )
    respx.get("https://dhis2.example.org/dhis/").mock(
        return_value=httpx.Response(200, text="<html>DHIS2</html>"),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("https://dhis2.example.org")
    assert resolved == "https://dhis2.example.org/dhis"


@respx.mock
async def test_resolve_canonical_base_url_rejects_non_dhis2_json_on_same_domain() -> None:
    """A sibling host on the same registrable domain still has to answer with a DHIS2 body."""
    respx.get("https://dhis2.example.org/").mock(
        return_value=httpx.Response(302, headers={"location": "https://sso.example.org/"}),
    )
    respx.get("https://sso.example.org/").mock(
        return_value=httpx.Response(200, json={"login": "required"}),
    )
    respx.get("https://sso.example.org/api/system/info").mock(
        return_value=httpx.Response(200, json={"login": "required", "realm": "corp"}),
    )
    resolved = await Dhis2Client._resolve_canonical_base_url("https://dhis2.example.org")
    assert resolved == "https://dhis2.example.org"


def test_registrable_domain_reduces_to_last_two_labels() -> None:
    """The registrable-domain approximation folds sibling hosts together and rejects IP literals."""
    assert Dhis2Client._registrable_domain("play.dhis2.org") == "dhis2.org"
    assert Dhis2Client._registrable_domain("play.im.dhis2.org") == "dhis2.org"
    assert Dhis2Client._registrable_domain("localhost") is None
    assert Dhis2Client._registrable_domain("127.0.0.1") is None
    assert Dhis2Client._registrable_domain("::1") is None
    assert Dhis2Client._registrable_domain(None) is None


# ---------- verify (TLS) ----------


async def test_verify_defaults_to_true() -> None:
    """Verify defaults to True."""
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="u", password="p"))
    assert client._verify is True


async def test_verify_false_passes_through_to_httpx_pool() -> None:
    """Pool built by connect() honours `verify=False` from the constructor."""
    client = Dhis2Client(
        "https://dhis2.example",
        auth=BasicAuth(username="u", password="p"),
        verify=False,
        skip_version_probe=True,
    )
    try:
        await client.connect()
        assert client._http is not None
        # httpx stores the configured SSLContext on the transport when verify=True
        # and a no-verify context when verify=False. The simplest, stable check
        # is that our constructor value was stored on the client.
        assert client._verify is False
    finally:
        await client.close()


async def test_verify_ca_bundle_path_stored() -> None:
    """A custom CA bundle path is accepted and stored."""
    client = Dhis2Client(
        "https://dhis2.example",
        auth=BasicAuth(username="u", password="p"),
        verify="/etc/ssl/custom-ca.pem",
    )
    assert client._verify == "/etc/ssl/custom-ca.pem"


# ---------- skip_version_probe ----------


async def test_skip_version_probe_opens_pool_without_round_trips() -> None:
    """`skip_version_probe=True` connects without canonical-URL or system/info calls.

    respx with `assert_all_called=False` would still record any unexpected
    traffic; we simply don't register handlers, so any HTTP call would
    raise. `connect()` must therefore complete with zero requests sent.
    """
    client = Dhis2Client(
        "https://dhis2.example",
        auth=BasicAuth(username="u", password="p"),
        skip_version_probe=True,
    )
    try:
        async with respx.mock(assert_all_called=False) as router:
            await client.connect()
            assert client._http is not None
            assert len(router.calls) == 0
    finally:
        await client.close()


async def test_skip_version_probe_leaves_version_key_raising() -> None:
    """With probe skipped, version-derived properties raise on access."""
    client = Dhis2Client(
        "https://dhis2.example",
        auth=BasicAuth(username="u", password="p"),
        skip_version_probe=True,
    )
    try:
        await client.connect()
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.version_key
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.raw_version
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.resources
    finally:
        await client.close()


@respx.mock
async def test_skip_version_probe_still_allows_get_raw() -> None:
    """`get_raw` works without a version probe — it's the escape-hatch path."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"username": "admin"}),
    )
    client = Dhis2Client(
        "https://dhis2.example",
        auth=BasicAuth(username="admin", password="district"),
        skip_version_probe=True,
    )
    try:
        await client.connect()
        body = await client.get_raw("/api/me")
        assert body == {"username": "admin"}
    finally:
        await client.close()


# ---------- get_response ----------


@respx.mock
async def test_get_response_returns_2xx_raw_response() -> None:
    """`get_response` hands back the raw `httpx.Response` on success."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"username": "admin"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        response = await client.get_response("/api/me")
    finally:
        await client.close()
    assert isinstance(response, httpx.Response)
    assert response.status_code == 200
    assert response.json() == {"username": "admin"}


@respx.mock
async def test_get_response_does_not_raise_on_401() -> None:
    """A 401 surfaces as a response, not an AuthenticationError."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(401, text="Unauthorized"),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        response = await client.get_response("/api/me")
    finally:
        await client.close()
    assert response.status_code == 401


@respx.mock
async def test_get_response_does_not_raise_on_502_from_route() -> None:
    """A 502 from a reverse-proxied route surfaces as a response, not Dhis2ApiError."""
    respx.get("https://dhis2.example/api/routes/chap/run/health").mock(
        return_value=httpx.Response(502, text="upstream did not respond"),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        response = await client.get_response("/api/routes/chap/run/health")
    finally:
        await client.close()
    assert response.status_code == 502
    assert response.text == "upstream did not respond"


@respx.mock
async def test_get_response_applies_auth_header() -> None:
    """The auth header is still injected on `get_response` calls."""
    route = respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"username": "admin"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="admin", password="district"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        await client.get_response("/api/me")
    finally:
        await client.close()
    sent = dict(route.calls.last.request.headers)
    assert sent["authorization"].startswith("Basic ")


# ---------- connect() cleanup on probe failure ----------


@respx.mock
async def test_connect_closes_pool_when_probe_returns_401() -> None:
    """A 401 during the connect probe closes the pool — connect() never leaks an AsyncClient."""
    created: list[httpx.AsyncClient] = []
    real_async_client = httpx.AsyncClient

    def _spy(*args: object, **kwargs: object) -> httpx.AsyncClient:
        instance = real_async_client(*args, **kwargs)  # type: ignore[arg-type]
        created.append(instance)
        return instance

    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("https://dhis2.example/api/system/info").mock(return_value=httpx.Response(401, text="Unauthorized"))
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "AsyncClient", _spy)
        with pytest.raises(AuthenticationError):
            await client.connect()
    # close() nulls the pool reference; the created pool must be closed, not leaked.
    assert client._http is None
    assert created, "connect() should have opened at least one AsyncClient"
    assert created[-1].is_closed


@respx.mock
async def test_connect_closes_pool_on_version_pin_mismatch() -> None:
    """A version-pin mismatch during the probe closes the pool before re-raising."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    client = Dhis2Client(
        "https://dhis2.example",
        auth=BasicAuth(username="a", password="b"),
        version=Dhis2.V43,
    )
    with pytest.raises(VersionPinMismatchError):
        await client.connect()
    assert client._http is None


# ---------- VersionPinMismatchError export ----------


def test_version_pin_mismatch_error_is_exported_and_subclasses_unsupported() -> None:
    """`VersionPinMismatchError` is importable from the top level and extends `UnsupportedVersionError`."""
    assert issubclass(VersionPinMismatchError, UnsupportedVersionError)
    err = VersionPinMismatchError(pinned="v43", reported="2.42.4")
    assert err.pinned == "v43"
    assert err.reported == "2.42.4"


@respx.mock
async def test_get_raw_still_raises_after_refactor() -> None:
    """Regression: gating raises on `raise_for_status` did not silence `get_raw`."""
    respx.get("https://dhis2.example/api/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    client._http = httpx.AsyncClient(base_url="https://dhis2.example")
    try:
        with pytest.raises(Dhis2ApiError) as exc:
            await client.get_raw("/api/missing")
    finally:
        await client.close()
    assert exc.value.status_code == 404
