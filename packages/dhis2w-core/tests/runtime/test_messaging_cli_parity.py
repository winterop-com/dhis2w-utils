"""Per-version CLI invocation parity for the `messaging` plugin — exercise cli.py command bodies on all trees.

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


def _conversation(core_version: str) -> object:
    """A minimal typed `MessageConversation` from the version's client tree."""
    cls = import_module(f"dhis2w_client.{core_version}").MessageConversation
    return cls.model_validate({"id": "convUid0001", "subject": "hello", "messageCount": 1})


def _web_message_response(core_version: str) -> object:
    """A minimal typed `WebMessageResponse` from the version's client tree."""
    cls = import_module(f"dhis2w_client.{core_version}").WebMessageResponse
    return cls.model_validate({"status": "OK", "httpStatus": "OK"})


def test_messaging_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging list` renders the conversations on every version tree."""
    conversations = [_conversation(core_version)]
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.list_conversations"
    with patch(target, new=AsyncMock(return_value=conversations)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "list"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging get <uid>` renders one conversation on every version tree."""
    conv = _conversation(core_version)
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.get_conversation"
    with patch(target, new=AsyncMock(return_value=conv)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "get", "convUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_send_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging send` reports the created conversation on every version tree."""
    conv = _conversation(core_version)
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.send"
    with patch(target, new=AsyncMock(return_value=conv)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "send", "hello", "body", "-u", "userUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_reply_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging reply <uid> <text>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.reply"
    with patch(target, new=AsyncMock(return_value=_web_message_response(core_version))):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "reply", "convUid0001", "thanks"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_mark_read_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging mark-read <uid>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.mark_read"
    with patch(target, new=AsyncMock(return_value=_web_message_response(core_version))):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "mark-read", "convUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_mark_unread_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w messaging mark-unread <uid>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.mark_unread"
    with patch(target, new=AsyncMock(return_value=_web_message_response(core_version))):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "mark-unread", "convUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_delete_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging delete <uid>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.delete_conversation"
    with patch(target, new=AsyncMock(return_value=None)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "delete", "convUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output


def test_messaging_set_priority_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w messaging set-priority <uid> <priority>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.set_priority"
    with patch(target, new=AsyncMock(return_value=None)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "set-priority", "convUid0001", "high"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output
    assert "HIGH" in result.output


def test_messaging_set_status_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w messaging set-status <uid> <status>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.set_status"
    with patch(target, new=AsyncMock(return_value=None)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "set-status", "convUid0001", "open"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output
    assert "OPEN" in result.output


def test_messaging_assign_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging assign <uid> <user>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.assign"
    with patch(target, new=AsyncMock(return_value=None)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "assign", "convUid0001", "userUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output
    assert "userUid0001" in result.output


def test_messaging_unassign_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w messaging unassign <uid>` runs on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.messaging.service.unassign"
    with patch(target, new=AsyncMock(return_value=None)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "messaging", "unassign", "convUid0001"])
    assert result.exit_code == 0, result.output
    assert "convUid0001" in result.output
