"""Read aggregate values back and stream a large export to a sink.

Two read paths on the same `/api/dataValueSets` endpoint the streaming import
writes to:

1. `client.data_values.export(...)` GETs the values for a data set at an
   organisation unit over a period or date range and returns a parsed
   `DataValueSet`. The whole response is buffered, so it fits a form's worth of
   values, not a national year.
2. `client.stream("GET", path, sink, params=...)` writes any endpoint's body to
   a sink chunk by chunk, so a national year lands in storage without ever
   being held in memory. The sink is a `pathlib.Path`, a file-like object with
   `.write(bytes)`, or a callable that takes each chunk.

Uses the seeded Child Health data set at Ngelehun CHC from the start of last
year to today, a window every seed rebuild carries values in.

Usage:
    uv run python examples/client/data_values_export.py
"""

from __future__ import annotations

import io
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

DATA_SET_UID = "BfMAe6Itzgt"  # Child Health
ORG_UNIT_UID = "DiszpKrYNg8"  # Ngelehun CHC


async def main() -> None:
    """Export one form's values as a typed envelope, then stream the same export three ways."""
    today = datetime.now(tz=UTC).date()
    start_date = date(today.year - 1, 1, 1).isoformat()
    end_date = today.isoformat()

    async with open_client(profile_from_env()) as client:
        # 1. Typed export. `data_set` / `period` / `org_unit` take one id or a
        # sequence; a date range replaces an explicit period list.
        print(f"--- export: data set {DATA_SET_UID} at {ORG_UNIT_UID}, {start_date}..{end_date} ---")
        data_value_set = await client.data_values.export(
            data_set=DATA_SET_UID,
            org_unit=ORG_UNIT_UID,
            start_date=start_date,
            end_date=end_date,
        )
        values = data_value_set.dataValues or []
        print(f"  {len(values)} values")
        for value in values[:3]:
            print(f"    {value.dataElement} {value.period} {value.categoryOptionCombo} = {value.value}")

        # 2. The same export streamed. `params` carries DHIS2's repeated-key
        # shape as a mapping with list values, exactly as `export` sends it.
        params = {
            "dataSet": [DATA_SET_UID],
            "orgUnit": [ORG_UNIT_UID],
            "startDate": start_date,
            "endDate": end_date,
        }

        # 2a. A Path sink. Parent directories are created; the file is written
        # chunk by chunk and never assembled in memory.
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "child-health.json"
            written = await client.stream("GET", "/api/dataValueSets.json", target, params=params)
            print(f"--- stream to Path: {written:,} bytes -> {target.name} ---")

        # 2b. A file-like sink. Anything with `.write(bytes)` works, sync or
        # async, so an open file, a socket wrapper, or an object-store upload
        # all fit.
        buffer = io.BytesIO()
        written = await client.stream("GET", "/api/dataValueSets.json", buffer, params=params)
        print(f"--- stream to BytesIO: {written:,} bytes, buffer holds {len(buffer.getvalue()):,} ---")

        # 2c. A chunk callable. The caller decides what each chunk means: count
        # it, hash it, forward it. Async callables are awaited.
        chunks: list[int] = []
        written = await client.stream(
            "GET",
            "/api/dataValueSets.json",
            lambda chunk: chunks.append(len(chunk)),
            params=params,
            chunk_size=16 * 1024,
        )
        print(f"--- stream to callable: {written:,} bytes in {len(chunks)} chunks of up to 16 KiB ---")


if __name__ == "__main__":
    run_example(main)
