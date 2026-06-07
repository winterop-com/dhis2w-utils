"""Call the `metadata_organisation_unit*` MCP tools in-process.

Mirrors `examples/v42/client/organisation_units.py` but via the MCP tool
surface: tree walk, level rename, group + group-set round-trip, clean
up.

Usage:
    uv run python examples/v42/mcp/organisation_units.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client

ROOT_UID = "ImspTQPwCqd"


async def main() -> None:
    """Exercise every OU/OUG/OUGS/OULevel MCP tool in one pass."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        tree_response = await mcp_client.call_tool(
            "metadata_organisation_unit_tree",
            {"root_uid": ROOT_UID, "max_depth": 1, "profile": profile},
        )
        tree = tree_response.data or tree_response.structured_content or []
        print(f"subtree rooted at {ROOT_UID}: {len(tree)} units")

        level_response = await mcp_client.call_tool(
            "metadata_list",
            {"resource": "organisationUnitLevels", "profile": profile},
        )
        levels = level_response.data or level_response.structured_content or []
        print(f"levels: {[row.get('level') for row in levels if isinstance(row, dict)]}")

        # Round-trip a demo group + group set and tear them down.
        group_response = await mcp_client.call_tool(
            "metadata_organisation_unit_group_create",
            {
                "name": "MCP demo group",
                "short_name": "MCPDemoGrp",
                "color": "#3388ff",
                "profile": profile,
            },
        )
        group = group_response.data or group_response.structured_content or {}
        group_uid = group.get("id") if isinstance(group, dict) else None
        print(f"created group {group_uid}")

        group_set_response = await mcp_client.call_tool(
            "metadata_organisation_unit_group_set_create",
            {"name": "MCP demo dimension", "short_name": "MCPDemoDim", "profile": profile},
        )
        group_set = group_set_response.data or group_set_response.structured_content or {}
        group_set_uid = group_set.get("id") if isinstance(group_set, dict) else None
        print(f"created group set {group_set_uid}")

        if group_uid and group_set_uid:
            await mcp_client.call_tool(
                "metadata_organisation_unit_group_set_add_groups",
                {"uid": group_set_uid, "group_uids": [group_uid], "profile": profile},
            )
            print(f"linked {group_uid} into {group_set_uid}")

            # Cleanup — group-set first so we don't leave dangling refs.
            await mcp_client.call_tool(
                "metadata_organisation_unit_group_set_delete",
                {"uid": group_set_uid, "profile": profile},
            )
            await mcp_client.call_tool(
                "metadata_organisation_unit_group_delete",
                {"uid": group_uid, "profile": profile},
            )
            print("cleaned up demo group + group set")


if __name__ == "__main__":
    asyncio.run(main())
