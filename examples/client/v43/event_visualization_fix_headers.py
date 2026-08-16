"""EventChart / EventReport / EventVisualization gained 3 new fields in v43.

v43 adds:

- fixColumnHeaders (bool)
- fixRowHeaders (bool)
- hideEmptyColumns (bool)

to all three event-* analytics shapes. (The plain `Visualization` had
these in v42 already.)

The hand-written `client.visualizations` accessor narrows fields to a
small allowlist and returns the v42-typed `Visualization`, so the
cleanest demo is to hit `/api/eventVisualizations` directly with
`get_raw` and pick the new fields out of the JSON.

Usage:
    uv run python examples/client/v43/event_visualization_fix_headers.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """List one event-visualization with the v43-only fields surfaced."""
    async with open_client(profile_from_env()) as client:
        raw = await client.get_raw(
            "/api/eventVisualizations",
            params={
                "fields": "id,name,type,fixColumnHeaders,fixRowHeaders,hideEmptyColumns",
                "pageSize": 1,
            },
        )
        items = raw.get("eventVisualizations") or []
        if not items:
            print("no event visualizations on this instance")
            return
        item = items[0]
        print(f"version={client.version_key} eventVisualization={item.get('id')} name={item.get('name')!r}")
        if client.version_key == "v42":
            print("  v42: fixColumnHeaders / fixRowHeaders / hideEmptyColumns absent (fields not in schema)")
            return
        print(
            f"  v43 fixColumnHeaders={item.get('fixColumnHeaders')} "
            f"fixRowHeaders={item.get('fixRowHeaders')} "
            f"hideEmptyColumns={item.get('hideEmptyColumns')}"
        )


if __name__ == "__main__":
    run_example(main)
