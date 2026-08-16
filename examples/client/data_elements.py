"""DataElement + DataElementGroup + DataElementGroupSet round-trip.

Exercises the three hand-written accessors:

* `client.data_elements` — create / rename / set_legend_sets / delete.
* `client.data_element_groups` — CRUD + per-item membership add/remove.
* `client.data_element_group_sets` — CRUD + per-item add_groups / remove_groups.

Creates a throw-away DE, a group, a group set, wires them together,
verifies the result, then tears everything down so the example is
idempotent.

Usage:
    uv run python examples/client/data_elements.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import NoProfileError, open_client, profile_from_env_raw


async def main() -> None:
    """Create DE/DEG/DEGS, link, then clean up."""
    profile = profile_from_env_raw()
    if profile is None:
        raise NoProfileError("set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD)")
    async with open_client(profile) as client:
        de = await client.data_elements.create(
            name="Example client demo DE",
            short_name="ExCliDemoDE",
            value_type="NUMBER",
        )
        print(f"created DE {de.id} name={de.name!r} valueType={de.valueType}")

        group = await client.data_element_groups.create(
            name="Example client demo DE group",
            short_name="ExCliDemoGrp",
        )
        print(f"created group {group.id}")

        await client.data_element_groups.add_members(group.id or "", data_element_uids=[de.id or ""])
        members = await client.data_element_groups.list_members(group.id or "", page_size=5)
        print(f"group now carries {len(members)} member(s): {[m.name for m in members]}")

        group_set = await client.data_element_group_sets.create(
            name="Example client demo DE dimension",
            short_name="ExCliDemoDim",
        )
        await client.data_element_group_sets.add_groups(
            group_set.id or "",
            group_uids=[group.id or ""],
        )
        print(f"group set {group_set.id} now contains {group.id}")

        # Partial-update: rename the DE. Should round-trip.
        renamed = await client.data_elements.rename(de.id or "", short_name="ExCliDEv2")
        print(f"renamed DE short_name -> {renamed.shortName!r}")

        # Cleanup
        await client.data_element_group_sets.delete(group_set.id or "")
        await client.data_element_groups.delete(group.id or "")
        await client.data_elements.delete(de.id or "")
        print("cleaned up demo DE + group + group set")


if __name__ == "__main__":
    run_example(main)
