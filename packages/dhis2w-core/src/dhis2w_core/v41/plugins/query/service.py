"""Service layer for the `query` plugin: parse d2ql, bind DHIS2 sources, run or explain.

Both the CLI and MCP surfaces call these functions. `run_query` executes a program against a live
profile; `explain_query` shows the pushdown split without fetching; `evaluate_path` runs a bare
d2path expression over local JSON.
"""

from __future__ import annotations

from typing import Any

from dhis2w_ql import (
    Evaluator,
    Library,
    Pipeline,
    QueryResult,
    parse,
    parse_expression,
    plan_pipeline,
    to_jsonable,
    write_rows,
)
from dhis2w_ql.ast import CallSource, ExprSource, NameSource, ReadSource, WhereStage
from dhis2w_ql.engine import QueryEngine

from dhis2w_core.profile import Profile
from dhis2w_core.v41.plugins.metadata import service as metadata_service
from dhis2w_core.v41.plugins.query.datasource import Dhis2Binder, collect_fields
from dhis2w_core.v41.plugins.query.models import QueryExplain


async def run_query(profile: Profile, text: str, *, define: str | None = None, out: str | None = None) -> QueryResult:
    """Parse and execute a d2ql program against the profile, optionally writing rows to `out`."""
    library = parse(text)
    binder = await _build_binder(profile, library)
    engine = QueryEngine(library, binder)
    result = await (engine.run_define(define) if define is not None else engine.run_terminal())
    if out is not None and result.written_to is None:
        written = write_rows(out, result.rows, scalar=result.scalar)
        return result.model_copy(update={"written_to": written})
    return result


async def explain_query(profile: Profile, text: str, *, define: str | None = None) -> QueryExplain:
    """Show how a d2ql pipeline splits between DHIS2 pushdown and local evaluation."""
    library = parse(text)
    pipeline = _select_pipeline(library, define)
    stages = _effective_stages(pipeline)
    source = pipeline.source
    if isinstance(source, ReadSource):
        return QueryExplain(source=source.path, source_kind="read", residual_stages=_stage_kinds(stages))
    if isinstance(source, ExprSource):
        return QueryExplain(source="<expression>", source_kind="expression", residual_stages=_stage_kinds(stages))
    if isinstance(source, CallSource):
        known = Dhis2Binder(profile, set(), None).bind_call(source.name, {}) is not None
        note = (
            f"fetched via {source.name}(...); all stages run locally"
            if known
            else f"{source.name!r}(...) is not a known call source"
        )
        return QueryExplain(source=source.name, source_kind="call", residual_stages=_stage_kinds(stages), note=note)
    binder = await _build_binder(profile, library)
    data_source = binder.bind(source.name)
    if data_source is None:
        if _is_defined(library, source.name):
            return QueryExplain(source=source.name, source_kind="definition", residual_stages=_stage_kinds(stages))
        return QueryExplain(
            source=source.name,
            source_kind="resource",
            residual_stages=_stage_kinds(stages),
            note=f"{source.name!r} is not a resource on this instance",
        )
    plan = plan_pipeline(source.name, data_source.capabilities(), stages)
    return QueryExplain(
        source=source.name,
        source_kind="resource",
        pushed_down=plan.native,
        residual_stages=_stage_kinds(plan.residual),
    )


def evaluate_path(expression: str, data: Any) -> list[Any]:
    """Evaluate a bare d2path expression over local JSON data (a single node or a list of nodes)."""
    focus = data if isinstance(data, list) else [data]
    result = Evaluator().evaluate(parse_expression(expression), focus)
    return [to_jsonable(value) for value in result]


async def _build_binder(profile: Profile, library: Library) -> Dhis2Binder:
    resource_names = set(await metadata_service.list_resource_types(profile))
    return Dhis2Binder(profile, resource_names, collect_fields(library))


def _select_pipeline(library: Library, define: str | None) -> Pipeline:
    if define is not None:
        for definition in library.definitions:
            body = getattr(definition, "body", None)
            if getattr(definition, "name", None) == define and isinstance(body, Pipeline):
                return body
        raise ValueError(f"no query definition named {define!r}")
    if library.terminal is None:
        raise ValueError("this program has no terminal pipeline; pass --define to explain a named query")
    return library.terminal


def _effective_stages(pipeline: Pipeline) -> list[Any]:
    source = pipeline.source
    if isinstance(source, NameSource) and source.inline_filter is not None:
        return [WhereStage(predicate=source.inline_filter), *pipeline.stages]
    return list(pipeline.stages)


def _stage_kinds(stages: list[Any]) -> list[str]:
    return [stage.kind for stage in stages]


def _is_defined(library: Library, name: str) -> bool:
    return any(getattr(definition, "name", None) == name for definition in library.definitions)
