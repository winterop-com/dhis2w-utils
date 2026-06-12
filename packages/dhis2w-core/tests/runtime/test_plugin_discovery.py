"""Unit tests for dhis2w-core plugin discovery + version-aware startup wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_client import Dhis2
from dhis2w_core.plugin import DEFAULT_VERSION_KEY, discover_plugins, resolve_startup_version
from dhis2w_core.profile import Profile, ProfilesFile, write_profiles_file


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every profile-related env var so tests start from a known state."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_VERSION"):
        monkeypatch.delenv(key, raising=False)


def test_discover_plugins_includes_system() -> None:
    """Discover plugins includes the built-in system plugin."""
    plugins = discover_plugins()
    names = {plugin.name for plugin in plugins}
    assert "system" in names


def test_system_plugin_has_cli_and_mcp_registrars() -> None:
    """System plugin exposes both registrar callables and a description."""
    plugins = {plugin.name: plugin for plugin in discover_plugins()}
    system = plugins["system"]
    assert callable(system.register_cli)
    assert callable(system.register_mcp)
    assert system.description


def test_default_version_is_v42() -> None:
    """v42 is the canonical baseline so no-config bootstrap lands there."""
    assert DEFAULT_VERSION_KEY == "v42"


def test_discover_plugins_default_matches_explicit_v42() -> None:
    """`discover_plugins()` with no arg walks the v42 plugin tree."""
    default_names = sorted(p.name for p in discover_plugins())
    explicit_names = sorted(p.name for p in discover_plugins("v42"))
    assert default_names == explicit_names
    assert len(default_names) > 0


@pytest.mark.parametrize("version_key", ["v41", "v42", "v43"])
def test_discover_plugins_finds_each_version_tree(version_key: str) -> None:
    """Each `v{N}/plugins/` tree carries the same plugin set today (mechanical copies)."""
    found = discover_plugins(version_key)
    names = {p.name for p in found}
    assert "metadata" in names
    assert "system" in names


def test_discover_plugins_unknown_version_returns_no_builtins() -> None:
    """A bogus version_key picks up no built-ins; entry-point plugins still run."""
    builtin_names = {"metadata", "system", "tracker", "aggregate"}
    found_names = {p.name for p in discover_plugins("v99")}
    assert not (builtin_names & found_names)


def test_resolve_startup_version_defaults_when_no_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No profile configured -> v42 fallback."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    assert resolve_startup_version() == "v42"


def test_resolve_startup_version_reads_profile_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile with explicit version -> that version key is returned."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project_dir = tmp_path / "proj"
    write_profiles_file(
        project_dir / ".dhis2" / "profiles.toml",
        ProfilesFile(
            default="local",
            profiles={
                "local": Profile(base_url="http://localhost:8080", auth="pat", token="d2p_x", version=Dhis2.V43),
            },
        ),
    )
    monkeypatch.chdir(project_dir)
    assert resolve_startup_version() == "v43"


def test_resolve_startup_version_defaults_when_profile_has_no_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile present but missing the version field -> v42 fallback (auto-detect at wire time)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project_dir = tmp_path / "proj"
    write_profiles_file(
        project_dir / ".dhis2" / "profiles.toml",
        ProfilesFile(
            default="local",
            profiles={"local": Profile(base_url="http://localhost:8080", auth="pat", token="d2p_x")},
        ),
    )
    monkeypatch.chdir(project_dir)
    assert resolve_startup_version() == "v42"
