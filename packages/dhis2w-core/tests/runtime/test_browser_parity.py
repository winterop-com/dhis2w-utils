"""Per-version parity for the `browser` plugin service's respx-testable surface.

The Playwright capture path is tested in `packages/dhis2w-browser/tests/` (slow, live). Here we exercise
the HTTP shortcut + auth-dispatch guards (`mint_jsessionid`) across all three trees, so the v41/v43
service module's non-Playwright logic runs. The browser service's Playwright orchestration stays
coverage-omitted (it needs the optional `[browser]` extra + a real page).
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile


@respx.mock
async def test_browser_mint_jsessionid_basic_parity(
    core_version: str,
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A Basic profile's GET /api/me JSESSIONID cookie is returned, on every version tree."""
    service = plugin_service("browser")
    respx.get("http://localhost:8080/api/me").mock(
        return_value=httpx.Response(
            200,
            headers={"set-cookie": "JSESSIONID=abc123deadbeef; Path=/; HttpOnly"},
            json={"id": "M5zQapPyTZI", "username": "admin"},
        ),
    )
    profile = Profile(base_url="http://localhost:8080", auth="basic", username="admin", password="district")
    assert await service.mint_jsessionid(profile) == "abc123deadbeef"


async def test_browser_mint_jsessionid_rejects_pat_parity(
    core_version: str,
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """PAT profiles can't mint a session cookie — the guard raises on every version tree."""
    service = plugin_service("browser")
    profile = Profile(base_url="http://localhost:8080", auth="pat", token="d2p_fake")
    with pytest.raises(service.BrowserWorkflowNotSupported, match="PAT"):
        await service.mint_jsessionid(profile)


async def test_browser_mint_jsessionid_rejects_session_parity(
    core_version: str,
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """Session profiles carry their cookie directly — minting is a no-op that raises on every tree."""
    service = plugin_service("browser")
    profile = Profile(base_url="http://localhost:8080", auth="session", cookie="JSESSIONID=abc123")
    with pytest.raises(service.BrowserWorkflowNotSupported, match="no JSESSIONID to mint"):
        await service.mint_jsessionid(profile)


async def test_browser_authenticated_session_empty_cookie_parity(
    core_version: str,
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A session profile with no cookie raises a truthful error before any browser launch."""
    service = plugin_service("browser")
    profile = Profile(base_url="http://localhost:8080", auth="session")
    with pytest.raises(service.BrowserWorkflowNotSupported, match="no session cookie"):
        async with service.authenticated_session(profile) as _:
            pass


async def test_browser_resolve_banner_username_basic_parity(
    core_version: str,
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A Basic profile's banner username is its own `username` — no HTTP call, on every tree."""
    service = plugin_service("browser")
    profile = Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")
    assert await service.resolve_banner_username(profile) == "admin"


@respx.mock
async def test_browser_resolve_banner_username_session_parity(
    core_version: str,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A session profile (no username) resolves its banner username via /api/me, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("browser")
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"username": "session_user"}),
    )
    profile = Profile(base_url="https://dhis2.example", auth="session", cookie="JSESSIONID=abc123")
    assert await service.resolve_banner_username(profile) == "session_user"
