# Metadata CRUD via generated resources

Every DHIS2 metadata type exposed on `/api/schemas` gets a generated `_<Name>Resource` class with full CRUD. `d2w codegen` stamps them into `dhis2w_client/generated/v{NN}/resources.py` and binds them to `Dhis2Client` as `client.resources.<attr_name>` at connect time.

## Surface per resource

```python
class _DataElementResource:
    _path = "/api/dataElements"
    _plural_key = "dataElements"

    async def get(self, uid, *, fields=None) -> DataElement: ...
    async def list(self, *, fields=None, filter=None, order=None) -> list[DataElement]: ...
    async def list_raw(self, *, fields=None, filter=None, order=None, paging=False) -> dict: ...
    async def create(self, item: DataElement) -> dict: ...
    async def update(self, item: DataElement) -> dict: ...
    async def delete(self, uid: str) -> dict: ...
```

## End-to-end usage

```python
from dhis2w_client import BasicAuth, Dhis2Client
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
from dhis2w_client.generated.v42.schemas.data_element import DataElement, Reference

async with Dhis2Client(
    base_url="https://play.im.dhis2.org/dev",
    auth=BasicAuth("system", "System123"),
) as client:
    # typed list
    elements = await client.resources.data_elements.list(fields="id,name")

    # typed get
    one = await client.resources.data_elements.get("abc123")

    # typed create — CONSTANT fields are StrEnums; bare strings also work.
    new = DataElement(
        id="abc12345678",
        name="Test DE",
        shortName="Test",
        valueType=ValueType.NUMBER,
        domainType=DataElementDomain.AGGREGATE,
        aggregationType=AggregationType.SUM,
        categoryCombo=Reference(id=cc_uid),
    )
    response = await client.resources.data_elements.create(new)

    # typed update — reads item.id for the URL
    one.name = "Renamed"
    await client.resources.data_elements.update(one)

    # delete
    await client.resources.data_elements.delete("abc123")
```

Enum classes live under `dhis2w_client.generated.v{N}.enums`. Each is a `StrEnum` so `ValueType.NUMBER == "NUMBER"` is true and a bare string passed to a pydantic constructor still validates.

## `list` vs `list_raw`

- **`list(...)`** — parses the response's plural key into typed models, returns `list[Model]`. Paging is forced off (single request). Simple, strongly typed.
- **`list_raw(..., paging=True)`** — returns the raw DHIS2 dict including the `pager` block (`{"page", "pageSize", "total", "pageCount"}`). Use this when you need pager metadata, or when you want to drive your own page loop.

A typed paging helper (`list_paged`) that yields models across pages will land when a real use-case surfaces. Today, `list(paging=False)` covers most workflows.

## Create/update request bodies

Both `create` and `update` dump the pydantic model with `model_dump(by_alias=True, exclude_none=True)`. Because generated models use camelCase field names directly (not aliases), this is effectively `exclude_none` — any field left as `None` is stripped before POST/PUT. This matches what DHIS2 expects: only send the fields you care about.

`update` requires `item.id` to be populated — `ValueError` is raised otherwise. DHIS2's PUT endpoint is a **full replace**, not a partial patch; callers should fetch-modify-put rather than PUTting partial payloads.

## What's *not* in the generated surface

- **PATCH** — DHIS2 supports RFC 6902 JSON Patch on some endpoints. We don't generate for it; use `client.put_raw` manually with a patched payload if needed.
- **Bulk `/api/metadata`** — that's a multi-type import bundle, not a per-resource operation. It gets a dedicated helper in `dhis2w-client/metadata_import.py` (deferred).
- **`/api/metadata` GET with schemas mixed into one response** — same story.
- **Sharing (`/api/sharing?type=...`)** — a separate endpoint that operates across metadata types; deferred.
- **Tracker** — lives at `/api/tracker/*` and has its own API shape. Hand-written module.
- **Data values** — `/api/dataValueSets` and `/api/dataValues`. Hand-written module.
- **Analytics** — `/api/analytics`. Hand-written module.

## Design choices

- **Typed `list` defaults to `paging=false`** — simplest mental model, single round trip. If you need pagination, drop to `list_raw`.
- **`create`/`update` return raw dicts**, not parsed models — DHIS2 returns an import-summary payload (`{status, stats, response}`) that isn't the resource shape. Parsing it into a model would hide detail; leaving it raw is honest.
- **`update` raises on missing id** — rather than POSTing to a URL without a UID. Catching the bug at the pydantic object level, not silently at HTTP level.
- **`model_dump(by_alias=True, exclude_none=True)`** — camelCase already matches DHIS2's wire format, so by_alias is technically a no-op. Keeping it anyway so if aliases ever appear (e.g. for reserved words), serialisation stays correct.
