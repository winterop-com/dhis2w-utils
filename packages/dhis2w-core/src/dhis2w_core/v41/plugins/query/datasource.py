"""DHIS2 data source for d2ql: fetch resource rows through the existing metadata service.

`Dhis2DataSource` declares filter/order/paging capabilities so the planner pushes those down; the
compiler renders them to DHIS2 list parameters. A field set extracted from the whole program is
requested so local stages can navigate nested paths (e.g. `categoryCombo.name`).
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.v41 import Grid
from dhis2w_ql import Library, NativeQuery, Pipeline, SourceCapabilities
from dhis2w_ql.ast import (
    ArrayExpr,
    BinaryExpr,
    CallExpr,
    CallSource,
    Define,
    DefineFunction,
    ExprSource,
    IndexExpr,
    MemberExpr,
    NameExpr,
    NameSource,
    ObjectExpr,
    UnaryExpr,
    VariableExpr,
)
from pydantic import BaseModel

from dhis2w_core.profile import Profile
from dhis2w_core.v41.plugins.aggregate import service as aggregate_service
from dhis2w_core.v41.plugins.analytics import service as analytics_service
from dhis2w_core.v41.plugins.metadata import service as metadata_service
from dhis2w_core.v41.plugins.query.compiler import compile_filters, compile_order, resolve_paging


class Dhis2DataSource:
    """A d2ql data source backed by one DHIS2 metadata resource."""

    def __init__(self, profile: Profile, resource: str, fields: str | None) -> None:
        """Bind the profile, the DHIS2 resource name, and the field selector to request."""
        self._profile = profile
        self._resource = resource
        self._fields = fields

    def capabilities(self) -> SourceCapabilities:
        """DHIS2 list endpoints support field filters, ordering, and paging.

        Embedded structures (GeoJSON `geometry`, `attributeValues`, `translations`) are not
        filterable paths — DHIS2 answers `geometry.type` with `400 Unknown path property` (BUGS.md)
        — so predicates touching them stay local instead of pushing down.
        """
        return SourceCapabilities(
            filter=True,
            order=True,
            paging=True,
            non_pushable_paths=("geometry", "attributeValues", "translations"),
        )

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Fetch rows for the native query, dropping the leading `skip` rows locally."""
        filters = compile_filters(native) or None
        order = compile_order(native) or None
        page = resolve_paging(native)
        rows: list[BaseModel] = await metadata_service.list_metadata(
            self._profile,
            self._resource,
            fields=self._fields,
            filters=filters,
            root_junction=native.root_junction,
            order=order,
            page=1 if page.paged else None,
            page_size=page.page_size,
            paging=page.paged,
        )
        return list(rows[page.drop :]) if page.drop else list(rows)


class AnalyticsDataSource:
    """A d2ql call source backed by `/api/analytics`; rows are dicts keyed by dimension (dx/pe/ou/value)."""

    def __init__(self, profile: Profile, args: dict[str, Any]) -> None:
        """Hold the profile and the call arguments (analytics dimensions plus an optional filter)."""
        self._profile = profile
        self._args = args

    def capabilities(self) -> SourceCapabilities:
        """Analytics dimensions are supplied as call args, so no pipeline stage pushes down here."""
        return SourceCapabilities()

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Run the analytics query and return one dict per Grid row, keyed by dimension header."""
        dimensions = [f"{key}:{value}" for key, value in self._args.items() if key != "filter"]
        raw_filter = self._args.get("filter")
        filters = [str(raw_filter)] if raw_filter is not None else None
        grid = await analytics_service.query_analytics(self._profile, dimensions=dimensions, filters=filters)
        if not isinstance(grid, Grid):
            return []
        headers = [header.name for header in grid.headers or []]
        return [dict(zip(headers, row, strict=False)) for row in (grid.rows or [])]


class AggregateDataSource:
    """A d2ql call source backed by `/api/dataValueSets`; rows are typed `DataValue` models."""

    def __init__(self, profile: Profile, args: dict[str, Any]) -> None:
        """Hold the profile and the call arguments (dataSet / period / orgUnit)."""
        self._profile = profile
        self._args = args

    def capabilities(self) -> SourceCapabilities:
        """Data-value-set selection is supplied as call args, so no pipeline stage pushes down here."""
        return SourceCapabilities()

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Fetch the data value set and return its `DataValue` rows."""
        value_set = await aggregate_service.get_data_values(
            self._profile,
            data_set=self._args.get("dataSet"),
            period=self._args.get("period"),
            org_unit=self._args.get("orgUnit"),
        )
        return list(value_set.dataValues or [])


class Dhis2Binder:
    """Binds d2ql source names to DHIS2 resources and call sources (analytics, dataValues)."""

    def __init__(self, profile: Profile, resource_names: set[str], fields: str | None) -> None:
        """Hold the profile, the set of bindable resource names, and the shared field selector."""
        self._profile = profile
        self._resource_names = resource_names
        self._fields = fields

    def bind(self, name: str) -> Dhis2DataSource | None:
        """Return a data source for `name`, or None when it is not a DHIS2 resource."""
        if name not in self._resource_names:
            return None
        return Dhis2DataSource(self._profile, name, self._fields)

    def bind_call(self, name: str, args: dict[str, Any]) -> AnalyticsDataSource | AggregateDataSource | None:
        """Bind a call source: `analytics(...)` and `dataValues(...)`; None for anything else."""
        if name == "analytics":
            return AnalyticsDataSource(self._profile, args)
        if name == "dataValues":
            return AggregateDataSource(self._profile, args)
        return None


def collect_fields(library: Library, entry: Pipeline) -> str | None:
    """Extract the DHIS2 `fields` selector for the resource the `entry` pipeline binds.

    Walks only the definitions reachable from `entry` — its source `define` chain and the
    `define function`s it calls — so unused definitions and unrelated resources never contaminate
    the selector. A single execution binds one metadata resource, so the reachable navigations all
    apply to it. Returns a comma-separated selector (e.g. `id,name,categoryCombo[name]`), or None.
    """
    defines = {d.name: d for d in library.definitions if isinstance(d, Define)}
    functions = {f.name: f for f in library.definitions if isinstance(f, DefineFunction)}
    known = set(functions)
    paths: set[str] = {"id", "name"}
    seen_pipelines: set[int] = set()
    seen_functions: set[str] = set()

    def visit_function(name: str) -> None:
        if name in seen_functions or name not in functions:
            return
        seen_functions.add(name)
        function = functions[name]
        # A function's parameters bind to rows at call time, so `$param.field` is a row field path.
        _collect_expr(function.body, paths, {"this", *function.params})
        for called in _called_functions(function.body, known):
            visit_function(called)

    def visit_pipeline(pipeline: Pipeline) -> None:
        if id(pipeline) in seen_pipelines:
            return
        seen_pipelines.add(id(pipeline))
        _collect_pipeline(pipeline, paths)
        for name in _called_functions_in_pipeline(pipeline, known):
            visit_function(name)
        source = pipeline.source
        if isinstance(source, NameSource) and source.name in defines:
            visit_pipeline(defines[source.name].body)

    visit_pipeline(entry)
    return _render_fields(paths) or None


def _scan_calls(expr: Any, known: set[str], found: set[str]) -> None:
    match expr:
        case CallExpr():
            if expr.name in known:
                found.add(expr.name)
            if expr.target is not None:
                _scan_calls(expr.target, known, found)
            for argument in expr.args:
                _scan_calls(argument, known, found)
        case MemberExpr():
            _scan_calls(expr.target, known, found)
        case IndexExpr():
            _scan_calls(expr.target, known, found)
            _scan_calls(expr.index, known, found)
        case UnaryExpr():
            _scan_calls(expr.operand, known, found)
        case BinaryExpr():
            _scan_calls(expr.left, known, found)
            _scan_calls(expr.right, known, found)
        case ObjectExpr():
            for field in expr.fields:
                _scan_calls(field.value, known, found)
        case ArrayExpr():
            for item in expr.items:
                _scan_calls(item, known, found)
        case _:
            return


def _called_functions(expr: Any, known: set[str]) -> set[str]:
    found: set[str] = set()
    _scan_calls(expr, known, found)
    return found


def _called_functions_in_pipeline(pipeline: Pipeline, known: set[str]) -> set[str]:
    found: set[str] = set()
    source = pipeline.source
    if isinstance(source, NameSource) and source.inline_filter is not None:
        _scan_calls(source.inline_filter, known, found)
    elif isinstance(source, ExprSource):
        _scan_calls(source.expr, known, found)
    elif isinstance(source, CallSource):
        for argument in source.args:
            _scan_calls(argument.value, known, found)
    for stage in pipeline.stages:
        for attribute in ("predicate", "group"):
            expr = getattr(stage, attribute, None)
            if expr is not None:
                _scan_calls(expr, known, found)
        for select_item in getattr(stage, "items", []) or []:
            _scan_calls(select_item.expr, known, found)
        for container in ("template", "aggregations"):
            built = getattr(stage, container, None)
            if built is not None:
                _scan_calls(built, known, found)
        for order_key in getattr(stage, "keys", []) or []:
            _scan_calls(order_key.expr, known, found)
    return found


def _collect_pipeline(pipeline: Pipeline, paths: set[str]) -> None:
    # `$this` is the current row in per-row stages; `$rows` is the stream inside `fold`. Both are
    # row-bound, so `$rows.dataSetElements.dataElement` collects the same field paths as bare navigation.
    row_vars = {"this", "rows"}
    source = pipeline.source
    if isinstance(source, NameSource) and source.inline_filter is not None:
        _collect_expr(source.inline_filter, paths, row_vars)
    elif isinstance(source, ExprSource):
        _collect_expr(source.expr, paths, row_vars)
    for stage in pipeline.stages:
        for attribute in ("predicate", "group"):
            expr = getattr(stage, attribute, None)
            if expr is not None:
                _collect_expr(expr, paths, row_vars)
        for select_item in getattr(stage, "items", []) or []:
            _collect_expr(select_item.expr, paths, row_vars)
        for container in ("template", "aggregations"):
            built = getattr(stage, container, None)
            if built is not None:
                _collect_expr(built, paths, row_vars)
        for order_key in getattr(stage, "keys", []) or []:
            _collect_expr(order_key.expr, paths, row_vars)


def _collect_expr(expr: Any, paths: set[str], row_vars: set[str]) -> None:
    path = _path_of(expr, row_vars)
    if path is not None:
        if path:
            paths.add(path)
        return
    match expr:
        case MemberExpr():
            _collect_expr(expr.target, paths, row_vars)
        case IndexExpr():
            _collect_expr(expr.target, paths, row_vars)
            _collect_expr(expr.index, paths, row_vars)
        case CallExpr():
            # A method on a field path (e.g. `options.select({ code: code })`, `options.where(...)`)
            # navigates the element, so its argument field paths belong under the target path.
            target = expr.target
            target_path = _path_of(target, row_vars) if target is not None else None
            if target is not None and target_path is None:
                _collect_expr(target, paths, row_vars)
            elif target_path:
                paths.add(target_path)
            for argument in expr.args:
                if target_path:
                    nested: set[str] = set()
                    _collect_expr(argument, nested, {"this"})
                    paths.update(f"{target_path}.{path}" for path in nested)
                else:
                    _collect_expr(argument, paths, row_vars)
        case UnaryExpr():
            _collect_expr(expr.operand, paths, row_vars)
        case BinaryExpr():
            _collect_expr(expr.left, paths, row_vars)
            if expr.op != "is":  # the right side of `is` is a type name, not a field path
                _collect_expr(expr.right, paths, row_vars)
        case ObjectExpr():
            for field in expr.fields:
                _collect_expr(field.value, paths, row_vars)
        case ArrayExpr():
            for item in expr.items:
                _collect_expr(item, paths, row_vars)
        case _:
            return


def _path_of(expr: Any, row_vars: set[str]) -> str | None:
    """Return the dotted field path for an expression, or None when it is not a field path.

    A row-bound variable (`$this`, a function parameter) resolves to the row root (empty string),
    so `$this.categoryCombo.name` and `$de.valueType` yield the same paths as bare navigation.
    """
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, VariableExpr):
        return "" if expr.name in row_vars else None
    if isinstance(expr, MemberExpr):
        base = _path_of(expr.target, row_vars)
        if base is None:
            return None
        return expr.name if base == "" else f"{base}.{expr.name}"
    return None


def _render_fields(paths: set[str]) -> str:
    tree: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        node = tree
        for segment in path.split("."):
            node = node.setdefault(segment, {})
    return _render_tree(tree)


def _render_tree(tree: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for name, children in tree.items():
        parts.append(f"{name}[{_render_tree(children)}]" if children else name)
    return ",".join(parts)
