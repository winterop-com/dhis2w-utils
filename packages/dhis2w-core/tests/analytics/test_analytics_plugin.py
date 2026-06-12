"""Unit tests for the analytics plugin."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from dhis2w_core.v42.plugins.analytics import plugin
from dhis2w_core.v42.plugins.analytics.cli import app as analytics_app
from typer.testing import CliRunner


def test_plugin_descriptor() -> None:
    """Plugin descriptor."""
    assert plugin.name == "analytics"
    assert "analytics" in plugin.description.lower()


def test_invalid_shape_renders_cleanly_without_traceback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`analytics query --shape garbage` should error cleanly, not stack-trace."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "smoketest")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    root = typer.Typer()
    root.add_typer(analytics_app, name="analytics")
    result = runner.invoke(
        root,
        ["analytics", "query", "--shape", "garbage", "--dim", "dx:x", "--dim", "pe:y", "--dim", "ou:z"],
    )
    assert result.exit_code == 1
    assert "unknown analytics shape 'garbage'" in result.output
    assert "Traceback" not in result.output
