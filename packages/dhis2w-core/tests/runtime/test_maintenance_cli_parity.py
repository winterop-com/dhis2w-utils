"""Per-version CLI invocation parity for the `maintenance` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions. The async jobs the
commands kick off are mocked at the service edge — these tests cover the CLI rendering, not the job.
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


def _web_message(core_version: str) -> object:
    """Build a simple `WebMessageResponse` envelope for the parametrized version tree."""
    web_message_cls = import_module(f"dhis2w_client.{core_version}").WebMessageResponse
    return web_message_cls.model_validate({"status": "OK", "message": "kicked off"})


def test_maintenance_cache_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w maintenance cache` confirms the cache clear on every tree."""
    mock = AsyncMock(return_value=None)
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.clear_cache", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "cache"])
    assert result.exit_code == 0, result.output
    assert "caches cleared" in result.output


def test_maintenance_task_types_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance task types` renders the task-type table on every tree."""
    mock = AsyncMock(return_value=["ANALYTICS_TABLE", "DATA_INTEGRITY"])
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.list_task_types", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "task", "types"])
    assert result.exit_code == 0, result.output
    assert "ANALYTICS_TABLE" in result.output


def test_maintenance_task_list_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance task list <type>` renders the task-UID table on every tree."""
    mock = AsyncMock(return_value=["taskUid0001"])
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.list_task_ids", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "task", "list", "ANALYTICS_TABLE"])
    assert result.exit_code == 0, result.output
    assert "taskUid0001" in result.output


def test_maintenance_cleanup_data_values_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance cleanup data-values` confirms the cleanup on every tree."""
    mock = AsyncMock(return_value=None)
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.remove_soft_deleted", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "cleanup", "data-values"])
    assert result.exit_code == 0, result.output
    assert "soft-deleted data values removed" in result.output


def test_maintenance_dataintegrity_list_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance dataintegrity list` renders the checks table on every tree."""
    check_cls = import_module(f"dhis2w_client.{core_version}").DataIntegrityCheck
    checks = [check_cls.model_validate({"name": "categories_no_options", "severity": "WARNING"})]
    with patch(
        f"dhis2w_core.{core_version}.plugins.maintenance.service.list_dataintegrity_checks",
        new=AsyncMock(return_value=checks),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "dataintegrity", "list"])
    assert result.exit_code == 0, result.output
    assert "categories_no_options" in result.output


def test_maintenance_dataintegrity_run_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance dataintegrity run` kicks off + renders the envelope on every tree."""
    mock = AsyncMock(return_value=_web_message(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.run_dataintegrity", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "dataintegrity", "run"])
    assert result.exit_code == 0, result.output


def test_maintenance_refresh_analytics_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance refresh analytics` kicks off + renders the envelope on every tree."""
    mock = AsyncMock(return_value=_web_message(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.refresh_analytics", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "refresh", "analytics"])
    assert result.exit_code == 0, result.output


def test_maintenance_validation_validate_expression_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance validation validate-expression <expr>` renders the parse result on every tree."""
    description_cls = import_module(f"dhis2w_client.{core_version}").ExpressionDescription
    description = description_cls.model_validate({"status": "OK", "message": "Valid", "description": "1 + 1"})
    with patch(
        f"dhis2w_core.{core_version}.plugins.maintenance.service.describe_expression",
        new=AsyncMock(return_value=description),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "maintenance", "validation", "validate-expression", "1+1"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_maintenance_predictors_run_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w maintenance predictors run` renders the run envelope on every tree."""
    mock = AsyncMock(return_value=_web_message(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.maintenance.service.run_predictors", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        args = ["-p", "probe", "maintenance", "predictors", "run"]
        args += ["--start-date", "2025-01-01", "--end-date", "2025-01-31"]
        result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
