"""Verify `dhis2 schema <type>` introspects the generated models for the connected server's version."""

from __future__ import annotations

import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, args: list[str], *, version: str = "v42") -> Any:
    """Invoke the schema command with a fake client whose `version_key` is `version`."""
    fake_client = MagicMock()
    fake_client.version_key = version

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    with patch("dhis2w_core.v42.plugins.schema.service.open_client", lambda _profile: ctx):
        return runner.invoke(build_app(), args)


def _text(result: Any) -> str:
    """Concatenate stdout + stderr regardless of how the runner split the streams."""
    combined = result.output or ""
    with contextlib.suppress(ValueError):
        combined += result.stderr or ""
    return combined


def test_schema_json_describes_oas_type(runner: CliRunner) -> None:
    """`--json schema dataElement` returns the OAS-tree shape with known fields."""
    result = _invoke(runner, ["--json", "schema", "dataElement"])
    assert result.exit_code == 0, _text(result)
    payload = json.loads(result.output)
    assert payload["name"] == "DataElement"
    assert payload["source"] == "oas"
    assert payload["version"] == "v42"
    names = {field["name"] for field in payload["fields"]}
    assert {"code", "valueType", "domainType"} <= names


def test_schema_accepts_plural_wire_name(runner: CliRunner) -> None:
    """A plural wire name resolves to its singular class (dataElements -> DataElement)."""
    result = _invoke(runner, ["--json", "schema", "dataElements"])
    assert result.exit_code == 0, _text(result)
    assert json.loads(result.output)["name"] == "DataElement"


def test_schema_human_table_titles_source_and_version(runner: CliRunner) -> None:
    """The human table header names the resolved type, source tree, and detected version."""
    result = _invoke(runner, ["schema", "dataElement"])
    assert result.exit_code == 0, _text(result)
    assert "DataElement (oas, v42)" in result.output


def test_schema_source_schemas_reads_the_other_tree(runner: CliRunner) -> None:
    """`--source schemas` reads the /api/schemas-derived tree instead of OAS."""
    result = _invoke(runner, ["--json", "schema", "dataElement", "--source", "schemas"])
    assert result.exit_code == 0, _text(result)
    assert json.loads(result.output)["source"] == "schemas"


def test_schema_resolves_tracker_write_types(runner: CliRunner) -> None:
    """Tracker write models (TrackerEvent, …) resolve via the OAS-folded index."""
    result = _invoke(runner, ["--json", "schema", "TrackerEvent"])
    assert result.exit_code == 0, _text(result)
    payload = json.loads(result.output)
    assert payload["name"] == "TrackerEvent"
    assert payload["field_count"] > 0


def test_schema_unknown_type_exits_2_with_candidates(runner: CliRunner) -> None:
    """An unknown type fails with exit 2 and a did-you-mean list."""
    result = _invoke(runner, ["schema", "dataElementz"])
    assert result.exit_code == 2
    combined = _text(result)
    assert "Did you mean" in combined
    assert "DataElement" in combined


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ("id,name,code,valueType", []),
        ("name,code,name_type,options_set_id", ["name_type", "options_set_id"]),
        (":owner", []),  # preset — skipped
        ("id,name,*", []),  # wildcard — skipped
        ("id,dataSetElements[dataSet[id]]", []),  # nested — skipped
        ("categoryCombo.id", []),  # dotted path — skipped
        ("id,name,!sharing", []),  # exclusion — skipped
    ],
)
def test_unknown_fields_flags_only_plain_unknown_identifiers(fields: str, expected: list[str]) -> None:
    """`unknown_fields` flags bare unknown names and skips any non-trivial --fields syntax."""
    from dhis2w_core.v42.plugins.schema import service

    assert service.unknown_fields("v42", "dataElements", fields) == expected


def test_unknown_fields_skips_unknown_type() -> None:
    """An unresolvable type yields no warnings (nothing to validate against)."""
    from dhis2w_core.v42.plugins.schema import service

    assert service.unknown_fields("v42", "bogusType", "a,b,c") == []


def test_schema_follows_the_detected_server_version(runner: CliRunner) -> None:
    """The output tracks the server's auto-detected version: v41 carries a `user` field v43 dropped."""
    v41 = json.loads(_invoke(runner, ["--json", "schema", "dataElement"], version="v41").output)
    v43 = json.loads(_invoke(runner, ["--json", "schema", "dataElement"], version="v43").output)
    assert v41["version"] == "v41"
    assert v43["version"] == "v43"
    assert "user" in {field["name"] for field in v41["fields"]}
    assert "user" not in {field["name"] for field in v43["fields"]}
