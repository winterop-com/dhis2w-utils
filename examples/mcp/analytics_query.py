"""Call the `analytics` MCP tools — aggregated query + resource-table refresh.

Mirrors examples/client/analytics_query.py but goes through the MCP server
in-process. Useful to confirm the analytics plugin's tools match the CLI
surface and to see how an agent would query analytics.

Usage:
    uv run python examples/mcp/analytics_query.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Run one aggregated analytics query, then trigger a refresh."""
    server = build_server()
    async with Client(server) as client:
        result = await client.call_tool(
            "analytics_query",
            {
                "dimensions": ["dx:fClA2Erf6IO;UOlfIjgN8X6", "pe:LAST_12_MONTHS", "ou:ImspTQPwCqd;LEVEL-2"],
                "skip_meta": True,
            },
        )
        payload = result.structured_content or result.data or {}
        rows = (payload.get("result") or payload).get("rows", [])
        print(f"analytics rows: {len(rows)}")
        for row in rows[:5]:
            print("  ", row)

        # Analytics-table refresh is a background job; it moved to the
        # maintenance plugin alongside the other resource-table refresh
        # verbs. Same semantics, new tool name.
        refresh = await client.call_tool("maintenance_refresh_analytics", {})
        print("\nmaintenance_refresh_analytics:", refresh.structured_content or refresh.data)


if __name__ == "__main__":
    asyncio.run(main())
