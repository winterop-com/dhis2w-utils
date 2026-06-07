"""Call the `metadata_program_*` MCP tools in-process.

Mirrors `examples/v42/client/tracker_programs.py` via the MCP surface.

Usage:
    uv run python examples/v42/mcp/tracker_programs.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a Program + PTEA + OU scope via MCP tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        tea_response = await mcp_client.call_tool(
            "metadata_tracked_entity_attribute_create",
            {
                "name": "MCP program demo given name",
                "short_name": "MCPPrgGivN",
                "value_type": "TEXT",
                "profile": profile,
            },
        )
        tea = tea_response.data or {}
        tea_uid = tea.get("id") if isinstance(tea, dict) else None
        print(f"created TEA {tea_uid}")

        tet_response = await mcp_client.call_tool(
            "metadata_tracked_entity_type_create",
            {
                "name": "MCP program demo person",
                "short_name": "MCPPrgPers",
                "allow_audit_log": True,
                "feature_type": "NONE",
                "min_attributes_required_to_search": 1,
                "profile": profile,
            },
        )
        tet = tet_response.data or {}
        tet_uid = tet.get("id") if isinstance(tet, dict) else None
        print(f"created TET {tet_uid}")

        ous_response = await mcp_client.call_tool(
            "metadata_list",
            {"resource": "organisationUnits", "page_size": 1, "profile": profile},
        )
        ous = ous_response.data or []
        ou_uid = ous[0]["id"] if isinstance(ous, list) and ous else None
        if not ou_uid:
            print("need at least one OU on the instance to run this example")
            return

        prg_response = await mcp_client.call_tool(
            "metadata_program_create",
            {
                "name": "MCP demo tracker program",
                "short_name": "MCPPrg",
                "program_type": "WITH_REGISTRATION",
                "tracked_entity_type_uid": tet_uid,
                "display_incident_date": True,
                "only_enroll_once": True,
                "min_attributes_required_to_search": 1,
                "profile": profile,
            },
        )
        prg = prg_response.data or {}
        prg_uid = prg.get("id") if isinstance(prg, dict) else None
        print(f"created program {prg_uid}")

        if prg_uid and tea_uid:
            await mcp_client.call_tool(
                "metadata_program_add_attribute",
                {
                    "program_uid": prg_uid,
                    "attribute_uid": tea_uid,
                    "mandatory": True,
                    "searchable": True,
                    "sort_order": 1,
                    "profile": profile,
                },
            )
        if prg_uid and ou_uid:
            await mcp_client.call_tool(
                "metadata_program_add_organisation_unit",
                {"program_uid": prg_uid, "organisation_unit_uid": ou_uid, "profile": profile},
            )
            print(f"linked TEA {tea_uid} + OU {ou_uid} onto {prg_uid}")

        # Cleanup
        if prg_uid:
            await mcp_client.call_tool("metadata_program_delete", {"uid": prg_uid, "profile": profile})
        if tet_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_type_delete",
                {"uid": tet_uid, "profile": profile},
            )
        if tea_uid:
            await mcp_client.call_tool(
                "metadata_tracked_entity_attribute_delete",
                {"uid": tea_uid, "profile": profile},
            )
        print("cleaned up demo program + TET + TEA")


if __name__ == "__main__":
    asyncio.run(main())
