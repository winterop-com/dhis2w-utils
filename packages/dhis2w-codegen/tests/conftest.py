"""Shared fixtures for dhis2w-codegen tests (mirrors dhis2w-client's local fixtures)."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest


def _load_seeded_env(start: Path) -> None:
    """Load `infra/home/credentials/.env.auth` into os.environ if present (setdefault)."""
    for parent in [start, *start.parents]:
        candidate = parent / "infra" / "home" / "credentials" / ".env.auth"
        if candidate.exists():
            for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
            return


_load_seeded_env(Path(__file__).resolve())


@pytest.fixture(scope="session")
def local_url() -> str:
    """Base URL of the local DHIS2 instance used by codegen integration tests."""
    return os.environ.get("DHIS2_LOCAL_URL", "http://localhost:8080").rstrip("/")


@pytest.fixture(scope="session")
def local_username() -> str:
    """Username for the local DHIS2 instance (Basic auth)."""
    return os.environ.get("DHIS2_LOCAL_USER", "admin")


@pytest.fixture(scope="session")
def local_password() -> str:
    """Password for the local DHIS2 instance (Basic auth)."""
    return os.environ.get("DHIS2_LOCAL_PASS", "district")


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
