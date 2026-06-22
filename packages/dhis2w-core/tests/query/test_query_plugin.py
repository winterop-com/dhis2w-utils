"""Integration tests for the `query` plugin: pushdown to DHIS2, local reshape, CLI surfaces."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.query import service
from typer.testing import CliRunner

_BASE = "http://mock.example"
_PROFILE = Profile(base_url=_BASE, auth="pat", token="t")


def _mock_connect() -> None:
    respx.get(f"{_BASE}/").mock(return_value=httpx.Response(200, text="ok"))
    respx.get(f"{_BASE}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.4"}))


def _mock_data_elements() -> respx.Route:
    return respx.get(f"{_BASE}/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 10, "total": 2},
                "dataElements": [
                    {"id": "a1", "name": "ANC", "domainType": "AGGREGATE"},
                    {"id": "b2", "name": "BCG", "domainType": "AGGREGATE"},
                ],
            },
        )
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@respx.mock
async def test_run_query_pushes_filter_and_reshapes() -> None:
    _mock_connect()
    route = _mock_data_elements()
    result = await service.run_query(
        _PROFILE,
        'dataElements | where domainType = "AGGREGATE" | transform { code: id, label: name } | limit 10',
    )
    assert route.called
    assert dict(route.calls.last.request.url.params).get("filter") == "domainType:eq:AGGREGATE"
    assert result.rows == [{"code": "a1", "label": "ANC"}, {"code": "b2", "label": "BCG"}]


@respx.mock
async def test_run_query_count_is_scalar() -> None:
    _mock_connect()
    _mock_data_elements()
    result = await service.run_query(_PROFILE, "dataElements | count")
    assert result.scalar is True
    assert result.rows == [2]


@respx.mock
async def test_explain_reports_pushdown() -> None:
    _mock_connect()
    explain = await service.explain_query(
        _PROFILE,
        'dataElements | where domainType = "AGGREGATE" | transform { code: id }',
    )
    assert explain.source == "dataElements"
    assert explain.source_kind == "resource"
    assert explain.pushed_down is not None
    assert [f.property for f in explain.pushed_down.filters] == ["domainType"]
    assert explain.residual_stages == ["transform"]


def test_evaluate_path_over_local_json() -> None:
    patient = {"name": [{"use": "official", "family": "King"}]}
    assert service.evaluate_path('name.where(use = "official").family', patient) == ["King"]


def test_cli_ast_is_offline(runner: CliRunner) -> None:
    result = runner.invoke(build_app(), ["query", "ast", "dataElements | select id, name | limit 5"])
    assert result.exit_code == 0
    assert '"kind": "select"' in result.stdout


def test_cli_d2path_over_input_file(runner: CliRunner, tmp_path: Path) -> None:
    data = tmp_path / "patient.json"
    data.write_text(json.dumps({"name": [{"given": ["Ada", "Lovelace"]}]}))
    result = runner.invoke(build_app(), ["query", "d2path", "name.given.first()", "--input", str(data)])
    assert result.exit_code == 0
    assert "Ada" in result.stdout
