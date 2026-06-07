"""Call the `metadata_validation_rule_*` + `metadata_predictor_*` MCP tools.

Mirrors `examples/v42/client/validation_rules_predictors.py` via the MCP
tool surface.

Usage:
    uv run python examples/v42/mcp/validation_rules_predictors.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Round-trip a rule + group + predictor + group via MCP tools."""
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

        # Cleanup
        if pdg_uid:
            await mcp_client.call_tool("metadata_predictor_group_delete", {"uid": pdg_uid, "profile": profile})
        if prd_uid:
            await mcp_client.call_tool("metadata_predictor_delete", {"uid": prd_uid, "profile": profile})
        if vrg_uid:
            await mcp_client.call_tool("metadata_validation_rule_group_delete", {"uid": vrg_uid, "profile": profile})
        if vr_uid:
            await mcp_client.call_tool("metadata_validation_rule_delete", {"uid": vr_uid, "profile": profile})
        print("cleaned up demo rule + predictor + groups")


if __name__ == "__main__":
    asyncio.run(main())
