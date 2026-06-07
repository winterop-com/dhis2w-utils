"""CliRunner tests for `dhis2 system settings` (set / set-many)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_runner = CliRunner()


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a global profiles.toml with one PAT profile and point resolution at it."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


def test_settings_set_writes_single_key(pat_profile: None) -> None:  # noqa: ARG001
    """`dhis2 system settings set KEY VALUE` routes to service.set_system_setting."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.system.service.set_system_setting", new=mock):
        result = _runner.invoke(build_app(), ["system", "settings", "set", "applicationTitle", "MoH"])
    assert result.exit_code == 0, result.output
    assert "set applicationTitle" in result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("applicationTitle", "MoH")


def test_settings_set_many_applies_object(pat_profile: None, tmp_path: Path) -> None:  # noqa: ARG001
    """`dhis2 system settings set-many file.json` bulk-applies a {key: value} object."""
    file = tmp_path / "s.json"
    file.write_text('{"applicationTitle": "MoH", "keyApplicationFooter": "bye"}', encoding="utf-8")
    mock = AsyncMock(return_value=["applicationTitle", "keyApplicationFooter"])
    with patch("dhis2w_core.v42.plugins.system.service.set_system_settings", new=mock):
        result = _runner.invoke(build_app(), ["system", "settings", "set-many", str(file)])
    assert result.exit_code == 0, result.output
    assert "set applicationTitle" in result.output


def test_settings_set_many_rejects_non_object(pat_profile: None, tmp_path: Path) -> None:  # noqa: ARG001
    """`set-many` fails on non-object JSON (e.g. a top-level list)."""
    bad = tmp_path / "bad.json"
    bad.write_text('["a", "b"]', encoding="utf-8")
    result = _runner.invoke(build_app(), ["system", "settings", "set-many", str(bad)])
    assert result.exit_code != 0
    assert "object" in result.output.lower() or "key" in result.output.lower()
