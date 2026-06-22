"""Per-version CLI invocation parity for the `profile` plugin — exercise cli.py command bodies on all trees.

`profile` is a local management surface: `list` and `show` read the active profiles.toml (no network), so
they run unmocked against the `core_profile` fixture's TOML; `verify` probes the instance, so its service is
mocked. Invoking via a version-pinned `build_app()` makes the v41/v43 cli.py command bodies (arg parsing +
result rendering) run, not just their import-time definitions. These commands manage TOML, so they do not take
the `-p` profile selector.
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


def _verify_result(core_version: str, *, ok: bool = True) -> object:
    """A typed `VerifyResult` from the version's profile service module."""
    cls = import_module(f"dhis2w_core.{core_version}.plugins.profile.service").VerifyResult
    return cls(
        name="probe",
        ok=ok,
        base_url="https://dhis2.example",
        auth="basic",
        version="2.42.0" if ok else None,
        username="admin" if ok else None,
        latency_ms=12 if ok else None,
        error=None if ok else "boom",
    )


def test_profile_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w profile list` renders the active profiles.toml on every version tree."""
    app = _build_versioned_app(core_version, monkeypatch)
    result = CliRunner().invoke(app, ["profile", "list"])
    assert result.exit_code == 0, result.output
    assert "probe" in result.output


def test_profile_show_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w profile show <name>` renders one profile (secrets redacted) on every version tree."""
    app = _build_versioned_app(core_version, monkeypatch)
    result = CliRunner().invoke(app, ["profile", "show", "probe"])
    assert result.exit_code == 0, result.output
    expected_host = "dhis2.example"
    assert expected_host in result.output


def test_profile_verify_one_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w profile verify <name>` reports the probe result on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.profile.service.verify_profile"
    with patch(target, new=AsyncMock(return_value=_verify_result(core_version))):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["profile", "verify", "probe"])
    assert result.exit_code == 0, result.output
    assert "probe" in result.output
    assert "OK" in result.output


def test_profile_verify_all_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w profile verify` (no name) renders the all-profiles table on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.profile.service.verify_all_profiles"
    with patch(target, new=AsyncMock(return_value=[_verify_result(core_version)])):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["profile", "verify"])
    assert result.exit_code == 0, result.output
    assert "probe" in result.output
