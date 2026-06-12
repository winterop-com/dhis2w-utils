# Indicators

Three accessors on `Dhis2Client` for the Indicator triple, matching the canonical DHIS2 resource names:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.indicators` | `/api/indicators` | Computed ratios / counts / percentages over DataElements. CRUD + rename + expression validation. |
| `client.indicator_groups` | `/api/indicatorGroups` | Thematic groupings (coverage, quality, mortality, …). Per-item membership. |
| `client.indicator_group_sets` | `/api/indicatorGroupSets` | Analytics dimensions collecting groups. |

Generic CRUD stays on the generated accessors (`client.resources.indicators`, …). The hand-written accessors add keyword-arg create shapes, partial-update rename, per-item membership shortcuts, and — unique to indicators — an `expression_validate(context="indicator")` pre-flight that catches bad DE references before the create round-trip.

## No `*Spec` builder

Same design call as the DataElement + organisation-unit surfaces: keyword args on the accessor rather than a spec-over-model hop. The Indicator wire shape doesn't need the kind of transformation work that motivates a spec — see the [Legend sets doc](legend-sets.md#legendsetspec-legendspec-the-builder-pattern) for the rule on when reaching for a `*Spec` is the right shape.

## Worked example

```python
async with Dhis2Client(...) as client:
    # Pre-flight the expression so create doesn't fail on a typo.
    desc = await client.indicators.validate_expression("#{s46m5MS0hxu}")
    assert desc.status == "OK", desc.message

    indicator = await client.indicators.create(
        name="BCG coverage",
        short_name="BCG cov",
        indicator_type_uid="JkWynlWMjJR",  # "Number (Factor 1)"
        numerator="#{s46m5MS0hxu}",        # BCG doses given
        denominator="1",
        numerator_description="BCG doses given",
        legend_set_uids=["LsDoseBand1"],
    )

    group = await client.indicator_groups.create(
        name="Immunization coverage",
        short_name="Immun cov",
    )
    await client.indicator_groups.add_members(group.id, indicator_uids=[indicator.id])

    dimension = await client.indicator_group_sets.create(
        name="Programme area",
        short_name="ProgArea",
    )
    await client.indicator_group_sets.add_groups(dimension.id, group_uids=[group.id])
```

Every `create` defaults `annualized=False`; flip to `True` for rate-per-year indicators that should be scaled by period length on aggregation.

## CLI

```bash
d2w metadata list indicators
d2w metadata indicators validate-expression "#{s46m5MS0hxu}"
d2w metadata indicators create \
    --name "BCG coverage" --short-name "BCG cov" \
    --indicator-type JkWynlWMjJR \
    --numerator "#{s46m5MS0hxu}" --denominator "1"
d2w metadata indicator-groups create --name "Immunization" --short-name "Immun"
d2w metadata indicator-groups add-members <GROUP_UID> --indicator <IND_UID>
d2w metadata indicator-group-sets create --name "ProgArea" --short-name "ProgArea"
d2w metadata indicator-group-sets add-groups <SET_UID> --group <GROUP_UID>
```

Every `list` has an `ls` alias; every destructive verb accepts `--yes` / `-y`.

## MCP

Seventeen tools: `metadata_indicator_{list,get,create,rename,validate_expression,set_legend_sets,delete}`, `metadata_indicator_group_{list,get,members,create,add_members,remove_members,delete}`, `metadata_indicator_group_set_{list,get,create,add_groups,remove_groups,delete}`.

::: dhis2w_client.v42.indicators

::: dhis2w_client.v42.indicator_groups

::: dhis2w_client.v42.indicator_group_sets
