"""`SqlViewRunner` — fast iteration on SQL against a live DHIS2 instance.

Three ways to use the runner:

1. `runner.run(uid, **variables)` — execute a saved view with keyword-style
   variable substitutions. Thin shortcut over `accessor.execute`.
2. `runner.run_with_criteria(uid, criteria=..., **variables)` — same but
   also applies VIEW / MATERIALIZED_VIEW column filters.
3. `runner.adhoc(name, sql, **variables)` — register a throwaway SqlView,
   execute once, and delete on the way out. Pass `keep=True` to leave it
   in place afterwards.

Use standalone or via the accessor:

    runner = client.sql_views.runner          # reach via accessor
    runner = SqlViewRunner(client.sql_views)  # construct directly

Subject to DHIS2's SQL allowlist — `DELETE`, `UPDATE`, `INSERT`, `DROP`,
etc. are rejected server-side. For fully free-form queries, go through a
direct Postgres connection (separate example forthcoming).

Usage:
    uv run python examples/v42/client/sql_view_runner.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

DE_BY_NAME_QUERY = "SqvDeByNm01"
OU_LEVEL_VIEW = "SqvOuLvl001"


async def main() -> None:
    """Drive SqlViewRunner through every shape of saved + ad-hoc execution."""
    async with open_client(profile_from_env()) as client:
        runner = client.sql_views.runner  # same object as SqlViewRunner(client.sql_views)
        # `client.sql_views.runner` is the per-version class; top-level `SqlViewRunner` import resolves to v42

        # --- saved QUERY view, keyword-style variable substitution ----------
        print(f"[run {DE_BY_NAME_QUERY} pattern=visit]")
        result = await runner.run(DE_BY_NAME_QUERY, pattern="visit")
        for row in result.as_dicts():
            print(f"  {row}")

        # --- saved VIEW with column criteria --------------------------------
        print(f"\n[run_with_criteria {OU_LEVEL_VIEW} level=3]")
        filtered = await runner.run_with_criteria(OU_LEVEL_VIEW, criteria={"level": "3"})
        for positional_row in filtered.rows:
            print(f"  {positional_row}")

        # --- adhoc: a throwaway QUERY view ----------------------------------
        # Register, execute, delete — no metadata lingers on the instance.
        adhoc = await runner.adhoc(
            "probe: average OU depth",
            """
            SELECT AVG(hierarchylevel::numeric) AS "avg_depth",
                   MAX(hierarchylevel)          AS "max_depth"
            FROM organisationunit
            """,
        )
        print(f"\n[adhoc avg OU depth] {adhoc.as_dicts()}")

        # --- adhoc with variables + keep=True -------------------------------
        # `keep=True` leaves the view in place so you can inspect it in the
        # UI between iterations. The example pre-cleans any view with the
        # same name (DHIS2 SqlView names are UNIQUE) + explicitly deletes
        # it again afterwards so reruns stay idempotent.
        kept_name = "probe: DE search (kept)"
        for existing in await client.sql_views.list_all():
            if existing.name == kept_name and existing.id:
                await client.sql_views.delete(existing.id)
                print(f"[pre-clean] removed stale {existing.id} ({kept_name!r})")
        kept = await runner.adhoc(
            kept_name,
            "SELECT name, valuetype FROM dataelement WHERE LOWER(name) LIKE LOWER('%${q}%')",
            q="anc",
            keep=True,
        )
        print(f"\n[adhoc DE search keep=True] {kept.height} rows — kept on instance for inspection")

        # Idempotent cleanup — find the view we kept and delete it.
        for view in await client.sql_views.list_all():
            if view.name == kept_name and view.id:
                await client.sql_views.delete(view.id)
                print(f"[cleanup] deleted {view.id}")


if __name__ == "__main__":
    run_example(main)
