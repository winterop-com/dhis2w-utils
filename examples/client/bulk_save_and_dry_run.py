"""Bulk-write + validate-before-commit — `save_bulk` + `client.metadata.dry_run`.

Two complementary surfaces:

1. **`client.resources.<resource>.save_bulk(items)`** — IDE-typed bulk
   create/update for a single resource type. Faster than N `create()`
   calls, and `items` is typed as `list[DataElement]` / `list[Indicator]`
   / etc. (pass bare dicts if you're working from raw JSON).

2. **`client.metadata.dry_run({...})`** — cross-resource validation
   without committing. `importMode=VALIDATE` runs DHIS2's full preheat
   + validation pipeline, returns the same `WebMessage` envelope a real
   import would produce, and rolls nothing back. Useful as a safety
   gate before a real `save_bulk` or `delete_bulk`.

Both support `import_strategy` (CREATE / CREATE_AND_UPDATE / UPDATE /
DELETE) and `atomic_mode` (NONE default / ALL rolls back on any conflict).

Usage:
    uv run python examples/client/bulk_save_and_dry_run.py
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
    """Dry-run a small bundle; then commit via `save_bulk`; then tear down via `delete_bulk`."""
    async with open_client(profile_from_env()) as client:
        default_cc = await client.system.default_category_combo_uid()

        # Build typed DataElements — IDE autocomplete, enum-safe values.
        elements = [
            DataElement(
                id=generate_uid(),
                name=f"bulk-save-demo {i}",
                shortName=f"bsd-{i}",
                aggregationType=AggregationType.SUM,
                domainType=DataElementDomain.AGGREGATE,
                valueType=ValueType.NUMBER,
                categoryCombo={"id": default_cc},  # type: ignore[arg-type]
            )
            for i in range(3)
        ]

        # 1. Dry-run first — validates without committing.
        print("--- dry_run (validate without commit) ---")
        envelope = await client.metadata.dry_run({"dataElements": elements})
        report = envelope.import_report()
        stats = report.stats if report else None
        print(f"  status={envelope.status}  would-create={stats.created if stats else '?'}")

        # 2. Commit via the typed per-resource save_bulk.
        print("\n--- save_bulk (typed list[DataElement]) ---")
        raw = await client.resources.data_elements.save_bulk(elements)
        response_stats = raw.get("response", {}).get("stats", {})
        print(
            f"  created={response_stats.get('created')}  "
            f"updated={response_stats.get('updated')}  total={response_stats.get('total')}"
        )

        # 3. Tear down with delete_bulk — same shape, opposite direction.
        print("\n--- delete_bulk (teardown) ---")
        uids = [e.id for e in elements if e.id is not None]
        envelope = await client.metadata.delete_bulk("dataElements", uids)
        report = envelope.import_report()
        stats = report.stats if report else None
        print(f"  deleted={stats.deleted if stats else '?'}")


if __name__ == "__main__":
    run_example(main)
