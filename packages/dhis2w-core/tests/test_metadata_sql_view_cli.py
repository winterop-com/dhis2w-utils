"""CliRunner + mock tests for `dhis2 metadata sql-view ...`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client import SqlViewResult
from dhis2w_client.generated.v42.schemas import SqlView
from dhis2w_client.v42.envelopes import WebMessageResponse
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Global profiles.toml with one PAT profile, pointed at by HOME."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


def _view() -> SqlView:
    return SqlView.model_validate(
        {
            "id": "SqvOuLvl001",
            "name": "OU per level",
            "description": "Count of org units per hierarchy level.",
            "type": "VIEW",
            "sqlQuery": "SELECT hierarchylevel, COUNT(*) FROM organisationunit GROUP BY hierarchylevel",
        },
    )


def _result() -> SqlViewResult:
    return SqlViewResult.from_api(
        {
            "listGrid": {
                "title": "OU per level",
                "headers": [{"name": "level", "type": "INTEGER"}, {"name": "count", "type": "INTEGER"}],
                "rows": [[1, 1], [2, 3], [3, 15]],
                "height": 3,
                "width": 2,
            }
        },
    )


def test_sql_view_show_prints_sql_query_body(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view show prints sql query body."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.show_sql_view",
        new=AsyncMock(return_value=_view()),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "sql-view", "get", "SqvOuLvl001"])
    assert result.exit_code == 0, result.output
    assert "OU per level" in result.output
    assert "SELECT hierarchylevel" in result.output


def test_sql_view_execute_table_renders_columns_and_rows(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view execute table renders columns and rows."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.execute_sql_view",
        new=AsyncMock(return_value=_result()),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "sql-view", "execute", "SqvOuLvl001"])
    assert result.exit_code == 0, result.output
    assert "level" in result.output
    assert "count" in result.output
    assert "15" in result.output


def test_sql_view_execute_json_emits_name_keyed_dicts(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view execute json emits name keyed dicts."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.execute_sql_view",
        new=AsyncMock(return_value=_result()),
    ):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "sql-view", "execute", "SqvOuLvl001", "--format", "json"],
        )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == [
        {"level": 1, "count": 1},
        {"level": 2, "count": 3},
        {"level": 3, "count": 15},
    ]


def test_sql_view_execute_csv_prints_header_row_plus_data(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view execute csv prints header row plus data."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.execute_sql_view",
        new=AsyncMock(return_value=_result()),
    ):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "sql-view", "execute", "SqvOuLvl001", "--format", "csv"],
        )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert lines[0].startswith("level,count")
    assert lines[-1].endswith("15")


def test_sql_view_execute_forwards_var_and_criteria_pairs(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view execute forwards var and criteria pairs."""
    mock = AsyncMock(return_value=_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.execute_sql_view", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "sql-view",
                "execute",
                "SqvDeByNm01",
                "--var",
                "pattern:anc",
                "--criteria",
                "value_type:TEXT",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    call_kwargs = mock.await_args.kwargs
    assert call_kwargs["variables"] == {"pattern": "anc"}
    assert call_kwargs["criteria"] == {"value_type": "TEXT"}


def test_sql_view_execute_rejects_malformed_var_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view execute rejects malformed var flag."""
    result = CliRunner().invoke(
        build_app(),
        ["metadata", "sql-view", "execute", "SqvOuLvl001", "--var", "no_colon_here"],
    )
    assert result.exit_code == 2, result.output
    assert "expected key:value" in result.output


def test_sql_view_refresh_calls_service_and_prints_summary(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view refresh calls service and prints summary."""
    envelope = WebMessageResponse.model_validate({"status": "OK", "message": "Refresh complete."})
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.refresh_sql_view",
        new=AsyncMock(return_value=envelope),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "sql-view", "refresh", "SqvOuLvl001"])
    assert result.exit_code == 0, result.output
    assert "Refresh complete" in result.output or "OK" in result.output


def test_sql_view_adhoc_reads_sql_file_and_runs(pat_profile: None, tmp_path: Path) -> None:  # noqa: ARG001
    """Sql view adhoc reads sql file and runs."""
    sql_file = tmp_path / "probe.sql"
    sql_file.write_text("SELECT 1 AS x")
    mock = AsyncMock(return_value=_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.adhoc_sql_view", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "sql-view", "adhoc", "probe", str(sql_file)],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    call_args, call_kwargs = mock.await_args.args, mock.await_args.kwargs
    assert call_args[1] == "probe"
    assert call_args[2] == "SELECT 1 AS x"
    assert call_kwargs["view_type"] == "QUERY"
    assert call_kwargs["keep"] is False


def test_sql_view_adhoc_refuses_missing_sql_file(pat_profile: None) -> None:  # noqa: ARG001
    """Sql view adhoc refuses missing sql file."""
    result = CliRunner().invoke(
        build_app(),
        ["metadata", "sql-view", "adhoc", "probe", "nonexistent.sql"],
    )
    assert result.exit_code == 2, result.output
    assert "SQL file not found" in result.output
