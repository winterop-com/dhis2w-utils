"""Per-version CLI invocation parity for the `schema` plugin — exercise cli.py command body on all trees.

`d2w schema <type>` detects the server version (async, opens a client) then describes the type from the
locally generated OAS trees (sync, offline). Mocking `detect_version` to return the parametrized version key
lets the offline `describe_type` introspection run for real, so the v41/v43 cli.py command body (arg parsing +
result rendering) runs against each tree, not just its import-time definition.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version.removeprefix("v"))
    return build_app()


def test_schema_human_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w schema dataElement` renders the OAS shape header on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.schema.service.detect_version"
    with patch(target, new=AsyncMock(return_value=core_version)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "schema", "dataElement"])
    assert result.exit_code == 0, result.output
    assert f"DataElement (oas, {core_version})" in result.output


def test_schema_json_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w --json schema dataElement` returns the typed schema for the detected version on every tree."""
    target = f"dhis2w_core.{core_version}.plugins.schema.service.detect_version"
    with patch(target, new=AsyncMock(return_value=core_version)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "--json", "schema", "dataElement"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "DataElement"
    assert payload["source"] == "oas"
    assert payload["version"] == core_version


def test_schema_source_schemas_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w schema dataElement --source schemas` reads the schemas tree on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.schema.service.detect_version"
    with patch(target, new=AsyncMock(return_value=core_version)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "--json", "schema", "dataElement", "--source", "schemas"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["source"] == "schemas"


def test_schema_unknown_type_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w schema <bogus>` exits 2 with a did-you-mean list on every version tree."""
    target = f"dhis2w_core.{core_version}.plugins.schema.service.detect_version"
    with patch(target, new=AsyncMock(return_value=core_version)):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "schema", "dataElementz"])
    assert result.exit_code == 2
    assert "Did you mean" in result.output
