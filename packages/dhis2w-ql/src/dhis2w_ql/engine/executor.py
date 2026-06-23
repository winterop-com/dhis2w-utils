"""The execution engine: resolve sources and definitions, plan pushdown, run residual stages locally.

`QueryEngine` ties a parsed `Library` to a `ResourceBinder`. It also acts as the expression
`Resolver`, so scalar `define`s and `define function`s are visible inside `where`/`select`/
`transform`. Pushdown-capable sources fetch a `NativeQuery`; everything else runs over the rows
the source returns.
"""

from __future__ import annotations

import csv
import io
import json
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_ql.ast import (
    AggregateStage,
    CallSource,
    CountStage,
    Define,
    DefineFunction,
    Expr,
    ExprSource,
    FileSink,
    FoldStage,
    Library,
    LimitStage,
    MemberExpr,
    NameExpr,
    NameSource,
    OrderStage,
    Pipeline,
    ReadSource,
    SelectItem,
    SelectStage,
    SkipStage,
    Stage,
    TransformStage,
    WhereStage,
)
from dhis2w_ql.d2path.evaluator import EvalContext, Evaluator
from dhis2w_ql.d2path.values import collapse, compare, truthy
from dhis2w_ql.engine.datasource import ResourceBinder
from dhis2w_ql.engine.planner import plan_pipeline
from dhis2w_ql.errors import EvaluationError, SemanticError


class _StageOutcome(BaseModel):
    """Rows produced by a stage (or stage chain) and whether they are a scalar result."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rows: list[Any] = Field(default_factory=list)
    scalar: bool = False


class _SourceResolution(BaseModel):
    """Rows fetched from a source plus the residual stages still to run locally."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rows: list[Any] = Field(default_factory=list)
    residual: list[Any] = Field(default_factory=list)


class QueryResult(BaseModel):
    """The outcome of running a pipeline: the produced rows plus sink/shape metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rows: list[Any] = Field(default_factory=list)
    count: int = 0
    scalar: bool = False
    written_to: str | None = None
    format: str | None = None


class QueryEngine:
    """Executes d2ql pipelines and definitions against a resource binder."""

    def __init__(self, library: Library, binder: ResourceBinder) -> None:
        """Index the library's definitions and bind the source resolver."""
        self._library = library
        self._binder = binder
        self._evaluator = Evaluator(resolver=self)
        self._defines: dict[str, Define] = {}
        self._functions: dict[str, DefineFunction] = {}
        self._scalar_cache: dict[str, list[Any]] = {}
        for definition in library.definitions:
            if isinstance(definition, Define):
                self._defines[definition.name] = definition
            else:
                self._functions[definition.name] = definition

    # ------------------------------------------------------------------ Resolver protocol

    def resolve_variable(self, name: str) -> list[Any] | None:
        """Resolve a `$name` reference to a scalar `define`'s value, or None when not scalar."""
        if name in self._scalar_cache:
            return self._scalar_cache[name]
        define = self._defines.get(name)
        if define is None or not _is_scalar_define(define):
            return None
        source = define.body.source
        assert isinstance(source, ExprSource)  # guaranteed by _is_scalar_define
        value = self._evaluator.evaluate(source.expr, [])
        self._scalar_cache[name] = value
        return value

    def resolve_function(self, name: str) -> DefineFunction | None:
        """Resolve a `define function` by name, or None when unknown."""
        return self._functions.get(name)

    # ------------------------------------------------------------------ public run surface

    async def run_terminal(self) -> QueryResult:
        """Run the library's terminal pipeline, raising when there is none."""
        if self._library.terminal is None:
            raise SemanticError("this program has no terminal pipeline to run")
        return await self.run(self._library.terminal)

    async def run_define(self, name: str) -> QueryResult:
        """Run a named `define`'s pipeline."""
        define = self._defines.get(name)
        if define is None:
            raise SemanticError(f"unknown definition {name!r}")
        return await self.run(define.body)

    async def run(self, pipeline: Pipeline) -> QueryResult:
        """Execute a pipeline and apply its sink, returning the rows and sink metadata."""
        outcome = await self._execute(pipeline)
        if isinstance(pipeline.sink, FileSink):
            written = _write_file(pipeline.sink, outcome.rows, scalar=outcome.scalar)
            return QueryResult(
                rows=outcome.rows,
                count=len(outcome.rows),
                scalar=outcome.scalar,
                written_to=written.path,
                format=written.format,
            )
        return QueryResult(rows=outcome.rows, count=len(outcome.rows), scalar=outcome.scalar)

    # ------------------------------------------------------------------ execution

    async def _execute(self, pipeline: Pipeline) -> _StageOutcome:
        stages = self._effective_stages(pipeline)
        resolved = await self._resolve_source(pipeline, stages)
        return self._run_local(resolved.residual, resolved.rows)

    def _effective_stages(self, pipeline: Pipeline) -> list[Stage]:
        source = pipeline.source
        if isinstance(source, NameSource) and source.inline_filter is not None:
            return [WhereStage(predicate=source.inline_filter), *pipeline.stages]
        return list(pipeline.stages)

    async def _resolve_source(self, pipeline: Pipeline, stages: list[Stage]) -> _SourceResolution:
        source = pipeline.source
        if isinstance(source, NameSource):
            data_source = self._binder.bind(source.name)
            if data_source is not None:
                plan = plan_pipeline(source.name, data_source.capabilities(), stages)
                rows = await data_source.fetch(plan.native)
                return _SourceResolution(rows=rows, residual=list(plan.residual))
            define = self._defines.get(source.name)
            if define is None:
                raise SemanticError(f"unknown source {source.name!r}: not a bound resource or definition")
            inner = await self._execute(define.body)
            return _SourceResolution(rows=inner.rows, residual=list(stages))
        if isinstance(source, CallSource):
            args = {field.name: collapse(self._evaluator.evaluate(field.value, [])) for field in source.args}
            data_source = self._binder.bind_call(source.name, args)
            if data_source is None:
                raise SemanticError(f"unknown source {source.name!r}(...): no call binding for it")
            plan = plan_pipeline(source.name, data_source.capabilities(), stages)
            rows = await data_source.fetch(plan.native)
            return _SourceResolution(rows=rows, residual=list(plan.residual))
        if isinstance(source, ReadSource):
            return _SourceResolution(rows=_read_rows(source.path), residual=list(stages))
        return _SourceResolution(rows=self._evaluator.evaluate(source.expr, []), residual=list(stages))

    def _run_local(self, stages: list[Any], rows: list[Any]) -> _StageOutcome:
        outcome = _StageOutcome(rows=rows, scalar=False)
        for stage in stages:
            outcome = self._apply_stage(stage, outcome.rows)
        return outcome

    def _apply_stage(self, stage: Stage, rows: list[Any]) -> _StageOutcome:
        match stage:
            case WhereStage():
                kept = [row for index, row in enumerate(rows) if truthy(self._per_item(stage.predicate, row, index))]
                return _StageOutcome(rows=kept, scalar=False)
            case SelectStage():
                _ensure_unique([_select_key(item, i) for i, item in enumerate(stage.items)], "select")
                return _StageOutcome(rows=[self._project(stage, row, index) for index, row in enumerate(rows)])
            case TransformStage():
                built = [collapse(self._per_item(stage.template, row, index)) for index, row in enumerate(rows)]
                return _StageOutcome(rows=built, scalar=False)
            case OrderStage():
                return _StageOutcome(rows=self._order(stage, rows), scalar=False)
            case LimitStage():
                return _StageOutcome(rows=rows[: stage.count], scalar=False)
            case SkipStage():
                return _StageOutcome(rows=rows[stage.count :], scalar=False)
            case CountStage():
                return _StageOutcome(rows=[len(rows)], scalar=True)
            case AggregateStage():
                return _StageOutcome(rows=self._aggregate(stage, rows), scalar=False)
            case FoldStage():
                scope = EvalContext().child(rows=rows)
                return _StageOutcome(rows=[self._evaluator.build_object(stage.template, rows, scope)], scalar=True)
            # No catch-all: `Stage` is a closed union and every variant is handled above, so the
            # type checkers prove exhaustiveness. Adding a variant without a case here is a
            # compile-time error (missing return), which is stronger than a runtime guard.

    def _per_item(self, expr: Expr, item: Any, index: int) -> list[Any]:
        return self._evaluator.per_item(expr, item, index, EvalContext())

    def _project(self, stage: SelectStage, item: Any, index: int) -> dict[str, Any]:
        return {
            _select_key(select_item, position): collapse(self._per_item(select_item.expr, item, index))
            for position, select_item in enumerate(stage.items)
        }

    def _aggregate(self, stage: AggregateStage, rows: list[Any]) -> list[Any]:
        key_name = _derive_name(stage.group, 0)
        _ensure_unique([key_name, *(field.name for field in stage.aggregations.fields)], "group by")
        buckets: list[tuple[Any, list[Any]]] = []
        for index, row in enumerate(rows):
            key = collapse(self._per_item(stage.group, row, index))
            for existing_key, bucket in buckets:
                if existing_key == key:
                    bucket.append(row)
                    break
            else:
                buckets.append((key, [row]))
        result: list[dict[str, Any]] = []
        for key, bucket in buckets:
            aggregated = self._evaluator.build_object(stage.aggregations, bucket, EvalContext())
            result.append({key_name: key, **aggregated})
        return result

    def _order(self, stage: OrderStage, rows: list[Any]) -> list[Any]:
        # Sort keys are per-row field/value expressions; `$index` has no meaning in a comparator and
        # is intentionally fixed to 0 (it would compare equal for every row anyway).
        def comparator(left: Any, right: Any) -> int:
            for key in stage.keys:
                left_value = collapse(self._per_item(key.expr, left, 0))
                right_value = collapse(self._per_item(key.expr, right, 0))
                order = _compare_nullable(left_value, right_value)
                if order != 0:
                    return -order if key.descending else order
            return 0

        return sorted(rows, key=cmp_to_key(comparator))


def _is_scalar_define(define: Define) -> bool:
    body = define.body
    return isinstance(body.source, ExprSource) and not body.stages and body.sink is None


def _derive_name(expr: Expr, position: int) -> str:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, MemberExpr):
        return expr.name
    return f"column{position + 1}"


def _select_key(item: SelectItem, position: int) -> str:
    return item.alias or _derive_name(item.expr, position)


def _ensure_unique(names: list[str], context: str) -> None:
    """Reject duplicate output column names so a projection never silently overwrites a column."""
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise SemanticError(
                f"{context} produces two columns named {name!r}; disambiguate with an alias, e.g. `… as {name}2`"
            )
        seen.add(name)


def _compare_nullable(left: Any, right: Any) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return -1
    if right is None:
        return 1
    order = compare(left, right)
    return order if order is not None else 0


def _read_rows(path: str) -> list[Any]:
    text = Path(path).read_text(encoding="utf-8")
    if path.lower().endswith(".ndjson"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return parsed
    return [parsed]


class _WriteOutcome(BaseModel):
    """Where a file sink wrote and in which format."""

    model_config = ConfigDict(frozen=True)

    path: str
    format: str


def _write_file(sink: FileSink, rows: list[Any], *, scalar: bool = False) -> _WriteOutcome:
    fmt = sink.format or "json"
    payload = [_jsonable(row) for row in rows]
    if fmt == "csv":
        text = _to_csv(payload)
    elif fmt == "ndjson":
        text = "\n".join(json.dumps(row, ensure_ascii=False) for row in payload) + "\n"
    else:
        # A scalar result (fold/count) writes the single value, not a one-element array.
        document: Any = payload[0] if scalar and len(payload) == 1 else payload
        text = json.dumps(document, indent=2, ensure_ascii=False)
    Path(sink.path).write_text(text, encoding="utf-8")
    return _WriteOutcome(path=sink.path, format=fmt)


def _to_csv(rows: list[Any]) -> str:
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise EvaluationError("csv output requires object rows; add a `select` or `transform` stage")
        for key in row:
            if key not in columns:
                columns.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(row.get(key)) for key in columns})
    return buffer.getvalue()


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def to_jsonable(value: Any) -> Any:
    """Convert a result value (pydantic models, dicts, lists, scalars) to JSON-serialisable data."""
    return _jsonable(value)


_EXT_FORMAT: dict[str, Literal["json", "ndjson", "csv"]] = {"json": "json", "ndjson": "ndjson", "csv": "csv"}


def write_rows(
    path: str, rows: list[Any], fmt: Literal["json", "ndjson", "csv"] | None = None, *, scalar: bool = False
) -> str:
    """Write rows to `path` as json/ndjson/csv (inferring the format from the extension when None)."""
    if fmt is None:
        extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        fmt = _EXT_FORMAT.get(extension, "json")
    return _write_file(FileSink(path=path, format=fmt), rows, scalar=scalar).path
