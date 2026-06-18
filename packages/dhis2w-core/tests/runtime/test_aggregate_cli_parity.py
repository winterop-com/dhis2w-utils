"""Per-version CLI invocation parity for the `aggregate` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions. Aggregate is mounted under
`d2w data aggregate`.
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
    monkeypatch.setenv("DHIS2_VERSION", core_version.removeprefix("v"))
    return build_app()


def test_aggregate_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data aggregate get` renders the data values on every version tree."""
    dvs_cls = import_module(f"dhis2w_client.{core_version}").DataValueSet
    envelope = dvs_cls.model_validate(
        {"dataValues": [{"dataElement": "fbfJHSPpUQD", "period": "202403", "orgUnit": "ImspTQPwCqd", "value": "12"}]}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.aggregate.service.get_data_values",
        new=AsyncMock(return_value=envelope),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "data", "aggregate", "get"]
        argv += ["--ds", "lyLU2wR22tC", "--pe", "202403", "--ou", "ImspTQPwCqd"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "fbfJHSPpUQD" in result.output


def test_aggregate_set_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data aggregate set` writes one value and confirms on every version tree."""
    wmr_cls = import_module(f"dhis2w_client.{core_version}").WebMessageResponse
    response = wmr_cls.model_validate({"status": "OK", "httpStatusCode": 200})
    with patch(
        f"dhis2w_core.{core_version}.plugins.aggregate.service.set_data_value",
        new=AsyncMock(return_value=response),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "data", "aggregate", "set"]
        argv += ["--de", "fbfJHSPpUQD", "--pe", "202403", "--ou", "ImspTQPwCqd", "--value", "12"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "fbfJHSPpUQD" in result.output


def test_aggregate_delete_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data aggregate delete` removes one value and confirms on every version tree."""
    wmr_cls = import_module(f"dhis2w_client.{core_version}").WebMessageResponse
    response = wmr_cls.model_validate({"status": "OK", "httpStatusCode": 200})
    with patch(
        f"dhis2w_core.{core_version}.plugins.aggregate.service.delete_data_value",
        new=AsyncMock(return_value=response),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        argv = ["-p", "probe", "data", "aggregate", "delete"]
        argv += ["--de", "fbfJHSPpUQD", "--pe", "202403", "--ou", "ImspTQPwCqd"]
        result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output


def test_aggregate_push_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w data aggregate push <file>` reads a JSON envelope and pushes it on every version tree."""
    wmr_cls = import_module(f"dhis2w_client.{core_version}").WebMessageResponse
    response = wmr_cls.model_validate(
        {"status": "OK", "httpStatusCode": 200, "response": {"status": "OK", "imported": 1}}
    )
    payload = tmp_path / "values.json"
    payload.write_text(
        '{"dataSet":"lyLU2wR22tC","dataValues":[{"dataElement":"de1","period":"202403","orgUnit":"ou1","value":"1"}]}',
        encoding="utf-8",
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.aggregate.service.push_data_values",
        new=AsyncMock(return_value=response),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "aggregate", "push", str(payload), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "pushed" in result.output
