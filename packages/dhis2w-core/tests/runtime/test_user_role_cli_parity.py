"""Per-version CLI invocation parity for the `user-role` plugin — exercise cli.py command bodies on all trees.

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
    monkeypatch.setenv("DHIS2_VERSION", core_version.removeprefix("v"))
    return build_app()


def _user_role(core_version: str) -> object:
    """Build a minimal `UserRole` model from the matching tree's generated schemas."""
    role_cls = import_module(f"dhis2w_client.generated.{core_version}.oas").UserRole
    return role_cls.model_validate(
        {"id": "rolUID_12345", "name": "Superuser", "displayName": "Superuser", "authorities": ["ALL"], "users": []}
    )


def _web_message(core_version: str) -> object:
    """Build a `WebMessageResponse` envelope from the matching tree's client package."""
    envelope_cls = import_module(f"dhis2w_client.{core_version}.envelopes").WebMessageResponse
    return envelope_cls.model_validate({"httpStatus": "OK", "httpStatusCode": 200, "status": "OK"})


def test_user_role_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user role list` renders the roles on every version tree."""
    roles = [_user_role(core_version)]
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_role.service.list_user_roles",
        new=AsyncMock(return_value=roles),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "role", "list"])
    assert result.exit_code == 0, result.output
    assert "rolUID_12345" in result.output


def test_user_role_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user role get <uid>` renders one role on every version tree."""
    role = _user_role(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_role.service.get_user_role",
        new=AsyncMock(return_value=role),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "role", "get", "rolUID_12345"])
    assert result.exit_code == 0, result.output
    assert "rolUID_12345" in result.output


def test_user_role_authority_list_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w user role authority-list <uid>` prints the authorities on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_role.service.list_authorities",
        new=AsyncMock(return_value=["ALL", "F_USER_ADD"]),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "role", "authority-list", "rolUID_12345"])
    assert result.exit_code == 0, result.output
    assert "F_USER_ADD" in result.output


def test_user_role_add_user_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user role add-user` reports the grant on every version tree."""
    envelope = _web_message(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_role.service.add_user",
        new=AsyncMock(return_value=envelope),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "role", "add-user", "rolUID_12345", "userUID_567"])
    assert result.exit_code == 0, result.output
    assert "userUID_567" in result.output


def test_user_role_remove_user_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w user role remove-user` reports the revoke on every version tree."""
    envelope = _web_message(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.user_role.service.remove_user",
        new=AsyncMock(return_value=envelope),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "role", "remove-user", "rolUID_12345", "userUID_567"])
    assert result.exit_code == 0, result.output
    assert "userUID_567" in result.output
