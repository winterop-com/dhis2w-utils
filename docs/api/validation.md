# Validation + predictors

`ValidationAccessor` on `Dhis2Client.validation` + `PredictorsAccessor` on `Dhis2Client.predictors`. Covers the DHIS2 validation-rule + predictor workflow endpoints (expression parse, run, browse persisted results, run predictors). CRUD on the rules / predictors themselves stays on the generated `client.resources.validation_rules` / `client.resources.predictors` accessors plus `client.predictors.list_all` / `create` / `update` / `rename` / `delete`.

## When to reach for it

- Pre-flighting an expression before saving a rule or indicator (the `validation-rule` / `indicator` / `predictor` / `program-indicator` contexts each have their own parser).
- Running validation rules on an org-unit subtree for a date range and collecting violations.
- Browsing persisted `/api/validationResults` (populated by runs with `persist=True`).
- Running predictors over a date range (`run_all` / `run_one(predictor_uid)` / `run_group(group_uid)`).

## Worked example — validate expression + run analysis

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async with open_client(profile_from_env()) as client:
    # 1. Pre-flight an expression. `context` picks the parser DHIS2 uses;
    #    default validates against the generic expression parser.
    description = await client.validation.describe_expression(
        "#{fClA2Erf6IO} > 0",
        context="validation-rule",
    )
    print(f"valid={description.valid}  text={description.description!r}")

    # 2. Run every validation rule on an org-unit subtree for a date range.
    violations = await client.validation.run_analysis(
        org_unit="ImspTQPwCqd",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )
    print(f"{len(violations)} violations")
    for v in violations[:5]:
        print(
            f"  rule={v.validationRuleDescription or v.validationRuleId}  "
            f"pe={v.periodDisplayName or v.periodId}  "
            f"ou={v.organisationUnitDisplayName or v.organisationUnitId}"
        )

    # 3. Browse persisted results (empty unless prior runs had `persist=True`).
    persisted = await client.validation.list_results(page_size=5)
    print(f"{len(persisted)} persisted results")
```

## Worked example — run predictors

```python
async with open_client(profile_from_env()) as client:
    # Run every predictor on the instance over a date range.
    envelope = await client.predictors.run_all(start_date="2025-01-01", end_date="2025-01-31")
    count = envelope.import_count()
    print(f"status={envelope.status}  imported={count.imported if count else '?'}")

    # Or target one predictor by UID.
    envelope = await client.predictors.run_one("PrdSumBCG01", start_date="2024-04-01", end_date="2024-04-30")
    # Or a PredictorGroup.
    envelope = await client.predictors.run_group("PdGImmun001", start_date="2024-04-01", end_date="2024-06-30")
```

## Related examples

- [`examples/client/validation_rules.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/validation_rules.py) — expression validation + run analysis + persisted-result browse.
- [`examples/client/predictors.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/predictors.py) — `run_all` over a date range.
- [`examples/client/validation_rules_predictors.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/validation_rules_predictors.py) — CRUD round-trip across both accessors + their groups.

::: dhis2w_client.v42.validation

::: dhis2w_client.v42.predictors
