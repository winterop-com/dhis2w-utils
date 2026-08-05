"""Shared fixtures for dhis2w-fhir tests: a probe profile, system-info mocking, and the attribute join."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

_WIRE_VERSIONS = {"v41": "2.41.8.1", "v42": "2.42.0", "v43": "2.43.0"}


@pytest.fixture(params=list(_WIRE_VERSIONS))
def wire_version(request: pytest.FixtureRequest) -> str:
    """Parametrize a test across the supported DHIS2 majors (the client auto-detects on connect)."""
    return str(request.param)


@pytest.fixture
def mock_system_info() -> Callable[..., None]:
    """Return a helper that mocks `/api/system/info` to a version key's wire version (respx-active)."""

    def _mock(version_key: str, base_url: str = "https://dhis2.example") -> None:
        respx.get(f"{base_url}/api/system/info").mock(
            return_value=httpx.Response(200, json={"version": _WIRE_VERSIONS[version_key]}),
        )

    return _mock


@pytest.fixture
def mock_attributes() -> Callable[..., None]:
    """Return a helper that mocks `/api/attributes` to a `uid -> code` mapping (respx-active).

    Every generate target that emits resources resolves the attribute code index off this
    endpoint, so a target test leaving it unmocked fails on the unmatched request rather than
    quietly emitting attribute extensions without their codes.
    """

    def _mock(codes: dict[str, str] | None = None, base_url: str = "https://dhis2.example") -> None:
        attributes = [{"id": uid, "code": code} for uid, code in (codes or {}).items()]
        respx.get(f"{base_url}/api/attributes").mock(
            return_value=httpx.Response(200, json={"attributes": attributes}),
        )

    return _mock


@pytest.fixture
def probe_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a profiles.toml with a Basic `probe` profile the service can open_client on."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)
