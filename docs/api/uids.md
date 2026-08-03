# UIDs

Client-side 11-char DHIS2 UID generator + validator. Same algorithm as `org.hisp.dhis.common.CodeGenerator.java` (leading letter + 10 alphanumeric chars, `secrets`-driven entropy), so values minted locally are accepted by every DHIS2 write endpoint without a server-side rename. Avoids a `/api/system/id` round-trip.

## When to reach for it

- Pre-generating UIDs for parent + child objects before the parent is created (the `programTrackedEntityAttributes` join table is one example — DHIS2 imports it as part of the parent's PUT body, so the child UID has to exist client-side first).
- Building a bulk metadata bundle where every object's `id` is known up front (`save_bulk` / `import_bundle` flows).
- Snapshotting a future-state UID into a fixture file for round-trip tests.

The two read-side helpers (`generate_uids(count)` for bulk, `is_valid_uid(s)` for guarding wire data) complete the surface.

## Worked example

```python
from dhis2w_client import generate_uid, generate_uids, is_valid_uid

# Single fresh UID, perfect for one-off metadata creates.
new_id = generate_uid()
assert is_valid_uid(new_id)
print(new_id)  # e.g. 'aB3xY7zK1pq' — 11 chars, starts with a letter

# 100 distinct UIDs for a bulk import.
ids = generate_uids(100)
assert len(set(ids)) == 100

# Guard wire data before treating a string as a UID.
candidate = "user-friendly-name"
if not is_valid_uid(candidate):
    print(f"{candidate!r} is not a valid DHIS2 UID — needs the 11-char shape")
```

## Pre-generating linked UIDs

The typical use is "I want to PUT a parent that references children that don't exist yet":

```python
from dhis2w_client import DataElement, generate_uid
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

new_de_id = generate_uid()
new_dataset_id = generate_uid()

async with open_client(profile_from_env()) as client:
    # Create the DE with the pre-generated ID...
    await client.data_elements.create(
        uid=new_de_id,
        name="My DE",
        short_name="MyDE",
        value_type="INTEGER",
    )
    # ...then create the DataSet that references it.
    await client.data_sets.create(
        uid=new_dataset_id,
        name="My DS",
        short_name="MyDS",
        period_type="Monthly",
        data_elements=[new_de_id],
    )
```

Property-based round-trip tests of `generate_uid` / `generate_uids` / `is_valid_uid` live in [`packages/dhis2w-client/tests/test_parser_properties.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/packages/dhis2w-client/tests/test_parser_properties.py).

::: dhis2w_client.v42.uids
