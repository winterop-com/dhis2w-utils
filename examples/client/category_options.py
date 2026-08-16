"""CategoryOption + CategoryOptionGroup + CategoryOptionGroupSet round-trip.

Completes the analytics-triples sweep. Same accessor shape as data
elements and indicators; CategoryOption adds a validity-window
helper (`set_validity_window(start_date=..., end_date=...)`).

Usage:
    uv run python examples/client/category_options.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Create CO/COG/COGS, link, flex the validity helper, tear down."""
    async with open_client(profile_from_env()) as client:
        co = await client.category_options.create(
            name="Example client demo CO",
            short_name="ExCliDemoCO",
            code="EX_CLI_DEMO_CO",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        print(f"created CO {co.id} name={co.name!r} window={co.startDate}..{co.endDate}")

        # Narrow the validity window to H1 2024 via the dedicated helper.
        co = await client.category_options.set_validity_window(
            co.id or "",
            start_date="2024-01-01",
            end_date="2024-06-30",
        )
        print(f"narrowed window -> {co.startDate}..{co.endDate}")

        group = await client.category_option_groups.create(
            name="Example client demo CO group",
            short_name="ExCliDemoGrp",
        )
        await client.category_option_groups.add_members(group.id or "", category_option_uids=[co.id or ""])
        members = await client.category_option_groups.list_members(group.id or "", page_size=5)
        print(f"group carries {len(members)} member(s): {[m.name for m in members]}")

        gs = await client.category_option_group_sets.create(
            name="Example client demo CO dimension",
            short_name="ExCliDemoDim",
        )
        await client.category_option_group_sets.add_groups(gs.id or "", group_uids=[group.id or ""])
        print(f"group set {gs.id} now contains {group.id}")

        # Cleanup
        await client.category_option_group_sets.delete(gs.id or "")
        await client.category_option_groups.delete(group.id or "")
        await client.category_options.delete(co.id or "")
        print("cleaned up demo CO + group + group set")


if __name__ == "__main__":
    run_example(main)
