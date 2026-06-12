"""ValidationRule + Predictor authoring round-trip.

The CRUD flip side of `d2w maintenance validation run` + `predictors
run`. Creates a throw-away rule + predictor on the first aggregate DE
found, groups each, then tears everything down.

Usage:
    uv run python examples/v41/client/validation_rules_predictors.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client.generated.v42.enums import Importance, MissingValueStrategy, Operator
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Round-trip a ValidationRule + group, then a Predictor + group."""
    async with open_client(profile_from_env()) as client:
        data_elements = await client.data_elements.list_all(page_size=1)
        if not data_elements:
            print("need at least one data element on the instance to run this example")
            return
        de_uid = data_elements[0].id or ""
        print(f"using data element {de_uid}")

        levels = await client.organisation_unit_levels.list_all()
        level_uid = (levels[-1].id or "") if levels else ""

        rule = await client.validation_rules.create(
            name="Example client demo rule",
            short_name="ExCliDemoVR",
            left_expression=f"#{{{de_uid}}}",
            operator=Operator.GREATER_THAN_OR_EQUAL_TO,
            right_expression="0",
            importance=Importance.MEDIUM,
            missing_value_strategy=MissingValueStrategy.SKIP_IF_ALL_VALUES_MISSING,
            organisation_unit_levels=[4],
        )
        print(f"created validationRule {rule.id}")

        rule_group = await client.validation_rule_groups.create(
            name="Example client demo rule group",
            short_name="ExCliDemoVRG",
        )
        rule_group = await client.validation_rule_groups.add_members(
            rule_group.id or "",
            validation_rule_uids=[rule.id or ""],
        )
        print(f"group {rule_group.id} carries {len(rule_group.validationRules or [])} rule(s)")

        predictor = await client.predictors.create(
            name="Example client demo predictor",
            short_name="ExCliDemoPrd",
            expression=f"#{{{de_uid}}}",
            output_data_element_uid=de_uid,
            sequential_sample_count=3,
            organisation_unit_level_uids=[level_uid] if level_uid else None,
        )
        print(f"created predictor {predictor.id}")

        predictor_group = await client.predictor_groups.create(
            name="Example client demo predictor group",
            short_name="ExCliDemoPDG",
        )
        predictor_group = await client.predictor_groups.add_members(
            predictor_group.id or "",
            predictor_uids=[predictor.id or ""],
        )
        print(f"group {predictor_group.id} carries {len(predictor_group.predictors or [])} predictor(s)")

        # Cleanup
        await client.predictor_groups.delete(predictor_group.id or "")
        await client.predictors.delete(predictor.id or "")
        await client.validation_rule_groups.delete(rule_group.id or "")
        await client.validation_rules.delete(rule.id or "")
        print("cleaned up demo rule + predictor + groups")


if __name__ == "__main__":
    run_example(main)
