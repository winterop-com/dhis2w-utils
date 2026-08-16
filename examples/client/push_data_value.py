"""Write one aggregate data value against the seeded Sierra Leone e2e dataset.

Exercises the bulk-import path at `/api/dataValueSets` with a single value.
Uses the org units / data elements baked into `infra/v42/dump.sql.gz` so the
write succeeds out of the box against `make dhis2-run`.

Usage:
    uv run python examples/03_push_data_value.py [value]

Defaults to value=100 for PMa2VCrupOd / fClA2Erf6IO / period 202603.

Env: same as 01_whoami.py.
"""

from __future__ import annotations

import sys

from _runner import run_example
from dhis2w_client import DataValue, DataValueSet
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

_DEFAULT_VALUE = "100"


async def main() -> None:
    """Push one data value and print the import summary."""
    value = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_VALUE
    # DataValue / DataValueSet are exported from dhis2w_client — same typed
    # envelope used by `d2w data aggregate get` returns.
    payload = DataValueSet(
        dataValues=[
            DataValue(
                dataElement="fClA2Erf6IO",  # Penta1 doses given — from the seeded dump
                period="202603",  # March 2026
                orgUnit="DiszpKrYNg8",  # Ngelehun CHC — facility-level, in the Child Health dataset
                value=value,
            ),
        ],
    )
    async with open_client(profile_from_env()) as client:
        # /api/dataValueSets is a bulk endpoint with no typed resource accessor;
        # post_raw is the escape hatch. The response is a WebMessageResponse.
        raw = await client.post_raw("/api/dataValueSets", payload.model_dump(exclude_none=True))
        from dhis2w_client import WebMessageResponse

        response = WebMessageResponse.model_validate(raw)
        counts = response.import_count()
        print(f"status: {response.status or response.httpStatus or '?'}")
        if counts is not None:
            print(
                f"  imported={counts.imported}  updated={counts.updated}  "
                f"ignored={counts.ignored}  deleted={counts.deleted}"
            )
        for conflict in response.conflicts()[:5]:
            print(f"  conflict: {conflict.property} = {conflict.value} [{conflict.errorCode}]")


if __name__ == "__main__":
    run_example(main)
