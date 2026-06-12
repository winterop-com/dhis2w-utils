# Data sets

Two accessors on `Dhis2Client` cover the aggregate-capture parent and its optional section tree:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.data_sets` | `/api/dataSets` | Aggregate-capture parent: period type + ordered `DataSetElements` + optional sections + per-OU assignment. |
| `client.sections` | `/api/sections` | Ordered grouping of DEs inside one DataSet for the data-entry app. |

A DataSet is a collection of `DataElement`s captured together for one period (monthly immunisation tally, weekly commodity stock, etc.). Sections optionally group + order the DEs inside the DataSet for rendering.

## DataSetElements are a join table

Wiring a `DataElement` into a `DataSet` isn't a simple ref list — the join is a `DataSetElement` that carries an optional per-set `CategoryCombo` override (the common pattern where one DE is captured under different disaggregations per set). The accessor's `add_element` / `remove_element` helpers round-trip the full DataSet, mutate `dataSetElements`, and PUT it back so the override travels without a dedicated endpoint:

```python
async with Dhis2Client(...) as client:
    ds = await client.data_sets.create(
        name="ANC Monthly",
        short_name="ANCm",
        period_type="Monthly",
        open_future_periods=2,
        expiry_days=10,
    )
    await client.data_sets.add_element(ds.id, "deFirstVisit")
    await client.data_sets.add_element(ds.id, "deSecondVisit", category_combo_uid="ccAgeGroup")
```

## Sections carry an ordered DE list

A DataSet can be sectionless (flat list) or ship multiple sections. The Data Entry app renders sections in `sortOrder` ascending; inside each section, DEs render in the order they appear in `Section.dataElements[]`.

`add_element` appends by default, `position=0` inserts at the front, `reorder` replaces the whole list in one PUT:

```python
section = await client.sections.create(
    name="Vaccination",
    data_set_uid=ds.id,
    sort_order=1,
    data_element_uids=["deFirstVisit", "deSecondVisit"],
)
section = await client.sections.reorder(section.id, ["deSecondVisit", "deFirstVisit"])
```

## No `*Spec` builder

Same call as the authoring triples — keyword args on the accessor.

## Per-OU assignment

`DataSet.organisationUnits[]` is not yet exposed through a dedicated helper. The `add-to-ou` / `remove-from-ou` surface is on the roadmap as the natural next DataSet PR. For now, attach OUs via `client.data_sets.update(ds)` after mutating the model, or via `metadata import`.

## Default `CategoryCombo`

DHIS2 rejects DataSets without a `categoryCombo`. Omit `category_combo_uid` on `create` to fall back to the instance's default combo (`client.system.default_category_combo_uid()`) — the common case.

## CLI

```bash
d2w metadata list dataSets --period-type Monthly
d2w metadata data-sets create \
    --name "ANC Monthly" --short-name "ANCm" --period-type Monthly \
    --open-future-periods 2 --expiry-days 10
d2w metadata data-sets add-element <DS_UID> <DE_UID>
d2w metadata data-sets add-element <DS_UID> <DE_UID> --category-combo <CC_UID>
d2w metadata sections create \
    --name "Vaccination" --data-set <DS_UID> --sort-order 1 \
    --data-element <DE_A> --data-element <DE_B>
d2w metadata sections reorder <SECTION_UID> <DE_B> <DE_A>
```

Every `list` has an `ls` alias; every destructive verb accepts `--yes` / `-y`.

## MCP

15 tools (`metadata_data_set_*` + `metadata_section_*`) mirror the CLI surface.

::: dhis2w_client.v42.data_sets

::: dhis2w_client.v42.sections
