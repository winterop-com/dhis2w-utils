"""Execution-surface helpers for DHIS2 SqlView workflows.

`/api/sqlViews` exposes three kinds of saved SQL:

- `VIEW` — a standard SQL view, materialised in DHIS2's Postgres schema
  the first time it is executed.
- `MATERIALIZED_VIEW` — persisted result set; refreshable on demand via
  `POST /execute`.
- `QUERY` — stored SQL executed ad-hoc with optional `${var}` substitutions.

Generic CRUD is already covered by the generated accessor
(`client.resources.sql_views`). This module layers the workflow surface
that generic CRUD doesn't provide:

- `list_all()` — every SqlView with type + sqlQuery eagerly loaded.
- `get(uid)` — one view.
- `execute(uid, *, variables=..., criteria=...)` — run and return a
  typed `SqlViewResult` (columns + rows + title).
- `refresh(uid)` — materialised-view refresh + first-time VIEW creation.
- `create(sql_view)` / `delete(uid)` — so one-shot register-run-delete
  flows work without round-tripping the generic accessor.

Plus `SqlViewRunner` — a small facade for iterative SQL debugging:

- `run(uid, **variables)` — execute a saved view with keyword-style var
  substitutions.
- `adhoc(name, sql, **variables)` — register a throwaway SqlView,
  execute once, delete on the way out. Useful when iterating on SQL
  without littering the instance with test metadata.

`SqlViewResult` model:

    {
      "listGrid": {
        "title": ...,
        "subtitle": ...,
        "headers": [{"name": "column1", "type": "TEXT", ...}, ...],
        "rows": [[col1, col2, ...], ...],
        "height": N, "width": M
      }
    }

Rows are inherently schema-less (the SQL defines the columns), so
`rows: list[list[Any]]` is the canonical shape — the paired `columns`
list tells callers what each position means. `.as_dicts()` pivots into
column-name-keyed dicts when preferred.

BUGS.md-worthy behaviours to watch for:

- Variable and criteria values are sanitised server-side to alphanumeric
  characters only — wildcards and punctuation live in the SQL template,
  not the variable value (`'%${q}%'`, pass `q=abc`).
- `VIEW` and `MATERIALIZED_VIEW` creation happens lazily: first GET on
  `/data` creates the database object. Call `refresh(uid)` right after
  `create()` when you want the DB view to exist immediately.
- DHIS2's SQL allowlist blocks DELETE/UPDATE/INSERT/DROP/etc. For
  fully free-form queries, go around the allowlist with a direct
  Postgres connection (see the PG-injector example).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_client.generated.v41.enums import SqlViewType
from dhis2w_client.generated.v41.schemas import SqlView
from dhis2w_client.v41.envelopes import WebMessageResponse

if TYPE_CHECKING:
    from dhis2w_client.v41.client import Dhis2Client


_VIEW_FIELDS: str = "id,name,description,type,cacheStrategy,sqlQuery,lastUpdated"


class SqlViewColumn(BaseModel):
    """One column in a SqlView execution result — name + declared SQL type."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    column: str | None = None
    type: str | None = None
    meta: bool | None = None
    hidden: bool | None = None


class SqlViewResult(BaseModel):
    """Typed execution result from `/api/sqlViews/{uid}/data`."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: str | None = None
    subtitle: str | None = None
    columns: list[SqlViewColumn] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    height: int = 0
    width: int = 0

    @classmethod
    def from_api(cls, body: dict[str, Any]) -> SqlViewResult:
        """Parse DHIS2's `listGrid`-nested response envelope into a typed result."""
        grid_raw = body.get("listGrid")
        grid = grid_raw if isinstance(grid_raw, dict) else body
        header_rows = grid.get("headers") or []
        columns: list[SqlViewColumn] = []
        for header in header_rows:
            if isinstance(header, dict):
                columns.append(SqlViewColumn.model_validate(header))
        rows: list[list[Any]] = []
        for row in grid.get("rows") or []:
            if isinstance(row, list):
                rows.append(list(row))
        height = grid.get("height")
        width = grid.get("width")
        return cls(
            title=grid.get("title") if isinstance(grid.get("title"), str) else None,
            subtitle=grid.get("subtitle") if isinstance(grid.get("subtitle"), str) else None,
            columns=columns,
            rows=rows,
            height=int(height) if isinstance(height, int) else len(rows),
            width=int(width) if isinstance(width, int) else len(columns),
        )

    def as_dicts(self) -> list[dict[str, Any]]:
        """Pivot rows into column-name-keyed dicts — convenience for ad-hoc inspection.

        The raw `rows` attribute keeps DHIS2's positional shape (zero per-row
        allocation for streaming). Use this helper at the call site when you
        want name-keyed access; do not pass the dicts back across module
        boundaries — the typed model is the canonical form.
        """
        names = [column.name for column in self.columns]
        return [dict(zip(names, row, strict=False)) for row in self.rows]

    def column_values(self, column_name: str) -> list[Any]:
        """Pull one column out across every row — raises KeyError if unknown."""
        names = [column.name for column in self.columns]
        try:
            index = names.index(column_name)
        except ValueError as exc:
            raise KeyError(f"column {column_name!r} not in SqlViewResult ({names!r})") from exc
        return [row[index] if index < len(row) else None for row in self.rows]


class SqlViewsAccessor:
    """`Dhis2Client.sql_views` — execution + lifecycle helpers over DHIS2 SqlViews."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client — reuses its auth + HTTP pool."""
        self._client = client
        self.runner: SqlViewRunner = SqlViewRunner(self)

    async def list_all(self, *, view_type: SqlViewType | str | None = None) -> list[SqlView]:
        """List every SqlView, optionally filtered by type. Sorted by name."""
        filters: list[str] | None = None
        if view_type is not None:
            value = view_type.value if isinstance(view_type, SqlViewType) else view_type
            filters = [f"type:eq:{value}"]
        return cast(
            list[SqlView],
            await self._client.resources.sql_views.list(
                fields=_VIEW_FIELDS,
                filters=filters,
                order=["name:asc"],
                paging=False,
            ),
        )

    async def get(self, uid: str) -> SqlView:
        """Fetch one SqlView, including its `sqlQuery` text."""
        raw = await self._client.get_raw(f"/api/sqlViews/{uid}", params={"fields": _VIEW_FIELDS})
        return SqlView.model_validate(raw)

    async def execute(
        self,
        uid: str,
        *,
        variables: Mapping[str, str] | None = None,
        criteria: Mapping[str, str] | None = None,
    ) -> SqlViewResult:
        """Execute a SqlView and return its result grid.

        `variables` populate `${name}` placeholders on `QUERY` views —
        values are alphanumeric-only (DHIS2 strips punctuation server-side;
        keep wildcards in the SQL template).

        `criteria` filter the output of `VIEW` and `MATERIALIZED_VIEW`
        executions by column value. Passed as repeated `?criteria=col:val`
        query params.
        """
        params: list[tuple[str, str]] = []
        if variables:
            for key, value in variables.items():
                params.append(("var", f"{key}:{value}"))
        if criteria:
            for key, value in criteria.items():
                params.append(("criteria", f"{key}:{value}"))
        raw = await self._client.get_raw(f"/api/sqlViews/{uid}/data", params=dict(params) if params else None)
        return SqlViewResult.from_api(raw)

    async def refresh(self, uid: str) -> WebMessageResponse:
        """Refresh a `MATERIALIZED_VIEW` (or create a lazy `VIEW` on first call).

        DHIS2 creates the underlying Postgres view on the first execute
        call. Invoking this right after `create()` guarantees the view
        exists in the DB before any query hits `/data`.
        """
        raw = await self._client.post_raw(f"/api/sqlViews/{uid}/execute")
        return WebMessageResponse.model_validate(raw)

    async def create(self, sql_view: SqlView) -> SqlView:
        """POST a new SqlView; returns the created view with server-assigned metadata."""
        body = sql_view.model_dump(by_alias=True, exclude_none=True, mode="json")
        await self._client.post_raw("/api/sqlViews", body=body)
        if sql_view.id is None:
            raise ValueError("SqlView.id must be set for create() so the caller can round-trip the fetched model")
        return await self.get(sql_view.id)

    async def delete(self, uid: str) -> None:
        """DELETE a SqlView by UID. No-op return on success."""
        await self._client.resources.sql_views.delete(uid)


class SqlViewRunner:
    """Lightweight facade for interactive SQL view execution.

    The accessor (`client.sql_views`) is the full API. This runner wraps
    it with two debugging shortcuts:

    - `run(uid, **variables)` — execute a saved view, passing `${name}`
      substitutions as kwargs.
    - `adhoc(name, sql, **variables)` — register a throwaway SqlView,
      execute it once, delete it on the way out. Perfect for iterating
      on SQL without leaving test metadata behind.

    Use standalone: `runner = SqlViewRunner(client.sql_views)`, or
    reach it off the accessor: `runner = client.sql_views.runner`.
    """

    def __init__(self, accessor: SqlViewsAccessor) -> None:
        """Bind to the owning accessor — the runner delegates every call back."""
        self._accessor = accessor

    async def run(self, uid: str, **variables: str) -> SqlViewResult:
        """Execute a saved view by UID, passing `${name}` substitutions as kwargs."""
        return await self._accessor.execute(uid, variables=variables if variables else None)

    async def run_with_criteria(
        self,
        uid: str,
        *,
        criteria: Mapping[str, str],
        **variables: str,
    ) -> SqlViewResult:
        """Execute a saved view with both variable substitutions and column criteria."""
        return await self._accessor.execute(
            uid,
            variables=variables if variables else None,
            criteria=criteria,
        )

    async def adhoc(
        self,
        name: str,
        sql: str,
        *,
        view_type: SqlViewType | str = SqlViewType.QUERY,
        keep: bool = False,
        **variables: str,
    ) -> SqlViewResult:
        """Register a throwaway SqlView, execute it once, then delete it.

        Set `keep=True` to leave the view in place afterwards (handy when
        the next iteration wants to inspect it via the DHIS2 UI).

        Subject to the DHIS2 SQL allowlist — for fully free-form SQL, use
        the Postgres injector example instead.
        """
        from dhis2w_client.v41.uids import generate_uid

        candidate = SqlView.model_validate(
            {
                "id": generate_uid(),
                "name": name,
                "type": view_type.value if isinstance(view_type, SqlViewType) else view_type,
                "sqlQuery": sql,
            },
        )
        created = await self._accessor.create(candidate)
        if created.id is None:
            raise RuntimeError("adhoc create did not return a UID — server may have rejected the view")
        try:
            if created.type in (SqlViewType.VIEW, SqlViewType.MATERIALIZED_VIEW):
                await self._accessor.refresh(created.id)
            return await self._accessor.execute(created.id, variables=variables if variables else None)
        finally:
            if not keep:
                await self._accessor.delete(created.id)


__all__ = [
    "SqlViewColumn",
    "SqlViewResult",
    "SqlViewRunner",
    "SqlViewsAccessor",
]
