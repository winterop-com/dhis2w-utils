"""Per-version CLI invocation parity for the `doctor` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + report rendering) run, not just their import-time definitions.
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


def _report(core_version: str) -> object:
    """Build a passing `DoctorReport` for the parametrized version tree."""
    models = import_module(f"dhis2w_core.{core_version}.plugins.doctor._models")
    probe = models.ProbeResult(name="data-sets-without-elements", category="metadata", status="pass", message="ok")
    return models.DoctorReport(base_url="https://dhis2.example", dhis2_version="2.42.0", probes=[probe])


def test_doctor_default_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w doctor` (no sub-command) runs metadata + integrity and renders the report on every tree."""
    mock = AsyncMock(return_value=_report(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.doctor.service.run_doctor", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "doctor"])
    assert result.exit_code == 0, result.output
    assert "data-sets-without-elements" in result.output


def test_doctor_metadata_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w doctor metadata` renders the metadata probes on every tree."""
    mock = AsyncMock(return_value=_report(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.doctor.service.run_doctor", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "doctor", "metadata"])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_doctor_integrity_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w doctor integrity` renders the integrity probes on every tree."""
    mock = AsyncMock(return_value=_report(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.doctor.service.run_doctor", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "doctor", "integrity"])
    assert result.exit_code == 0, result.output
    assert "data-sets-without-elements" in result.output


def test_doctor_bugs_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w doctor bugs` renders the bugs probes on every tree."""
    mock = AsyncMock(return_value=_report(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.doctor.service.run_doctor", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "doctor", "bugs"])
    assert result.exit_code == 0, result.output
    assert "data-sets-without-elements" in result.output


def test_doctor_all_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w doctor --all` runs every category and renders the report on every tree."""
    mock = AsyncMock(return_value=_report(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.doctor.service.run_doctor", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "doctor", "--all"])
    assert result.exit_code == 0, result.output
    assert "data-sets-without-elements" in result.output
