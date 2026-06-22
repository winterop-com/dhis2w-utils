"""Tests for `d2w profile env` — emit `export DHIS2_*` lines for `eval`."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from dhis2w_core.v41.plugins.profile.cli import app as app_v41
from dhis2w_core.v42.plugins.profile.cli import app as app_v42
from dhis2w_core.v43.plugins.profile.cli import app as app_v43
from typer import Typer
from typer.testing import CliRunner

# One test tree, parametrised over the three version trees — the command is
# identical across them and must honour the profile's pin regardless of tree.
TREES = pytest.mark.parametrize("app", [app_v41, app_v42, app_v43], ids=["v41", "v42", "v43"])


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin TOMLs into tmp_path and strip every env var the resolver consults."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_VERSION"):
        monkeypatch.delenv(key, raising=False)
    yield


def _write_basic_profile(tmp_path: Path, *, version_line: str = 'version = "v41"\n') -> None:
    """Drop a basic-auth profile into the global TOML."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "local_basic"\n\n'
        "[profiles.local_basic]\n"
        'base_url = "http://localhost:8080"\n'
        'auth = "basic"\n'
        'username = "admin"\n'
        'password = "district"\n' + version_line,
        encoding="utf-8",
    )


@TREES
def test_env_emits_exports_with_real_values(app: Typer, tmp_path: Path) -> None:
    """Every field — including the password — is emitted as-is, ready for `eval`."""
    _write_basic_profile(tmp_path)
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "export DHIS2_PROFILE=local_basic" in result.output
    assert "export DHIS2_URL=http://localhost:8080" in result.output
    assert "export DHIS2_VERSION=v41" in result.output
    assert "export DHIS2_USERNAME=admin" in result.output
    assert "export DHIS2_PASSWORD=district" in result.output
    assert "*****" not in result.output


@TREES
def test_env_version_pin_wins_over_tree(app: Typer, tmp_path: Path) -> None:
    """The emitted DHIS2_VERSION is the profile's pin, even from a different tree."""
    _write_basic_profile(tmp_path, version_line='version = "v43"\n')
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "export DHIS2_VERSION=v43" in result.output


@TREES
def test_env_unpinned_falls_back_to_default(app: Typer, tmp_path: Path) -> None:
    """An unpinned profile emits the v42 default and warns on stderr."""
    _write_basic_profile(tmp_path, version_line="")
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "export DHIS2_VERSION=v42" in result.output


@TREES
def test_env_unknown_profile_errors(app: Typer, tmp_path: Path) -> None:
    """A non-existent profile name fails rather than emitting empty exports."""
    _write_basic_profile(tmp_path)
    result = CliRunner().invoke(app, ["env", "ghost"])
    assert result.exit_code != 0
