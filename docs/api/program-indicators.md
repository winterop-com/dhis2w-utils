# Program indicators

Two accessors on `Dhis2Client` for the ProgramIndicator authoring surface:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.program_indicators` | `/api/programIndicators` | Computed values over tracker event / enrollment data. CRUD + rename + expression validation. |
| `client.program_indicator_groups` | `/api/programIndicatorGroups` | Thematic groupings of program indicators. Per-item membership add/remove. |

Unlike the aggregate `indicators` surface, DHIS2 does **not** expose a `programIndicatorGroupSet` resource — so this is a **pair** rather than the `X / XGroup / XGroupSet` triple used by data elements, indicators, organisation units, and (soon) category options.

## No `*Spec` builder

Continues the design call from the org-unit / DE / indicator surfaces: keyword args on the accessor rather than a spec-over-model hop. The ProgramIndicator wire shape doesn't need the kind of transformation work that motivates a spec — see the [Legend sets doc](legend-sets.md#legendsetspec-legendspec-the-builder-pattern) for the rule on when reaching for a `*Spec` is the right shape.

## Expression shape

Program-indicator expressions reference event / enrollment data elements + tracked-entity attributes:

- `#{<program_uid>.<de_uid>}` — one event's data-element value.
- `A{<tea_uid>}` — the enrolled tracked entity's attribute value.
- `V{<program_variable>}` — program-context variables (`event_date`, `enrollment_date`, `org_unit`, `event_count`, etc.).

Arithmetic + aggregation operators apply as for aggregate indicators. The optional `filter` expression is a **boolean** predicate that narrows which rows the main `expression` runs over.

## Worked example

```python
async with Dhis2Client(...) as client:
    # Pre-flight so DE / TEA / program UID typos surface as a 200 OK
    # with status FAILED instead of a 409 create rejection.
    desc = await client.program_indicators.validate_expression(
        "#{IpHINAT79UW.s46m5MS0hxu}",
    )
    assert desc.status == "OK", desc.message

    pi = await client.program_indicators.create(
        name="BCG per enrollment",
        short_name="BCG per enr",
        program_uid="IpHINAT79UW",
        expression="#{IpHINAT79UW.s46m5MS0hxu}",
        analytics_type="EVENT",
        filter_expression="A{child_age_in_months} < 12",
    )

    group = await client.program_indicator_groups.create(
        name="Immunisation program indicators",
        short_name="Immun PI",
    )
    await client.program_indicator_groups.add_members(
        group.id,
        program_indicator_uids=[pi.id],
    )
```

`analytics_type` picks the aggregation granularity: `EVENT` aggregates per event row; `ENROLLMENT` aggregates per enrolled tracked entity.

## CLI

```bash
dhis2 metadata list programIndicators --filter program.id:eq:IpHINAT79UW
dhis2 metadata program-indicators validate-expression "#{IpHINAT79UW.s46m5MS0hxu}"
dhis2 metadata program-indicators create \
    --name "BCG per enrollment" --short-name "BCG per enr" \
    --program IpHINAT79UW \
    --expression "#{IpHINAT79UW.s46m5MS0hxu}" \
    --analytics-type EVENT
dhis2 metadata program-indicator-groups create --name "Immun PI" --short-name "Immun"
dhis2 metadata program-indicator-groups add-members <GROUP_UID> --program-indicator <PI_UID>
```

Every `list` has an `ls` alias; every destructive verb accepts `--yes` / `-y`.

## MCP

14 tools: `metadata_program_indicator_{list,get,create,rename,validate_expression,set_legend_sets,delete}`, `metadata_program_indicator_group_{list,get,members,create,add_members,remove_members,delete}`.

::: dhis2w_client.v42.program_indicators

::: dhis2w_client.v42.program_indicator_groups
