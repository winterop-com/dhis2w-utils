# Validation rules + predictors

The CRUD flip side of `d2w maintenance validation run` + `d2w maintenance predictors run`. Both domains now expose authoring surfaces alongside the run endpoints:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.validation_rules` | `/api/validationRules` | Compare two DHIS2 expressions (`leftSide` vs `rightSide`) under a chosen operator; fire violations when the comparison fails. |
| `client.validation_rule_groups` | `/api/validationRuleGroups` | Collect rules into named runs for `maintenance validation run --group`. |
| `client.predictors` | `/api/predictors` | CRUD + run. Generates synthetic data values from an expression over historical samples. |
| `client.predictor_groups` | `/api/predictorGroups` | Collect predictors into named runs for `maintenance predictors run --group`. |

## Expression sides are nested objects

`ValidationRule.leftSide` / `rightSide` and `Predictor.generator` are all DHIS2 `Expression` sub-objects. Each carries at least an `expression` string + `missingValueStrategy` flag. The accessors assemble the wrapper from plain kwargs so callers hand in the expression text directly:

```python
rule = await client.validation_rules.create(
    name="BCG doses > 0",
    short_name="BCGgt0",
    left_expression="#{deBCG000001}",
    operator=Operator.GREATER_THAN,
    right_expression="0",
    importance=Importance.HIGH,
    organisation_unit_levels=[4],  # facility level
)

predictor = await client.predictors.create(
    name="BCG 3-month rolling average",
    short_name="BCG3mAvg",
    expression="#{deBCG000001}",
    output_data_element_uid="deOutput0001",
    sequential_sample_count=3,
    organisation_unit_level_uids=["ouLvlFac001"],
)
```

## `organisationUnitLevels` asymmetry (upstream quirk)

Both models carry `organisationUnitLevels` but with different shapes:

- `ValidationRule.organisationUnitLevels` — list of integer level numbers (`[4]`).
- `Predictor.organisationUnitLevels` — list of `OrganisationUnitLevel` references (`[{"id": uid}]`).

The accessors expose this as `organisation_unit_levels: list[int]` vs `organisation_unit_level_uids: list[str]` respectively, matching DHIS2's wire shape. DHIS2 v42 returns a 500 on predictor create without valid level references.

## `missingValueStrategy`

Defaults to `SKIP_IF_ALL_VALUES_MISSING` on both sides — rows where every operand is null are excluded from the comparison instead of counting as a violation. Flip to `NEVER_SKIP` to fail any row missing an operand.

## No `*Spec` builder

Same call as every other authoring accessor: keyword args. Continues the spec-audit data point.

## CLI

```bash
# ValidationRule + group
d2w metadata validation-rules create \
    --name "BCG gt zero" --short-name BCGgt0 \
    --left "#{deBCG000001}" --operator greater_than --right "0" \
    --importance HIGH --ou-level 4
d2w metadata validation-rule-groups create --name "BCG rules"
d2w metadata validation-rule-groups add-members <GRP_UID> --rule <RULE_UID>

# Predictor + group
d2w metadata predictors create \
    --name "BCG 3m avg" --short-name BCG3m \
    --expression "#{deBCG000001}" --output deOutput0001 \
    --sequential 3 --ou-level ouLvlFac001
d2w metadata predictor-groups create --name "BCG predictors"
d2w metadata predictor-groups add-members <PDG_UID> --predictor <PRD_UID>
```

Every `list` has an `ls` alias; every destructive verb accepts `--yes` / `-y`.

## MCP

24 tools mirroring the CLI: `metadata_validation_rule_*` (list / get / create / rename / delete), `metadata_validation_rule_group_*` (list / get / members / create / add-members / remove-members / delete), `metadata_predictor_*` (list / get / create / rename / delete), `metadata_predictor_group_*` (list / get / members / create / add-members / remove-members / delete).

## Running them

Creating the rule or predictor is decoupled from running it:

- `d2w maintenance validation run --group <GRP_UID> --ds <DATASET_UID> --start-date … --end-date …`
- `d2w maintenance predictors run --group <PDG_UID> --start-date … --end-date …`

See the [maintenance plugin](../architecture/maintenance-plugin.md) for the run-side reference.

::: dhis2w_client.v42.validation_rules

::: dhis2w_client.v42.validation_rule_groups

::: dhis2w_client.v42.predictors

::: dhis2w_client.v42.predictor_groups
