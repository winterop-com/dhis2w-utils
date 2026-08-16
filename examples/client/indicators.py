"""Indicator + IndicatorGroup + IndicatorGroupSet round-trip.

Exercises the three hand-written indicator accessors:

* `client.indicators` — create / rename / validate_expression / delete.
* `client.indicator_groups` — CRUD + per-item membership add/remove.
* `client.indicator_group_sets` — CRUD + per-item add_groups / remove_groups.

Validates the numerator expression up-front via
`client.indicators.validate_expression(...)` — catches typos before
the create round-trip.

Usage:
    uv run python examples/client/indicators.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

INDICATOR_TYPE_UID = "JkWynlWMjJR"  # "Number (Factor 1)" seeded on Sierra Leone
BCG_DE_UID = "s46m5MS0hxu"  # BCG doses given


async def main() -> None:
    """Validate expression, create / link / teardown an indicator stack."""
    async with open_client(profile_from_env()) as client:
        desc = await client.indicators.validate_expression(f"#{{{BCG_DE_UID}}}")
        print(f"expression validation: status={desc.status} description={desc.description}")

        indicator = await client.indicators.create(
            name="Example client demo indicator",
            short_name="ExCliDemoInd",
            indicator_type_uid=INDICATOR_TYPE_UID,
            numerator=f"#{{{BCG_DE_UID}}}",
            denominator="1",
            numerator_description="BCG doses",
        )
        print(f"created indicator {indicator.id} name={indicator.name!r}")

        group = await client.indicator_groups.create(
            name="Example client demo indicator group",
            short_name="ExCliDemoGrp",
        )
        await client.indicator_groups.add_members(group.id or "", indicator_uids=[indicator.id or ""])
        members = await client.indicator_groups.list_members(group.id or "", page_size=5)
        print(f"group carries {len(members)} member(s): {[m.name for m in members]}")

        gs = await client.indicator_group_sets.create(
            name="Example client demo indicator dimension",
            short_name="ExCliDemoDim",
        )
        await client.indicator_group_sets.add_groups(gs.id or "", group_uids=[group.id or ""])
        print(f"group set {gs.id} now contains {group.id}")

        renamed = await client.indicators.rename(indicator.id or "", short_name="ExIndv2")
        print(f"renamed indicator short_name -> {renamed.shortName!r}")

        # Cleanup — delete the leaf (indicator) before its container.
        # On v43 deleting an IndicatorGroup cascades to its members
        # (it didn't on v42); leaf-first ordering is correct on both.
        await client.indicators.delete(indicator.id or "")
        await client.indicator_group_sets.delete(gs.id or "")
        await client.indicator_groups.delete(group.id or "")
        print("cleaned up demo indicator + group + group set")


if __name__ == "__main__":
    run_example(main)
