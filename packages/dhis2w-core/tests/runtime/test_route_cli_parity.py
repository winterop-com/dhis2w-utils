"""Per-version CLI invocation parity for the `route` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions.
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


def test_route_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w route list` renders the routes on every version tree."""
    route_cls = import_module(f"dhis2w_client.generated.{core_version}.schemas").Route
    routes = [
        route_cls.model_validate({"id": "E8OPcc45A22", "code": "chap", "name": "chap", "url": "http://up.example"})
    ]
    with patch(f"dhis2w_core.{core_version}.plugins.route.service.list_routes", new=AsyncMock(return_value=routes)):
        result = CliRunner().invoke(_build_versioned_app(core_version, monkeypatch), ["-p", "probe", "route", "list"])
    assert result.exit_code == 0, result.output
    assert "E8OPcc45A22" in result.output


def test_route_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w route get <uid>` renders one route on every version tree."""
    route_cls = import_module(f"dhis2w_client.generated.{core_version}.schemas").Route
    route = route_cls.model_validate({"id": "E8OPcc45A22", "code": "chap", "name": "chap", "url": "http://up.example"})
    with patch(f"dhis2w_core.{core_version}.plugins.route.service.get_route", new=AsyncMock(return_value=route)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "route", "get", "E8OPcc45A22"])
    assert result.exit_code == 0, result.output
    assert "E8OPcc45A22" in result.output
