"""Call the `metadata_program_indicator*` MCP tools in-process.

Mirrors `examples/client/program_indicators.py` via the MCP tool
surface. Idempotent end-to-end round-trip.

Usage:
    uv run python examples/mcp/program_indicators.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client

CHILD_PROGRAM = "IpHINAT79UW"
BCG_DE = "s46m5MS0hxu"


async def main() -> None:
    """Exercise PI + group tools in one pass."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        val = await mcp_client.call_tool(
            "metadata_program_indicator_validate_expression",
            {"expression": f"#{{{CHILD_PROGRAM}.{BCG_DE}}}", "profile": profile},
        )
        env = val.data or val.structured_content or {}
        status = env.get("status") if isinstance(env, dict) else getattr(env, "status", None)
        print(f"expression status: {status}")

        pi_response = await mcp_client.call_tool(
            "metadata_program_indicator_create",
            {
                "name": "MCP demo PI",
                "short_name": "MCPDemoPI",
                "program_uid": CHILD_PROGRAM,
                "expression": f"#{{{CHILD_PROGRAM}.{BCG_DE}}}",
                "analytics_type": "EVENT",
                "profile": profile,
            },
        )
        pi = pi_response.data or pi_response.structured_content or {}
        pi_uid = pi.get("id") if isinstance(pi, dict) else getattr(pi, "id", None)
        print(f"created programIndicator {pi_uid}")

        group_response = await mcp_client.call_tool(
            "metadata_program_indicator_group_create",
            {"name": "MCP demo PI group", "short_name": "MCPDemoGrp", "profile": profile},
        )
        group = group_response.data or group_response.structured_content or {}
        group_uid = group.get("id") if isinstance(group, dict) else getattr(group, "id", None)

        if pi_uid and group_uid:
            await mcp_client.call_tool(
                "metadata_program_indicator_group_add_members",
                {"uid": group_uid, "program_indicator_uids": [pi_uid], "profile": profile},
            )
            print(f"linked {pi_uid} into {group_uid}")

        # Cleanup
        if group_uid:
            await mcp_client.call_tool(
                "metadata_program_indicator_group_delete",
                {"uid": group_uid, "profile": profile},
            )
        if pi_uid:
            await mcp_client.call_tool(
                "metadata_program_indicator_delete",
                {"uid": pi_uid, "profile": profile},
            )
        print("cleaned up demo PI + group")


if __name__ == "__main__":
    asyncio.run(main())
