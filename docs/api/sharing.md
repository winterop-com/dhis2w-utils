# Sharing helpers

Typed helpers over `/api/sharing`. Use them to read and replace the sharing block of any DHIS2 object without hand-writing JSON Patch.

## Access strings

DHIS2 packs four capabilities into an 8-char string:

| Positions | Meaning |
|---|---|
| 0–1 | metadata read / write — `rw`, `r-`, `--` |
| 2–3 | data read / write (only meaningful on dataValue-carrying objects) |
| 4–7 | reserved; always `----` |

```python
from dhis2w_client import access_string, ACCESS_READ_METADATA, ACCESS_READ_WRITE_DATA

access_string()  # '--------'
access_string(metadata="rw")  # 'rw------'
access_string(metadata="r-", data="r-")  # 'r-r-----'
ACCESS_READ_METADATA  # 'r-------'
ACCESS_READ_WRITE_DATA  # 'rwrw----'
```

The four constants cover >95% of callsites; `access_string()` handles the rest without concatenation at the use site.

## Get / apply

```python
from dhis2w_client import Dhis2Client, SharingBuilder, apply_sharing, get_sharing

async with Dhis2Client(url, auth) as client:
    current = await get_sharing(client, "dataSet", ds_uid)
    # current is a `SharingObject` (publicAccess, externalAccess, user, userAccesses[], userGroupAccesses[]).

    sharing = (
        SharingBuilder(owner_user_id=admin_uid)
        .grant_user(admin_uid, "rwrw----")
        .grant_user_group(group_uid, "r-------")
    )
    envelope = await apply_sharing(client, "dataSet", ds_uid, sharing)
    assert envelope.status == "OK"
```

`apply_sharing` accepts either a `SharingBuilder` or a raw `SharingObject` (use the builder for ergonomics, drop down to the object when you already have one from `get_sharing`).

## Resource types

`resource_type` is DHIS2's singular metadata name as it appears in filter strings and in the sharing API's `?type=` param. Common values:

- `dataSet`, `dataElement`, `categoryCombo`, `categoryOption`
- `program`, `programStage`, `trackedEntityType`
- `user`, `userGroup`, `userRole`
- `dashboard`, `visualization`, `map`, `report`, `eventChart`, `eventReport`

DHIS2 returns 400 on unknown types — if you get that, check the resource's schema at `/api/schemas/{type}` (the sharing endpoint uses the same names).

## Why this exists

Before this helper, callers typically reached for JSON Patch against `/api/<resource>/<uid>`:

```python
# Old pattern — works but verbose, error-prone, untyped.
await client.patch_raw(
    f"/api/dataSets/{uid}",
    [{"op": "add", "path": "/sharing/users", "value": {admin_uid: {"id": admin_uid, "access": "rwrw----"}}}],
)
```

The typed helper replaces that with one line, and `get_sharing` + builder composition makes additive edits (preserve everything, append one grant) straightforward. See `examples/client/bootstrap_zero_to_data.py` step 5 for the before/after.

::: dhis2w_client.v42.sharing
