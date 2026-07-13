"""Confirmation-prompt coverage for the destructive tracker delete CLI commands.

`data tracker delete`, `data tracker event delete`, and `data tracker enrollment delete`
each guard the destructive call behind a `typer.confirm(..., abort=True)` prompt, skippable
with `--yes`/`-y`. These invoke the CLI on every version tree (v41/v42/v43) with the version's
`delete_tracker_objects` mocked, asserting the prompt gates the service call.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def _web_message_response(core_version: str) -> object:
    """Build an OK WebMessageResponse from the version tree's write-result models."""
    module: ModuleType = import_module(f"dhis2w_client.{core_version}")
    return module.WebMessageResponse.model_validate({"status": "OK", "httpStatusCode": 200})


# (command path under `data tracker`, sample UID) for each destructive delete command.
_DELETE_COMMANDS = [
    (["data", "tracker", "delete"], "teI01234567"),
    (["data", "tracker", "event", "delete"], "evt01234567"),
    (["data", "tracker", "enrollment", "delete"], "enr01234567"),
]


@pytest.mark.parametrize(("command", "uid"), _DELETE_COMMANDS)
def test_delete_yes_flag_skips_prompt(
    core_version: str,
    core_profile: None,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    uid: str,
) -> None:
    """`--yes` runs the delete without prompting on every version tree."""
    delete_mock = AsyncMock(return_value=_web_message_response(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.tracker.service.delete_tracker_objects", new=delete_mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", *command, uid, "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output
    assert delete_mock.await_count == 1


@pytest.mark.parametrize(("command", "uid"), _DELETE_COMMANDS)
def test_delete_confirm_yes_input_proceeds(
    core_version: str,
    core_profile: None,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    uid: str,
) -> None:
    """Answering `y` at the prompt runs the delete on every version tree."""
    delete_mock = AsyncMock(return_value=_web_message_response(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.tracker.service.delete_tracker_objects", new=delete_mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", *command, uid], input="y\n")
    assert result.exit_code == 0, result.output
    assert delete_mock.await_count == 1


@pytest.mark.parametrize(("command", "uid"), _DELETE_COMMANDS)
def test_delete_confirm_no_input_aborts_without_calling_service(
    core_version: str,
    core_profile: None,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    uid: str,
) -> None:
    """Answering `n` aborts before the service is called on every version tree."""
    delete_mock = AsyncMock(return_value=_web_message_response(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.tracker.service.delete_tracker_objects", new=delete_mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", *command, uid], input="n\n")
    assert result.exit_code != 0
    assert delete_mock.await_count == 0


def test_tracked_entity_delete_prompt_warns_about_cascade(
    core_version: str,
    core_profile: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tracked-entity delete prompt spells out the enrollment + event cascade."""
    delete_mock = AsyncMock(return_value=_web_message_response(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.tracker.service.delete_tracker_objects", new=delete_mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "tracker", "delete", "teI01234567"], input="n\n")
    assert "cascades to their enrollments and events" in result.output
    assert delete_mock.await_count == 0
