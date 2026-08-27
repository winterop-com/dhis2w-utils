"""Typed bulk create/update — `client.resources.<resource>.save_bulk(items)`.

One call writes a whole list of one resource type, where N `create()` calls
would be N round trips. `items` is typed as `list[DataElement]` /
`list[Indicator]` / etc., so the IDE completes the fields and the enums guard
the values at edit time (bare dicts also go through, for callers working from
raw JSON).

`import_strategy` picks CREATE / CREATE_AND_UPDATE / UPDATE / DELETE, and
`atomic_mode` decides whether one refused object rolls the batch back (`ALL`)
or the survivors commit (`NONE`, the default).

Validating a bundle before committing it is its own surface — see
`metadata_dry_run.py`.

Usage:
    uv run python examples/client/bulk_save.py
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
    """Save three typed DataElements in one call, rename them in a second, tear down."""
    async with open_client(profile_from_env()) as client:
        default_cc = await client.system.default_category_combo_uid()

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

        print("--- save_bulk (create)")
        raw = await client.resources.data_elements.save_bulk(elements)
        stats = raw.get("response", {}).get("stats", {})
        print(f"  created={stats.get('created')}  updated={stats.get('updated')}  total={stats.get('total')}")

        # Same call, same UIDs: CREATE_AND_UPDATE (the default) overwrites what is already there.
        print("\n--- save_bulk (update — same UIDs, new names)")
        for index, element in enumerate(elements):
            element.name = f"bulk-save-demo {index} (renamed)"
        raw = await client.resources.data_elements.save_bulk(elements)
        stats = raw.get("response", {}).get("stats", {})
        print(f"  created={stats.get('created')}  updated={stats.get('updated')}  total={stats.get('total')}")

        print("\n--- teardown")
        uids = [element.id for element in elements if element.id is not None]
        envelope = await client.metadata.delete_bulk("dataElements", uids)
        report = envelope.import_report()
        report_stats = report.stats if report else None
        print(f"  deleted={report_stats.deleted if report_stats else '?'}")


if __name__ == "__main__":
    run_example(main)
