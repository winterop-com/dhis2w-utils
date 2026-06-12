"""Unit tests for `d2w profile rename` service behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_core.profile import (
    InvalidProfileNameError,
    Profile,
    ProfilesFile,
    UnknownProfileError,
    load_profiles_file,
    write_profiles_file,
)
from dhis2w_core.v42.plugins.profile.service import ProfileAlreadyExistsError, rename_profile


def _clear_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _seed(project_dir: Path, *, default: str = "prod") -> Path:
    path = project_dir / ".dhis2" / "profiles.toml"
    write_profiles_file(
        path,
        ProfilesFile(
            default=default,
            profiles={
                "local": Profile(base_url="http://localhost", auth="pat", token="d2p_l"),
                "prod": Profile(base_url="https://prod.example", auth="pat", token="d2p_p"),
            },
        ),
    )
    return path


def test_rename_updates_file_and_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Rename updates file and default."""
    _clear_env(monkeypatch, tmp_path)
    project_dir = tmp_path / "proj"
    _seed(project_dir, default="prod")

    rename_profile("prod", "prodeu", start=project_dir)

    reloaded = load_profiles_file(project_dir / ".dhis2" / "profiles.toml")
    assert "prodeu" in reloaded.profiles
    assert "prod" not in reloaded.profiles
    assert reloaded.default == "prodeu"


def test_rename_non_default_leaves_default_alone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Rename non default leaves default alone."""
    _clear_env(monkeypatch, tmp_path)
    project_dir = tmp_path / "proj"
    _seed(project_dir, default="prod")

    rename_profile("local", "laohis42", start=project_dir)

    reloaded = load_profiles_file(project_dir / ".dhis2" / "profiles.toml")
    assert "laohis42" in reloaded.profiles
    assert reloaded.default == "prod"


def test_rename_rejects_invalid_new_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Rename rejects invalid new name."""
    _clear_env(monkeypatch, tmp_path)
    project_dir = tmp_path / "proj"
    _seed(project_dir)
    with pytest.raises(InvalidProfileNameError):
        rename_profile("prod", "he llo", start=project_dir)


def test_rename_refuses_to_clobber_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Rename refuses to clobber existing."""
    _clear_env(monkeypatch, tmp_path)
    project_dir = tmp_path / "proj"
    _seed(project_dir)
    with pytest.raises(ProfileAlreadyExistsError):
        rename_profile("prod", "local", start=project_dir)


def test_rename_raises_for_unknown_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Rename raises for unknown profile."""
    _clear_env(monkeypatch, tmp_path)
    project_dir = tmp_path / "proj"
    _seed(project_dir)
    with pytest.raises(UnknownProfileError):
        rename_profile("ghost", "something", start=project_dir)
