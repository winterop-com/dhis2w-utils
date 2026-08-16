"""Three top-level resources removed in v43: pushAnalysis, externalFileResource, dataInputPeriods.

v42 exposed three resources that are gone in v43:

- `pushanalysis` — the entire push-analysis subsystem is removed.
- `externalFileResource` — replaced by reading `externalAccess` directly off
  `fileResource`.
- `dataInputPeriods` — folded inline under `dataSet.dataInputPeriods` (no
  top-level resource, but the data is still reachable through
  `client.data_sets.get(uid)` on both versions).

There is no v43 codegen accessor for these resources because the
codegen reflects each version's live `/api/schemas` response. Code that
needs to talk to the v42-only resource should branch on
`client.version_key`.

Usage:
    uv run python examples/client/v43/removed_resources.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Demonstrate version-gated reads of resources that exist only on v42."""
    async with open_client(profile_from_env()) as client:
        print(f"version={client.version_key}")

        if client.version_key == "v42":
            # pushAnalysis is still a top-level listable resource on v42 — gone in v43.
            raw = await client.get_raw(
                "/api/pushAnalysis",
                params={"fields": "id,name", "pageSize": 3},
            )
            items = raw.get("pushAnalyses") or []
            print(f"  v42 pushAnalysis count={len(items)} ids={[item.get('id') for item in items[:3]]}")
            # externalFileResource appears in `/api/schemas` on v42 but the list
            # endpoint isn't routable (returns 404) — items live nested under
            # `fileResource` instead. v43 dropped the schema entry entirely.
            print("  v42 externalFileResource: schema-only, not listable (resource UIDs travel via fileResource)")
            return

        # v43: the resources are gone — calling them would 404. Show the
        # version-gated branch + the surviving inline path for dataInputPeriods.
        print("  v43: pushAnalysis / externalFileResource / dataInputPeriods removed")
        data_sets = await client.data_sets.list_all()
        if data_sets:
            data_set = await client.data_sets.get(data_sets[0].id or "")
            inline_periods = getattr(data_set, "dataInputPeriods", None) or []
            print(f"  v43 dataSet {data_set.id} now exposes inline dataInputPeriods (count={len(inline_periods)})")


if __name__ == "__main__":
    run_example(main)
