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


async def test_explain_call_source() -> None:
    explain = await service.explain_query(_PROFILE, 'analytics(dx: "x", pe: "y", ou: "z") | limit 5')
    assert explain.source == "analytics"
    assert explain.source_kind == "call"
    assert explain.pushed_down is None
    assert "limit" in explain.residual_stages


async def test_explain_unknown_call_source() -> None:
    explain = await service.explain_query(_PROFILE, "wat(a: 1) | limit 5")
    assert explain.source_kind == "call"
    assert explain.note is not None and "not a known call source" in explain.note


@respx.mock
async def test_explain_resolves_named_query_pushdown() -> None:
    _mock_connect()
    explain = await service.explain_query(
        _PROFILE,
        'define Aggregates: dataElements | where domainType = "AGGREGATE"\nAggregates | select id, name | limit 10',
    )
    # The reusable-library wrapper resolves to the real resource + pushed-down filter.
    assert explain.source == "dataElements"
    assert explain.source_kind == "resource"
    assert explain.pushed_down is not None
    assert [f.property for f in explain.pushed_down.filters] == ["domainType"]
    assert explain.residual_stages == ["select", "limit"]
    assert explain.note is not None and "Aggregates" in explain.note


def test_non_metadata_sources_need_no_catalog() -> None:
    from dhis2w_core.v42.plugins.query.service import _binds_metadata_resource
    from dhis2w_ql import parse

    def binds(text: str) -> bool:
        library = parse(text)
        assert library.terminal is not None
        return _binds_metadata_resource(library, library.terminal)

    assert binds("dataElements | select id") is True
    assert binds('define A: dataElements | where domainType = "AGGREGATE"\nA | select id') is True
    assert binds('analytics(dx: "x", pe: "y", ou: "z") | limit 5') is False
    assert binds('dataValues(dataSet: "d", period: "p", orgUnit: "o") | limit 5') is False
    assert binds('read("x.json") | select id') is False
    assert binds("1 + 2") is False


def _fields(text: str, define: str | None = None) -> str | None:
    from dhis2w_core.v42.plugins.query.datasource import collect_fields
    from dhis2w_core.v42.plugins.query.service import _select_pipeline
    from dhis2w_ql import parse

    library = parse(text)
    return collect_fields(library, _select_pipeline(library, define))


def test_collect_fields_includes_function_param_paths() -> None:
    direct = _fields('dataElements | where valueType = "NUMBER" | select id')
    via_function = _fields(
        'define function isNum(de): $de.valueType = "NUMBER"\ndataElements | where isNum($this) | select id'
    )
    assert direct is not None and "valueType" in direct
    assert via_function == direct


def test_collect_fields_is_scoped_to_the_entry_pipeline() -> None:
    # An unused definition for another resource must not contaminate the terminal's selector.
    fields = _fields("define A: dataElements | select categoryCombo.name\norganisationUnits | select level")
    assert fields is not None
    assert "categoryCombo" not in fields
    assert "level" in fields


def test_collect_fields_skips_is_type_names() -> None:
    fields = _fields("dataElements | where value is Integer | select id")
    assert fields is not None
    assert "Integer" not in fields
    assert "value" in fields


def test_collect_fields_attributes_method_args_to_their_target() -> None:
    fields = _fields("optionSets | fold { c: options.select({ code: code, display: name }) }")
    assert fields is not None
    assert "options[code,name]" in fields


def test_collect_fields_resolves_rows_navigation_in_fold() -> None:
    fields = _fields("dataSets | fold { item: $rows.dataSetElements.dataElement.select({ id: id, name: name }) }")
    assert fields is not None
    assert "dataSetElements[dataElement[id,name]]" in fields


def test_collect_fields_ignores_post_reshape_aliases() -> None:
    # `label` is a select alias, not a DHIS2 field — it must not reach fields=.
    fields = _fields("dataElements | select id, name as label | order label asc")
    assert fields is not None
    assert "label" not in fields
    assert fields == "id,name"


def test_collect_fields_through_element_preserving_method() -> None:
    # `options.where(code = "A").name` needs both code (the filter) and name (the trailing member).
    fields = _fields('optionSets | select options.where(code = "A").name as picked')
    assert fields is not None
    assert "options[code,name]" in fields


def test_collect_fields_fetches_all_for_whole_row_output() -> None:
    # No projection, or a whole-row passthrough, means the consumer sees full rows -> fetch `*`.
    assert _fields("dataElements | limit 25") == "*"
    assert _fields("dataElements | transform { raw: $this }") == "*"
    assert _fields('dataElements | where categoryCombo.name = "default" | limit 5') == "*,categoryCombo[name]"
    # An explicit projection still narrows.
    assert _fields("dataElements | select id, name") == "id,name"


def test_collect_fields_keeps_whole_object_when_requested() -> None:
    # A whole `geometry` must not be narrowed to `geometry[type]` by the filter on geometry.type.
    fields = _fields('organisationUnits | where geometry.type = "Polygon" | transform { id: id, geometry: geometry }')
    assert fields is not None
    assert "geometry[" not in fields
    assert "geometry" in fields.split(",")


async def test_mcp_query_eval_rejects_file_access() -> None:
    for program in ['dataElements | select id >> "/tmp/evil.json"', 'read("/etc/hosts") | select id']:
        with pytest.raises(Exception, match="local file access"):
            await service.run_query(_PROFILE, program, allow_local_files=False)


@respx.mock
async def test_cli_run_query_still_allows_file_sink(tmp_path: Path) -> None:
    _mock_connect()
    _mock_data_elements()
    out = tmp_path / "elements.csv"
    result = await service.run_query(_PROFILE, f'dataElements | select id, name >> "{out}"')
    assert result.written_to == str(out)
    assert out.exists()


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
