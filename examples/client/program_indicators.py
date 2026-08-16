"""ProgramIndicator + ProgramIndicatorGroup round-trip via the hand-written accessors.

DHIS2 does NOT expose a `ProgramIndicatorGroupSet` resource, so the
program-indicator authoring surface is a *pair* rather than the `X /
XGroup / XGroupSet` triple used by data elements / indicators / org
units. This example creates a throw-away PI, attaches it to a fresh
group, then tears everything down.

Usage:
    uv run python examples/client/program_indicators.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

CHILD_PROGRAM = "IpHINAT79UW"  # Seeded Sierra Leone Child Programme (tracker)
BCG_DE = "s46m5MS0hxu"  # BCG doses given — seeded DE


async def main() -> None:
    """Validate expression, create PI + group, link, clean up."""
    async with open_client(profile_from_env()) as client:
        desc = await client.program_indicators.validate_expression(
            f"#{{{CHILD_PROGRAM}.{BCG_DE}}}",
        )
        print(f"expression validation: status={desc.status} description={desc.description}")

        pi = await client.program_indicators.create(
            name="Example client demo PI",
            short_name="ExCliDemoPI",
            program_uid=CHILD_PROGRAM,
            expression=f"#{{{CHILD_PROGRAM}.{BCG_DE}}}",
            analytics_type="EVENT",
        )
        print(f"created programIndicator {pi.id} name={pi.name!r}")

        group = await client.program_indicator_groups.create(
            name="Example client demo PI group",
            short_name="ExCliDemoGrp",
        )
        await client.program_indicator_groups.add_members(
            group.id or "",
            program_indicator_uids=[pi.id or ""],
        )
        members = await client.program_indicator_groups.list_members(group.id or "", page_size=5)
        print(f"group carries {len(members)} member(s): {[m.name for m in members]}")

        renamed = await client.program_indicators.rename(pi.id or "", short_name="ExPIv2")
        print(f"renamed PI short_name -> {renamed.shortName!r}")

        # Cleanup
        await client.program_indicator_groups.delete(group.id or "")
        await client.program_indicators.delete(pi.id or "")
        print("cleaned up demo PI + group")


if __name__ == "__main__":
    run_example(main)
