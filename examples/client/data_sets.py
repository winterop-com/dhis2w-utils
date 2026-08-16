"""DataSet + Section authoring round-trip.

Two DataElements get wired into a throw-away DataSet, then grouped
and ordered inside a Section. The accessor API matches the CLI
verbs; DataSetElements carry the optional per-set CategoryCombo
override, Sections carry the ordered DE list for the data-entry app.

Usage:
    uv run python examples/client/data_sets.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Create a DataSet, attach two DEs, order them inside a Section, tear everything down."""
    async with open_client(profile_from_env()) as client:
        # Round up two DEs off the instance to use as section members.
        data_elements = await client.data_elements.list_all(page_size=2)
        if len(data_elements) < 2:
            print("need at least two data elements on the instance to run this example")
            return
        de_a = data_elements[0].id or ""
        de_b = data_elements[1].id or ""
        print(f"using data elements {de_a} + {de_b}")

        data_set = await client.data_sets.create(
            name="Example client demo DataSet",
            short_name="ExCliDS",
            period_type="Monthly",
            code="EX_CLI_DEMO_DS",
            open_future_periods=2,
            expiry_days=10,
            timely_days=3,
        )
        ds_uid = data_set.id or ""
        print(f"created dataSet {ds_uid} name={data_set.name!r} period={data_set.periodType}")

        # Attach both DEs to the DataSet.
        await client.data_sets.add_element(ds_uid, de_a)
        await client.data_sets.add_element(ds_uid, de_b)
        data_set = await client.data_sets.get(ds_uid)
        print(f"dataSet now carries {len(data_set.dataSetElements or [])} DE(s)")

        # Create a Section with the two DEs seeded in order, then flip them.
        section = await client.sections.create(
            name="Example client demo Section",
            data_set_uid=ds_uid,
            sort_order=1,
            data_element_uids=[de_a, de_b],
        )
        sec_uid = section.id or ""
        print(f"created section {sec_uid} with {len(section.dataElements or [])} DE(s)")

        section = await client.sections.reorder(sec_uid, [de_b, de_a])
        print(f"reordered section: {[ref['id'] for ref in (section.model_dump().get('dataElements') or [])]}")

        # Cleanup
        await client.sections.delete(sec_uid)
        await client.data_sets.remove_element(ds_uid, de_a)
        await client.data_sets.remove_element(ds_uid, de_b)
        await client.data_sets.delete(ds_uid)
        print("cleaned up demo dataSet + section")


if __name__ == "__main__":
    run_example(main)
