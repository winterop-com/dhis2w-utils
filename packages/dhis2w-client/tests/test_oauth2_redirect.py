"""Unit tests for the OAuth2 loopback redirect receiver.

`capture_code` is the asyncio-based receiver shared by `OAuth2Auth`'s
default capturer and any caller that wants the same handling for a
custom flow. Each test fires a real httpx request at the running server
and asserts the resolved code (or the expected `OAuth2FlowError`).
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
from dhis2w_client.errors import OAuth2FlowError
from dhis2w_client.v42.auth.oauth2 import capture_code


def _free_port() -> int:
    """Pick a free TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


async def _fire_redirect(url: str, *, max_tries: int = 30) -> None:
    """Hit `url` once the server is up; retry briefly on ConnectError."""
    last_err: Exception | None = None
    for _ in range(max_tries):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.get(url)
            return
        except httpx.ConnectError as exc:
            last_err = exc
            await asyncio.sleep(0.05)
    if last_err is not None:
        raise last_err


_STUB_AUTH_URL = "http://127.0.0.1:9/oauth2/authorize?fake=1"


async def test_capture_happy_path() -> None:
    """Receiver returns the `code` query parameter when state matches."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    fire = asyncio.create_task(_fire_redirect(f"{redirect_uri}?code=abc123&state=expected-state"))
    try:
        code = await capture_code(
            redirect_uri,
            "expected-state",
            auth_url=_STUB_AUTH_URL,
            open_browser=False,
            timeout=10.0,
        )
    finally:
        await fire
    assert code == "abc123"


async def test_capture_state_mismatch_raises() -> None:
    """`OAuth2FlowError` raised when the IdP-supplied state differs from `expected_state`."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    fire = asyncio.create_task(_fire_redirect(f"{redirect_uri}?code=abc&state=wrong"))
    try:
        with pytest.raises(OAuth2FlowError, match="state mismatch"):
            await capture_code(
                redirect_uri,
                "right",
                auth_url=_STUB_AUTH_URL,
                open_browser=False,
                timeout=10.0,
            )
    finally:
        await fire


async def test_capture_error_param_raises() -> None:
    """An `error=...` redirect from the IdP surfaces as `OAuth2FlowError(authorization failed: ...)`."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    fire = asyncio.create_task(_fire_redirect(f"{redirect_uri}?error=access_denied&error_description=user+declined"))
    try:
        with pytest.raises(OAuth2FlowError, match="authorization failed"):
            await capture_code(
                redirect_uri,
                "expected-state",
                auth_url=_STUB_AUTH_URL,
                open_browser=False,
                timeout=10.0,
            )
    finally:
        await fire


async def test_capture_missing_code_raises() -> None:
    """A redirect with the right state but no `code` param raises `OAuth2FlowError`."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    fire = asyncio.create_task(_fire_redirect(f"{redirect_uri}?state=expected-state"))
    try:
        with pytest.raises(OAuth2FlowError, match="no authorization code"):
            await capture_code(
                redirect_uri,
                "expected-state",
                auth_url=_STUB_AUTH_URL,
                open_browser=False,
                timeout=10.0,
            )
    finally:
        await fire


async def test_capture_timeout_raises() -> None:
    """No redirect arriving within `timeout` raises `OAuth2FlowError(no OAuth2 redirect received ...)`."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    with pytest.raises(OAuth2FlowError, match="no OAuth2 redirect received"):
        await capture_code(
            redirect_uri,
            "expected-state",
            auth_url=_STUB_AUTH_URL,
            open_browser=False,
            timeout=0.5,
        )


async def test_capture_no_browser_prints_url(capsys: pytest.CaptureFixture[str]) -> None:
    """`open_browser=False` prints the auth URL to stderr for copy-paste."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    auth_url = "http://idp.example.test/oauth2/authorize?client_id=cid&state=s"
    fire = asyncio.create_task(_fire_redirect(f"{redirect_uri}?code=xyz&state=s"))
    try:
        code = await capture_code(
            redirect_uri,
            "s",
            auth_url=auth_url,
            open_browser=False,
            timeout=10.0,
        )
    finally:
        await fire
    assert code == "xyz"
    captured = capsys.readouterr()
    assert auth_url in captured.err
    assert "Open this URL in a browser to authenticate" in captured.err
