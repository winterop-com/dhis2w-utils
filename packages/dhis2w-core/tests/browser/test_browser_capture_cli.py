"""CliRunner tests for `d2w browser {map,viz} screenshot` — typed CaptureResult consumption.

`capture_maps` / `capture_visualizations` return typed `MapCaptureResult` /
`VisualizationCaptureResult` models (mirroring `capture_dashboards`), never
`list[dict]`; the CLI renders them via attribute access + `model_dump`. The full
Playwright path is exercised by the slow live-stack tests in
`packages/dhis2w-browser/tests/`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("dhis2w_browser")

from dhis2w_browser import MapCaptureResult, VisualizationCaptureResult  # noqa: E402 — after importorskip
from dhis2w_cli.main import build_app  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

_runner = CliRunner()


@pytest.fixture
def basic_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a global profiles.toml with a Basic `probe` profile so `profile_from_env` resolves."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


def test_map_screenshot_renders_typed_results(basic_profile: None) -> None:  # noqa: ARG001
    """The map command reads `output_path` / `display_name` off the typed model (not dict indexing)."""
    results = [MapCaptureResult(uid="m1", display_name="Malaria cases", output_path=Path("/tmp/m1.png"), rendered=True)]
    with (
        patch("dhis2w_core.v42.plugins.browser.service.require_browser", return_value=None),
        patch("dhis2w_core.v42.plugins.browser.service.capture_maps", new=AsyncMock(return_value=results)),
    ):
        result = _runner.invoke(build_app(), ["browser", "map", "screenshot"])
    assert result.exit_code == 0, result.output
    assert "/tmp/m1.png" in result.output
    assert "Malaria cases" in result.output


def test_map_screenshot_json_dumps_typed_models(basic_profile: None) -> None:  # noqa: ARG001
    """`--json` serializes the typed models via `model_dump`, emitting a parseable array."""
    results = [
        MapCaptureResult(uid="m1", display_name="Malaria cases", output_path=Path("/tmp/m1.png"), rendered=False)
    ]
    with (
        patch("dhis2w_core.v42.plugins.browser.service.require_browser", return_value=None),
        patch("dhis2w_core.v42.plugins.browser.service.capture_maps", new=AsyncMock(return_value=results)),
    ):
        result = _runner.invoke(build_app(), ["--json", "browser", "map", "screenshot"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["uid"] == "m1"
    assert payload[0]["rendered"] is False


def test_viz_screenshot_renders_typed_results(basic_profile: None) -> None:  # noqa: ARG001
    """The viz command reads attributes off the typed `VisualizationCaptureResult` model."""
    results = [
        VisualizationCaptureResult(uid="v1", display_name="ANC trend", output_path=Path("/tmp/v1.png"), rendered=True),
    ]
    with (
        patch("dhis2w_core.v42.plugins.browser.service.require_browser", return_value=None),
        patch("dhis2w_core.v42.plugins.browser.service.capture_visualizations", new=AsyncMock(return_value=results)),
    ):
        result = _runner.invoke(build_app(), ["browser", "viz", "screenshot"])
    assert result.exit_code == 0, result.output
    assert "/tmp/v1.png" in result.output
    assert "ANC trend" in result.output
