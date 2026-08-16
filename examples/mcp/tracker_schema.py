"""Call the `metadata_tracked_entity_*` MCP tools in-process.

Mirrors `examples/client/tracker_schema.py` via the MCP tool surface.

Usage:
    uv run python examples/mcp/tracker_schema.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a TET + two TEAs via MCP tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        nat_response = await mcp_client.call_tool(
            "metadata_tracked_entity_attribute_create",
            {
                "name": "MCP demo national id",
                "short_name": "MCPNatID",
                "value_type": "TEXT",
                "unique": True,
                "generated": True,
                "pattern": "RANDOM(#######)",
                "profile": profile,
            },
        )
        nat = nat_response.data or {}
        nat_uid = nat.get("id") if isinstance(nat, dict) else None
        print(f"created TEA {nat_uid} (national id)")

        name_response = await mcp_client.call_tool(
            "metadata_tracked_entity_attribute_create",
            {
                "name": "MCP demo given name",
                "short_name": "MCPGivN",
                "value_type": "TEXT",
                "profile": profile,
            },
        )
        name = name_response.data or {}
        name_uid = name.get("id") if isinstance(name, dict) else None
        print(f"created TEA {name_uid} (given name)")

        tet_response = await mcp_client.call_tool(
            "metadata_tracked_entity_type_create",
            {
                "name": "MCP demo person",
                "short_name": "MCPPers",
                "allow_audit_log": True,
                "feature_type": "NONE",
                "min_attributes_required_to_search": 1,
                "profile": profile,
            },
        )
        tet = tet_response.data or {}
        tet_uid = tet.get("id") if isinstance(tet, dict) else None
        print(f"created TET {tet_uid}")

        if tet_uid and nat_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_type_add_attribute",
                {
                    "tet_uid": tet_uid,
                    "attribute_uid": nat_uid,
                    "mandatory": True,
                    "searchable": True,
                    "profile": profile,
                },
            )
        if tet_uid and name_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_type_add_attribute",
                {"tet_uid": tet_uid, "attribute_uid": name_uid, "profile": profile},
            )
            print(f"linked {nat_uid} + {name_uid} onto {tet_uid}")

        # Cleanup
        if tet_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_type_delete",
                {"uid": tet_uid, "profile": profile},
            )
        if name_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_attribute_delete",
                {"uid": name_uid, "profile": profile},
            )
        if nat_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_attribute_delete",
                {"uid": nat_uid, "profile": profile},
            )
        print("cleaned up demo TET + 2 TEAs")


if __name__ == "__main__":
    asyncio.run(main())
