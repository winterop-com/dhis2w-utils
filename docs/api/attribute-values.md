# Attribute values

`client.attribute_values` — read + write the `attributeValues` collection that every `Identifiable` metadata resource carries. DHIS2 lets implementations stamp arbitrary typed `Attribute` records onto any metadata (program, data element, indicator, ...) — the accessor is the typed entry point for that pattern.

```python
async with Dhis2Client(...) as client:
    # Read every attribute value across one resource.
    values = await client.attribute_values.list_for(
        resource="dataElements",
        uid="dataEl0001U",
    )
    # Find a specific one by Attribute UID.
    one = await client.attribute_values.find(
        resource="dataElements",
        uid="dataEl0001U",
        attribute_uid="legacyId001",
    )
    # Set / overwrite.
    await client.attribute_values.set(
        resource="dataElements",
        uid="dataEl0001U",
        attribute_uid="legacyId001",
        value="DE-123",
    )
```

Works against every resource that has an `attributeValues` field (the bulk of `/api/{resource}` endpoints). Worked example: [`examples/client/attribute_values.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/attribute_values.py).

::: dhis2w_client.v42.attribute_values
