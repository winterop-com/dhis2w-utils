# Aggregate data values

`DataValue` and `DataValueSet` — the typed wire shapes for DHIS2's aggregate-data path (`/api/dataValueSets` GET / POST and the per-value `/api/dataValues` endpoint). Pairs with [Data values (streaming)](data-values.md), which exposes the same shape via `client.data_values.stream(...)` for very large imports.

`CompleteDataSetRegistration` and `CompleteDataSetRegistrations` are the sibling completeness resource: DHIS2 records whether a data set is *finished* for a period separately from the values, under the same `(dataSet, period, organisationUnit, attributeOptionCombo)` key, at `/api/completeDataSetRegistrations`.

## When to reach for it

- Pushing a small or medium batch of aggregate values from a script (CSV-to-DHIS2 sync, ETL pipeline, integration test fixture).
- Reading values back to verify a write landed or to drive an analytics-side check.
- Building the typed payload the streaming accessor and the bulk-grouped helper both consume.
- Marking a data set complete for a period once its values are in.

## Worked example — typed write, then read-back

```python
from dhis2w_client import DataValue, DataValueSet
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # Push two values. `import_grouped_by_dataset` is the cross-version
    # write path (required on v43 BUGS #35, accepted on v41 + v42). The
    # typed `DataValue`s are validated by pydantic before they hit the wire.
    values = [
        DataValue(
            dataElement="fbfJHSPpUQD",
            period="202604",
            orgUnit="ImspTQPwCqd",
            categoryOptionCombo="HllvX50cXC0",
            attributeOptionCombo="HllvX50cXC0",
            value="42",
        ),
        DataValue(
            dataElement="fbfJHSPpUQD",
            period="202605",
            orgUnit="ImspTQPwCqd",
            categoryOptionCombo="HllvX50cXC0",
            attributeOptionCombo="HllvX50cXC0",
            value="43",
        ),
    ]
    # `import_grouped_by_dataset` POSTs one envelope per DataSet group
    # (required on v43 BUGS #35). Returns a list — one WebMessageResponse
    # per POST. Aggregate the per-envelope counts to get a total.
    envelopes = await client.data_values.import_grouped_by_dataset(values)
    total_imported = sum((env.import_count().imported if env.import_count() else 0) for env in envelopes)
    print(f"posted {len(envelopes)} group(s)  total imported={total_imported}")
    for env in envelopes:
        print(f"  status={env.status}  message={env.message!r}")

    # Read back. `/api/dataValueSets` returns the typed DataValueSet shape;
    # validate the raw dict through the pydantic model.
    raw = await client.get_raw(
        "/api/dataValueSets",
        params={"dataSet": "lyLU2wR22tC", "period": "202604", "orgUnit": "ImspTQPwCqd"},
    )
    dvs = DataValueSet.model_validate(raw)
    for v in dvs.dataValues or []:
        print(f"  DE={v.dataElement}  pe={v.period}  ou={v.orgUnit}  value={v.value}")
```

## Worked example — mark a data set complete for a period

```python
from dhis2w_client import CompleteDataSetRegistration, CompleteDataSetRegistrations
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # Register completeness only once the values are in: the claim is about
    # data DHIS2 has taken, and a claim about data it refused would be false.
    registrations = CompleteDataSetRegistrations(
        completeDataSetRegistrations=[
            CompleteDataSetRegistration(
                dataSet="BfMAe6Itzgt",
                period="202604",
                organisationUnit="ImspTQPwCqd",
                # Omit attributeOptionCombo on a default-combo data set - DHIS2 fills it.
                date="2026-05-02",
                completed=True,
            )
        ]
    )
    answer = await client.post_raw(
        "/api/completeDataSetRegistrations",
        registrations.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )
    print(answer["response"]["importCount"])  # {'imported': 1, ...}

    # Read the tuple back. DHIS2 answers `{}` - not an empty list - when it
    # holds no registration for it.
    stored = await client.get_raw(
        "/api/completeDataSetRegistrations",
        params={"dataSet": "BfMAe6Itzgt", "period": "202604", "orgUnit": "ImspTQPwCqd"},
    )
    print(stored.get("completeDataSetRegistrations", []))
```

Registering a tuple DHIS2 already holds counts `updated` rather than conflicting, so re-running the same registration is safe.

## When to use which write path

`import_grouped_by_dataset(values)` is the safe cross-version default. It pre-fetches each `DataElement`'s `DataSet` membership and POSTs one `{"dataSet": …, "dataValues": [...]}` envelope per group — required on DHIS2 v43 for any DE that belongs to multiple DataSets (BUGS #35: v43 rejects mixed batches with `409 E8002`). v41 + v42 accept the same envelope shape, so the call is portable.

`client.data_values.stream(values, ...)` is the streaming alternative for very large imports — wraps the values as an async-byte stream so httpx doesn't have to materialise the full payload in memory.

## Related examples

- [`examples/client/push_data_value.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/push_data_value.py) — minimal single-value push.
- [`examples/client/stream_data_values.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/stream_data_values.py) — streaming reads, four shapes (bytes, sync generator, Path/CSV, 1000-row file with timing).
- [`examples/client/aggregate_bulk_grouped.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/aggregate_bulk_grouped.py) — the grouped bulk path.

::: dhis2w_client.v42.aggregate
