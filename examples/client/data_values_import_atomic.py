"""Send a partly invalid import under both atomic modes and read what DHIS2 did.

`client.data_values.stream(..., atomic_mode=...)` forwards DHIS2's `atomicMode`
switch on `/api/dataValueSets`. DHIS2 documents `ALL` (its default) as rejecting
the whole import when any row is rejected, and `OBJECT` as committing the rows
that pass while reporting the rest as ignored.

The same two-row payload goes in under each mode. One row carries text where
the data element takes a number. On DHIS2 2.42 and 2.43 both modes commit the
valid row and ignore the invalid one (BUGS.md #112), so this example prints
what the instance actually did rather than what the switch promises. The good
row's value changes on every import, because a value equal to what the
instance already holds is reported as ignored too.

DHIS2 v42 answers an import that carries any conflict with HTTP 409, even when
the other row was committed; v43 answers 200 (BUGS.md #6). The client raises
on the 409, and the import summary is the exception's body, so both shapes
are read here.

Writes to Ngelehun CHC, the same facility the other data-value examples write
to, on periods the seeded Child Health data set is open for.

Usage:
    uv run python examples/client/data_values_import_atomic.py
"""

from __future__ import annotations

import json
import time

from _runner import run_example
from dhis2w_client import Dhis2Client, WebMessageResponse
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

DATA_ELEMENT_UID = "fClA2Erf6IO"  # Penta1 doses given, a numeric data element
CATEGORY_OPTION_COMBO_UID = "Prlt0C1RF0s"  # Fixed, <1y
ORG_UNIT_UID = "DiszpKrYNg8"  # Ngelehun CHC


async def main() -> None:
    """Import one valid and one invalid row under each atomic mode and compare the counts."""
    async with open_client(profile_from_env()) as client:
        for offset, atomic_mode in enumerate(("ALL", "OBJECT")):
            # A fresh value per import, so the good row is an update rather than a no-op.
            value = str((int(time.time()) + offset) % 1000)
            body = json.dumps(
                {
                    "dataValues": [
                        {
                            "dataElement": DATA_ELEMENT_UID,
                            "categoryOptionCombo": CATEGORY_OPTION_COMBO_UID,
                            "period": "202603",
                            "orgUnit": ORG_UNIT_UID,
                            "value": value,
                        },
                        {
                            "dataElement": DATA_ELEMENT_UID,
                            "categoryOptionCombo": CATEGORY_OPTION_COMBO_UID,
                            "period": "202602",
                            "orgUnit": ORG_UNIT_UID,
                            "value": "not-a-number",
                        },
                    ]
                }
            ).encode()
            envelope = await _import(client, body, atomic_mode)
            count = envelope.import_count()
            print(f"--- atomic_mode={atomic_mode}: status={envelope.status} ---")
            if count is not None:
                print(f"  imported={count.imported} updated={count.updated} ignored={count.ignored}")
            for conflict in envelope.conflicts()[:2]:
                print(f"  conflict on {conflict.object}: {conflict.value}")


async def _import(client: Dhis2Client, body: bytes, atomic_mode: str) -> WebMessageResponse:
    """Run the import and return its summary whether DHIS2 sent it as 200 or as 409."""
    try:
        return await client.data_values.stream(
            body,
            content_type="application/json",
            atomic_mode=atomic_mode,
        )
    except Dhis2ApiError as exc:
        if exc.status_code != 409 or not isinstance(exc.body, dict):
            raise
        return WebMessageResponse.model_validate(exc.body)


if __name__ == "__main__":
    run_example(main)
