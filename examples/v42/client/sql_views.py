"""SqlView execution walkthrough — `client.sql_views` end-to-end.

Covers every method on `SqlViewsAccessor`:

1. `list_all()` — catalog every view with type + description.
2. `get(uid)` — one view including its stored `sqlQuery`.
3. `execute(uid, variables=..., criteria=...)` — run and parse the
   `listGrid` response into a typed `SqlViewResult` (columns + rows).
4. `refresh(uid)` — force a MATERIALIZED_VIEW re-run (or create a
   lazy VIEW's DB object on first call).
5. `create(sql_view)` / `delete(uid)` — lifecycle helpers.

The seeded maternal stack exposes three SqlViews — one of each type
(`SqvOuLvl001` VIEW, `SqvDeByNm01` QUERY, `SqvDeVtMV01` MATERIALIZED_VIEW).

Usage:
    uv run python examples/v42/client/sql_views.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

OU_LEVEL_VIEW = "SqvOuLvl001"
DE_BY_NAME_QUERY = "SqvDeByNm01"
DE_VALUETYPE_MV = "SqvDeVtMV01"


async def main() -> None:
    """Walk every SqlViewsAccessor method against the seeded views."""
    async with open_client(profile_from_env()) as client:
        views = await client.sql_views.list_all()
        print(f"[list_all] {len(views)} views on the instance:")
        for view in views:
            print(f"  {view.id}  type={view.type}  {view.name!r}")

        one = await client.sql_views.get(OU_LEVEL_VIEW)
        print(f"\n[get {OU_LEVEL_VIEW}] name={one.name!r}  type={one.type}")
        if one.sqlQuery:
            print(f"  sqlQuery: {one.sqlQuery.splitlines()[0]} ...")

        # Plain execution of a VIEW — server returns a `listGrid` with two
        # columns (level, count) and one row per hierarchy depth.
        result = await client.sql_views.execute(OU_LEVEL_VIEW)
        print(
            f"\n[execute {OU_LEVEL_VIEW}] {[c.name for c in result.columns]} x {result.height} rows",
        )
        for row in result.as_dicts():
            print(f"  {row}")

        # QUERY view with `${pattern}` variable substitution. DHIS2 sanitises
        # the value to alphanumerics — wildcards belong in the SQL template.
        search = await client.sql_views.execute(
            DE_BY_NAME_QUERY,
            variables={"pattern": "anc"},
        )
        print(f"\n[execute {DE_BY_NAME_QUERY} pattern=anc] {search.height} matches")
        for positional_row in search.rows[:5]:
            print(f"  {positional_row}")

        # MATERIALIZED_VIEW refresh — re-runs the underlying SQL. For plain
        # VIEW types the first call creates the DB view; subsequent calls
        # are no-ops.
        refresh = await client.sql_views.refresh(DE_VALUETYPE_MV)
        print(f"\n[refresh {DE_VALUETYPE_MV}] status={refresh.status}")

        # After refresh, read the materialised rows.
        mv_result = await client.sql_views.execute(DE_VALUETYPE_MV)
        print(f"[execute {DE_VALUETYPE_MV}] {mv_result.height} value-type buckets")
        for row in mv_result.as_dicts():
            print(f"  {row}")


if __name__ == "__main__":
    run_example(main)
