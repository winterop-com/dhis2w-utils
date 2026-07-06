"""Verify-path resolution: the caller's `start` drives the catalog used for lookup and scope.

`verify_profile(name, start=...)` and `verify_all_profiles(start=...)` must work against a
project-local `profiles.toml` discovered from `start`, even when the process cwd (and the global
config) know nothing about that profile. A broken profile in the sweep becomes a
`VerifyResult(ok=False)` entry instead of aborting the whole run.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

_HOST = "https://dhis2.example"

_PROJECT_PROFILES_TOML = f"""\
default = "proj_only"

[profiles.proj_only]
base_url = "{_HOST}"
auth = "basic"
username = "admin"
password = "district"
"""


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project-scoped profiles.toml under tmp, with cwd and the global config pointed elsewhere."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    project = tmp_path / "project"
    (project / ".dhis2").mkdir(parents=True)
    (project / ".dhis2" / "profiles.toml").write_text(_PROJECT_PROFILES_TOML, encoding="utf-8")
    empty_config = tmp_path / "xdg"
    empty_config.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(empty_config))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    return project


def _mock_probe_endpoints(mock_system_info: Callable[..., None], core_version: str) -> None:
    """Mock the /api/system/info + /api/me probes `_verify_one` performs."""
    mock_system_info(core_version)
    respx.get(f"{_HOST}/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "usr01234567", "username": "admin"}),
    )


@respx.mock
async def test_verify_profile_resolves_against_start_catalog(
    core_version: str,
    project_dir: Path,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A project-only profile verifies via `start` even when cwd has no catalog entry for it."""
    _mock_probe_endpoints(mock_system_info, core_version)
    service = plugin_service("profile")

    result = await service.verify_profile("proj_only", start=project_dir)

    assert result.ok, result.error
    assert result.name == "proj_only"
    assert result.username == "admin"


@respx.mock
async def test_verify_all_profiles_covers_project_only_profiles(
    core_version: str,
    project_dir: Path,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """The sweep verifies profiles that exist only in the `start` project catalog."""
    _mock_probe_endpoints(mock_system_info, core_version)
    service = plugin_service("profile")

    results = await service.verify_all_profiles(start=project_dir)

    assert [r.name for r in results] == ["proj_only"]
    assert results[0].ok, results[0].error


async def test_verify_all_profiles_converts_probe_failures(
    core_version: str,
    project_dir: Path,
    plugin_service: Callable[[str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-profile failure becomes a VerifyResult(ok=False) entry, not an exception out of the sweep."""
    service = plugin_service("profile")

    async def _boom(resolved: object) -> object:
        raise RuntimeError("token store exploded")

    monkeypatch.setattr(service, "_verify_one", _boom)

    results = await service.verify_all_profiles(start=project_dir)

    assert [r.name for r in results] == ["proj_only"]
    assert results[0].ok is False
    assert "token store exploded" in (results[0].error or "")
