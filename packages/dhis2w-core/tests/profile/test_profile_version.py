"""Tests for the `Profile.version` field and `DHIS2_VERSION` env propagation."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_client import Dhis2
from dhis2w_core.profile import (
    Profile,
    ProfilesFile,
    load_profiles_file,
    resolve,
    write_profiles_file,
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every env var the profile resolver consults."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_VERSION"):
        monkeypatch.delenv(key, raising=False)


def test_profile_defaults_to_no_version() -> None:
    """A profile without an explicit version stays None so auto-detect kicks in."""
    profile = Profile(base_url="http://x", auth="pat", token="d2p_x")
    assert profile.version is None


@pytest.mark.parametrize("value", [Dhis2.V41, Dhis2.V42, Dhis2.V43])
def test_profile_accepts_supported_versions(value: Dhis2) -> None:
    """Each supported major round-trips through the model."""
    profile = Profile(base_url="http://x", auth="pat", token="d2p_x", version=value)
    assert profile.version == value


def test_profile_rejects_unsupported_version() -> None:
    """An unknown major fails validation rather than silently passing through."""
    with pytest.raises(ValueError):
        Profile(base_url="http://x", auth="pat", token="d2p_x", version="v40")  # type: ignore[arg-type]


def test_version_round_trips_through_toml(tmp_path: Path) -> None:
    """`version` survives a write/read cycle on the TOML file."""
    path = tmp_path / ".dhis2" / "profiles.toml"
    data = ProfilesFile(
        default="local",
        profiles={
            "local": Profile(base_url="http://localhost:8080", auth="pat", token="d2p_x", version=Dhis2.V43),
        },
    )
    write_profiles_file(path, data)
    text = path.read_text(encoding="utf-8")
    assert 'version = "v43"' in text
    loaded = load_profiles_file(path)
    assert loaded.profiles["local"].version == Dhis2.V43


def test_version_omitted_when_none_on_toml_write(tmp_path: Path) -> None:
    """A None version stays out of the rendered TOML so the file stays clean."""
    path = tmp_path / ".dhis2" / "profiles.toml"
    data = ProfilesFile(
        profiles={"local": Profile(base_url="http://localhost:8080", auth="pat", token="d2p_x")},
    )
    write_profiles_file(path, data)
    text = path.read_text(encoding="utf-8")
    assert "version" not in text


def test_env_raw_picks_up_dhis2_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DHIS2_VERSION env (no `v` prefix) populates `Profile.version` in raw-env mode."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    monkeypatch.setenv("DHIS2_VERSION", "43")
    resolved = resolve(start=tmp_path)
    assert resolved.profile.version is Dhis2.V43


def test_env_raw_accepts_v_prefixed_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DHIS2_VERSION already prefixed with `v` works too."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    monkeypatch.setenv("DHIS2_VERSION", "v42")
    resolved = resolve(start=tmp_path)
    assert resolved.profile.version is Dhis2.V42


def test_env_raw_ignores_unknown_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown major in DHIS2_VERSION is dropped; auto-detect remains the fallback."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    monkeypatch.setenv("DHIS2_VERSION", "v40")
    resolved = resolve(start=tmp_path)
    assert resolved.profile.version is None


def test_env_raw_no_version_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without DHIS2_VERSION the profile arrives with version=None."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    resolved = resolve(start=tmp_path)
    assert resolved.profile.version is None
