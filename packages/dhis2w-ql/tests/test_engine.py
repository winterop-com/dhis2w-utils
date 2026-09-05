"""End-to-end engine tests over an in-memory binder: stages, definitions, functions, sinks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_ql import InMemoryBinder, QueryEngine, parse
from dhis2w_ql.engine.datasource import DataSource
from dhis2w_ql.engine.plan import NativeQuery, SourceCapabilities
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


async def test_as_overrides_file_extension(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"  # .txt -> no inferred format; `as csv` forces CSV
    text = f'dataElements | transform {{ code: id }} >> "{path}" as csv'
    result = await _engine(text).run_terminal()
    assert result.written_to == str(path)
    assert path.read_text().splitlines()[0] == "code"


async def test_stdout_format_is_reported_not_written() -> None:
    # `>> stdout as ndjson` and the bare `>> ndjson` shorthand both set the result format, no file.
    for text in ("dataElements | select id >> stdout as ndjson", "dataElements | select id >> ndjson"):
        result = await _engine(text).run_terminal()
        assert result.written_to is None
        assert result.format == "ndjson"
        assert result.rows == [{"id": "a1"}, {"id": "b2"}, {"id": "c3"}]


async def test_serialize_rows_matches_each_format() -> None:
    from dhis2w_ql import serialize_rows

    rows = [{"id": "a1", "name": "ANC"}, {"id": "b2", "name": "BCG"}]
    assert serialize_rows(rows, "ndjson") == '{"id": "a1", "name": "ANC"}\n{"id": "b2", "name": "BCG"}\n'
    assert serialize_rows(rows, "csv").splitlines()[0] == "id,name"
    assert json.loads(serialize_rows(rows, "json")) == rows


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


async def test_file_sink_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "monthly" / "out.json"
    text = f'dataElements | select id >> "{path}"'
    result = await _engine(text).run_terminal()
    assert result.written_to == str(path)
    assert json.loads(path.read_text()) == [{"id": "a1"}, {"id": "b2"}, {"id": "c3"}]


async def test_allow_file_io_false_blocks_read_source(tmp_path: Path) -> None:
    """A `read(...)` source raises when the engine is created with allow_file_io=False."""
    source = tmp_path / "in.json"
    source.write_text(json.dumps([{"id": "a1"}]), encoding="utf-8")
    engine = QueryEngine(
        parse(f'read("{source}") | select id'), InMemoryBinder({"dataElements": _ROWS}), allow_file_io=False
    )
    with pytest.raises(SemanticError, match="read\\(...\\) file sources are disabled"):
        await engine.run_terminal()


async def test_allow_file_io_false_blocks_file_sink(tmp_path: Path) -> None:
    """A `>> "path"` file sink raises when the engine is created with allow_file_io=False."""
    path = tmp_path / "out.json"
    engine = QueryEngine(
        parse(f'dataElements | select id >> "{path}"'), InMemoryBinder({"dataElements": _ROWS}), allow_file_io=False
    )
    with pytest.raises(SemanticError, match="file sinks .* are disabled"):
        await engine.run_terminal()
    assert not path.exists()  # refused before any bytes are written


async def test_allow_file_io_true_is_the_default_and_permits_read_and_sinks(tmp_path: Path) -> None:
    """The default (True) preserves the CLI's local-file capability for both sources and sinks."""
    source = tmp_path / "in.json"
    source.write_text(json.dumps([{"id": "z9", "name": "Z"}]), encoding="utf-8")
    out = tmp_path / "out.json"
    engine = QueryEngine(parse(f'read("{source}") | select id >> "{out}"'), InMemoryBinder({}))
    result = await engine.run_terminal()
    assert result.written_to == str(out)
    assert json.loads(out.read_text()) == [{"id": "z9"}]


async def test_define_chain_over_the_depth_limit_is_a_semantic_error() -> None:
    from dhis2w_ql.engine.executor import MAX_DEFINE_CHAIN_DEPTH

    depth = MAX_DEFINE_CHAIN_DEPTH + 5
    lines = ["define Q0: dataElements | limit 3"]
    lines.extend(f"define Q{i}: Q{i - 1} | limit 3" for i in range(1, depth))
    lines.append(f"Q{depth - 1} | count")
    with pytest.raises(SemanticError, match=f"definition chain exceeds {MAX_DEFINE_CHAIN_DEPTH} levels"):
        await _engine("\n".join(lines)).run_terminal()


async def test_define_chain_under_the_depth_limit_runs() -> None:
    from dhis2w_ql.engine.executor import MAX_DEFINE_CHAIN_DEPTH

    depth = MAX_DEFINE_CHAIN_DEPTH - 2
    lines = ["define Q0: dataElements | limit 3"]
    lines.extend(f"define Q{i}: Q{i - 1} | limit 3" for i in range(1, depth))
    lines.append(f"Q{depth - 1} | count")
    result = await _engine("\n".join(lines)).run_terminal()
    assert result.rows == [3]


async def test_function_call_chain_over_the_depth_limit_is_a_typed_error() -> None:
    from dhis2w_ql.d2path.evaluator import MAX_FUNCTION_CALL_DEPTH
    from dhis2w_ql.errors import EvaluationError

    depth = MAX_FUNCTION_CALL_DEPTH + 5
    lines = ["define function f0(x): $x"]
    lines.extend(f"define function f{i}(x): f{i - 1}($x)" for i in range(1, depth))
    lines.append(f"dataElements | where f{depth - 1}(value) > 0 | count")
    with pytest.raises(EvaluationError, match=f"call chain exceeds {MAX_FUNCTION_CALL_DEPTH} levels"):
        await _engine("\n".join(lines)).run_terminal()


async def test_function_call_chain_under_the_depth_limit_runs() -> None:
    from dhis2w_ql.d2path.evaluator import MAX_FUNCTION_CALL_DEPTH

    depth = MAX_FUNCTION_CALL_DEPTH - 2
    lines = ["define function f0(x): $x"]
    lines.extend(f"define function f{i}(x): f{i - 1}($x)" for i in range(1, depth))
    lines.append(f"dataElements | where f{depth - 1}(value) > 0 | count")
    result = await _engine("\n".join(lines)).run_terminal()
    assert result.rows == [3]


# --------------------------------------------------- native count fast path vs. plain execution

_PAGED_TOTAL = 100
_PAGED_ROWS = [{"id": f"x{index:03d}", "value": index} for index in range(_PAGED_TOTAL)]


class _PagingCountingSource:
    """A countable source that pushes paging down, mirroring the DHIS2 list binding."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Hold the rows this source pages over."""
        self._rows = rows

    def capabilities(self) -> SourceCapabilities:
        """Paging pushes down; filtering and ordering stay local."""
        return SourceCapabilities(paging=True)

    async def fetch(self, native: NativeQuery) -> list[dict[str, Any]]:
        """Return the rows the native paging selects."""
        rows = self._rows[(native.skip or 0) :]
        return rows if native.limit is None else rows[: native.limit]

    async def count(self, native: NativeQuery) -> int:
        """Report the matching total, ignoring paging exactly as the DHIS2 pager total does."""
        return len(self._rows)


class _PlainSource:
    """The same rows with no pushdown at all, so every stage runs locally."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Hold the rows this source returns verbatim."""
        self._rows = rows

    def capabilities(self) -> SourceCapabilities:
        """Nothing pushes down; the engine applies every stage locally."""
        return SourceCapabilities()

    async def fetch(self, native: NativeQuery) -> list[dict[str, Any]]:
        """Return every row; the engine applies the stages."""
        return list(self._rows)


class _SingleSourceBinder:
    """Binds the name `dataElements` to one source."""

    def __init__(self, source: DataSource) -> None:
        """Hold the source this binder resolves to."""
        self._source = source

    def bind(self, name: str) -> DataSource | None:
        """Return the held source for `dataElements`, else None."""
        return self._source if name == "dataElements" else None

    def bind_call(self, name: str, args: dict[str, Any]) -> DataSource | None:
        """This binder has no call sources."""
        return None


@pytest.mark.parametrize(
    ("stages", "expected"),
    [
        ("| limit 0", 0),
        ("| limit 5", 5),
        ("| skip 20", 80),
        ("| skip 200", 0),
        ("| skip 20 | limit 5", 5),
        ("| skip 98 | limit 5", 2),
        ("| limit 5 | skip 2", 3),
        ("", _PAGED_TOTAL),
    ],
)
async def test_native_count_fast_path_agrees_with_plain_execution(stages: str, expected: int) -> None:
    program = f"dataElements {stages} | count"
    paging_source = _SingleSourceBinder(_PagingCountingSource(_PAGED_ROWS))
    optimised = await QueryEngine(parse(program), paging_source).run_terminal()
    plain = await QueryEngine(parse(program), _SingleSourceBinder(_PlainSource(_PAGED_ROWS))).run_terminal()
    assert optimised.rows == [expected]
    assert plain.rows == [expected]
