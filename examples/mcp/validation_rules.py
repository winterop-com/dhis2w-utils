"""Call the `metadata_validation_rule_*` MCP tools.

Mirrors `examples/client/validation_rules.py` via the MCP tool surface.

Usage:
    uv run python examples/mcp/validation_rules.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a rule and its group via MCP tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        des_response = await mcp_client.call_tool(
            "metadata_list",
            {"resource": "dataElements", "page_size": 1, "profile": profile},
        )
        des = des_response.data or []
        if not isinstance(des, list) or not des:
            print("need at least one data element on the instance to run this example")
            return
        de_uid = des[0]["id"]

        vr_response = await mcp_client.call_tool(
            "metadata_validation_rule_create",
            {
                "name": "MCP demo rule",
                "short_name": "MCPDemoVR",
                "left_expression": f"#{{{de_uid}}}",
                "operator": "greater_than_or_equal_to",
                "right_expression": "0",
                "organisation_unit_levels": [4],
                "profile": profile,
            },
        )
        vr = vr_response.data or {}
        vr_uid = vr.get("id") if isinstance(vr, dict) else None
        print(f"created validationRule {vr_uid}")

        vrg_response = await mcp_client.call_tool(
            "metadata_validation_rule_group_create",
            {"name": "MCP demo rule group", "profile": profile},
        )
        vrg = vrg_response.data or {}
        vrg_uid = vrg.get("id") if isinstance(vrg, dict) else None

        if vr_uid and vrg_uid:
            await mcp_client.call_tool(
                "metadata_validation_rule_group_add_members",
                {"uid": vrg_uid, "validation_rule_uids": [vr_uid], "profile": profile},
            )
            print(f"linked rule {vr_uid} into {vrg_uid}")

        if vrg_uid:
            await mcp_client.call_tool("metadata_validation_rule_group_delete", {"uid": vrg_uid, "profile": profile})
        if vr_uid:
            await mcp_client.call_tool("metadata_validation_rule_delete", {"uid": vr_uid, "profile": profile})
        print("cleaned up demo rule + group")


if __name__ == "__main__":
    asyncio.run(main())
