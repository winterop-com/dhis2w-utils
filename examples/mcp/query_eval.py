"""MCP: run a d2ql query and a d2path expression via the `query` tools."""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Call query_eval against the active profile and query_d2path over inline JSON."""
    server = build_server()
    async with Client(server) as client:
        evaluated = await client.call_tool(
            "query_eval",
            {"query": 'dataElements | where domainType = "AGGREGATE" | select id, name | limit 5'},
        )
        payload = evaluated.structured_content or evaluated.data or {}
        print(f"query_eval rows: {payload.get('count')}")

        path = await client.call_tool(
            "query_d2path",
            {
                "expression": 'name.where(use = "official").family',
                "data": {"name": [{"use": "official", "family": "King"}]},
            },
        )
        print(f"query_d2path: {path.structured_content or path.data}")


if __name__ == "__main__":
    asyncio.run(main())
