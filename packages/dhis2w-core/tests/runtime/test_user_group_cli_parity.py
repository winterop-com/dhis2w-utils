"""Per-version CLI invocation parity for the `user-group` plugin — exercise cli.py command bodies on all trees.

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


def _user_group(core_version: str) -> object:
    """Build a minimal `UserGroup` model from the matching tree's generated schemas."""
    group_cls = import_module(f"dhis2w_client.generated.{core_version}.oas").UserGroup
    return group_cls.model_validate({"id": "grpUID_12345", "name": "Admins", "displayName": "Admins", "users": []})


def _web_message(core_version: str) -> object:
    """Build a `WebMessageResponse` envelope from the matching tree's client package."""
    envelope_cls = import_module(f"dhis2w_client.{core_version}.envelopes").WebMessageResponse
    return envelope_cls.model_validate({"httpStatus": "OK", "httpStatusCode": 200, "status": "OK"})


def test_user_group_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user group list` renders the groups on every version tree."""
    groups = [_user_group(core_version)]
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_group.service.list_user_groups",
        new=AsyncMock(return_value=groups),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "group", "list"])
    assert result.exit_code == 0, result.output
    assert "grpUID_12345" in result.output


def test_user_group_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user group get <uid>` renders one group on every version tree."""
    group = _user_group(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_group.service.get_user_group",
        new=AsyncMock(return_value=group),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "group", "get", "grpUID_12345"])
    assert result.exit_code == 0, result.output
    assert "grpUID_12345" in result.output


def test_user_group_add_member_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w user group add-member` reports the add on every version tree."""
    envelope = _web_message(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_group.service.add_member",
        new=AsyncMock(return_value=envelope),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "group", "add-member", "grpUID_12345", "userUID_567"])
    assert result.exit_code == 0, result.output
    assert "userUID_567" in result.output


def test_user_group_remove_member_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w user group remove-member` reports the removal on every version tree."""
    envelope = _web_message(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_group.service.remove_member",
        new=AsyncMock(return_value=envelope),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app, ["-p", "probe", "user", "group", "remove-member", "grpUID_12345", "userUID_567"]
        )
    assert result.exit_code == 0, result.output
    assert "userUID_567" in result.output
