# Category options

Three accessors on `Dhis2Client` for the CategoryOption triple — the last of the four analytics-authoring triples:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.category_options` | `/api/categoryOptions` | Disaggregation values (sex, age band, ownership, …). CRUD + rename + validity-window helper. |
| `client.category_option_groups` | `/api/categoryOptionGroups` | Thematic groupings of options. Per-item membership add/remove. |
| `client.category_option_group_sets` | `/api/categoryOptionGroupSets` | Analytics dimensions collecting option groups. |

## Scope

This triple covers the **CategoryOption** layer of DHIS2's disaggregation model. The surrounding `Category` → `CategoryCombo` → `CategoryOptionCombo` authoring is documented separately — they have their own typed accessors and pages: [Categories](categories.md), [Category combos](category-combos.md), [Category option combos](category-option-combos.md), and the one-call [Category combo builder](category-combo-builder.md). The split keeps each page focused on one resource; the builder lets callers materialise the whole tree (categories + options + combo + COCs) in a single idempotent call when that's what they want.

## No `*Spec` builder

Same design call as every other triple: keyword args on the accessor.

## Validity window

`CategoryOption` is the only one of the four triples with a `startDate` / `endDate` bound. DHIS2 rejects data-value entry against options whose window doesn't cover the period being written. The accessor exposes a dedicated helper so callers can narrow / widen the window without reaching for `update(option)`:

```python
async with Dhis2Client(...) as client:
    co = await client.category_options.create(
        name="Calendar Year 2024",
        short_name="CY2024",
        start_date="2024-01-01",
        end_date="2024-12-31",
    )

    # Narrow to H1 later without reconstructing the model.
    co = await client.category_options.set_validity_window(
        co.id,
        start_date="2024-01-01",
        end_date="2024-06-30",
    )
```

Pass `None` on either side of `set_validity_window` to clear that bound — DHIS2 treats an unset window as "always valid".

## CLI

```bash
d2w metadata list categoryOptions
d2w metadata category-options create \
    --name "CY2024" --short-name "CY2024" \
    --start-date 2024-01-01 --end-date 2024-12-31
d2w metadata category-options set-validity <CO_UID> --start-date 2024-01-01 --end-date 2024-06-30
d2w metadata category-option-groups create --name "Calendar years" --short-name "Years"
d2w metadata category-option-groups add-members <GROUP_UID> --category-option <CO_UID>
d2w metadata category-option-group-sets create --name "Reporting calendar" --short-name "Cal"
d2w metadata category-option-group-sets add-groups <SET_UID> --group <GROUP_UID>
```

Every `list` has an `ls` alias; every destructive verb accepts `--yes` / `-y`.

## MCP

18 tools mirroring the CLI surface.

::: dhis2w_client.v42.category_options

::: dhis2w_client.v42.category_option_groups

::: dhis2w_client.v42.category_option_group_sets
