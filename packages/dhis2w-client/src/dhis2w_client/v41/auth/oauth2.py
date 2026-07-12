"""OAuth 2.1 authorization-code flow with PKCE for DHIS2 OpenID Connect."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import secrets
import sys
import time
import urllib.parse
import webbrowser
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field, field_serializer
from pydantic_core.core_schema import SerializationInfo

from dhis2w_client.errors import OAuth2FlowError

RedirectCapturer = Callable[[str, str], Awaitable[str]]
"""Callable signature for the redirect-receiver hook.

Takes `(auth_url, expected_state)` and returns the authorization code. The
default implementation calls `capture_code()` with sensible defaults; tests
and specialised callers (e.g. `d2w profile verify`'s "don't open a
browser, just fail" probe) can inject their own implementation here.
"""

DEFAULT_REDIRECT_PORT = 8765
"""Loopback port the OAuth2 redirect receiver listens on by default."""

DEFAULT_REDIRECT_URI = f"http://localhost:{DEFAULT_REDIRECT_PORT}"
"""Canonical loopback redirect URI used by every CLI / service / example default.

Single source of truth so the port number doesn't drift across the six
profile / dev / sample / oauth2-registration call sites that previously
inlined `"http://localhost:8765"`. Override via the matching `--redirect-uri`
flag (CLI) or `redirect_uri` keyword argument (service / library)."""

_REDIRECT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>dhis2w login</title>
<style>
 body {{
   font-family: -apple-system, system-ui, sans-serif;
   padding: 3rem; color: #eee; background: #0f1117;
 }}
 .box {{
   max-width: 540px; margin: 0 auto; padding: 2rem;
   background: #1a1d26; border-radius: 12px;
   border: 1px solid #2a2e3a;
 }}
 h1 {{ margin: 0 0 0.5rem; color: {accent};
      font-weight: 500; font-size: 1.5rem; }}
 p {{ color: #a1a1aa; line-height: 1.5; }}
</style></head>
<body><div class="box">
 <h1>{heading}</h1>
 <p>{body}</p>
</div></body></html>
"""


def _render_html(*, heading: str, body: str, success: bool) -> bytes:
    """Render the small confirmation page returned to the browser."""
    accent = "#4ade80" if success else "#f87171"
    return _REDIRECT_HTML.format(heading=heading, body=body, accent=accent).encode("utf-8")


async def capture_code(
    redirect_uri: str,
    expected_state: str,
    *,
    auth_url: str,
    open_browser: bool = True,
    timeout: float = 300.0,
) -> str:
    """Listen on `redirect_uri`'s host:port for the OAuth2 redirect; return `code`.

    Bare `asyncio.start_server` — no FastAPI / uvicorn dependency. Validates
    `state` and surfaces `error` / `error_description` query params raised
    by the IdP. The browser sees a styled HTML confirmation page either
    way.

    `auth_url` is opened with `webbrowser.open()` once the server is
    listening (skip with `open_browser=False`; URL is then printed to
    stderr so the user can paste it into any browser). `timeout` bounds
    the wait — raises `OAuth2FlowError` on timeout, state mismatch, or
    IdP error.

    Requests whose query string carries no `code` parameter (port scans,
    browser preconnects, favicon fetches) get a 404 and are ignored — the
    receiver keeps listening. Only a request that carries a `code` but a
    wrong or missing `state` fails the flow.
    """
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or DEFAULT_REDIRECT_PORT

    loop = asyncio.get_running_loop()
    captured: asyncio.Future[str] = loop.create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Answer one loopback request — resolve the OAuth2 redirect, 404 anything else."""
        request_line = (await reader.readline()).decode("latin-1")
        while (await reader.readline()).strip():
            pass
        try:
            path = request_line.split(" ", 2)[1]
        except IndexError:
            path = ""
        params = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(path).query).items() if v}

        status_line, body = b"HTTP/1.1 200 OK\r\n", b""
        try:
            error = params.get("error")
            if error:
                description = params.get("error_description") or error
                status_line = b"HTTP/1.1 400 Bad Request\r\n"
                body = _render_html(heading="Authentication failed", body=description, success=False)
                if not captured.done():
                    captured.set_exception(OAuth2FlowError(f"authorization failed: {description}"))
                return
            code = params.get("code")
            if not code:
                # Not an OAuth2 redirect (port scan, browser preconnect,
                # favicon fetch, ...) — 404 it and keep listening. The
                # fixed loopback port makes stray local traffic routine;
                # it must not kill the login.
                status_line = b"HTTP/1.1 404 Not Found\r\n"
                return
            if params.get("state") != expected_state:
                status_line = b"HTTP/1.1 400 Bad Request\r\n"
                body = _render_html(heading="Authentication failed", body="State mismatch.", success=False)
                if not captured.done():
                    captured.set_exception(OAuth2FlowError("state mismatch — possible CSRF"))
                return
            body = _render_html(
                heading="Authentication successful",
                body="You can close this tab and return to the terminal.",
                success=True,
            )
            if not captured.done():
                captured.set_result(code)
        finally:
            writer.write(status_line)
            writer.write(b"Content-Type: text/html; charset=utf-8\r\n")
            writer.write(f"Content-Length: {len(body)}\r\n".encode("ascii"))
            writer.write(b"Connection: close\r\n\r\n")
            writer.write(body)
            with contextlib.suppress(Exception):  # best-effort teardown
                await writer.drain()
                writer.close()
                await writer.wait_closed()

    server = await asyncio.start_server(handle, host, port)
    try:
        if open_browser:
            webbrowser.open(auth_url)
        else:
            print(  # noqa: T201 — user-facing copy-paste prompt
                f"\nOpen this URL in a browser to authenticate:\n\n  {auth_url}\n\n"
                f"Waiting for redirect to {redirect_uri} ...",
                file=sys.stderr,
                flush=True,
            )
        try:
            return await asyncio.wait_for(captured, timeout=timeout)
        except TimeoutError as exc:
            raise OAuth2FlowError(f"no OAuth2 redirect received within {timeout}s") from exc
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()


class OAuth2Token(BaseModel):
    """Access + refresh token pair with expiry info (unix epoch seconds).

    Both token values stay out of `repr()` (`Field(repr=False)`) and are masked
    in `model_dump()`; pass `context={"reveal": True}` to `model_dump()` to
    reveal them. Read the plain attributes when building an Authorization header
    or a token-endpoint request body.
    """

    access_token: str = Field(repr=False)
    refresh_token: str | None = Field(default=None, repr=False)
    expires_at: float

    @field_serializer("access_token", "refresh_token")
    def _redact(self, value: str | None, info: SerializationInfo) -> str | None:
        """Mask both token values unless serialization runs with `context={"reveal": True}`."""
        if value is None:
            return None
        if info.context and info.context.get("reveal"):
            return value
        return "**********"


@runtime_checkable
class TokenStore(Protocol):
    """Persists OAuth2 tokens across runs — filesystem, keyring, SQLite, etc."""

    async def get(self, key: str) -> OAuth2Token | None:
        """Load tokens for `key` or return None if none stored."""
        ...

    async def set(self, key: str, token: OAuth2Token) -> None:
        """Persist tokens for `key`."""
        ...


class OAuth2Auth:
    """Authorization-code flow with PKCE against DHIS2 /oauth2/* endpoints."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        redirect_uri: str,
        token_store: TokenStore,
        store_key: str | None = None,
        redirect_capturer: RedirectCapturer | None = None,
        open_browser: bool = True,
        verify: bool | str = True,
    ) -> None:
        """Construct the provider.

        `store_key` distinguishes tokens across profiles. `redirect_capturer`
        is an optional callable `(auth_url, expected_state) -> code` that
        replaces the default `asyncio.start_server` loopback implementation
        — `dhis2w-core` injects a FastAPI-backed one here for a nicer UX.

        `open_browser=False` skips the `webbrowser.open()` call in the
        default capturer and prints the authorization URL to stderr for
        copy-paste instead. Ignored when a custom `redirect_capturer` is
        supplied — in that case, the caller owns the "how to get the URL
        in front of the user" decision.

        `verify` controls TLS certificate verification on the token-endpoint
        calls (`/oauth2/token`). Pass the same value you pass to
        `Dhis2Client(verify=...)` so the code exchange and refresh use the
        same trust decision as the API traffic — `False` for self-signed
        staging boxes, or a path to a custom CA bundle.
        """
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._redirect_uri = redirect_uri
        self._token_store = token_store
        self._store_key = store_key or f"{base_url}:{client_id}"
        self._token: OAuth2Token | None = None
        self._redirect_capturer = redirect_capturer
        self._open_browser = open_browser
        self._verify = verify
        self._refresh_lock = asyncio.Lock()

    async def headers(self) -> dict[str, str]:
        """Return Authorization: Bearer <access_token>, running interactive flow if needed."""
        await self.refresh_if_needed()
        if self._token is None:
            raise OAuth2FlowError("token missing after refresh — refresh_if_needed should have set it")
        return {"Authorization": f"Bearer {self._token.access_token}"}

    async def refresh_if_needed(self) -> None:
        """Load cached token, refresh if close to expiry, run interactive flow if missing.

        The whole check-refresh-persist section runs under an `asyncio.Lock`:
        of N concurrent requests hitting an expired token, one refreshes (or
        runs the interactive flow) while the rest wait and re-check, then
        reuse the fresh token — a second concurrent refresh would submit an
        already-rotated (revoked) refresh_token, and a second concurrent
        first-time request would launch a duplicate browser flow. The token
        store is written only when a new token was obtained, so the steady
        state (valid cached token) costs zero store writes per request.
        """
        async with self._refresh_lock:
            if self._token is None:
                self._token = await self._token_store.get(self._store_key)
            if self._token is None:
                self._token = await self._run_authorization_flow()
            elif self._token.expires_at < time.time() + 60:
                self._token = await self._refresh(self._token)
            else:
                return
            await self._token_store.set(self._store_key, self._token)

    async def _run_authorization_flow(self) -> OAuth2Token:
        """Run the browser-based PKCE authorization-code flow."""
        code_verifier = secrets.token_urlsafe(96)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        state = secrets.token_urlsafe(16)

        auth_params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "scope": self._scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"{self._base_url}/oauth2/authorize?{urllib.parse.urlencode(auth_params)}"

        capturer = self._redirect_capturer or self._capture_code
        code = await capturer(auth_url, state)
        return await self._exchange_code(code, code_verifier)

    async def _capture_code(self, auth_url: str, expected_state: str) -> str:
        """Default capturer — delegate to the module-level `capture_code`."""
        return await capture_code(
            self._redirect_uri,
            expected_state,
            auth_url=auth_url,
            open_browser=self._open_browser,
        )

    async def _exchange_code(self, code: str, code_verifier: str) -> OAuth2Token:
        """Exchange an authorization code for access+refresh tokens.

        Wraps HTTP failures in `OAuth2FlowError` so callers see a clean
        actionable message instead of a raw `httpx.HTTPStatusError`
        traceback. Common failure modes: rejected client secret (DHIS2
        returns 401), redirect-URI mismatch with the OAuth2 client
        registration (400), or DHIS2-side OAuth2 misconfig (5xx).
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(follow_redirects=True, verify=self._verify) as http_client:
            response = await http_client.post(f"{self._base_url}/oauth2/token", data=data)
        if response.status_code >= 400:
            raise OAuth2FlowError(_format_token_endpoint_failure("authorization-code exchange", response))
        return self._token_from_response(response.json())

    async def _refresh(self, expired: OAuth2Token) -> OAuth2Token:
        """Refresh tokens using the refresh_token grant.

        Wraps HTTP failures in `OAuth2FlowError` so callers see a clean
        actionable message ("run `d2w profile login <name>`") instead of a
        raw `httpx.HTTPStatusError` traceback. The most common case is DHIS2
        rotating its OAuth2 client (volume wiped, client UID reissued) —
        the stored refresh_token no longer matches and DHIS2 returns 400.
        """
        if expired.refresh_token is None:
            raise OAuth2FlowError(
                "access token expired and no refresh_token available — run `d2w profile login <name>` to re-authorise"
            )
        data = {
            "grant_type": "refresh_token",
            "refresh_token": expired.refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        async with httpx.AsyncClient(follow_redirects=True, verify=self._verify) as http_client:
            response = await http_client.post(f"{self._base_url}/oauth2/token", data=data)
        if response.status_code >= 400:
            raise OAuth2FlowError(
                f"token refresh failed ({response.status_code}) — "
                "stored refresh_token rejected by DHIS2. "
                "Run `d2w profile login <name>` to re-authorise."
            )
        return self._token_from_response(response.json(), fallback_refresh=expired.refresh_token)

    @staticmethod
    def _token_from_response(data: dict[str, Any], fallback_refresh: str | None = None) -> OAuth2Token:
        """Parse a token-endpoint JSON response into an OAuth2Token."""
        expires_in = float(data.get("expires_in", 3600))
        refresh = data.get("refresh_token") or fallback_refresh
        return OAuth2Token(
            access_token=str(data["access_token"]),
            refresh_token=str(refresh) if refresh else None,
            expires_at=time.time() + expires_in,
        )


_TOKEN_ERROR_BODY_MAX = 400


def _format_token_endpoint_failure(context: str, response: httpx.Response) -> str:
    """Render an OAuth2FlowError message for a non-2xx response from `/oauth2/token`.

    Includes the HTTP status, the OAuth2 `error` + `error_description` fields
    when present (RFC 6749 standard error envelope), and a truncated body
    snippet otherwise — DHIS2 surfaces useful diagnostics in that body for
    common misconfigurations (rejected client_secret, redirect_uri mismatch,
    OAuth2 client not registered, etc.) and re-emitting them gives the caller
    actionable signal without dumping headers or secrets.
    """
    detail: str
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 — body might not be JSON
        body = None
    if isinstance(body, dict) and "error" in body:
        error = str(body.get("error"))
        description = body.get("error_description")
        detail = f"{error}: {description}" if description else error
    else:
        text = response.text.strip()
        detail = text[:_TOKEN_ERROR_BODY_MAX] + ("..." if len(text) > _TOKEN_ERROR_BODY_MAX else "")
        if not detail:
            detail = "(empty response body)"
    return (
        f"OAuth2 {context} failed ({response.status_code}): {detail}. "
        "Common causes: wrong client_secret, redirect_uri not registered on the "
        "DHIS2 OAuth2 client, or DHIS2-side OAuth2 misconfiguration."
    )
