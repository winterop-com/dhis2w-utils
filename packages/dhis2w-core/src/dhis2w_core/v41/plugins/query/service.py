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
    SemanticError,
    parse,
    parse_expression,
    plan_pipeline,
    to_jsonable,
    write_rows,
)
from dhis2w_ql.ast import CallSource, Define, ExprSource, FileSink, NameSource, ReadSource, WhereStage
from dhis2w_ql.engine import QueryEngine

from dhis2w_core.profile import Profile
from dhis2w_core.v41.plugins.metadata import service as metadata_service
from dhis2w_core.v41.plugins.query.datasource import Dhis2Binder, collect_fields
from dhis2w_core.v41.plugins.query.models import QueryExplain


async def run_query(
    profile: Profile,
    text: str,
    *,
    define: str | None = None,
    out: str | None = None,
    allow_local_files: bool = True,
) -> QueryResult:
    """Parse and execute a d2ql program against the profile, optionally writing rows to `out`.

    `allow_local_files` gates local filesystem access: trusted surfaces (the CLI) allow `read(...)`
    sources and `>> "..."` sinks; untrusted ones (MCP) set it False so a caller cannot read or write
    arbitrary host files through a query.
    """
    library = parse(text)
    if not allow_local_files and (out is not None or _uses_local_files(library)):
        raise SemanticError("local file access (read(...) / >> sinks) is not permitted here")
    entry = _select_pipeline(library, define)
    binder = await _build_binder(profile, library, entry)
    engine = QueryEngine(library, binder)
    result = await (engine.run_define(define) if define is not None else engine.run_terminal())
    if out is not None and result.written_to is None:
        written = write_rows(out, result.rows, scalar=result.scalar)
        return result.model_copy(update={"written_to": written})
    return result


async def explain_query(profile: Profile, text: str, *, define: str | None = None) -> QueryExplain:
    """Show how a d2ql pipeline splits between DHIS2 pushdown and local evaluation.

    Resolves the source `define` chain so the pushdown reported for `A | select ...` (where A is a
    named query over a resource) reflects what execution actually pushes down, not just the wrapper.
    """
    library = parse(text)
    root_source, stages, followed = _resolve_chain(library, _select_pipeline(library, define))
    via = f" (via {' -> '.join(followed)})" if followed else ""
    if isinstance(root_source, ReadSource):
        return QueryExplain(source=root_source.path, source_kind="read", residual_stages=_stage_kinds(stages))
    if isinstance(root_source, ExprSource):
        return QueryExplain(source="<expression>", source_kind="expression", residual_stages=_stage_kinds(stages))
    if isinstance(root_source, CallSource):
        known = Dhis2Binder(profile, set(), None).bind_call(root_source.name, {}) is not None
        head = (
            f"fetched via {root_source.name}(...); all stages run locally"
            if known
            else f"{root_source.name!r}(...) is not a known call source"
        )
        return QueryExplain(
            source=root_source.name, source_kind="call", residual_stages=_stage_kinds(stages), note=head + via
        )
    binder = await _build_binder(profile, library, _select_pipeline(library, define))
    data_source = binder.bind(root_source.name)
    if data_source is None:
        return QueryExplain(
            source=root_source.name,
            source_kind="resource",
            residual_stages=_stage_kinds(stages),
            note=f"{root_source.name!r} is not a resource on this instance" + via,
        )
    plan = plan_pipeline(root_source.name, data_source.capabilities(), stages)
    return QueryExplain(
        source=root_source.name,
        source_kind="resource",
        pushed_down=plan.native,
        residual_stages=_stage_kinds(plan.residual),
        note=via.strip() or None,
    )


def evaluate_path(expression: str, data: Any) -> list[Any]:
    """Evaluate a bare d2path expression over local JSON data (a single node or a list of nodes)."""
    focus = data if isinstance(data, list) else [data]
    result = Evaluator().evaluate(parse_expression(expression), focus)
    return [to_jsonable(value) for value in result]


async def _build_binder(profile: Profile, library: Library, entry: Pipeline) -> Dhis2Binder:
    # Only fetch the resource catalog when the program actually binds a metadata resource — an
    # analytics(...)/dataValues(...)/read(...)/expression program needs no catalog round-trip.
    fields = collect_fields(library, entry)
    if _binds_metadata_resource(library, entry):
        return Dhis2Binder(profile, set(await metadata_service.list_resource_types(profile)), fields)
    return Dhis2Binder(profile, set(), fields)


def _defines(library: Library) -> dict[str, Pipeline]:
    return {d.name: d.body for d in library.definitions if isinstance(d, Define)}


def _resolve_chain(library: Library, entry: Pipeline) -> tuple[Any, list[Any], list[str]]:
    """Follow the source `define` chain to its root source, returning (root source, effective stages, names).

    Effective stages are concatenated innermost-first (the root's stages run before the wrappers'),
    matching execution, so a plan over them reflects the real pushdown.
    """
    defines = _defines(library)
    chain: list[Pipeline] = []
    seen: set[int] = set()
    pipeline = entry
    while id(pipeline) not in seen:
        seen.add(id(pipeline))
        chain.append(pipeline)
        source = pipeline.source
        if isinstance(source, NameSource) and source.name in defines:
            pipeline = defines[source.name]
        else:
            break
    stages: list[Any] = []
    for pipe in reversed(chain):
        stages.extend(_effective_stages(pipe))
    followed = [p.source.name for p in chain[:-1] if isinstance(p.source, NameSource)]
    return chain[-1].source, stages, followed


def _binds_metadata_resource(library: Library, entry: Pipeline) -> bool:
    root_source, _, _ = _resolve_chain(library, entry)
    return isinstance(root_source, NameSource)


def _select_pipeline(library: Library, define: str | None) -> Pipeline:
    if define is not None:
        for definition in library.definitions:
            body = getattr(definition, "body", None)
            if getattr(definition, "name", None) == define and isinstance(body, Pipeline):
                return body
        raise SemanticError(f"no query definition named {define!r}")
    if library.terminal is None:
        raise SemanticError("this program has no terminal pipeline; pass --define to run a named query")
    return library.terminal


def _effective_stages(pipeline: Pipeline) -> list[Any]:
    source = pipeline.source
    if isinstance(source, NameSource) and source.inline_filter is not None:
        return [WhereStage(predicate=source.inline_filter), *pipeline.stages]
    return list(pipeline.stages)


def _stage_kinds(stages: list[Any]) -> list[str]:
    return [stage.kind for stage in stages]


def _uses_local_files(library: Library) -> bool:
    pipelines = [definition.body for definition in library.definitions if isinstance(definition.body, Pipeline)]
    if library.terminal is not None:
        pipelines.append(library.terminal)
    return any(isinstance(p.source, ReadSource) or isinstance(p.sink, FileSink) for p in pipelines)
