"""Tracker schema authoring — step 1: TET + TEA round-trip.

Creates two TrackedEntityAttributes (a unique generated National ID
and a plain Given Name), then a TrackedEntityType that wires both in
with different mandatory / searchable flags, then tears everything
down.

Usage:
    uv run python examples/client/tracker_schema.py
"""

from __future__ import annotations

from _runner import run_example

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import ValueType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Round-trip a TET with two TEAs attached."""
    async with open_client(profile_from_env()) as client:
        nat_id = await client.tracked_entity_attributes.create(
            name="Example client demo national id",
            short_name="ExCliNID",
            value_type=ValueType.TEXT,
            unique=True,
            generated=True,
            pattern="RANDOM(#######)",
        )
        print(f"created TEA {nat_id.id} (national id, unique + generated)")

        given_name = await client.tracked_entity_attributes.create(
            name="Example client demo given name",
            short_name="ExCliGivN",
            value_type=ValueType.TEXT,
        )
        print(f"created TEA {given_name.id} (given name)")

        tet = await client.tracked_entity_types.create(
            name="Example client demo person",
            short_name="ExCliPers",
            allow_audit_log=True,
            feature_type="NONE",
            min_attributes_required_to_search=1,
        )
        print(f"created TET {tet.id}")

        # National ID: mandatory + searchable. Given Name: display in list only.
        await client.tracked_entity_types.add_attribute(
            tet.id or "",
            nat_id.id or "",
            mandatory=True,
            searchable=True,
        )
        tet = await client.tracked_entity_types.add_attribute(tet.id or "", given_name.id or "")
        print(f"TET carries {len(tet.trackedEntityTypeAttributes or [])} attribute(s)")

        # Cleanup
        await client.tracked_entity_types.delete(tet.id or "")
        await client.tracked_entity_attributes.delete(given_name.id or "")
        await client.tracked_entity_attributes.delete(nat_id.id or "")
        print("cleaned up demo TET + 2 TEAs")


if __name__ == "__main__":
    run_example(main)
