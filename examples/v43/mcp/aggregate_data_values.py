"""Call the `aggregate` MCP tools — GET / SET / DELETE a data value.

Mirrors examples/client/push_data_value.py but via the MCP server.

Usage:
    uv run python examples/v43/mcp/aggregate_data_values.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Read, set, read-back, delete — one aggregate data value."""
    server = build_server()
    async with Client(server) as client:
        before = await client.call_tool(
            "data_aggregate_get",
            {"data_set": "BfMAe6Itzgt", "period": "202603", "org_unit": "DiszpKrYNg8"},
        )
        envelope = before.structured_content or before.data or {}
        rows = envelope.get("dataValues", [])
        print(f"before: {len(rows)} data values for 202603")

        # Extra read filters: only values modified recently (last_updated), including
        # soft-deleted ones (include_deleted). org_unit_group selects by OU group instead of org_unit.
        recent = await client.call_tool(
            "data_aggregate_get",
            {
                "data_set": "BfMAe6Itzgt",
                "period": "202603",
                "org_unit": "DiszpKrYNg8",
                "last_updated": "7d",
                "include_deleted": True,
            },
        )
        env = recent.structured_content or recent.data or {}
        print(f"recent: {len(env.get('dataValues', []))} values modified in the last 7 days")

        await client.call_tool(
            "data_aggregate_set",
            {
                "data_element": "fClA2Erf6IO",
                "period": "202603",
                "org_unit": "DiszpKrYNg8",
                "value": "77",
            },
        )
        print("set     fClA2Erf6IO / 202603 / DiszpKrYNg8 = 77")

        after = await client.call_tool(
            "data_aggregate_get",
            {"data_set": "BfMAe6Itzgt", "period": "202603", "org_unit": "DiszpKrYNg8"},
        )
        envelope = after.structured_content or after.data or {}
        print(f"after:  {len(envelope.get('dataValues', []))} data values for 202603")

        await client.call_tool(
            "data_aggregate_delete",
            {"data_element": "fClA2Erf6IO", "period": "202603", "org_unit": "DiszpKrYNg8"},
        )
        print("delete  fClA2Erf6IO / 202603 / DiszpKrYNg8")

        # Set then clear the follow-up flag on a value (self-cleaning).
        for flag in (True, False):
            await client.call_tool(
                "data_aggregate_followup",
                {"data_element": "fClA2Erf6IO", "period": "202603", "org_unit": "DiszpKrYNg8", "followup": flag},
            )
        print("followup set then cleared  fClA2Erf6IO / 202603 / DiszpKrYNg8")


if __name__ == "__main__":
    asyncio.run(main())
