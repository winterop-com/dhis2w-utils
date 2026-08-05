"""Shared fixtures for dhis2w-codegen tests (mirrors dhis2w-client's local fixtures)."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest


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
    """Base URL of the local DHIS2 instance used by codegen integration tests."""
    return _SEEDED_ENVIRONMENT.get("DHIS2_LOCAL_URL", "http://localhost:8080").rstrip("/")


@pytest.fixture(scope="session")
def local_username() -> str:
    """Username for the local DHIS2 instance (Basic auth)."""
    return _SEEDED_ENVIRONMENT.get("DHIS2_LOCAL_USER", "admin")


@pytest.fixture(scope="session")
def local_password() -> str:
    """Password for the local DHIS2 instance (Basic auth)."""
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
    """Whether the local DHIS2 instance is reachable; skip integration tests otherwise."""
    return _is_local_reachable(local_url)
