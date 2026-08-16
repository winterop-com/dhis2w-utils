"""Reverse metadata lookup via `client.metadata.usage` — deletion-safety probe.

Given a UID, `usage` resolves the owning resource via
`/api/identifiableObjects/{uid}`, then fans out concurrent
`/api/<target>?filter=<path>:eq:<uid>` calls against every known
reference path for that owning type. Everything that references the UID
shows up in the result grouped by resource.

Useful before a metadata delete: "which dashboards / visualizations /
data sets would break if I removed this data element?"

Usage:
    uv run python examples/client/metadata_usage.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Probe DE / viz / map / OU references against the seeded stack."""
    async with open_client(profile_from_env()) as client:
        # DataElement — hits every dataset / viz / map / program stage / rule
        # variable / indicator expression / validation rule referencing it.
        result = await client.metadata.usage("s46m5MS0hxu")
        print(f"DE s46m5MS0hxu (BCG doses given) is referenced by {result.total} objects:")
        for resource, hits in result.hits.items():
            print(f"  {resource}: {len(hits)}")
            for hit in hits[:3]:
                print(f"    - {hit.uid}: {hit.name}")

        # Visualization — owned by dashboards via dashboardItems.visualization.id
        result = await client.metadata.usage("Qyuliufvfjl")
        print(f"\nViz Qyuliufvfjl is on {result.total} dashboard(s):")
        for hit in result.flat():
            print(f"  - {hit.uid}: {hit.name}")

        # Org unit — shows users, org-unit groups, datasets, programs assigned.
        result = await client.metadata.usage("ImspTQPwCqd")
        print(f"\nOU ImspTQPwCqd (Sierra Leone root) is referenced by {result.total} objects:")
        for resource, hits in result.hits.items():
            print(f"  {resource}: {len(hits)}")


if __name__ == "__main__":
    run_example(main)
