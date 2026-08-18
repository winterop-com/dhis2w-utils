"""Predictor authoring round-trip.

The CRUD flip side of `d2w maintenance predictors run`. Creates a
throw-away predictor writing into the first aggregate DE found (a real
predictor writes into a dedicated output DE), groups it, then tears
everything down.

Usage:
    uv run python examples/client/predictors.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Round-trip a Predictor and its group."""
    async with open_client(profile_from_env()) as client:
        data_elements = await client.data_elements.list_all(page_size=1)
        if not data_elements:
            print("need at least one data element on the instance to run this example")
            return
        de_uid = data_elements[0].id or ""
        print(f"using data element {de_uid}")

        levels = await client.organisation_unit_levels.list_all()
        level_uid = (levels[-1].id or "") if levels else ""

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

        await client.predictor_groups.delete(predictor_group.id or "")
        await client.predictors.delete(predictor.id or "")
        print("cleaned up demo predictor + group")


if __name__ == "__main__":
    run_example(main)
