# Data values (streaming import)

`DataValuesAccessor` on `Dhis2Client.data_values` — streams uploads to `POST /api/dataValueSets` without buffering the whole payload in memory. Accepts JSON / XML / CSV / ADX content types. For the typed-list-of-`DataValue` case, see [Aggregate data values](aggregate.md); the streaming accessor is the right tool when the payload is too large to materialise (CSV with hundreds of thousands of rows, etc.).

## When to reach for it

- Importing a CSV / JSON file that's larger than the host's free RAM.
- Pipe-style imports where the source is an `AsyncIterable[bytes]` (e.g. a transform step that emits a row at a time).
- Mixed-DataSet writes on DHIS2 v43 — the grouped path is the workaround for BUGS #35.

## Worked example — stream a CSV file to DHIS2

```python
from pathlib import Path

from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async with open_client(profile_from_env()) as client:
    # `stream` takes a Path (or any AsyncIterable[bytes]) + a content type.
    # The body is sent chunked; httpx never materialises the whole file.
    envelope = await client.data_values.stream(
        Path("./monthly-coverage-2026.csv"),
        content_type="application/csv",
    )
    count = envelope.import_count()
    if envelope.status == "OK" and count:
        print(f"imported {count.imported}  updated {count.updated}  ignored {count.ignored}")
    else:
        print(f"status={envelope.status!r}  message={envelope.message!r}")
```

## Worked example — typed `DataValue` write (small batch)

```python
from dhis2w_client import DataValue


values = [
    DataValue(
        dataElement="fbfJHSPpUQD",
        period="202604",
        orgUnit="ImspTQPwCqd",
        categoryOptionCombo="HllvX50cXC0",
        attributeOptionCombo="HllvX50cXC0",
        value="42",
    ),
]

async with open_client(profile_from_env()) as client:
    # `import_grouped_by_dataset` is the cross-version write path
    # (required on v43 for DEs in multiple DataSets — BUGS #35).
    # Returns `list[WebMessageResponse]` — one envelope per DataSet group.
    envelopes = await client.data_values.import_grouped_by_dataset(values)
    for env in envelopes:
        count = env.import_count()
        print(f"  status={env.status}  imported={count.imported if count else '?'}")
```

## Related examples

- [`examples/client/stream_data_values.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/stream_data_values.py) — four streaming shapes (bytes, sync generator, Path/CSV, 1000-row file with timing).
- [`examples/client/aggregate_bulk_grouped.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/aggregate_bulk_grouped.py) — the grouped path against a v43 stack.

::: dhis2w_client.v42.data_values
