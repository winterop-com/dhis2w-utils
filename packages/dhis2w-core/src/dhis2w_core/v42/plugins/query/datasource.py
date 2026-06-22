"""DHIS2 data source for d2ql: fetch resource rows through the existing metadata service.

`Dhis2DataSource` declares filter/order/paging capabilities so the planner pushes those down; the
compiler renders them to DHIS2 list parameters. A field set extracted from the whole program is
requested so local stages can navigate nested paths (e.g. `categoryCombo.name`).
"""

from __future__ import annotations

from typing import Any

from dhis2w_ql import Library, NativeQuery, Pipeline, SourceCapabilities
from dhis2w_ql.ast import (
    ArrayExpr,
    BinaryExpr,
    CallExpr,
    Define,
    ExprSource,
    IndexExpr,
    MemberExpr,
    NameExpr,
    NameSource,
    ObjectExpr,
    UnaryExpr,
)
from pydantic import BaseModel

from dhis2w_core.profile import Profile
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
        """DHIS2 list endpoints support field filters, ordering, and paging."""
        return SourceCapabilities(filter=True, order=True, paging=True)

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


class Dhis2Binder:
    """Binds d2ql source names to DHIS2 resources (anything in the instance's resource catalog)."""

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


def collect_fields(library: Library) -> str | None:
    """Extract a DHIS2 `fields` selector covering every path the program navigates.

    Returns a comma-separated selector (e.g. `id,name,categoryCombo[name]`) so residual local
    stages can read nested values, or None to let the accessor use its default when no path is found.
    """
    paths: set[str] = {"id", "name"}
    for definition in library.definitions:
        if isinstance(definition, Define):
            _collect_pipeline(definition.body, paths)
        else:
            _collect_expr(definition.body, paths)
    if library.terminal is not None:
        _collect_pipeline(library.terminal, paths)
    return _render_fields(paths) or None


def _collect_pipeline(pipeline: Pipeline, paths: set[str]) -> None:
    source = pipeline.source
    if isinstance(source, NameSource) and source.inline_filter is not None:
        _collect_expr(source.inline_filter, paths)
    elif isinstance(source, ExprSource):
        _collect_expr(source.expr, paths)
    for stage in pipeline.stages:
        for attribute in ("predicate",):
            expr = getattr(stage, attribute, None)
            if expr is not None:
                _collect_expr(expr, paths)
        for select_item in getattr(stage, "items", []) or []:
            _collect_expr(select_item.expr, paths)
        template = getattr(stage, "template", None)
        if template is not None:
            _collect_expr(template, paths)
        for order_key in getattr(stage, "keys", []) or []:
            _collect_expr(order_key.expr, paths)


def _collect_expr(expr: Any, paths: set[str]) -> None:
    path = _path_of(expr)
    if path is not None:
        paths.add(path)
        return
    match expr:
        case MemberExpr():
            _collect_expr(expr.target, paths)
        case IndexExpr():
            _collect_expr(expr.target, paths)
            _collect_expr(expr.index, paths)
        case CallExpr():
            if expr.target is not None:
                _collect_expr(expr.target, paths)
            for argument in expr.args:
                _collect_expr(argument, paths)
        case UnaryExpr():
            _collect_expr(expr.operand, paths)
        case BinaryExpr():
            _collect_expr(expr.left, paths)
            _collect_expr(expr.right, paths)
        case ObjectExpr():
            for field in expr.fields:
                _collect_expr(field.value, paths)
        case ArrayExpr():
            for item in expr.items:
                _collect_expr(item, paths)
        case _:
            return


def _path_of(expr: Any) -> str | None:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, MemberExpr):
        base = _path_of(expr.target)
        return f"{base}.{expr.name}" if base is not None else None
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
