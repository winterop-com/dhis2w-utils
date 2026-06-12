"""Run DHIS2 predictor expressions via `client.predictors`.

Predictors are DHIS2 server-side expressions that generate synthetic
`DataValue`s from historical data (averages, sums, projections over
sliding windows). `dhis2w-core` mounts the run surface under
`d2w maintenance predictors`. CRUD on the predictors themselves stays
on the generic metadata surface (`d2w metadata list predictors`).

What this example exercises:

- **`run_all`** — `POST /api/predictors/run` for every predictor on the
  instance, over the given date range. Returns a `WebMessageResponse`
  envelope with `importCount` summarising how many new values landed.

The plugin also exposes `run_group(group_uid, ...)` and
`run_one(predictor_uid, ...)` for targeted runs; same envelope shape.

Validation-rule runs live in the sibling `validation_rules.py` example —
same plugin namespace (`d2w maintenance ...`) but a different engine
that returns violations, not generated data values.

Usage:
    uv run python examples/v41/client/predictors.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Run every predictor on the instance over Jan 2025 and report the import envelope."""
    async with open_client(profile_from_env()) as client:
        envelope = await client.predictors.run_all(start_date="2025-01-01", end_date="2025-01-31")
        count = envelope.import_count()
        print(
            f"status={envelope.status or envelope.httpStatus}  "
            f"imported={count.imported if count else '?'}  "
            f"message={envelope.message or '-'}"
        )


if __name__ == "__main__":
    run_example(main)
