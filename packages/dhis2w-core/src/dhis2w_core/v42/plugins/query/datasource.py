"""DHIS2 data source for d2ql: fetch resource rows through the existing metadata service.

`Dhis2DataSource` declares filter/order/paging capabilities so the planner pushes those down; the
compiler renders them to DHIS2 list parameters. A field set extracted from the whole program is
requested so local stages can navigate nested paths (e.g. `categoryCombo.name`).
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.v42 import Grid
from dhis2w_ql import Library, NativeQuery, Pipeline, SourceCapabilities
from dhis2w_ql.ast import (
    ArrayExpr,
    BinaryExpr,
    CallExpr,
    Define,
    DefineFunction,
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
from dhis2w_core.v42.plugins.aggregate import service as aggregate_service
from dhis2w_core.v42.plugins.analytics import service as analytics_service
from dhis2w_core.v42.plugins.metadata import service as metadata_service
from dhis2w_core.v42.plugins.query.compiler import compile_filters, compile_order, resolve_paging


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

    async def count(self, native: NativeQuery) -> int:
        """Count matching rows via DHIS2's pager total — no rows fetched (the `count` fast-path)."""
        filters = compile_filters(native) or None
        return await metadata_service.count_metadata(
            self._profile, self._resource, filters=filters, root_junction=native.root_junction
        )


# Analytics option args carried as named call args, mapped to `query_analytics` kwargs. Anything not
# listed here (and not `filter`) is an analytics dimension (`dx`/`pe`/`ou`/`co`/UID), rendered `key:value`.
_ANALYTICS_STR_OPTIONS = {
    "aggregationType": "aggregation_type",
    "measureCriteria": "measure_criteria",
    "outputIdScheme": "output_id_scheme",
    "displayProperty": "display_property",
    "startDate": "start_date",
    "endDate": "end_date",
    "relativePeriodDate": "relative_period_date",
}
_ANALYTICS_BOOL_OPTIONS = {"skipMeta": "skip_meta", "skipData": "skip_data", "includeNumDen": "include_num_den"}


def _as_bool(value: Any) -> bool:
    """Coerce a call-arg value to bool, accepting the d2ql `true`/`false` literal or string forms."""
    return value if isinstance(value, bool) else str(value).strip().lower() in {"true", "1", "yes"}


class AnalyticsDataSource:
    """A d2ql call source backed by `/api/analytics`; rows are dicts keyed by dimension (dx/pe/ou/value)."""

    def __init__(self, profile: Profile, args: dict[str, Any]) -> None:
        """Hold the profile and the call arguments (analytics dimensions, options, and an optional filter)."""
        self._profile = profile
        self._args = args

    def capabilities(self) -> SourceCapabilities:
        """Analytics dimensions are supplied as call args, so no pipeline stage pushes down here."""
        return SourceCapabilities()

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Run the analytics query and return one dict per Grid row, keyed by dimension header.

        Named call args split into analytics options (a known set, routed to the matching query
        params) and dimensions (everything else, rendered `key:value`); `filter` stays a filter.
        """
        dimensions: list[str] = []
        filters: list[str] | None = None
        options: dict[str, Any] = {}
        for key, value in self._args.items():
            if key == "filter":
                filters = [str(value)]
            elif key in _ANALYTICS_STR_OPTIONS:
                options[_ANALYTICS_STR_OPTIONS[key]] = str(value)
            elif key in _ANALYTICS_BOOL_OPTIONS:
                options[_ANALYTICS_BOOL_OPTIONS[key]] = _as_bool(value)
            else:
                dimensions.append(f"{key}:{value}")
        grid = await analytics_service.query_analytics(self._profile, dimensions=dimensions, filters=filters, **options)
        if not isinstance(grid, Grid):
            return []
        headers = [header.name for header in grid.headers or []]
        return [dict(zip(headers, row, strict=False)) for row in (grid.rows or [])]


class AggregateDataSource:
    """A d2ql call source backed by `/api/dataValueSets`; rows are typed `DataValue` models."""

    def __init__(self, profile: Profile, args: dict[str, Any]) -> None:
        """Hold the profile and the call arguments (dataSet/period/orgUnit/startDate/endDate/...)."""
        self._profile = profile
        self._args = args

    def capabilities(self) -> SourceCapabilities:
        """Data-value-set selection is supplied as call args, so no pipeline stage pushes down here."""
        return SourceCapabilities()

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Fetch the data value set (honouring every selection arg) and return its `DataValue` rows."""
        limit = self._args.get("limit")
        value_set = await aggregate_service.get_data_values(
            self._profile,
            data_set=self._str("dataSet"),
            period=self._str("period"),
            org_unit=self._str("orgUnit"),
            org_unit_group=self._str("orgUnitGroup"),
            start_date=self._str("startDate"),
            end_date=self._str("endDate"),
            children=_as_bool(self._args.get("children", False)),
            data_element_group=self._str("dataElementGroup"),
            include_deleted=_as_bool(self._args.get("includeDeleted", False)),
            last_updated=self._str("lastUpdated"),
            limit=int(limit) if limit is not None else None,
        )
        return list(value_set.dataValues or [])

    def _str(self, key: str) -> str | None:
        """Return a call argument as a string, or None when it was not supplied."""
        value = self._args.get(key)
        return str(value) if value is not None else None


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


_RESHAPING_STAGES = frozenset({"select", "transform", "aggregate", "fold", "count"})
_ELEMENT_PRESERVING = frozenset({"where", "first", "last", "tail", "skip", "take", "distinct", "single"})


def collect_fields(library: Library, entry: Pipeline) -> str | None:
    """Extract the DHIS2 `fields` selector for the resource the `entry` pipeline binds.

    Walks only the definitions reachable from `entry` (its source `define` chain + the functions it
    calls), and only while rows are still resource-shaped — collection stops after the first
    reshaping stage (`select`/`transform`/`group by`/`fold`/`count`), because later stages reference
    the new shape (aliases), not DHIS2 fields. A single execution binds one resource, so the
    reachable navigations all apply to it. Returns e.g. `id,name,categoryCombo[name]`, or None.
    """
    defines = {d.name: d for d in library.definitions if isinstance(d, Define)}
    functions = {f.name: f for f in library.definitions if isinstance(f, DefineFunction)}
    known = set(functions)
    paths: set[str] = {"id", "name"}
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

    def collect_from(expr: Any) -> None:
        _collect_expr(expr, paths, {"this", "rows"})
        for name in _called_functions(expr, known):
            visit_function(name)

    def visit_pipeline(pipeline: Pipeline, seen: set[int]) -> bool:
        """Collect resource-shaped navigations; return whether the pipeline's output stays resource-shaped."""
        if id(pipeline) in seen:
            return False
        seen.add(id(pipeline))
        source = pipeline.source
        if isinstance(source, NameSource) and source.name in defines:
            shaped = visit_pipeline(defines[source.name].body, seen)
        elif isinstance(source, NameSource):  # a DHIS2 resource — rows start resource-shaped
            shaped = True
            if source.inline_filter is not None:
                collect_from(source.inline_filter)
        else:  # read / expr / call source — not a DHIS2 metadata resource
            shaped = False
        for stage in pipeline.stages:
            if shaped:
                for expr in _stage_exprs(stage):
                    collect_from(expr)
            if stage.kind in _RESHAPING_STAGES:
                shaped = False
        return shaped

    if visit_pipeline(entry, set()):
        # The output stays resource-shaped (no select/transform/group/fold/count narrows it), so the
        # consumer sees whole rows — fetch every field, not just the navigated ones.
        paths.add("*")
    return _render_fields(paths) or None


def _stage_exprs(stage: Any) -> list[Any]:
    exprs: list[Any] = []
    for attribute in ("predicate", "group"):
        expr = getattr(stage, attribute, None)
        if expr is not None:
            exprs.append(expr)
    exprs.extend(item.expr for item in getattr(stage, "items", []) or [])
    for container in ("template", "aggregations"):
        built = getattr(stage, container, None)
        if built is not None:
            exprs.append(built)
    exprs.extend(key.expr for key in getattr(stage, "keys", []) or [])
    return exprs


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


def _collect_expr(expr: Any, paths: set[str], row_vars: set[str]) -> None:
    # A navigation chain (members + element-preserving methods like `where`/`first`) resolves to a
    # single field path; `_nav_path` returns it and collects any method arguments along the way.
    path = _nav_path(expr, paths, row_vars)
    if path is not None:
        if path:
            paths.add(path)
        else:
            paths.add("*")  # a bare whole-row reference ($this/$rows/$param) needs every field
        return
    match expr:
        case MemberExpr():
            _collect_expr(expr.target, paths, row_vars)
        case IndexExpr():
            _collect_expr(expr.target, paths, row_vars)
            _collect_expr(expr.index, paths, row_vars)
        case CallExpr():
            # A type-changing method on a field path (e.g. `options.select({ code: code })`):
            # its argument field paths describe the projected element, so they live under the target.
            target = expr.target
            target_path = _nav_path(target, paths, row_vars) if target is not None else None
            if target is not None and target_path is None:
                _collect_expr(target, paths, row_vars)
            narrowed = False
            for argument in expr.args:
                if target_path is not None:
                    nested: set[str] = set()
                    _collect_expr(argument, nested, {"this"})
                    if nested:
                        paths.update(f"{target_path}.{path}" if target_path else path for path in nested)
                        narrowed = True
                elif isinstance(argument, VariableExpr) and argument.name in row_vars:
                    # A whole row passed to a function (`isNum($this)`) — the function body, walked
                    # separately, determines the fields it needs; don't treat it as whole-row output.
                    continue
                else:
                    _collect_expr(argument, paths, row_vars)
            if target_path and not narrowed:
                # The method does not narrow to specific subfields, so the whole element is needed.
                paths.add(target_path)
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


def _nav_path(expr: Any, paths: set[str], row_vars: set[str]) -> str | None:
    """Resolve a navigation chain to its field path, collecting any method arguments as nested paths.

    A row-bound variable (`$this`, `$rows`, a function parameter) is the row root (empty string).
    Element-preserving methods (`where`/`first`/`last`/…) keep the element type, so a member after
    them belongs to the same path and their arguments (e.g. `where(code = "A")`) collect under it.
    Returns None when the expression is not a pure navigation (e.g. a `select`, a free function).
    """
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, VariableExpr):
        return "" if expr.name in row_vars else None
    if isinstance(expr, MemberExpr):
        base = _nav_path(expr.target, paths, row_vars)
        if base is None:
            return None
        return expr.name if base == "" else f"{base}.{expr.name}"
    if isinstance(expr, CallExpr) and expr.target is not None and expr.name in _ELEMENT_PRESERVING:
        base = _nav_path(expr.target, paths, row_vars)
        if base is None:
            return None
        for argument in expr.args:
            nested: set[str] = set()
            _collect_expr(argument, nested, {"this"})
            paths.update(f"{base}.{path}" if base else path for path in nested)
        return base
    return None


def _render_fields(paths: set[str]) -> str:
    # `*` (whole row) subsumes every top-level field; keep only explicit nested expansions beside it.
    if "*" in paths:
        nested = {path for path in paths if "." in path}
        groups = _render_tree(_build_tree(nested), "", nested)
        return "*" + (f",{groups}" if groups else "")
    return _render_tree(_build_tree(paths), "", paths)


def _build_tree(paths: set[str]) -> dict[str, dict[str, Any]]:
    tree: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        node = tree
        for segment in path.split("."):
            node = node.setdefault(segment, {})
    return tree


def _render_tree(tree: dict[str, dict[str, Any]], prefix: str, whole: set[str]) -> str:
    parts: list[str] = []
    for name, children in tree.items():
        full = f"{prefix}.{name}" if prefix else name
        # If the whole object was navigated (its exact path was collected), fetch all of it — a
        # descendant like `geometry.type` must not narrow a whole `geometry` (which needs coordinates).
        if not children or full in whole:
            parts.append(name)
        else:
            parts.append(f"{name}[{_render_tree(children, full, whole)}]")
    return ",".join(parts)
