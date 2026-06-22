"""Per-version CLI invocation parity for the `system` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def test_system_whoami_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w system whoami` renders the authenticated user on every version tree."""
    me_cls = import_module(f"dhis2w_client.{core_version}").Me
    me = me_cls.model_validate({"id": "usr01234567", "username": "admin", "authorities": ["ALL"]})
    with patch(f"dhis2w_core.{core_version}.plugins.system.service.whoami", new=AsyncMock(return_value=me)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "system", "whoami"])
    assert result.exit_code == 0, result.output
    assert "admin" in result.output


def test_system_info_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w system info` renders the system info envelope on every version tree."""
    info_cls = import_module(f"dhis2w_client.{core_version}").SystemInfo
    info = info_cls.model_validate({"version": "2.42.0", "systemName": "DHIS2 Demo", "systemId": "sys01234567"})
    with patch(f"dhis2w_core.{core_version}.plugins.system.service.system_info", new=AsyncMock(return_value=info)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "system", "info"])
    assert result.exit_code == 0, result.output
    assert "2.42.0" in result.output


def test_system_calendar_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w system calendar` (no value) prints the active calendar on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.system.service.get_calendar",
        new=AsyncMock(return_value="ethiopian"),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "system", "calendar"])
    assert result.exit_code == 0, result.output
    assert "ethiopian" in result.output


def test_system_settings_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w system settings get <key>` prints the setting value on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.system.service.get_setting",
        new=AsyncMock(return_value="sierra_leone"),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "system", "settings", "get", "keyFlag"])
    assert result.exit_code == 0, result.output
    assert "sierra_leone" in result.output


def test_system_settings_set_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w system settings set <key> <value>` confirms the write on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.system.service.set_system_setting",
        new=AsyncMock(return_value=None),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "system", "settings", "set", "applicationTitle", "Demo"])
    assert result.exit_code == 0, result.output
    assert "applicationTitle" in result.output


def test_system_settings_list_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w system settings list` renders every key=value pair on every version tree."""
    snapshot_cls = import_module(f"dhis2w_core.{core_version}.plugins.system.models").SystemSettingsSnapshot
    snapshot = snapshot_cls.model_validate({"keyCalendar": "iso8601", "keyFlag": "sierra_leone"})
    with patch(
        f"dhis2w_core.{core_version}.plugins.system.service.list_settings",
        new=AsyncMock(return_value=snapshot),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "system", "settings", "list"])
    assert result.exit_code == 0, result.output
    assert "keyCalendar = iso8601" in result.output
