# Data values (import + export)

`DataValuesAccessor` on `Dhis2Client.data_values` — both directions of `/api/dataValueSets`. `stream` uploads JSON / XML / CSV / ADX without buffering the whole payload in memory; `export` reads a form's values back as a typed `DataValueSet`; and for an export too large to hold, `client.stream("GET", "/api/dataValueSets.json", sink, params=...)` writes the body straight to storage. For the typed-list-of-`DataValue` case, see [Aggregate data values](aggregate.md); the streaming accessor is the large-payload path.

## When to reach for it

- Importing a CSV / JSON file that's larger than the host's free RAM.
- Pipe-style imports where the source is an `AsyncIterable[bytes]` (e.g. a transform step that emits a row at a time).
- Mixed-DataSet writes on DHIS2 v43 — the grouped path is the workaround for BUGS #35.
- Reading a form's values back after a write, or pulling one organisation unit's year for a report.
- Exporting a national year to a file or an object store without holding it in memory.

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

## Partly invalid imports: `atomic_mode`

`stream(..., atomic_mode="ALL" | "OBJECT")` forwards DHIS2's `atomicMode` switch. DHIS2 documents `ALL` as rejecting the whole import when any row is rejected and `OBJECT` as committing the rows that pass. On DHIS2 2.42 and 2.43 the switch has no observable effect on `/api/dataValueSets`: a payload with one valid row and one row that fails value-type validation commits the valid row under both modes and reports the other as ignored (BUGS.md #112). The parameter is forwarded so a build that honours it gets the documented behaviour; do not rely on `ALL` to keep a partly invalid import out.

A value equal to what the instance already holds also counts as ignored, so an unchanged re-import reads as `ignored=N` under either mode.

DHIS2 v42 answers any import that carries a conflict with HTTP 409, even when the other rows were committed; v43 answers 200 with the same `WARNING` envelope (BUGS.md #6). `stream` raises `Dhis2ApiError` on the 409, and the import summary is the exception's `body`:

```python
from dhis2w_client import WebMessageResponse
from dhis2w_client.errors import Dhis2ApiError

try:
    envelope = await client.data_values.stream(body, content_type="application/json", atomic_mode="OBJECT")
except Dhis2ApiError as exc:
    if exc.status_code != 409 or not isinstance(exc.body, dict):
        raise
    envelope = WebMessageResponse.model_validate(exc.body)
count = envelope.import_count()
for conflict in envelope.conflicts():
    print(f"{conflict.object}: {conflict.value}")
```

## Worked example — export a form's values

```python
async with open_client(profile_from_env()) as client:
    # `data_set` / `period` / `org_unit` take one id or a sequence and repeat
    # on the wire. A date range replaces an explicit period list;
    # `children=True` includes the organisation units below `org_unit`.
    data_value_set = await client.data_values.export(
        data_set="BfMAe6Itzgt",
        org_unit="DiszpKrYNg8",
        start_date="2026-01-01",
        end_date="2026-06-30",
    )
    for value in data_value_set.dataValues or []:
        print(f"{value.dataElement} {value.period} {value.categoryOptionCombo} = {value.value}")
```

`last_updated` / `last_updated_duration` (`2h`, `1d`) narrow to recently touched values; `extra_params` carries the rest of the endpoint's surface (`idScheme`, `includeDeleted`, `dataElementGroup`, ...).

## Worked example — stream an export to a sink

`export` buffers the whole response. `client.stream` does not: it writes the body chunk by chunk to a `pathlib.Path`, to any object with `.write(bytes)` (sync or async), or to a callable that receives each chunk. It works for any endpoint, and `client.analytics.stream_to` is the Path-only convenience over it.

```python
import io
from pathlib import Path

params = {
    "dataSet": ["BfMAe6Itzgt"],
    "orgUnit": ["ImspTQPwCqd"],
    "children": "true",
    "startDate": "2025-01-01",
    "endDate": "2025-12-31",
}

async with open_client(profile_from_env()) as client:
    # To a file. Parent directories are created; the file is never assembled in memory.
    written = await client.stream("GET", "/api/dataValueSets.json", Path("./exports/2025.json"), params=params)

    # To anything with .write(bytes): an open file, an upload stream, a BytesIO.
    buffer = io.BytesIO()
    await client.stream("GET", "/api/dataValueSets.json", buffer, params=params)

    # To a callable: count, hash, or forward each chunk. Async callables are awaited.
    async def forward(chunk: bytes) -> None:
        await queue.put(chunk)

    await client.stream("GET", "/api/dataValueSets.json", forward, params=params, chunk_size=64 * 1024)
```

A 4xx / 5xx raises `AuthenticationError` or `Dhis2ApiError` before anything is written; a Path sink is not created when the request fails.

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
- [`examples/client/data_values_import_atomic.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/data_values_import_atomic.py) — the same partly invalid payload under `ALL` and `OBJECT`.
- [`examples/client/data_values_export.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/data_values_export.py) — `export` as a typed envelope, then `client.stream` to a Path, a BytesIO, and a callable.

::: dhis2w_client.v42.data_values
