"""Tear down metadata in one call — `client.metadata.delete_bulk`.

Wraps `POST /api/metadata?importStrategy=DELETE` with a minimal
`{resource_type: [{id: uid}, ...]}` bundle, so one HTTP request deletes
every UID at once. Useful for:

- Fixture teardown after a test run.
- Reacting to a `d2w doctor` report — feed it a list of orphan UIDs
  the probes surfaced.
- Bulk cleanup after a scripted import that's obsolete.

Two entry points:

- `client.metadata.delete_bulk(resource_type, uids)` — single resource
  type, single HTTP call.
- `client.metadata.delete_bulk_multi({resource: [uids], ...})` — cross
  multiple resource types in one bundle. `atomic_mode="ALL"` rolls the
  whole bundle back on any conflict; the default `"NONE"` lets partial
  failures through (typical deletion usage).

Usage:
    uv run python examples/client/bulk_delete.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import generate_uid

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
from dhis2w_client.generated.v42.schemas.data_element import DataElement
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Create three throwaway DataElements, bulk-delete them, show the import-report stats."""
    async with open_client(profile_from_env()) as client:
        default_cc = await client.system.default_category_combo_uid()
        uids = [generate_uid() for _ in range(3)]
        print(f"creating 3 test DataElements: {uids}")
        elements = [
            DataElement(
                id=uid,
                name=f"bulk-delete-demo {uid}",
                shortName=f"bdd-{uid[:7]}",
                aggregationType=AggregationType.SUM,
                domainType=DataElementDomain.AGGREGATE,
                valueType=ValueType.TEXT,
                categoryCombo={"id": default_cc},  # type: ignore[arg-type]
            )
            for uid in uids
        ]
        # One bulk-save call — typed, replaces three per-element POSTs.
        await client.resources.data_elements.save_bulk(elements)

        before = await client.resources.data_elements.list(
            filters=["name:like:bulk-delete-demo"],
            fields="id",
        )
        print(f"before delete: {len(before)} matching")

        # One HTTP call deletes every UID.
        envelope = await client.metadata.delete_bulk("dataElements", uids)
        report = envelope.import_report()
        stats = report.stats if report else None
        print(f"delete_bulk -> import_report.stats.deleted = {stats.deleted if stats else '?'}")

        after = await client.resources.data_elements.list(
            filters=["name:like:bulk-delete-demo"],
            fields="id",
        )
        print(f"after delete: {len(after)} matching")

        # Empty list short-circuits — no HTTP call.
        print("\nempty-input short-circuit:")
        noop = await client.metadata.delete_bulk("dataElements", [])
        print(f"  status={noop.status}  message={noop.message}")

        # `delete_bulk_multi` for cross-type teardown. (Nothing to delete
        # here — just shows the shape for a real cleanup script.)
        print("\ndelete_bulk_multi — multi-type shape:")
        multi = await client.metadata.delete_bulk_multi(
            {
                "dataElements": [],
                "indicators": [],
            }
        )
        print(f"  status={multi.status}  message={multi.message}")


if __name__ == "__main__":
    run_example(main)
