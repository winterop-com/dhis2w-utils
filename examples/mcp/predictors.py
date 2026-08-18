"""Call the `metadata_predictor_*` MCP tools.

Mirrors `examples/client/predictors.py` via the MCP tool surface.

Usage:
    uv run python examples/mcp/predictors.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a predictor and its group via MCP tools."""
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

        levels_response = await mcp_client.call_tool(
            "metadata_list",
            {"resource": "organisationUnitLevels", "profile": profile},
        )
        levels = levels_response.data or []
        ou_level_uid = levels[-1]["id"] if isinstance(levels, list) and levels else None

        predictor_args: dict[str, object] = {
            "name": "MCP demo predictor",
            "short_name": "MCPDemoPrd",
            "expression": f"#{{{de_uid}}}",
            "output_data_element_uid": de_uid,
            "sequential_sample_count": 3,
            "profile": profile,
        }
        if ou_level_uid:
            predictor_args["organisation_unit_level_uids"] = [ou_level_uid]
        prd_response = await mcp_client.call_tool("metadata_predictor_create", predictor_args)
        prd = prd_response.data or {}
        prd_uid = prd.get("id") if isinstance(prd, dict) else None
        print(f"created predictor {prd_uid}")

        pdg_response = await mcp_client.call_tool(
            "metadata_predictor_group_create",
            {"name": "MCP demo predictor group", "profile": profile},
        )
        pdg = pdg_response.data or {}
        pdg_uid = pdg.get("id") if isinstance(pdg, dict) else None

        if prd_uid and pdg_uid:
            await mcp_client.call_tool(
                "metadata_predictor_group_add_members",
                {"uid": pdg_uid, "predictor_uids": [prd_uid], "profile": profile},
            )
            print(f"linked predictor {prd_uid} into {pdg_uid}")

        if pdg_uid:
            await mcp_client.call_tool("metadata_predictor_group_delete", {"uid": pdg_uid, "profile": profile})
        if prd_uid:
            await mcp_client.call_tool("metadata_predictor_delete", {"uid": prd_uid, "profile": profile})
        print("cleaned up demo predictor + group")


if __name__ == "__main__":
    asyncio.run(main())
