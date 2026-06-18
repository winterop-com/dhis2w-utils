"""Per-version CLI invocation parity for the `datastore` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version.removeprefix("v"))
    return build_app()


def test_datastore_namespaces_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w datastore namespaces` prints each namespace on every version tree."""
    mock = AsyncMock(return_value=["capture", "analytics"])
    with patch(f"dhis2w_core.{core_version}.plugins.datastore.service.list_namespaces", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "datastore", "namespaces"])
    assert result.exit_code == 0, result.output
    assert "capture" in result.output


def test_datastore_keys_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w datastore keys <ns>` prints each key on every version tree."""
    mock = AsyncMock(return_value=["k1", "k2"])
    with patch(f"dhis2w_core.{core_version}.plugins.datastore.service.list_keys", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "datastore", "keys", "ns"])
    assert result.exit_code == 0, result.output
    assert "k1" in result.output


def test_datastore_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w datastore get <ns> <key>` renders the JSON value on every version tree."""
    mock = AsyncMock(return_value={"enabled": True})
    with patch(f"dhis2w_core.{core_version}.plugins.datastore.service.get_value", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "datastore", "get", "ns", "k"])
    assert result.exit_code == 0, result.output
    assert "enabled" in result.output


def test_datastore_set_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w datastore set <ns> <key> <value>` confirms the write on every version tree."""
    mock = AsyncMock(return_value=None)
    with patch(f"dhis2w_core.{core_version}.plugins.datastore.service.set_value", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "datastore", "set", "ns", "k", '{"a": 1}'])
    assert result.exit_code == 0, result.output
    assert "set ns/k" in result.output


def test_datastore_delete_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w datastore delete <ns> <key> --yes` confirms the delete on every version tree."""
    mock = AsyncMock(return_value=None)
    with patch(f"dhis2w_core.{core_version}.plugins.datastore.service.delete_key", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "datastore", "delete", "ns", "k", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted ns/k" in result.output


def test_datastore_delete_namespace_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w datastore delete-namespace <ns> --yes` confirms the delete on every version tree."""
    mock = AsyncMock(return_value=None)
    with patch(f"dhis2w_core.{core_version}.plugins.datastore.service.delete_namespace", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "datastore", "delete-namespace", "ns", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted namespace ns" in result.output
