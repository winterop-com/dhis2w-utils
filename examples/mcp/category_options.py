"""Call the `metadata_category_option*` MCP tools in-process.

Mirrors `examples/client/category_options.py` via the MCP tool surface.

Usage:
    uv run python examples/mcp/category_options.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a CO + group + group-set via MCP tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        co_response = await mcp_client.call_tool(
            "metadata_category_option_create",
            {
                "name": "MCP demo CO",
                "short_name": "MCPDemoCO",
                "code": "MCP_DEMO_CO",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "profile": profile,
            },
        )
        co = co_response.data or co_response.structured_content or {}
        co_uid = co.get("id") if isinstance(co, dict) else getattr(co, "id", None)
        print(f"created CO {co_uid}")

        group_response = await mcp_client.call_tool(
            "metadata_category_option_group_create",
            {"name": "MCP demo CO group", "short_name": "MCPDemoGrp", "profile": profile},
        )
        group = group_response.data or group_response.structured_content or {}
        group_uid = group.get("id") if isinstance(group, dict) else getattr(group, "id", None)

        if co_uid and group_uid:
            await mcp_client.call_tool(
                "metadata_category_option_group_add_members",
                {"uid": group_uid, "category_option_uids": [co_uid], "profile": profile},
            )
            print(f"linked {co_uid} into {group_uid}")

        gs_response = await mcp_client.call_tool(
            "metadata_category_option_group_set_create",
            {"name": "MCP demo CO dimension", "short_name": "MCPDemoDim", "profile": profile},
        )
        gs = gs_response.data or gs_response.structured_content or {}
        gs_uid = gs.get("id") if isinstance(gs, dict) else getattr(gs, "id", None)

        if group_uid and gs_uid:
            await mcp_client.call_tool(
                "metadata_category_option_group_set_add_groups",
                {"uid": gs_uid, "group_uids": [group_uid], "profile": profile},
            )
            print(f"linked {group_uid} into {gs_uid}")

        # Cleanup
        if gs_uid:
            await mcp_client.call_tool(
                "metadata_category_option_group_set_delete",
                {"uid": gs_uid, "profile": profile},
            )
        if group_uid:
            await mcp_client.call_tool(
                "metadata_category_option_group_delete",
                {"uid": group_uid, "profile": profile},
            )
        if co_uid:
            await mcp_client.call_tool(
                "metadata_category_option_delete",
                {"uid": co_uid, "profile": profile},
            )
        print("cleaned up demo CO + group + group set")


if __name__ == "__main__":
    asyncio.run(main())
