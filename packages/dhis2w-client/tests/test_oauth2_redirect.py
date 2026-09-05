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


async def _get_once_up(client: httpx.AsyncClient, url: str, *, max_tries: int = 30) -> httpx.Response:
    """GET `url` as soon as the receiver is listening, returning its response."""
    last_err: Exception | None = None
    for _ in range(max_tries):
        try:
            return await client.get(url)
        except httpx.ConnectError as exc:
            last_err = exc
            await asyncio.sleep(0.05)
    raise AssertionError(f"receiver never accepted a connection on {url}") from last_err


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


async def test_capture_wrong_state_is_ignored_and_flow_survives() -> None:
    """A code carrying someone else's state gets a 404 and the receiver keeps waiting."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"

    async def fire_wrong_then_right() -> int:
        async with httpx.AsyncClient(timeout=2.0) as http_client:
            stray = await _get_once_up(http_client, f"{redirect_uri}?code=abc&state=wrong")
            await http_client.get(f"{redirect_uri}?code=survivor&state=right")
        return stray.status_code

    fire = asyncio.create_task(fire_wrong_then_right())
    try:
        code = await capture_code(
            redirect_uri,
            "right",
            auth_url=_STUB_AUTH_URL,
            open_browser=False,
            timeout=10.0,
        )
    finally:
        stray_status = await fire
    assert code == "survivor"
    assert stray_status == 404


async def test_capture_error_param_raises() -> None:
    """An `error=...` redirect from the IdP surfaces as `OAuth2FlowError(authorization failed: ...)`."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    fire = asyncio.create_task(
        _fire_redirect(f"{redirect_uri}?error=access_denied&error_description=user+declined&state=expected-state")
    )
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


async def test_capture_ignores_requests_without_code() -> None:
    """Stray local requests (port scans, preconnects, favicon fetches) get a 404 and don't kill the flow.

    The receiver listens on a fixed loopback port, so unrelated local
    traffic is routine. Anything without a `code` query parameter must be
    answered 404 and ignored — the flow keeps waiting for the real
    redirect and resolves normally afterwards.
    """
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"

    async def fire_strays_then_redirect() -> list[int]:
        statuses: list[int] = []
        stray_paths = ["favicon.ico", "?probe=1", "?state=expected-state", ""]
        async with httpx.AsyncClient(timeout=2.0) as http_client:
            for stray_path in stray_paths:
                for _ in range(30):
                    try:
                        response = await http_client.get(f"{redirect_uri}{stray_path}")
                        statuses.append(response.status_code)
                        break
                    except httpx.ConnectError:
                        await asyncio.sleep(0.05)
            await http_client.get(f"{redirect_uri}?code=survivor&state=expected-state")
        return statuses

    fire = asyncio.create_task(fire_strays_then_redirect())
    try:
        code = await capture_code(
            redirect_uri,
            "expected-state",
            auth_url=_STUB_AUTH_URL,
            open_browser=False,
            timeout=10.0,
        )
    finally:
        stray_statuses = await fire
    assert code == "survivor"
    assert stray_statuses == [404, 404, 404, 404]


async def test_capture_code_without_state_is_ignored() -> None:
    """A request that carries a `code` but no `state` is 404ed — the CSRF guard stays intact."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    fire = asyncio.create_task(_fire_redirect(f"{redirect_uri}?code=abc"))
    try:
        with pytest.raises(OAuth2FlowError, match="no OAuth2 redirect received"):
            await capture_code(
                redirect_uri,
                "expected-state",
                auth_url=_STUB_AUTH_URL,
                open_browser=False,
                timeout=1.0,
            )
    finally:
        await fire


async def test_capture_wrong_state_error_does_not_end_the_flow() -> None:
    """A forged `error=` callback without this flow's state cannot terminate the login."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"

    async def fire_forged_then_real() -> int:
        async with httpx.AsyncClient(timeout=2.0) as http_client:
            forged = await _get_once_up(http_client, f"{redirect_uri}?error=access_denied&state=wrong")
            await http_client.get(f"{redirect_uri}?code=real-code&state=expected-state")
        return forged.status_code

    fire = asyncio.create_task(fire_forged_then_real())
    try:
        code = await capture_code(
            redirect_uri,
            "expected-state",
            auth_url=_STUB_AUTH_URL,
            open_browser=False,
            timeout=10.0,
        )
    finally:
        forged_status = await fire
    assert code == "real-code"
    assert forged_status == 404


async def test_capture_error_description_is_html_escaped() -> None:
    """Markup in `error_description` reaches the browser as text, never as active HTML."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    description = "<script>alert('x')</script>"
    body: dict[str, str] = {}

    async def fire_error() -> None:
        async with httpx.AsyncClient(timeout=2.0) as http_client:
            for _ in range(30):
                try:
                    response = await http_client.get(
                        redirect_uri,
                        params={
                            "error": "invalid_request",
                            "error_description": description,
                            "state": "expected-state",
                        },
                    )
                    body["html"] = response.text
                    return
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)

    fire = asyncio.create_task(fire_error())
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
    assert "<script>" not in body["html"]
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in body["html"]


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
