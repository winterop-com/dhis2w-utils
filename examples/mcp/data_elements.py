"""Call the `metadata_data_element*` MCP tools in-process.

Mirrors `examples/client/data_elements.py` but via the MCP tool
surface. Create / link / clean up round-trip — idempotent enough that
a crashed prior run doesn't block the next one (cleanup is unconditional
on whatever UIDs we've created in this run).

Usage:
    uv run python examples/mcp/data_elements.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Exercise the DataElement + DE group + DEG-set tools in one pass."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        de_response = await mcp_client.call_tool(
            "metadata_data_element_create",
            {
                "name": "MCP demo DE",
                "short_name": "MCPDemoDE",
                "value_type": "NUMBER",
                "profile": profile,
            },
        )
        de = de_response.data or de_response.structured_content or {}
        de_uid = de.get("id") if isinstance(de, dict) else None
        print(f"created DE {de_uid}")

        group_response = await mcp_client.call_tool(
            "metadata_data_element_group_create",
            {"name": "MCP demo DE group", "short_name": "MCPDemoGrp", "profile": profile},
        )
        group = group_response.data or group_response.structured_content or {}
        group_uid = group.get("id") if isinstance(group, dict) else None
        print(f"created group {group_uid}")

        if de_uid and group_uid:
            await mcp_client.call_tool(
                "metadata_data_element_group_add_members",
                {"uid": group_uid, "data_element_uids": [de_uid], "profile": profile},
            )
            print(f"linked {de_uid} into {group_uid}")

        gs_response = await mcp_client.call_tool(
            "metadata_data_element_group_set_create",
            {"name": "MCP demo DE dimension", "short_name": "MCPDemoDim", "profile": profile},
        )
        gs = gs_response.data or gs_response.structured_content or {}
        gs_uid = gs.get("id") if isinstance(gs, dict) else None

        if group_uid and gs_uid:
            await mcp_client.call_tool(
                "metadata_data_element_group_set_add_groups",
                {"uid": gs_uid, "group_uids": [group_uid], "profile": profile},
            )
            print(f"linked {group_uid} into {gs_uid}")

        # Cleanup — group-set first to avoid dangling refs.
        if gs_uid:
            await mcp_client.call_tool(
                "metadata_data_element_group_set_delete",
                {"uid": gs_uid, "profile": profile},
            )
        if group_uid:
            await mcp_client.call_tool(
                "metadata_data_element_group_delete",
                {"uid": group_uid, "profile": profile},
            )
        if de_uid:
            await mcp_client.call_tool(
                "metadata_data_element_delete",
                {"uid": de_uid, "profile": profile},
            )
        print("cleaned up demo DE + group + group set")


if __name__ == "__main__":
    asyncio.run(main())
