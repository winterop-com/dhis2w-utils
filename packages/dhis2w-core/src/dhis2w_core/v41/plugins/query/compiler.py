"""Compile a d2ql `NativeQuery` into DHIS2 metadata list parameters (filters, order, paging).

The DHIS2 list endpoint applies `filter` -> `order` -> paging, which is exactly the order the d2ql
planner pushes stages in, so the compiled request is semantically equivalent to the pushed-down
prefix of the pipeline. Paging has no offset, so `skip`/`limit` resolve to a first-page fetch whose
size covers `skip + limit`; the data source then drops the first `skip` rows locally.
"""

from __future__ import annotations

from typing import Any

from dhis2w_ql import NativeFilter, NativeQuery
from pydantic import BaseModel, ConfigDict


class PageSpec(BaseModel):
    """How to page a native fetch: a first-page size to request, then rows to drop locally."""

    model_config = ConfigDict(frozen=True)

    paged: bool
    page_size: int | None = None
    drop: int = 0


def compile_filters(native: NativeQuery) -> list[str]:
    """Render each native filter as a DHIS2 `property:operator:value` clause."""
    return [_render_filter(native_filter) for native_filter in native.filters]


def compile_order(native: NativeQuery) -> list[str]:
    """Render each native sort key as a DHIS2 `property:asc|desc` clause."""
    return [f"{key.property}:{'desc' if key.descending else 'asc'}" for key in native.order]


def resolve_paging(native: NativeQuery) -> PageSpec:
    """Resolve `skip`/`limit` into a first-page fetch size plus a local drop count."""
    skip = native.skip or 0
    if native.limit is None and skip == 0:
        return PageSpec(paged=False)
    page_size = skip + native.limit if native.limit is not None else None
    if page_size is None:
        return PageSpec(paged=False, drop=skip)
    return PageSpec(paged=True, page_size=page_size, drop=skip)


def _render_filter(native_filter: NativeFilter) -> str:
    if native_filter.operator == "in":
        members = native_filter.value if isinstance(native_filter.value, list) else [native_filter.value]
        rendered = ",".join(_scalar(member) for member in members)
        return f"{native_filter.property}:in:[{rendered}]"
    return f"{native_filter.property}:{native_filter.operator}:{_scalar(native_filter.value)}"


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
