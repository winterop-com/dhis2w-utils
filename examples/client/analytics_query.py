"""Analytics queries (typed `Grid`) + resource-table refresh via task-awaiter.

Two things:
  1. Query `/api/analytics` via the typed service layer — returns a `Grid`
     with `headers: list[GridHeader]`, `rows: list[list[Any]]`, and
     `metaData: dict[str, Any]`. Callers who want structured metadata
     (`{items, dimensions}`) lift it via `AnalyticsMetaData.model_validate`.
  2. Trigger `/api/resourceTables/analytics` and poll the background
     job via `client.tasks.await_completion` — beats manually polling
     `/api/system/tasks/ANALYTICS_TABLE/<id>`.

Usage:
    uv run python examples/client/analytics_query.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import AnalyticsMetaData, Grid
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.analytics import service as analytics_service
from dhis2w_core.v42.plugins.maintenance import service as maintenance_service


async def main() -> None:
    """Run an aggregated analytics query, then trigger + await a resource-table refresh."""
    profile = profile_from_env()

    # Penta1 doses given across all 4 Sierra Leone districts for the last 12 months.
    # dx = data element / indicator, pe = period, ou = org unit.
    response = await analytics_service.query_analytics(
        profile,
        dimensions=[
            "dx:fClA2Erf6IO;UOlfIjgN8X6",
            "pe:LAST_12_MONTHS",
            "ou:ImspTQPwCqd;LEVEL-2",
        ],
        skip_meta=False,  # keep the metaData block so the AnalyticsMetaData demo lands.
    )
    # `query_analytics` returns `Grid | DataValueSet` depending on the `shape`
    # argument; default `shape="table"` gives us a Grid. Narrow explicitly
    # so the typed accessors below are safe.
    assert isinstance(response, Grid), "expected Grid envelope from the default shape"
    grid = response

    headers = [h.name for h in grid.headers or []]
    rows = grid.rows or []
    print(f"analytics: {len(rows)} rows × {len(headers)} columns")
    print(f"  headers: {headers}")
    for row in rows[:5]:
        print(f"  {row}")

    # Optional: lift `Grid.metaData` (a bare dict on the wire) into a typed
    # helper when you need to walk `dimensions` / `items`.
    if grid.metaData:
        typed_meta = AnalyticsMetaData.model_validate(grid.metaData)
        print(
            f"\n  metaData.dimensions.dx = {typed_meta.dimensions.get('dx', [])}\n"
            f"  metaData.items sample  = {next(iter(typed_meta.items.items()), None)}"
        )

    # Trigger + await the analytics-table refresh via the maintenance service wrapper.
    envelope = await maintenance_service.refresh_analytics(profile, last_years=1)
    task_ref = envelope.task_ref()
    if task_ref is None:
        print("\n(no task ref in refresh response — skipping await)")
        return
    job_type, task_uid = task_ref
    print(f"\nrefresh queued: {job_type}/{task_uid} — awaiting completion...")
    async with open_client(profile) as client:
        completion = await client.tasks.await_completion(task_ref, timeout=300.0)
    print(f"  done in {len(completion.notifications)} notifications; final: {completion.message}")


if __name__ == "__main__":
    run_example(main)
