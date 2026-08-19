# Category combos

`client.category_combos` — CRUD over `/api/categoryCombos`. A `CategoryCombo` is the actual disaggregation attached to a `DataElement` (or `DataSet`); it's defined as a cross-product of `Category` records. The server materialises the cross-product as a matrix of `CategoryOptionCombo` rows.

```python
async with Dhis2Client(...) as client:
    cc = await client.category_combos.create(
        name="Sex x Age",
        category_uids=["sexCat0001U", "ageCat0001U"],
    )
```

## v43 caveat — manual COC matrix regeneration

DHIS2 regenerates the `CategoryOptionCombo` matrix in the background on every `CategoryCombo` save, and on a cold instance a large combo can take tens of seconds to land. The accessor exposes `wait_for_coc_generation(uid, expected_count, ...)`, which polls until the matrix reaches the expected count.

```python
cc = await client.category_combos.create(name="Sex x Age", category_uids=[...])
# v43: kick the maintenance trigger; on v42 / v41 this is a no-op.
await client.category_combos.wait_for_coc_generation(cc.id, expected_count=4)
```

Worked example: [`examples/client/v43/category_combo_coc_regen.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/category_combo_coc_regen.py).

For the higher-level "build everything in one call" helper see [Category combo builder](category-combo-builder.md).

::: dhis2w_client.v42.category_combos
