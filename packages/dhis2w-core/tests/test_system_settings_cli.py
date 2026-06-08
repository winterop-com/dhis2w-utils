"""CliRunner tests for `dhis2 system` — settings (set / set-many / get / list) + whoami."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.v42 import Me
from dhis2w_core.v42.plugins.system.models import SystemSettingsSnapshot
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


def test_whoami_json_emits_parseable_object(pat_profile: None) -> None:  # noqa: ARG001
    """`dhis2 --json system whoami` emits a JSON object (with `id`), not the plain text form."""
    import json

    me = Me.model_validate({"id": "abc123XYZ", "username": "admin", "displayName": "Admin User"})
    with patch("dhis2w_core.v42.plugins.system.service.whoami", new=AsyncMock(return_value=me)):
        result = _runner.invoke(build_app(), ["--json", "system", "whoami"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["id"] == "abc123XYZ"


def test_whoami_plain_shows_named_refs(pat_profile: None) -> None:  # noqa: ARG001
    """Plain `system whoami` renders roles/groups/org-units as `name (uid)`, plus a superuser hint."""
    me = Me.model_validate(
        {
            "id": "abc123XYZ",
            "username": "admin",
            "displayName": "Admin User",
            "authorities": ["ALL", "F_EXPORT_DATA"],
            "userRoles": [{"id": "r1", "displayName": "Superuser"}],
            "userGroups": [{"id": "g1"}],
            "organisationUnits": [{"id": "ou1", "displayName": "Sierra Leone"}],
        }
    )
    with patch("dhis2w_core.v42.plugins.system.service.whoami", new=AsyncMock(return_value=me)):
        result = _runner.invoke(build_app(), ["system", "whoami"])
    assert result.exit_code == 0, result.output
    assert "superuser" in result.output  # ALL authority -> hint
    assert "Superuser (r1)" in result.output  # role rendered as name (uid)
    assert "Sierra Leone (ou1)" in result.output  # org unit rendered as name (uid)
    assert "g1" in result.output  # group with no displayName falls back to uid
    assert "F_EXPORT_DATA" in result.output  # every authority is listed out


def test_settings_get_prints_value(pat_profile: None) -> None:  # noqa: ARG001
    """`system settings get <key>` prints the value from service.get_setting."""
    with patch("dhis2w_core.v42.plugins.system.service.get_setting", new=AsyncMock(return_value="MoH")):
        result = _runner.invoke(build_app(), ["system", "settings", "get", "applicationTitle"])
    assert result.exit_code == 0, result.output
    assert "MoH" in result.output


def test_settings_get_missing_exits_nonzero(pat_profile: None) -> None:  # noqa: ARG001
    """`system settings get <key>` exits non-zero when the key is unset."""
    with patch("dhis2w_core.v42.plugins.system.service.get_setting", new=AsyncMock(return_value=None)):
        result = _runner.invoke(build_app(), ["system", "settings", "get", "noSuchKey"])
    assert result.exit_code != 0
    assert "not set" in result.output


def test_settings_list_prints_pairs(pat_profile: None) -> None:  # noqa: ARG001
    """`system settings list` prints each key = value pair from the snapshot."""
    snapshot = SystemSettingsSnapshot.model_validate({"applicationTitle": "MoH", "keyDateFormat": "yyyy-MM-dd"})
    with patch("dhis2w_core.v42.plugins.system.service.list_settings", new=AsyncMock(return_value=snapshot)):
        result = _runner.invoke(build_app(), ["system", "settings", "list"])
    assert result.exit_code == 0, result.output
    assert "applicationTitle = MoH" in result.output
    assert "keyDateFormat = yyyy-MM-dd" in result.output
