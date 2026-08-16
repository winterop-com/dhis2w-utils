"""Stream a large analytics response to disk — `client.analytics.stream_to`.

Counterpart to `client.data_values.stream` (the import direction); this
one handles the export direction. Uses httpx's `stream()` + `aiter_bytes`
to pipe the body straight to a file without buffering the full response
in Python memory. Useful for:

- Monthly / yearly pivots that produce millions of cells.
- Raw-data dumps via `/api/analytics/rawData.json`.
- Programmatic CSV exports for downstream ETL (pandas, duckdb, ...).

Three shapes covered below:

1. `/api/analytics.json` — typed envelope, easy to parse downstream.
2. `/api/analytics.csv` — tiny wire format when cells are the whole point.
3. `/api/analytics/rawData.json` — BUGS.md #1 workaround path
   (Accept-negotiation is broken on the sub-resources; the `.json`
   extension must be on the URL).

Usage:
    uv run python examples/client/stream_analytics.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

# Known-good dimensions on the seeded v42 stack.
_DIMENSIONS = ["dx:fClA2Erf6IO", "pe:LAST_12_MONTHS", "ou:PMa2VCrupOd"]


async def main() -> None:
    """Stream analytics responses in three formats and print per-format timing."""
    async with open_client(profile_from_env()) as client:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            for label, endpoint in [
                ("JSON", "/api/analytics.json"),
                ("CSV", "/api/analytics.csv"),
                ("rawData.json", "/api/analytics/rawData.json"),
            ]:
                destination = tmp / f"analytics-{label.lower().replace('.json', '')}.out"
                t0 = time.monotonic()
                written = await client.analytics.stream_to(
                    destination,
                    params={"dimension": _DIMENSIONS},
                    endpoint=endpoint,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000
                head = destination.read_bytes()[:80]
                head_display = head.replace(b"\n", b" ").decode(errors="replace")
                print(f"--- {label:14} {written:>6} B in {elapsed_ms:>5.0f} ms ---")
                print(f"  {destination.name}  head: {head_display!r}")


if __name__ == "__main__":
    run_example(main)
