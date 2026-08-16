"""Call the `metadata_data_set_*` + `metadata_section_*` MCP tools in-process.

Mirrors `examples/client/data_sets.py` via the MCP tool surface.

Usage:
    uv run python examples/mcp/data_sets.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a DataSet + Section via MCP tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")

    async with Client(build_server()) as mcp_client:
        # Round up two DEs to seed the section with.
        des_response = await mcp_client.call_tool(
            "metadata_list",
            {"resource": "dataElements", "page_size": 2, "profile": profile},
        )
        des = des_response.data or []
        if not isinstance(des, list) or len(des) < 2:
            print("need at least two data elements on the instance to run this example")
            return
        de_a = des[0]["id"]
        de_b = des[1]["id"]

        ds_response = await mcp_client.call_tool(
            "metadata_data_set_create",
            {
                "name": "MCP demo DataSet",
                "short_name": "MCPDemoDS",
                "period_type": "Monthly",
                "code": "MCP_DEMO_DS",
                "open_future_periods": 2,
                "expiry_days": 10,
                "timely_days": 3,
                "profile": profile,
            },
        )
        ds_payload = ds_response.data or ds_response.structured_content or {}
        ds_uid = ds_payload.get("id") if isinstance(ds_payload, dict) else None
        print(f"created dataSet {ds_uid}")

        if not ds_uid:
            return

        await mcp_client.call_tool(
            "metadata_data_set_add_element",
            {"data_set_uid": ds_uid, "data_element_uid": de_a, "profile": profile},
        )
        await mcp_client.call_tool(
            "metadata_data_set_add_element",
            {"data_set_uid": ds_uid, "data_element_uid": de_b, "profile": profile},
        )
        print(f"attached DE {de_a} + {de_b} to {ds_uid}")

        sec_response = await mcp_client.call_tool(
            "metadata_section_create",
            {
                "name": "MCP demo Section",
                "data_set_uid": ds_uid,
                "sort_order": 1,
                "data_element_uids": [de_a, de_b],
                "profile": profile,
            },
        )
        sec_payload = sec_response.data or sec_response.structured_content or {}
        sec_uid = sec_payload.get("id") if isinstance(sec_payload, dict) else None
        print(f"created section {sec_uid}")

        if sec_uid:
            await mcp_client.call_tool(
                "metadata_section_reorder",
                {"section_uid": sec_uid, "data_element_uids": [de_b, de_a], "profile": profile},
            )
            print(f"reordered section {sec_uid}")

        # Cleanup
        if sec_uid:
            await mcp_client.call_tool("metadata_section_delete", {"uid": sec_uid, "profile": profile})
        await mcp_client.call_tool(
            "metadata_data_set_remove_element",
            {"data_set_uid": ds_uid, "data_element_uid": de_a, "profile": profile},
        )
        await mcp_client.call_tool(
            "metadata_data_set_remove_element",
            {"data_set_uid": ds_uid, "data_element_uid": de_b, "profile": profile},
        )
        await mcp_client.call_tool("metadata_data_set_delete", {"uid": ds_uid, "profile": profile})
        print("cleaned up demo dataSet + section")


if __name__ == "__main__":
    asyncio.run(main())
