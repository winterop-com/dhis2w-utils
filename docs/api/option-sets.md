# Option sets

`client.option_sets` — CRUD + bulk-sync over `/api/optionSets`. An `OptionSet` is a controlled-vocabulary list of `Option` values (e.g. "Yes / No / Unknown"); referenced by `DataElement.optionSet` and `TrackedEntityAttribute.optionSet` to constrain captured values.

```python
async with Dhis2Client(...) as client:
    # Declarative spec — name + options, server fills in the rest.
    report = await client.option_sets.sync(
        name="Yes/No/Unknown",
        options=[
            OptionSpec(code="Y", name="Yes"),
            OptionSpec(code="N", name="No"),
            OptionSpec(code="U", name="Unknown"),
        ],
    )
    # `report` is an `UpsertReport` listing which options were created / updated / removed.
```

The `sync()` helper diffs the desired option list against the live set and issues exactly the writes needed — useful for CI-driven option-list management. Individual `list_all` / `get` / `create` / `update` / `delete` verbs follow the standard accessor pattern.

Worked example: [`examples/client/options_integration.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/options_integration.py).

::: dhis2w_client.v42.option_sets
