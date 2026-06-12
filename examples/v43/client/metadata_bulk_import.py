"""Bulk metadata import via `service.import_metadata` — typed dry-run + real.

Shows the `d2w metadata import` plumbing as a Python-level script: build
a typed bundle, call `service.import_metadata` with full DHIS2 import flags
(`import_strategy`, `atomic_mode`, `dry_run`, `identifier`, ...), inspect the
parsed `WebMessageResponse`, then clean up via the typed CRUD accessors.

Replaces what used to be two hand-rolled `client.post_raw("/api/metadata", ...)`
calls with the typed service surface that ships the same wire contract but
returns a parsed envelope with `.import_count()`, `.conflicts()`, etc.

Usage:
    uv run python examples/v43/client/metadata_bulk_import.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import Dhis2Client, generate_uids
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
from dhis2w_client.generated.v42.oas import AtomicMode, ImportStrategy
from dhis2w_client.generated.v42.schemas import DataElement
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v42.plugins.metadata import service
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle


async def _default_category_combo(client: Dhis2Client) -> str:
    """Fetch the built-in default category combo UID via the typed accessor."""
    combos = await client.resources.category_combos.list(filters=["name:eq:default"], fields="id")
    return str(combos[0].id)


async def main() -> None:
    """Run a dry-run metadata import, then the real one, then clean up."""
    profile = profile_from_env()

    async with open_client(profile) as client:
        uids = generate_uids(2)
        cc_uid = await _default_category_combo(client)
        print(f"minted: {uids}  default CC: {cc_uid}")

        # Each DataElement is fully typed — StrEnums guard against typos at edit time.
        data_elements = [
            DataElement(
                id=uid,
                code=f"EX_BULK_{uid}",
                name=f"Bulk example {idx + 1}",
                shortName=f"BulkEx{idx + 1}",
                domainType=DataElementDomain.AGGREGATE,
                valueType=ValueType.INTEGER_ZERO_OR_POSITIVE,
                aggregationType=AggregationType.SUM,
                categoryCombo=Reference(id=cc_uid),
            )
            for idx, uid in enumerate(uids)
        ]
        bundle = MetadataBundle.from_raw(
            {
                "dataElements": [de.model_dump(by_alias=True, exclude_none=True, mode="json") for de in data_elements],
            }
        )

        # 1. DRY-RUN — DHIS2 validates the payload but persists nothing.
        print("\n>>> 1/3 dry-run (importMode=VALIDATE)")
        dry = await service.import_metadata(
            profile,
            bundle,
            import_strategy=ImportStrategy.CREATE_AND_UPDATE,
            atomic_mode=AtomicMode.ALL,
            dry_run=True,
        )
        counts = dry.import_count()
        print(f"    status={dry.status}  counts={counts.model_dump() if counts else None}")

        # 2. REAL IMPORT.
        print("\n>>> 2/3 real import")
        real = await service.import_metadata(
            profile,
            bundle,
            import_strategy=ImportStrategy.CREATE_AND_UPDATE,
            atomic_mode=AtomicMode.ALL,
        )
        counts = real.import_count()
        print(f"    status={real.status}  counts={counts.model_dump() if counts else None}")

        # 3. CLEANUP — delete via the typed accessor.
        print("\n>>> 3/3 cleanup")
        for uid in uids:
            await client.resources.data_elements.delete(uid)
            print(f"    deleted dataElements/{uid}")


if __name__ == "__main__":
    run_example(main)
