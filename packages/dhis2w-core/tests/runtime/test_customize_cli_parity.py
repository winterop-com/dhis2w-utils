"""Per-version CLI invocation parity for the `customize` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions. Customize is mounted under
`d2w customize`.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def test_customize_logo_front_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w customize logo-front <file>` uploads and confirms on every version tree."""
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"png")
    with patch(
        f"dhis2w_core.{core_version}.plugins.customize.service.upload_logo_front",
        new=AsyncMock(return_value=None),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "customize", "logo-front", str(logo)])
    assert result.exit_code == 0, result.output
    assert "logo_front" in result.output


def test_customize_logo_banner_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w customize logo-banner <file>` uploads and confirms on every version tree."""
    logo = tmp_path / "banner.png"
    logo.write_bytes(b"png")
    with patch(
        f"dhis2w_core.{core_version}.plugins.customize.service.upload_logo_banner",
        new=AsyncMock(return_value=None),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "customize", "logo-banner", str(logo)])
    assert result.exit_code == 0, result.output
    assert "logo_banner" in result.output


def test_customize_style_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w customize style <file>` uploads CSS and confirms on every version tree."""
    css = tmp_path / "style.css"
    css.write_text("body{}", encoding="utf-8")
    with patch(
        f"dhis2w_core.{core_version}.plugins.customize.service.upload_style",
        new=AsyncMock(return_value=None),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "customize", "style", str(css)])
    assert result.exit_code == 0, result.output
    assert "keyStyle" in result.output


def test_customize_apply_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w customize apply <dir>` applies a preset and reports each uploaded artifact on every version tree."""
    result_cls = import_module(f"dhis2w_client.{core_version}").CustomizationResult
    preset_dir = tmp_path / "preset"
    preset_dir.mkdir()
    applied = result_cls(logo_front_uploaded=True, settings_applied=["applicationTitle"])
    with patch(
        f"dhis2w_core.{core_version}.plugins.customize.service.apply_preset_dir",
        new=AsyncMock(return_value=applied),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "customize", "apply", str(preset_dir)])
    assert result.exit_code == 0, result.output
    assert "logo_front" in result.output
    assert "applicationTitle" in result.output


def test_customize_show_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w customize show` renders the live login config on every version tree."""
    config_cls = import_module(f"dhis2w_client.generated.{core_version}.oas").LoginConfigResponse
    config = config_cls.model_validate({"applicationTitle": "My DHIS2", "loginPageLayout": "DEFAULT"})
    with patch(
        f"dhis2w_core.{core_version}.plugins.customize.service.get_login_config",
        new=AsyncMock(return_value=config),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "customize", "show"])
    assert result.exit_code == 0, result.output
    assert "My DHIS2" in result.output
