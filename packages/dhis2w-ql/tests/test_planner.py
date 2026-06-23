"""Planner tests: which stages push down to the native query vs. stay local."""

from __future__ import annotations

from dhis2w_ql import QueryPlan, SourceCapabilities, parse_pipeline, plan_pipeline

_CAPABLE = SourceCapabilities(filter=True, order=True, paging=True)
_INCAPABLE = SourceCapabilities()


def _plan(text: str, capabilities: SourceCapabilities = _CAPABLE) -> QueryPlan:
    pipeline = parse_pipeline(text)
    return plan_pipeline("dataElements", capabilities, pipeline.stages)


def test_simple_filter_pushes_down() -> None:
    plan = _plan('dataElements | where domainType = "AGGREGATE"')
    assert [(f.property, f.operator, f.value) for f in plan.native.filters] == [("domainType", "eq", "AGGREGATE")]
    assert plan.residual == []


def test_and_filters_push_down_with_and_junction() -> None:
    plan = _plan('dataElements | where domainType = "AGGREGATE" and valueType = "NUMBER"')
    assert plan.native.root_junction == "AND"
    assert len(plan.native.filters) == 2


def test_or_filters_use_or_junction() -> None:
    plan = _plan('dataElements | where name ~ "ANC" or name ~ "BCG"')
    assert plan.native.root_junction == "OR"
    assert [f.operator for f in plan.native.filters] == ["ilike", "ilike"]


def test_order_and_limit_push_down() -> None:
    plan = _plan("dataElements | order name asc | limit 25")
    assert [(o.property, o.descending) for o in plan.native.order] == [("name", False)]
    assert plan.native.limit == 25
    assert plan.residual == []


def test_transform_stays_local() -> None:
    plan = _plan('dataElements | where domainType = "AGGREGATE" | transform { code: id }')
    assert len(plan.native.filters) == 1
    assert [s.kind for s in plan.residual] == ["transform"]


def test_function_predicate_stays_local() -> None:
    plan = _plan('dataElements | where name.substring(0, 3) = "ANC"')
    assert plan.native.filters == []
    assert [s.kind for s in plan.residual] == ["where"]


def test_in_operator_pushes_down() -> None:
    plan = _plan('dataElements | where valueType in ["NUMBER", "INTEGER"]')
    assert plan.native.filters[0].operator == "in"
    assert plan.native.filters[0].value == ["NUMBER", "INTEGER"]


def test_incapable_source_keeps_everything_local() -> None:
    plan = _plan('dataElements | where domainType = "AGGREGATE" | limit 5', _INCAPABLE)
    assert plan.native.filters == []
    assert [s.kind for s in plan.residual] == ["where", "limit"]


def test_skip_then_limit_push_down_in_order() -> None:
    plan = _plan("dataElements | skip 10 | limit 5")
    assert plan.native.skip == 10
    assert plan.native.limit == 5
    assert plan.residual == []


def test_non_pushable_path_stays_local() -> None:
    caps = SourceCapabilities(filter=True, order=True, paging=True, non_pushable_paths=("geometry",))
    plan = _plan('organisationUnits | where geometry.type = "Point"', caps)
    assert plan.native.filters == []
    assert [s.kind for s in plan.residual] == ["where"]


def test_non_pushable_path_blocks_whole_and_clause() -> None:
    caps = SourceCapabilities(filter=True, order=True, paging=True, non_pushable_paths=("geometry",))
    plan = _plan('organisationUnits | where level >= 2 and geometry.type = "Point"', caps)
    assert plan.native.filters == []
    assert [s.kind for s in plan.residual] == ["where"]
