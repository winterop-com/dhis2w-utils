"""CliRunner tests for `d2w system calendar` (read + write)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a global profiles.toml with one PAT profile and point resolution at it."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    profiles = config_dir / "profiles.toml"
    profiles.write_text(
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


def test_calendar_no_arg_prints_current_value(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w system calendar` with no arg routes to `service.get_calendar` and prints the value."""
    with patch("dhis2w_core.v42.plugins.system.service.get_calendar", new=AsyncMock(return_value="ethiopian")):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["system", "calendar"])
    assert result.exit_code == 0, result.output
    assert "ethiopian" in result.output


def test_calendar_with_arg_and_yes_writes_setting(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w system calendar nepali --yes` skips the prompt and writes via `service.set_calendar`."""
    set_mock = AsyncMock(return_value=None)
    with (
        patch("dhis2w_core.v42.plugins.system.service.get_calendar", new=AsyncMock(return_value="iso8601")),
        patch("dhis2w_core.v42.plugins.system.service.set_calendar", new=set_mock),
    ):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["system", "calendar", "nepali", "--yes"])
    assert result.exit_code == 0, result.output
    assert "keyCalendar set to nepali (was iso8601)" in result.output
    set_mock.assert_awaited_once()
    assert set_mock.await_args is not None
    _, calendar_arg = set_mock.await_args.args
    assert calendar_arg.value == "nepali"


def test_calendar_prompt_confirm_writes(pat_profile: None) -> None:  # noqa: ARG001
    """Answering `y` at the confirmation prompt routes to `service.set_calendar`."""
    set_mock = AsyncMock(return_value=None)
    with (
        patch("dhis2w_core.v42.plugins.system.service.get_calendar", new=AsyncMock(return_value="iso8601")),
        patch("dhis2w_core.v42.plugins.system.service.set_calendar", new=set_mock),
    ):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["system", "calendar", "nepali"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "Current calendar: iso8601" in result.output
    assert "New calendar:     nepali" in result.output
    assert "WARNING" in result.output
    assert "keyCalendar set to nepali (was iso8601)" in result.output
    set_mock.assert_awaited_once()


def test_calendar_prompt_default_aborts(pat_profile: None) -> None:  # noqa: ARG001
    """Hitting Enter (default `N`) aborts the change with a non-zero exit and no service call."""
    set_mock = AsyncMock(return_value=None)
    with (
        patch("dhis2w_core.v42.plugins.system.service.get_calendar", new=AsyncMock(return_value="iso8601")),
        patch("dhis2w_core.v42.plugins.system.service.set_calendar", new=set_mock),
    ):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["system", "calendar", "nepali"], input="\n")
    assert result.exit_code != 0
    assert "Aborted" in result.output
    set_mock.assert_not_awaited()


def test_calendar_same_as_current_skips_write(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w system calendar iso8601` is a no-op when iso8601 is already set."""
    set_mock = AsyncMock(return_value=None)
    with (
        patch("dhis2w_core.v42.plugins.system.service.get_calendar", new=AsyncMock(return_value="iso8601")),
        patch("dhis2w_core.v42.plugins.system.service.set_calendar", new=set_mock),
    ):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["system", "calendar", "iso8601"])
    assert result.exit_code == 0, result.output
    assert "keyCalendar already iso8601" in result.output
    set_mock.assert_not_awaited()


def test_calendar_rejects_unknown_value(pat_profile: None) -> None:  # noqa: ARG001
    """An unknown calendar name fails with a non-zero exit (Typer enum validation)."""
    runner = CliRunner()
    result = runner.invoke(build_app(), ["system", "calendar", "mayan"])
    assert result.exit_code != 0
