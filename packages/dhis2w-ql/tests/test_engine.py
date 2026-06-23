"""End-to-end engine tests over an in-memory binder: stages, definitions, functions, sinks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dhis2w_ql import InMemoryBinder, QueryEngine, parse
from dhis2w_ql.errors import SemanticError

_ROWS = [
    {"id": "a1", "name": "ANC 1st visit", "domainType": "AGGREGATE", "categoryCombo": {"name": "default"}, "value": 12},
    {"id": "b2", "name": "BCG doses", "domainType": "AGGREGATE", "categoryCombo": {"name": "default"}, "value": 7},
    {"id": "c3", "name": "ANC 2nd visit", "domainType": "TRACKER", "categoryCombo": {"name": "EPI"}, "value": 30},
]


def _engine(text: str) -> QueryEngine:
    return QueryEngine(parse(text), InMemoryBinder({"dataElements": _ROWS}))


async def _rows(text: str) -> list:
    return (await _engine(text).run_terminal()).rows


async def test_where_filters_rows() -> None:
    rows = await _rows('dataElements | where domainType = "AGGREGATE"')
    assert [r["id"] for r in rows] == ["a1", "b2"]


async def test_where_like_is_case_insensitive() -> None:
    rows = await _rows('dataElements | where name ~ "anc"')
    assert {r["id"] for r in rows} == {"a1", "c3"}


async def test_select_projects_and_aliases() -> None:
    rows = await _rows("dataElements | select id, categoryCombo.name as combo | limit 1")
    assert rows == [{"id": "a1", "combo": "default"}]


async def test_select_duplicate_derived_names_error() -> None:
    # `name` and `categoryCombo.name` both derive the column `name` — fail loudly, never overwrite.
    with pytest.raises(SemanticError, match="two columns named 'name'"):
        await _rows("dataElements | select name, categoryCombo.name")


async def test_group_by_key_collides_with_aggregation() -> None:
    with pytest.raises(SemanticError, match="two columns named 'domainType'"):
        await _rows("dataElements | group by domainType { domainType: count() }")


async def test_transform_builds_objects() -> None:
    rows = await _rows('dataElements | where domainType = "TRACKER" | transform { code: id, big: value > 20 }')
    assert rows == [{"code": "c3", "big": True}]


async def test_order_and_limit() -> None:
    rows = await _rows("dataElements | select name | order name desc | limit 2")
    assert [r["name"] for r in rows] == ["BCG doses", "ANC 2nd visit"]


async def test_skip() -> None:
    rows = await _rows("dataElements | select id | skip 2")
    assert rows == [{"id": "c3"}]


async def test_count_is_scalar() -> None:
    result = await _engine('dataElements | where domainType = "AGGREGATE" | count').run_terminal()
    assert result.scalar is True
    assert result.rows == [2]


async def test_scalar_define_reference() -> None:
    rows = await _rows("define MinValue: 10\ndataElements | where value >= $MinValue | select id")
    assert [r["id"] for r in rows] == ["a1", "c3"]


async def test_define_function_predicate() -> None:
    text = 'define function isAnc(de): $de.name ~ "ANC"\ndataElements | where isAnc($this) | count'
    result = await _engine(text).run_terminal()
    assert result.rows == [3 - 1]  # two ANC rows


async def test_named_query_reuse_as_source() -> None:
    text = 'define Aggregates: dataElements | where domainType = "AGGREGATE"\nAggregates | select id'
    rows = await _rows(text)
    assert [r["id"] for r in rows] == ["a1", "b2"]


async def test_run_define_directly() -> None:
    text = 'define Aggregates: dataElements | where domainType = "AGGREGATE" | select id'
    result = await _engine(text).run_define("Aggregates")
    assert [r["id"] for r in result.rows] == ["a1", "b2"]


async def test_csv_sink(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    text = f'dataElements | transform {{ code: id, label: name }} >> "{path}"'
    result = await _engine(text).run_terminal()
    assert result.written_to == str(path)
    body = path.read_text()
    assert body.splitlines()[0] == "code,label"
    assert "a1,ANC 1st visit" in body


async def test_json_sink(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    text = f'dataElements | select id >> "{path}"'
    await _engine(text).run_terminal()
    assert json.loads(path.read_text()) == [{"id": "a1"}, {"id": "b2"}, {"id": "c3"}]


async def test_inline_filter_source() -> None:
    rows = await _rows('dataElements[domainType = "TRACKER"] | select id')
    assert rows == [{"id": "c3"}]


async def test_aggregate_groups_and_reduces() -> None:
    rows = await _rows("dataElements | group by domainType { total: sum(value), n: count() } | order domainType asc")
    assert rows == [
        {"domainType": "AGGREGATE", "total": 19.0, "n": 2},
        {"domainType": "TRACKER", "total": 30.0, "n": 1},
    ]


async def test_aggregate_count_with_no_value_field() -> None:
    rows = await _rows("dataElements | group by categoryCombo.name { n: count() } | order n desc")
    assert {row["n"] for row in rows} == {2, 1}


async def test_fold_collapses_stream_to_one_object() -> None:
    result = await _engine(
        'dataElements | where domainType = "AGGREGATE" | transform { resource: { id: id } } '
        '| fold { resourceType: "Bundle", entry: $rows }'
    ).run_terminal()
    assert result.scalar is True
    assert result.rows == [
        {"resourceType": "Bundle", "entry": [{"resource": {"id": "a1"}}, {"resource": {"id": "b2"}}]}
    ]


async def test_transform_accepts_a_function_call() -> None:
    text = (
        "define function entry(de): { resource: { code: $de.id, label: $de.name } }\n"
        'dataElements | where domainType = "TRACKER" | transform entry($this)'
    )
    rows = await _rows(text)
    assert rows == [{"resource": {"code": "c3", "label": "ANC 2nd visit"}}]


async def test_fold_to_json_file_writes_object_not_array(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    text = f'dataElements | transform {{ id: id }} | fold {{ resourceType: "Bundle", entry: $rows }} >> "{path}"'
    await _engine(text).run_terminal()
    document = json.loads(path.read_text())
    assert document["resourceType"] == "Bundle"
    assert [e["id"] for e in document["entry"]] == ["a1", "b2", "c3"]
