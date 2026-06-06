"""Verify `dhis2 schema <type>` introspects generated models — offline and version-bound."""

from __future__ import annotations

import contextlib
import json
from typing import Any

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the plugin tree to v42 and avoid TOML profile resolution."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_VERSION", "42")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _text(result: Any) -> str:
    """Concatenate stdout + stderr regardless of how the runner split the streams."""
    combined = result.output or ""
    with contextlib.suppress(ValueError):
        combined += result.stderr or ""
    return combined


def test_schema_json_describes_oas_type(runner: CliRunner) -> None:
    """`--json schema dataElement` returns the OAS-tree shape with known fields."""
    result = runner.invoke(build_app(), ["--json", "schema", "dataElement"])
    assert result.exit_code == 0, _text(result)
    payload = json.loads(result.output)
    assert payload["name"] == "DataElement"
    assert payload["source"] == "oas"
    assert payload["version"] == "v42"
    names = {field["name"] for field in payload["fields"]}
    assert {"code", "valueType", "domainType"} <= names


def test_schema_accepts_plural_wire_name(runner: CliRunner) -> None:
    """A plural wire name resolves to its singular class (dataElements -> DataElement)."""
    result = runner.invoke(build_app(), ["--json", "schema", "dataElements"])
    assert result.exit_code == 0, _text(result)
    assert json.loads(result.output)["name"] == "DataElement"


def test_schema_human_table_titles_source_and_version(runner: CliRunner) -> None:
    """The human table header names the resolved type, source tree, and version."""
    result = runner.invoke(build_app(), ["schema", "dataElement"])
    assert result.exit_code == 0, _text(result)
    assert "DataElement (oas, v42)" in result.output


def test_schema_source_schemas_reads_the_other_tree(runner: CliRunner) -> None:
    """`--source schemas` reads the /api/schemas-derived tree instead of OAS."""
    result = runner.invoke(build_app(), ["--json", "schema", "dataElement", "--source", "schemas"])
    assert result.exit_code == 0, _text(result)
    assert json.loads(result.output)["source"] == "schemas"


def test_schema_unknown_type_exits_2_with_candidates(runner: CliRunner) -> None:
    """An unknown type fails with exit 2 and a did-you-mean list."""
    result = runner.invoke(build_app(), ["schema", "dataElementz"])
    assert result.exit_code == 2
    combined = _text(result)
    assert "Did you mean" in combined
    assert "DataElement" in combined


def test_schema_is_version_bound(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """The output reflects the active version tree: v41 carries a `user` field v43 dropped."""
    monkeypatch.setenv("DHIS2_VERSION", "41")
    v41 = json.loads(runner.invoke(build_app(), ["--json", "schema", "dataElement"]).output)
    monkeypatch.setenv("DHIS2_VERSION", "43")
    v43 = json.loads(runner.invoke(build_app(), ["--json", "schema", "dataElement"]).output)
    assert v41["version"] == "v41"
    assert v43["version"] == "v43"
    assert "user" in {field["name"] for field in v41["fields"]}
    assert "user" not in {field["name"] for field in v43["fields"]}
