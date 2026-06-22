"""Per-version CLI invocation parity for the `analytics` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + Grid rendering) run, not just their import-time definitions. Analytics is mounted under
`d2w analytics`.
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


def _grid(core_version: str) -> object:
    """Build a minimal two-column `Grid` for the parametrized version tree."""
    grid_cls = import_module(f"dhis2w_client.{core_version}").Grid
    headers = [{"name": "dx", "column": "Data"}, {"name": "value", "column": "Value"}]
    return grid_cls.model_validate({"headers": headers, "rows": [["Uvn6LCg7dVU", "42"]]})


def test_analytics_query_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w analytics query` renders a Grid on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.analytics.service.query_analytics",
        new=AsyncMock(return_value=_grid(core_version)),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "analytics", "query", "--dim", "dx:Uvn6LCg7dVU", "--dim", "pe:LAST_12_MONTHS"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "Uvn6LCg7dVU" in result.output


def test_analytics_events_query_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w analytics events query <program>` renders a Grid on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.analytics.service.query_events",
        new=AsyncMock(return_value=_grid(core_version)),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "analytics", "events", "query", "IpHINAT79UW", "--dim", "pe:LAST_12_MONTHS"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "Uvn6LCg7dVU" in result.output


def test_analytics_enrollments_query_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w analytics enrollments query <program>` renders a Grid on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.analytics.service.query_enrollments",
        new=AsyncMock(return_value=_grid(core_version)),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "analytics", "enrollments", "query", "IpHINAT79UW", "--dim", "pe:LAST_12_MONTHS"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "Uvn6LCg7dVU" in result.output


def test_analytics_outlier_detection_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w analytics outlier-detection` renders a Grid on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.analytics.service.query_outlier_detection",
        new=AsyncMock(return_value=_grid(core_version)),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "analytics", "outlier-detection", "--ds", "lyLU2wR22tC", "--ou", "ImspTQPwCqd"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "Uvn6LCg7dVU" in result.output


def test_analytics_tracked_entities_query_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w analytics tracked-entities query <TET>` renders a Grid on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.analytics.service.query_tracked_entities",
        new=AsyncMock(return_value=_grid(core_version)),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "analytics", "tracked-entities", "query", "nEenWmSyUEp", "--dim", "pe:LAST_12_MONTHS"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "Uvn6LCg7dVU" in result.output
