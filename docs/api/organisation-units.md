# Organisation units

Four accessors on `Dhis2Client` cover the DHIS2 `X / XGroup / XGroupSet` triple for the organisation-unit hierarchy, plus per-level naming:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.organisation_units` | `/api/organisationUnits` | Hierarchy nodes — parent / children / descendants / move / create / delete |
| `client.organisation_unit_groups` | `/api/organisationUnitGroups` | Orthogonal groupings (public/private, urban/rural, …) + member add/remove |
| `client.organisation_unit_group_sets` | `/api/organisationUnitGroupSets` | Analytics dimensions that collect groups (e.g. "Facility Ownership") |
| `client.organisation_unit_levels` | `/api/organisationUnitLevels` | Per-depth naming — give level 2 a human label like "Province" |

Generic CRUD is still available on the generated accessors (`client.resources.organisation_units` and friends). The hand-written accessors layer workflow primitives — bounded subtree walks, per-item membership POST/DELETE shortcuts, `rename_by_level` — that the generated CRUD can't express in one call.

## Naming convention

The CLI, MCP tools, and Python attribute names mirror the DHIS2 API paths 1:1 (camelCase → kebab-case / snake_case):

| DHIS2 | CLI | MCP tool prefix | Client attribute |
| --- | --- | --- | --- |
| `/api/organisationUnits` | `dhis2 metadata organisation-units …` | `metadata_organisation_unit_*` | `client.organisation_units` |
| `/api/organisationUnitGroups` | `dhis2 metadata organisation-unit-groups …` | `metadata_organisation_unit_group_*` | `client.organisation_unit_groups` |
| `/api/organisationUnitGroupSets` | `dhis2 metadata organisation-unit-group-sets …` | `metadata_organisation_unit_group_set_*` | `client.organisation_unit_group_sets` |
| `/api/organisationUnitLevels` | `dhis2 metadata organisation-unit-levels …` | `metadata_organisation_unit_level_*` | `client.organisation_unit_levels` |

One rule — "lowercase the DHIS2 resource name, hyphenate or underscore the camelCase boundary" — so anyone who knows the API URL can guess every other surface. The same rule will apply to every future `X / XGroup / XGroupSet` triple (data elements, indicators, category options, program indicators).

## No `*Spec` builders

Unlike the legend-set / map / visualisation accessors, the organisation-unit accessors don't ship dedicated `*Spec` classes. The argument is that OU + group + level creates are narrow enough (5–10 meaningful fields) that keyword args on the accessor are cleaner than a spec-over-model hop. Callers that need fine-grained control over the full generated `OrganisationUnit` model still have `update(unit)` — mutate the returned model, pass it back.

This sits on the kwargs side of the resolved spec-vs-kwargs rule documented on the [Legend sets doc](legend-sets.md#legendsetspec-legendspec-the-builder-pattern): a `*Spec` is justified only where the wire shape needs transformation the generated model can't carry (chart-type-aware placement, enum fan-out, inline children with synthesised UIDs). OUs need none of that, so kwargs win.

## Tree navigation

```python
async with Dhis2Client(...) as client:
    roots = await client.organisation_units.list_by_level(1)
    subtree = await client.organisation_units.list_descendants(
        roots[0].id,
        max_depth=2,
    )
    for unit in subtree:
        print(f"L{unit.hierarchyLevel}  {unit.name}  ({unit.id})")
```

`list_descendants` is breadth-first — the returned list opens with the root, then every direct child, then grandchildren. `max_depth=0` returns just the root.

## Group + group-set membership

```python
group = await client.organisation_unit_groups.get("CXw2yu5fodb")
members = await client.organisation_unit_groups.list_members(group.id, page_size=200)

# Move five facilities into a different grouping without a full PUT
await client.organisation_unit_groups.add_members(
    "CXw2yu5fodb",
    ou_uids=[f.id for f in members[:5]],
)

# Wire the group into a new analytics dimension
group_set = await client.organisation_unit_group_sets.create(
    name="Provincial oversight",
    short_name="ProvOversight",
)
await client.organisation_unit_group_sets.add_groups(
    group_set.id,
    group_uids=[group.id],
)
```

Both `add_members` / `add_groups` use the per-item `POST /<resource>/{uid}/<inverse>/{target_uid}` DHIS2 shortcut so the server never sees a full-collection payload. That keeps edits atomic and avoids the "losing members on round-trip" class of bug where a naive PUT drops rows that changed under you.

## Naming levels

DHIS2 auto-creates one `OrganisationUnitLevel` row per depth the first time an OU is stored at that level. They arrive without human labels — renaming them to `Country`, `Province`, `District`, `Facility` is the main write operation:

```python
await client.organisation_unit_levels.rename_by_level(2, name="Province")
await client.organisation_unit_levels.rename_by_level(3, name="District")
await client.organisation_unit_levels.rename_by_level(4, name="Facility")
```

The CLI mirrors this:

```bash
dhis2 metadata list organisationUnitLevels
dhis2 metadata organisation-unit-levels rename 2 --by-level --name Province
```

::: dhis2w_client.v42.organisation_units

::: dhis2w_client.v42.organisation_unit_groups

::: dhis2w_client.v42.organisation_unit_group_sets

::: dhis2w_client.v42.organisation_unit_levels
