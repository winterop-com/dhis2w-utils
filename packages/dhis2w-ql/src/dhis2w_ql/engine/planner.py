"""The planner: split a pipeline's stages into a native-pushdown prefix and a local residual.

Pushdown is conservative and always correctness-preserving: a contiguous leading run of `where`
stages folds into native filters, followed by an optional `order`, then `skip`, then `limit` — the
exact order the DHIS2 list endpoint applies them (filter -> order -> paging). The first stage that
cannot be expressed natively, and everything after it, becomes the local residual.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from dhis2w_ql.ast import (
    ArrayExpr,
    BinaryExpr,
    Expr,
    LimitStage,
    LiteralExpr,
    MemberExpr,
    NameExpr,
    OrderKey,
    OrderStage,
    SkipStage,
    Stage,
    WhereStage,
)
from dhis2w_ql.engine.plan import NativeFilter, NativeOrder, NativeQuery, QueryPlan, SourceCapabilities


class _CompiledClause(BaseModel):
    """A single `where` predicate compiled to native filters joined by one junction."""

    model_config = ConfigDict(frozen=True)

    filters: list[NativeFilter]
    junction: Literal["AND", "OR"]


class _PagingPushdown(BaseModel):
    """The order/skip/limit a planner pushed down, plus the index where residual stages begin."""

    model_config = ConfigDict(frozen=True)

    order: list[NativeOrder]
    skip: int | None
    limit: int | None
    next_index: int


_COMPARISON_OPS: dict[str, Literal["eq", "ne", "ilike", "gt", "ge", "lt", "le"]] = {
    "=": "eq",
    "!=": "ne",
    "~": "ilike",
    ">": "gt",
    ">=": "ge",
    "<": "lt",
    "<=": "le",
}


def plan_pipeline(resource: str, capabilities: SourceCapabilities, stages: list[Stage]) -> QueryPlan:
    """Split `stages` into a `NativeQuery` (pushed down) and a residual list (run locally)."""
    filters: list[NativeFilter] = []
    root_junction: Literal["AND", "OR"] = "AND"
    index = 0

    while index < len(stages) and capabilities.filter:
        stage = stages[index]
        if not isinstance(stage, WhereStage):
            break
        compiled = _compile_predicate(stage.predicate)
        if compiled is None:
            break
        if compiled.junction == "OR" and len(compiled.filters) > 1:
            if filters:
                break  # cannot AND an OR-group onto already-collected filters
            filters, root_junction = compiled.filters, "OR"
            index += 1
            break  # a pushed OR-group cannot be combined with further AND'd where stages
        filters.extend(compiled.filters)
        index += 1

    paging = _consume_paging(stages, index, capabilities)
    native = NativeQuery(
        resource=resource,
        filters=filters,
        root_junction=root_junction,
        order=paging.order,
        skip=paging.skip,
        limit=paging.limit,
    )
    return QueryPlan(native=native, residual=list(stages[paging.next_index :]))


def _consume_paging(stages: list[Stage], start: int, capabilities: SourceCapabilities) -> _PagingPushdown:
    order: list[NativeOrder] = []
    skip: int | None = None
    limit: int | None = None
    seen_order = seen_skip = seen_limit = False
    index = start
    while index < len(stages):
        stage = stages[index]
        if isinstance(stage, OrderStage) and capabilities.order and not (seen_order or seen_skip or seen_limit):
            keys = _compile_order(stage.keys)
            if keys is None:
                break
            order, seen_order = keys, True
        elif isinstance(stage, SkipStage) and capabilities.paging and not (seen_skip or seen_limit):
            skip, seen_skip = stage.count, True
        elif isinstance(stage, LimitStage) and capabilities.paging and not seen_limit:
            limit, seen_limit = stage.count, True
        else:
            break
        index += 1
    return _PagingPushdown(order=order, skip=skip, limit=limit, next_index=index)


def _compile_order(keys: list[OrderKey]) -> list[NativeOrder] | None:
    compiled: list[NativeOrder] = []
    for key in keys:
        path = _field_path(key.expr)
        if path is None:
            return None
        compiled.append(NativeOrder(property=path, descending=key.descending))
    return compiled


def _compile_predicate(expr: Expr) -> _CompiledClause | None:
    if isinstance(expr, BinaryExpr) and expr.op in ("and", "or"):
        left = _compile_predicate(expr.left)
        right = _compile_predicate(expr.right)
        if left is None or right is None:
            return None
        junction: Literal["AND", "OR"] = "AND" if expr.op == "and" else "OR"
        for side in (left, right):
            if side.junction != junction and len(side.filters) > 1:
                return None  # mixed AND/OR cannot be a flat native filter list
        return _CompiledClause(filters=left.filters + right.filters, junction=junction)
    single = _compile_comparison(expr)
    return _CompiledClause(filters=[single], junction="AND") if single is not None else None


def _compile_comparison(expr: Expr) -> NativeFilter | None:
    if not isinstance(expr, BinaryExpr):
        return None
    path = _field_path(expr.left)
    if path is None:
        return None
    if expr.op == "in":
        values = _array_literal(expr.right)
        return NativeFilter(property=path, operator="in", value=values) if values is not None else None
    operator = _COMPARISON_OPS.get(expr.op)
    if operator is None or not isinstance(expr.right, LiteralExpr) or expr.right.literal_type == "null":
        return None
    return NativeFilter(property=path, operator=operator, value=expr.right.value)


def _field_path(expr: Expr) -> str | None:
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, MemberExpr):
        parent = _field_path(expr.target)
        return f"{parent}.{expr.name}" if parent is not None else None
    return None


def _array_literal(expr: Expr) -> list[object] | None:
    if not isinstance(expr, ArrayExpr):
        return None
    values: list[object] = []
    for item in expr.items:
        if not isinstance(item, LiteralExpr) or item.literal_type == "null":
            return None
        values.append(item.value)
    return values
