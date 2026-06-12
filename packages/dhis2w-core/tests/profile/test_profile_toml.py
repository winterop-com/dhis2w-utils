"""Unit tests for TOML profile loading, writing, and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_core.profile import (
    NoProfileError,
    Profile,
    ProfilesFile,
    UnknownProfileError,
    load_catalog,
    load_profiles_file,
    resolve,
    resolve_profile,
    write_profiles_file,
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_VERSION"):
        monkeypatch.delenv(key, raising=False)


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    """Write and read round trip."""
    path = tmp_path / ".dhis2" / "profiles.toml"
    data = ProfilesFile(
        default="local",
        profiles={
            "local": Profile(base_url="http://localhost:8080", auth="pat", token="d2p_x"),
            "prod": Profile(base_url="https://prod.example.org", auth="basic", username="u", password="p"),
        },
    )
    write_profiles_file(path, data)
    assert path.exists()
    loaded = load_profiles_file(path)
    assert loaded.default == "local"
    assert loaded.profiles["local"].token == "d2p_x"
    assert loaded.profiles["prod"].auth == "basic"


def test_resolve_by_project_toml_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve by project toml default."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project_dir = tmp_path / "proj"
    profiles_path = project_dir / ".dhis2" / "profiles.toml"
    write_profiles_file(
        profiles_path,
        ProfilesFile(
            default="local",
            profiles={"local": Profile(base_url="http://x", auth="pat", token="d2p_a")},
        ),
    )
    resolved = resolve(start=project_dir)
    assert resolved.name == "local"
    assert resolved.source == "project-toml"
    assert resolved.profile.base_url == "http://x"


def test_resolve_explicit_name_argument_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve explicit name argument wins."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project_dir = tmp_path / "proj"
    profiles_path = project_dir / ".dhis2" / "profiles.toml"
    write_profiles_file(
        profiles_path,
        ProfilesFile(
            default="local",
            profiles={
                "local": Profile(base_url="http://local", auth="pat", token="d2p_local"),
                "prod": Profile(base_url="http://prod", auth="pat", token="d2p_prod"),
            },
        ),
    )
    resolved = resolve(name="prod", start=project_dir)
    assert resolved.name == "prod"
    assert resolved.source == "arg"


def test_dhis2_profile_env_var_beats_toml_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dhis2 profile env var beats toml default."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project_dir = tmp_path / "proj"
    profiles_path = project_dir / ".dhis2" / "profiles.toml"
    write_profiles_file(
        profiles_path,
        ProfilesFile(
            default="local",
            profiles={
                "local": Profile(base_url="http://local", auth="pat", token="d2p_local"),
                "prod": Profile(base_url="http://prod", auth="pat", token="d2p_prod"),
            },
        ),
    )
    monkeypatch.setenv("DHIS2_PROFILE", "prod")
    resolved = resolve(start=project_dir)
    assert resolved.name == "prod"
    assert resolved.source == "env-profile"


def test_raw_env_beats_toml_when_no_profile_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw env beats toml when no profile name."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project_dir = tmp_path / "proj"
    profiles_path = project_dir / ".dhis2" / "profiles.toml"
    write_profiles_file(
        profiles_path,
        ProfilesFile(
            default="prod",
            profiles={"prod": Profile(base_url="http://prod", auth="pat", token="d2p_prod")},
        ),
    )
    monkeypatch.setenv("DHIS2_URL", "http://raw-env")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    resolved = resolve(start=project_dir)
    assert resolved.source == "env-raw"
    assert resolved.profile.base_url == "http://raw-env"


def test_resolve_raises_when_unknown_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve raises when unknown name."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with pytest.raises(UnknownProfileError):
        resolve(name="does-not-exist", start=tmp_path)


def test_resolve_raises_when_nothing_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve raises when nothing configured."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with pytest.raises(NoProfileError):
        resolve_profile(start=tmp_path)


def test_project_overrides_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Project overrides global."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    # Global "prod" points at A; project "prod" points at B.
    (tmp_path / "xdg" / "dhis2").mkdir(parents=True)
    write_profiles_file(
        tmp_path / "xdg" / "dhis2" / "profiles.toml",
        ProfilesFile(profiles={"prod": Profile(base_url="http://global-prod", auth="pat", token="g")}),
    )
    project_dir = tmp_path / "proj"
    write_profiles_file(
        project_dir / ".dhis2" / "profiles.toml",
        ProfilesFile(profiles={"prod": Profile(base_url="http://project-prod", auth="pat", token="p")}),
    )
    catalog = load_catalog(start=project_dir)
    assert catalog.merged["prod"].profile.base_url == "http://project-prod"
    assert catalog.merged["prod"].source == "project-toml"
