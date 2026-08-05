"""Shared pytest fixtures for dhis2w-client tests, including live DHIS2 access."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

# --- per-version accessor coverage -------------------------------------------------
# A respx accessor unit test that connects via `Dhis2Client` and mocks `/api/system/info`
# exercises whichever version tree the connected server reports (the client dispatches
# accessors by major on connect). Parametrizing the mocked version therefore re-runs the
# same v42 test against the v41 + v43 accessor trees — closing their coverage without
# duplicating the test. Use both fixtures: take `server_version`, then call
# `mock_system_info(server_version)` in place of a hardcoded `2.42.0` preamble.

_SERVER_VERSIONS = {"v41": "2.41.4", "v42": "2.42.0", "v43": "2.43.0"}


@pytest.fixture(params=list(_SERVER_VERSIONS))
def server_version(request: pytest.FixtureRequest) -> str:
    """Parametrize a respx accessor test across all three DHIS2 majors (wire version string)."""
    return _SERVER_VERSIONS[request.param]


_PLAY_SERVERS = {
    "v41": "https://play.im.dhis2.org/dev-2-41",
    "v42": "https://play.im.dhis2.org/dev-2-42",
    "v43": "https://play.im.dhis2.org/dev-2-43",
}


@pytest.fixture(params=list(_PLAY_SERVERS))
def play_target(request: pytest.FixtureRequest) -> tuple[str, str]:
    """Live read-only DHIS2 play server per major: returns (base_url, version_key).

    Skips if the server isn't reachable, so offline runs don't fail. Reads only — the
    live tier never writes to the shared play demo (writes go to a local stack).
    """
    version_key = str(request.param)
    url = _PLAY_SERVERS[version_key]
    try:
        with httpx.Client(timeout=5.0) as client:
            client.get(f"{url}/api/system/info.json", auth=("admin", "district")).raise_for_status()
    except (httpx.RequestError, httpx.HTTPError):
        pytest.skip(f"play {version_key} not reachable at {url}")
    return url, version_key


@pytest.fixture
def mock_system_info() -> Callable[..., None]:
    """Return a helper that mocks the redirect probe + `/api/system/info` for a given version.

    The connected `Dhis2Client` then binds that major's accessor tree, so the test body runs
    against v41 / v42 / v43 depending on the version passed.
    """

    def _mock(version: str, base_url: str = "https://dhis2.example") -> None:
        respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text="<html></html>"))
        respx.get(f"{base_url}/api/system/info").mock(return_value=httpx.Response(200, json={"version": version}))

    return _mock


def _load_seeded_environment(start: Path) -> dict[str, str]:
    """Snapshot the environment with `infra/home/credentials/.env.auth` merged in underneath it.

    The seeded credentials stay in this mapping instead of going into `os.environ`: `DHIS2_URL`
    and its credential pair are the highest-precedence layer of profile resolution, so leaving
    them in the process environment makes every profile-resolving test in the session resolve
    against the local stack instead of the profile its own fixture wrote. Tests that want the
    seeded stack take the fixtures below and `monkeypatch.setenv` it for themselves.
    """
    values = dict(os.environ)
    for parent in [start, *start.parents]:
        candidate = parent / "infra" / "home" / "credentials" / ".env.auth"
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values.setdefault(key.strip(), value.strip())
        break
    return values


_SEEDED_ENVIRONMENT = _load_seeded_environment(Path(__file__).resolve())


@pytest.fixture(scope="session")
def local_url() -> str:
    """Base URL of the local DHIS2 instance used by destructive integration tests."""
    return _SEEDED_ENVIRONMENT.get("DHIS2_LOCAL_URL", "http://localhost:8080").rstrip("/")


@pytest.fixture(scope="session")
def local_username() -> str:
    """Username for the local DHIS2 instance (Basic auth fallback)."""
    return _SEEDED_ENVIRONMENT.get("DHIS2_LOCAL_USER", "admin")


@pytest.fixture(scope="session")
def local_password() -> str:
    """Password for the local DHIS2 instance (Basic auth fallback)."""
    return _SEEDED_ENVIRONMENT.get("DHIS2_LOCAL_PASS", "district")


def _is_local_reachable(url: str) -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            client.get(f"{url}/dhis-web-login/")
        return True
    except (httpx.RequestError, httpx.HTTPError):
        return False


@pytest.fixture(scope="session")
def local_available(local_url: str) -> bool:
    """Whether the local DHIS2 instance is reachable; skip destructive tests otherwise."""
    return _is_local_reachable(local_url)


@pytest.fixture(scope="session")
def local_pat(
    local_url: str,
    local_username: str,
    local_password: str,
    local_available: bool,
) -> Iterator[str]:
    """Return a valid PAT for the local DHIS2 instance.

    Prefers the `DHIS2_LOCAL_PAT` env var (fast reuse). Otherwise mints a fresh
    PAT via Playwright. Skips the requesting test if neither is available.
    """
    env_token = _SEEDED_ENVIRONMENT.get("DHIS2_LOCAL_PAT")
    if env_token:
        yield env_token
        return
    if not local_available:
        pytest.skip(f"local DHIS2 not reachable at {local_url}")
    try:
        from dhis2w_browser.pat import create_pat
    except ImportError:
        pytest.skip("dhis2w-browser not installed — cannot mint PAT via Playwright")
    try:
        token = asyncio.run(create_pat(local_url, local_username, local_password))
    except Exception as exc:  # noqa: BLE001 — surface as skip so we don't wedge CI
        pytest.skip(f"PAT creation failed: {exc}")
    yield token
