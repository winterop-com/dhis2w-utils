"""Shared fixtures for dhis2w-core tests, incl. per-version plugin parametrization.

Core plugin tests import a service module from one version tree (`dhis2w_core.v42.plugins.X`)
and call it. To cover the v41/v43 plugin code — which is otherwise omitted from coverage and
only smoke-tested — a test takes `core_version` + `plugin_service` and resolves the service
module dynamically, so one test body exercises all three trees. `mock_system_info(core_version)`
mocks `/api/system/info` to the matching wire version so the client the service opens dispatches
its accessors to the same tree.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

_CORE_WIRE_VERSIONS = {"v41": "2.41.8.1", "v42": "2.42.0", "v43": "2.43.0"}


@pytest.fixture(params=list(_CORE_WIRE_VERSIONS))
def core_version(request: pytest.FixtureRequest) -> str:
    """Parametrize a core plugin test across all three version trees (v41/v42/v43)."""
    return str(request.param)


@pytest.fixture
def plugin_service(core_version: str) -> Callable[[str], ModuleType]:
    """Return a helper that imports a plugin's service module for the parametrized version tree."""

    def _service(plugin_name: str) -> ModuleType:
        return import_module(f"dhis2w_core.{core_version}.plugins.{plugin_name}.service")

    return _service


@pytest.fixture
def mock_system_info() -> Callable[..., None]:
    """Return a helper that mocks `/api/system/info` to a version key's wire version (respx-active)."""

    def _mock(version_key: str, base_url: str = "https://dhis2.example") -> None:
        respx.get(f"{base_url}/api/system/info").mock(
            return_value=httpx.Response(200, json={"version": _CORE_WIRE_VERSIONS[version_key]}),
        )

    return _mock


@pytest.fixture
def core_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a profiles.toml with a Basic `probe` profile the services can open_client on."""
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
