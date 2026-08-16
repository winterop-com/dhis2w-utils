# Analytics streaming

`AnalyticsAccessor` on `Dhis2Client.analytics` — streaming GETs against the `/api/analytics*` endpoint family. Uses httpx's `stream()` + `aiter_bytes` to pipe the response body straight to disk without buffering the full body in memory. Counterpart to [Data values (streaming)](data-values.md) for the export direction.

## When to reach for it

- Exporting an analytics pivot too large to materialise as a single string in memory (city-level monthly population indicators, multi-year datasets, etc.).
- Writing a CSV or JSON file an analytics tool downstream will read.
- Snapshotting `rawData` for offline analysis (the rawData endpoint can produce hundreds of MB).

For small / interactive queries, `client.analytics.aggregate(dx=..., pe=..., ou=...)` returns a parsed `Grid` synchronously — see the parent `Analytics` page. Streaming is the right tool only when the response size makes the synchronous shape impractical.

## Worked example — stream a CSV to disk

```python
from pathlib import Path

from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # Bytes-iterator interface: useful when you want to pipe somewhere else.
    async for chunk in client.analytics.stream(
        dx="fbfJHSPpUQD",
        pe="LAST_12_MONTHS",
        ou="ImspTQPwCqd",
        output_format="csv",
    ):
        ...

    # `stream_to(Path, ...)` writes directly; httpx never buffers the body.
    bytes_written = await client.analytics.stream_to(
        Path("./monthly-anc.csv"),
        dx="fbfJHSPpUQD",
        pe="LAST_12_MONTHS",
        ou="ImspTQPwCqd",
        output_format="csv",
    )
    print(f"wrote {bytes_written:,} bytes to ./monthly-anc.csv")
```

## Output formats

- `csv` — the most common downstream-tool target.
- `json` — analytics pivot in JSON; equivalent to the parsed `Grid` but un-parsed.
- `rawData` — DHIS2 returns rows in the source schema (data values, not pivoted cells). Use for offline re-analysis.

`stream_to(..., output_format="rawData")` works the same way; the suffix on the URL changes.

## Related examples

- [`examples/client/stream_analytics.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/stream_analytics.py) — JSON / CSV / rawData exports to disk with per-format timing.

::: dhis2w_client.v42.analytics_stream
