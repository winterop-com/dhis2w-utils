"""Verify `dhis2 security settings` renders the security slice of /api/systemSettings."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.v42.plugins.security.models import SecuritySettings
from typer.testing import CliRunner

_SETTINGS = SecuritySettings(
    minPasswordLength=8,
    maxPasswordLength=72,
    credentialsExpires=0,
    credentialsExpiresReminderInDays=28,
    credentialsExpiryAlert=False,
    keyAccountRecovery=True,
    keySelfRegistrationNoRecaptcha=False,
    keyLockMultipleFailedLogins=False,
    enforceVerifiedEmail=False,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, args: list[str]) -> Any:
    """Invoke `dhis2 security settings ...` with a fake client returning `_SETTINGS`."""
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_SETTINGS)

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    with patch("dhis2w_core.v42.plugins.security.service.open_client", lambda _profile: ctx):
        return runner.invoke(build_app(), args)


def test_settings_json_emits_security_slice(runner: CliRunner) -> None:
    """`--json security settings` emits exactly the typed security fields."""
    result = _invoke(runner, ["--json", "security", "settings"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "minPasswordLength": 8,
        "maxPasswordLength": 72,
        "credentialsExpires": 0,
        "credentialsExpiresReminderInDays": 28,
        "credentialsExpiryAlert": False,
        "keyAccountRecovery": True,
        "keySelfRegistrationNoRecaptcha": False,
        "keyLockMultipleFailedLogins": False,
        "enforceVerifiedEmail": False,
    }


def test_settings_human_output(runner: CliRunner) -> None:
    """The table reads the never-expire default and the enabled/disabled toggles."""
    result = _invoke(runner, ["security", "settings"])
    assert result.exit_code == 0, result.output
    assert "0 (never)" in result.output
    assert "enabled" in result.output
    assert "disabled" in result.output
