"""Tracker schema authoring — step 2: Program + PTEA + OU round-trip.

Creates a throw-away Person TET + one TEA, then a tracker Program
that binds them together, wires the TEA into the enrollment form,
scopes the program to the root OU, then tears everything down.

Usage:
    uv run python examples/client/tracker_programs.py
"""

from __future__ import annotations

from _runner import run_example

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import ValueType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Round-trip a Program with a TEA + OU linked in."""
    async with open_client(profile_from_env()) as client:
        tea = await client.tracked_entity_attributes.create(
            name="Example client program demo given name",
            short_name="ExCliPrgGivN",
            value_type=ValueType.TEXT,
        )
        print(f"created TEA {tea.id}")

        tet = await client.tracked_entity_types.create(
            name="Example client program demo person",
            short_name="ExCliPrgPers",
            allow_audit_log=True,
            feature_type="NONE",
            min_attributes_required_to_search=1,
        )
        print(f"created TET {tet.id}")

        # Grab the root OU to scope the program to.
        units = await client.organisation_units.list_all(page_size=1)
        ou_uid = (units[0].id or "") if units else ""
        if not ou_uid:
            print("need at least one OU on the instance to run this example")
            return

        program = await client.programs.create(
            name="Example client demo tracker program",
            short_name="ExCliPrg",
            program_type="WITH_REGISTRATION",
            tracked_entity_type_uid=tet.id or "",
            display_incident_date=True,
            only_enroll_once=True,
            min_attributes_required_to_search=1,
        )
        print(f"created program {program.id}")

        program = await client.programs.add_attribute(
            program.id or "",
            tea.id or "",
            mandatory=True,
            searchable=True,
            sort_order=1,
        )
        program = await client.programs.add_organisation_unit(program.id or "", ou_uid)
        print(
            f"program carries {len(program.programTrackedEntityAttributes or [])} TEA(s) "
            f"and {len(program.organisationUnits or [])} OU(s)",
        )

        # Cleanup
        await client.programs.delete(program.id or "")
        await client.tracked_entity_types.delete(tet.id or "")
        await client.tracked_entity_attributes.delete(tea.id or "")
        print("cleaned up demo program + TET + TEA")


if __name__ == "__main__":
    run_example(main)
