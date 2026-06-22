"""Per-version CLI invocation parity for the `user` plugin — exercise cli.py command bodies on all trees.

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


def _user(core_version: str) -> object:
    """Build a minimal `User` model from the matching tree's generated schemas."""
    user_cls = import_module(f"dhis2w_client.generated.{core_version}.oas").User
    return user_cls.model_validate({"id": "abcDEFghiJK", "username": "alice", "displayName": "Alice Example"})


def _web_message(core_version: str, uid: str | None = None) -> object:
    """Build a `WebMessageResponse` envelope from the matching tree's client package."""
    envelope_cls = import_module(f"dhis2w_client.{core_version}.envelopes").WebMessageResponse
    payload: dict[str, object] = {"httpStatus": "OK", "httpStatusCode": 200, "status": "OK"}
    if uid is not None:
        payload["response"] = {"uid": uid, "klass": "org.hisp.dhis.user.User"}
    return envelope_cls.model_validate(payload)


def test_user_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user list` renders the users on every version tree."""
    users = [_user(core_version)]
    with patch(f"dhis2w_core.{core_version}.plugins.user.service.list_users", new=AsyncMock(return_value=users)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "list"])
    assert result.exit_code == 0, result.output
    assert "abcDEFghiJK" in result.output


def test_user_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user get <uid>` renders one user on every version tree."""
    user = _user(core_version)
    with patch(f"dhis2w_core.{core_version}.plugins.user.service.get_user", new=AsyncMock(return_value=user)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "get", "abcDEFghiJK"])
    assert result.exit_code == 0, result.output
    assert "abcDEFghiJK" in result.output


def test_user_invite_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user invite` prints the new user's UID on every version tree."""
    envelope = _web_message(core_version, uid="newUserUID1")
    with patch(f"dhis2w_core.{core_version}.plugins.user.service.invite_user", new=AsyncMock(return_value=envelope)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app,
            ["-p", "probe", "user", "invite", "alice@example.com", "--first-name", "Alice", "--surname", "Example"],
        )
    assert result.exit_code == 0, result.output
    assert "newUserUID1" in result.output


def test_user_reinvite_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user reinvite <uid>` reports the queued status on every version tree."""
    envelope = _web_message(core_version)
    with patch(f"dhis2w_core.{core_version}.plugins.user.service.reinvite_user", new=AsyncMock(return_value=envelope)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "reinvite", "abcDEFghiJK"])
    assert result.exit_code == 0, result.output
    assert "abcDEFghiJK" in result.output


def test_user_reset_password_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w user reset-password <uid>` reports the mailed status on every version tree."""
    envelope = _web_message(core_version)
    with patch(f"dhis2w_core.{core_version}.plugins.user.service.reset_password", new=AsyncMock(return_value=envelope)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "user", "reset-password", "abcDEFghiJK"])
    assert result.exit_code == 0, result.output
    assert "abcDEFghiJK" in result.output
