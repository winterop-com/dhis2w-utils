"""Per-version CLI invocation parity for the `security` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.security_core import build_account_authorities
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def _settings(core_version: str) -> object:
    """Build a `SecuritySettings` model from the matching tree's plugin models."""
    settings_cls = import_module(f"dhis2w_core.{core_version}.plugins.security.models").SecuritySettings
    return settings_cls(
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


def test_security_settings_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w security settings` renders the security-relevant settings on every version tree."""
    settings = _settings(core_version)
    with patch(
        f"dhis2w_core.{core_version}.plugins.security.service.get_security_settings",
        new=AsyncMock(return_value=settings),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "security", "settings"])
    assert result.exit_code == 0, result.output
    assert "0 (never)" in result.output


def test_security_authorities_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w security authorities` renders the categorised authorities on every version tree."""
    account = build_account_authorities(["F_USER_ADD", "F_SQLVIEW_PUBLIC_ADD", "F_DATAVALUE_ADD"])
    with patch(
        f"dhis2w_core.{core_version}.plugins.security.service.get_account_authorities",
        new=AsyncMock(return_value=account),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "security", "authorities"])
    assert result.exit_code == 0, result.output
    assert "security authorities" in result.output
