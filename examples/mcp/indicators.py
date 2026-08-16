"""Call the `metadata_indicator*` MCP tools in-process.

Mirrors `examples/client/indicators.py` but via the MCP tool surface.
Creates and tears down a throw-away indicator + group + group-set.

Usage:
    uv run python examples/mcp/indicators.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client

INDICATOR_TYPE_UID = "JkWynlWMjJR"
BCG_DE_UID = "s46m5MS0hxu"


async def main() -> None:
    """Exercise indicator + group + group-set tools in one pass."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        validation = await mcp_client.call_tool(
            "metadata_indicator_validate_expression",
            {"expression": f"#{{{BCG_DE_UID}}}", "profile": profile},
        )
        val = validation.data or validation.structured_content or {}
        status = val.get("status") if isinstance(val, dict) else getattr(val, "status", None)
        print(f"expression status: {status}")

        ind_response = await mcp_client.call_tool(
            "metadata_indicator_create",
            {
                "name": "MCP demo indicator",
                "short_name": "MCPDemoInd",
                "indicator_type_uid": INDICATOR_TYPE_UID,
                "numerator": f"#{{{BCG_DE_UID}}}",
                "denominator": "1",
                "profile": profile,
            },
        )
        ind = ind_response.data or ind_response.structured_content or {}
        ind_uid = ind.get("id") if isinstance(ind, dict) else getattr(ind, "id", None)
        print(f"created indicator {ind_uid}")

        group_response = await mcp_client.call_tool(
            "metadata_indicator_group_create",
            {"name": "MCP demo indicator group", "short_name": "MCPDemoGrp", "profile": profile},
        )
        group = group_response.data or group_response.structured_content or {}
        group_uid = group.get("id") if isinstance(group, dict) else getattr(group, "id", None)

        if ind_uid and group_uid:
            await mcp_client.call_tool(
                "metadata_indicator_group_add_members",
                {"uid": group_uid, "indicator_uids": [ind_uid], "profile": profile},
            )
            print(f"linked {ind_uid} into {group_uid}")

        gs_response = await mcp_client.call_tool(
            "metadata_indicator_group_set_create",
            {"name": "MCP demo indicator dimension", "short_name": "MCPDemoDim", "profile": profile},
        )
        gs = gs_response.data or gs_response.structured_content or {}
        gs_uid = gs.get("id") if isinstance(gs, dict) else getattr(gs, "id", None)

        if group_uid and gs_uid:
            await mcp_client.call_tool(
                "metadata_indicator_group_set_add_groups",
                {"uid": gs_uid, "group_uids": [group_uid], "profile": profile},
            )

        # Cleanup — delete the leaf (indicator) before its container.
        # On v43, deleting an IndicatorGroup cascades to its member
        # indicators (it didn't on v42), so a v42-style group-first order
        # leaves the indicator already-gone and the explicit delete 404s.
        if ind_uid:
            await mcp_client.call_tool(
                "metadata_indicator_delete",
                {"uid": ind_uid, "profile": profile},
            )
        if gs_uid:
            await mcp_client.call_tool(
                "metadata_indicator_group_set_delete",
                {"uid": gs_uid, "profile": profile},
            )
        if group_uid:
            await mcp_client.call_tool(
                "metadata_indicator_group_delete",
                {"uid": group_uid, "profile": profile},
            )
        print("cleaned up demo indicator + group + group set")


if __name__ == "__main__":
    asyncio.run(main())
