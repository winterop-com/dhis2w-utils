"""Unit tests for the `browser` plugin's service layer.

Slow, live-stack tests for the full Playwright path live in
`packages/dhis2w-browser/tests/`; this file exercises the profile-dispatch
+ HTTP shortcut in isolation via respx.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.browser.service import (
    BrowserWorkflowNotSupported,
    mint_jsessionid,
)


async def test_mint_jsessionid_rejects_pat_profile() -> None:
    """PAT profiles can't produce a session cookie — must raise a clear error."""
    pat_profile = Profile(base_url="http://localhost:8080", auth="pat", token="d2p_fake")
    with pytest.raises(BrowserWorkflowNotSupported, match="PAT profiles"):
        await mint_jsessionid(pat_profile)


async def test_mint_jsessionid_rejects_oauth2_profile() -> None:
    """OAuth2 dispatch is not wired; should raise BrowserWorkflowNotSupported with an actionable message."""
    oauth2_profile = Profile(
        base_url="http://localhost:8080",
        auth="oauth2",
        client_id="cid",
        client_secret="csecret",
    )
    with pytest.raises(BrowserWorkflowNotSupported, match="OAuth2 / OIDC profiles cannot drive browser workflows"):
        await mint_jsessionid(oauth2_profile)


@respx.mock
async def test_mint_jsessionid_basic_captures_set_cookie() -> None:
    """Basic profile: GET /api/me → response's JSESSIONID cookie is returned."""
    respx.get("http://localhost:8080/api/me").mock(
        return_value=httpx.Response(
            200,
            headers={"set-cookie": "JSESSIONID=abc123deadbeef; Path=/; HttpOnly; SameSite=Lax"},
            json={"id": "M5zQapPyTZI", "username": "admin"},
        ),
    )
    profile = Profile(
        base_url="http://localhost:8080",
        auth="basic",
        username="admin",
        password="district",
    )
    jsessionid = await mint_jsessionid(profile)
    assert jsessionid == "abc123deadbeef"


@respx.mock
async def test_mint_jsessionid_basic_raises_when_no_cookie_returned() -> None:
    """Defensive path: a 200 without Set-Cookie means Basic auth is disabled server-side."""
    respx.get("http://localhost:8080/api/me").mock(
        return_value=httpx.Response(200, json={"id": "abc", "username": "admin"}),
    )
    profile = Profile(
        base_url="http://localhost:8080",
        auth="basic",
        username="admin",
        password="district",
    )
    with pytest.raises(RuntimeError, match="did not return a JSESSIONID"):
        await mint_jsessionid(profile)


async def test_mint_jsessionid_basic_without_credentials_raises() -> None:
    """Basic auth type but missing username/password: refuses to proceed."""
    profile = Profile(base_url="http://localhost:8080", auth="basic")
    with pytest.raises(BrowserWorkflowNotSupported, match="no username/password"):
        await mint_jsessionid(profile)
