"""Per-version CLI invocation parity for the `apps` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + table rendering) run, not just their import-time definitions. Apps is mounted under `d2w apps`.
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


def test_apps_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps list` renders the installed apps on every version tree."""
    app_cls = import_module(f"dhis2w_client.{core_version}").App
    apps = [app_cls.model_validate({"key": "data-visualizer", "name": "Data Visualizer", "version": "100.1.1"})]
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.list_apps",
        new=AsyncMock(return_value=apps),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "list"])
    assert result.exit_code == 0, result.output
    assert "data-visualizer" in result.output


def test_apps_add_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps add <hub-id>` resolves + installs via the hub on every version tree."""
    models = import_module(f"dhis2w_core.{core_version}.plugins.apps.models")
    target = models.InstallTarget(version_id="ver-1", app_name="Scorecard", version="2.0", resolved_from="app-id")
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.install_from_hub",
        new=AsyncMock(return_value=target),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "add", "some-hub-app-id"])
    assert result.exit_code == 0, result.output
    assert "Scorecard" in result.output


def test_apps_remove_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps remove <key> --yes` uninstalls and confirms on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.uninstall",
        new=AsyncMock(return_value=None),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "remove", "data-visualizer", "--yes"])
    assert result.exit_code == 0, result.output
    assert "removed data-visualizer" in result.output


def test_apps_reload_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps reload` asks DHIS2 to re-read apps and confirms on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.reload_apps",
        new=AsyncMock(return_value=None),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "reload"])
    assert result.exit_code == 0, result.output
    assert "reloaded" in result.output


def test_apps_update_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps update <key>` renders a one-row update summary on every version tree."""
    models = import_module(f"dhis2w_core.{core_version}.plugins.apps.models")
    outcome = models.UpdateOutcome(
        key="data-visualizer", name="Data Visualizer", from_version="1.0", to_version="2.0", status="UPDATED"
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.update_one",
        new=AsyncMock(return_value=outcome),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "update", "data-visualizer"])
    assert result.exit_code == 0, result.output
    assert "data-visualizer" in result.output


def test_apps_update_all_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps update --all --dry-run` previews available updates on every version tree."""
    models = import_module(f"dhis2w_core.{core_version}.plugins.apps.models")
    outcome = models.UpdateOutcome(
        key="data-visualizer", name="Data Visualizer", from_version="1.0", to_version="2.0", status="AVAILABLE"
    )
    summary = models.UpdateSummary(outcomes=[outcome])
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.update_all",
        new=AsyncMock(return_value=summary),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "update", "--all", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "available" in result.output.lower()


def test_apps_snapshot_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps snapshot` prints a portable JSON inventory on every version tree."""
    snapshot_cls = import_module(f"dhis2w_client.{core_version}").AppsSnapshot
    entry = {
        "key": "data-visualizer",
        "name": "Data Visualizer",
        "version": "100.1.1",
        "source": "side-loaded",
    }
    snapshot = snapshot_cls.model_validate({"entries": [entry]})
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.snapshot",
        new=AsyncMock(return_value=snapshot),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "snapshot"])
    assert result.exit_code == 0, result.output
    assert "data-visualizer" in result.output


def test_apps_restore_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w apps restore <manifest>` reinstalls from a snapshot and renders a summary on every version tree."""
    client = import_module(f"dhis2w_client.{core_version}")
    manifest = tmp_path / "snapshot.json"
    manifest.write_text(
        '{"entries":[{"key":"data-visualizer","name":"Data Visualizer","version":"1.0","source":"app-hub",'
        '"hub_version_id":"ver-1"}]}',
        encoding="utf-8",
    )
    outcome = client.RestoreOutcome(
        key="data-visualizer", name="Data Visualizer", from_version="1.0", to_version="2.0", status="RESTORED"
    )
    summary = client.RestoreSummary(outcomes=[outcome])
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.restore",
        new=AsyncMock(return_value=summary),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "restore", str(manifest)])
    assert result.exit_code == 0, result.output
    assert "data-visualizer" in result.output


def test_apps_hub_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps hub-list` renders the App Hub catalog on every version tree."""
    hub_cls = import_module(f"dhis2w_client.{core_version}").AppHubApp
    hub = [hub_cls.model_validate({"id": "hubapp-1", "name": "Scorecard", "app_type": "APP", "versions": []})]
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.hub_list",
        new=AsyncMock(return_value=hub),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "hub-list"])
    assert result.exit_code == 0, result.output
    assert "Scorecard" in result.output


def test_apps_hub_versions_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps hub-versions <app-id>` lists published versions on every version tree."""
    hub_cls = import_module(f"dhis2w_client.{core_version}").AppHubApp
    record = hub_cls.model_validate(
        {"id": "hubapp-1", "name": "Scorecard", "versions": [{"id": "ver-1", "version": "2.0", "channel": "stable"}]}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.hub_versions",
        new=AsyncMock(return_value=record),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "hub-versions", "hubapp-1"])
    assert result.exit_code == 0, result.output
    assert "ver-1" in result.output


def test_apps_hub_url_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w apps hub-url` reads the configured App Hub URL on every version tree."""
    with patch(
        f"dhis2w_core.{core_version}.plugins.apps.service.get_hub_url",
        new=AsyncMock(return_value="https://apps.dhis2.org/api"),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "apps", "hub-url"])
    assert result.exit_code == 0, result.output
    expected_host = "apps.dhis2.org"
    assert expected_host in result.output
