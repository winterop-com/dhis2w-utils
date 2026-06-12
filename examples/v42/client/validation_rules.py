"""Validate DHIS2 expressions, run validation analysis, browse results — `client.validation`.

Covers the read + run surface of `dhis2w-core`'s validation plugin
(`d2w maintenance validation ...`). CRUD on the rules themselves stays
on the generic metadata surface (`d2w metadata list validationRules`).

What this example exercises:

1. **Expression validation** — `/api/expressions/description` + per-context
   variants (`validation-rule`, `indicator`, `predictor`, `program-indicator`).
   Useful as a pre-save check before creating a VR or indicator: parses
   the formula and reports missing references.
2. **`run_analysis`** — `POST /api/dataAnalysis/validationRules`. Evaluates
   every validation rule on the org-unit sub-tree for a date range and
   returns violations. Synchronous; no task polling.
3. **`list_results`** — browse DHIS2's persistent `/api/validationResults`
   table (populated by runs with `persist=True`).

Predictor runs live in the sibling `predictors.py` example — same plugin
namespace (`d2w maintenance ...`) but a different engine that generates
data values, not violations.

Usage:
    uv run python examples/v42/client/validation_rules.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Validate an expression, run an analysis, list any persisted results."""
    async with open_client(profile_from_env()) as client:
        # 1. Expression validation — a valid DE ref + a bogus one.
        print("--- expression validation ---")
        ok = await client.validation.describe_expression("#{fClA2Erf6IO}")
        print(f"  valid expression: {ok.valid} — description={ok.description!r}")

        bad = await client.validation.describe_expression("#{noSuchDeUid}")
        print(f"  invalid expression: {bad.valid} — message={bad.message!r}")

        # Per-context (validation-rule) — same DHIS2 parser as the VR engine uses.
        vr_ctx = await client.validation.describe_expression(
            "#{fClA2Erf6IO} > 0",
            context="validation-rule",
        )
        print(f"  VR-context: {vr_ctx.valid} — description={vr_ctx.description!r}")

        # 2. Run validation analysis (seeded instance often has 0 violations).
        print("\n--- validation analysis ---")
        violations = await client.validation.run_analysis(
            org_unit="ImspTQPwCqd",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        print(f"  {len(violations)} violations on the seeded stack")
        for v in violations[:5]:
            print(
                f"    rule={v.validationRuleDescription or v.validationRuleId}  "
                f"pe={v.periodDisplayName or v.periodId}  "
                f"ou={v.organisationUnitDisplayName or v.organisationUnitId}  "
                f"left={v.leftSideValue} {v.operator} right={v.rightSideValue}"
            )

        # 3. Browse persisted results (empty unless some run had `persist=True`).
        print("\n--- persisted validation results ---")
        results = await client.validation.list_results(page_size=5)
        print(f"  {len(results)} persisted results")


if __name__ == "__main__":
    run_example(main)
