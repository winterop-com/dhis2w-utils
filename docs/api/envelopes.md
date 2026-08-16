# Envelopes + responses

The `WebMessageResponse` envelope and its inner shapes (`ObjectReport`, `ImportReport`, `ImportCount`, `Conflict`, `ErrorReport`, `Stats`, `TypeReport`). Every DHIS2 write endpoint — `POST /api/metadata`, `POST /api/dataValueSets`, `POST /api/tracker`, the per-resource write endpoints, etc. — returns one of these shapes.

## When to reach for it

You don't usually instantiate envelopes; you parse them from a write response and branch on the typed fields. The accessor surface returns them already-parsed:

```python
# A bulk metadata import; envelope is a fully-typed model.
envelope = await client.metadata.import_bundle(payload)
assert isinstance(envelope, WebMessageResponse)
```

What you read off it:

- `envelope.status` — `"OK"` / `"WARNING"` / `"ERROR"` / `"SUCCESS"`. Always check this before declaring victory.
- `envelope.message` — a one-line human description (often duplicates `httpStatusCode`'s reason phrase).
- `envelope.import_count()` — convenience accessor on `WebMessageResponse` that walks the typed response into a `ImportCount` (imported / updated / ignored / deleted) without dict navigation.
- `envelope.response.conflicts` — list of `Conflict`s with per-row error messages. Empty on `status="OK"`.
- `envelope.response.typeReports` — per-resource breakdown (e.g. how many DataElements vs DataSets vs OrgUnits landed in a metadata bundle).

## Worked example — write + branch on envelope

```python
from dhis2w_client import DataValue, WebMessageResponse
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
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
    # Returns `list[WebMessageResponse]` — one envelope per DataSet group.
    envelopes: list[WebMessageResponse] = await client.data_values.import_grouped_by_dataset(values)

    for envelope in envelopes:
        count = envelope.import_count()
        if envelope.status == "OK" and count and count.ignored == 0:
            print(f"imported={count.imported}  updated={count.updated}")
        else:
            # Conflict shape: row index + per-field message. Read first 5.
            for conflict in (envelope.response.conflicts or [])[:5] if envelope.response else []:
                print(f"  row {conflict.object} -> {conflict.value}")
            raise RuntimeError(f"import failed: status={envelope.status} message={envelope.message}")
```

## Error-side shape

Failed writes raise `Dhis2ApiError`. Call `.web_message()` to materialise the parsed `WebMessageResponse` if DHIS2 returned one (it returns `None` when the error body wasn't a WebMessage — e.g. a plain 401 or a network error). The typed `conflicts` list is the actionable bit.

```python
from dhis2w_client import Dhis2ApiError

try:
    await client.metadata.import_bundle(bad_payload)
except Dhis2ApiError as exc:
    wm = exc.web_message()
    if wm is not None and wm.response is not None:
        for c in wm.response.conflicts or []:
            print(f"  {c.object}: {c.value}")
    else:
        # No WebMessage envelope — fall back to the raw status + message.
        print(f"  HTTP {exc.status_code}: {exc.message}")
```

## Related examples

- [`examples/client/error_handling.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/error_handling.py) — `Dhis2ApiError` + WebMessage conflict shape.
- [`examples/client/metadata_bulk_import.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/metadata_bulk_import.py) — typed dry-run + real import branching on the envelope.

::: dhis2w_client.v42.envelopes
