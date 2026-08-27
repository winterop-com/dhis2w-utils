"""List DHIS2 metadata through the MCP `metadata_list` tool.

Opens with `metadata_type_list` because that answers the question the listing
depends on: which resource names this instance accepts. Then pages one of them,
narrowed by fields and by a filter.

Usage:
    uv run python examples/mcp/metadata_list.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Enumerate the metadata types, then page one of them two ways."""
    server = build_server()
    async with Client(server) as client:
        # metadata_type_list returns a flat list (wrapped by fastmcp under "result").
        types = (await client.call_tool("metadata_type_list")).structured_content or {}
        all_types: list[str] = types.get("result", [])
        print(f"{len(all_types)} metadata types; first 8: {all_types[:8]}")

        # metadata_list takes `page_size` (and optionally filters / order / paging).
        listing = (
            await client.call_tool(
                "metadata_list",
                {"resource": "dataElements", "page_size": 5, "fields": "id,name,valueType"},
            )
        ).structured_content or {}
        items: list[dict[str, Any]] = listing.get("result", [])
        print("\ndataElements (first 5):")
        for item in items:
            print(f"  {item.get('id'):<12} {item.get('name'):<30} {item.get('valueType')}")

        # The same `property:operator:value` filter DSL the CLI takes.
        filtered = (
            await client.call_tool(
                "metadata_list",
                {"resource": "dataElements", "filters": ["name:like:Penta"], "fields": "id,name"},
            )
        ).structured_content or {}
        matches: list[dict[str, Any]] = filtered.get("result", [])
        print(f"\ndataElements with Penta in the name: {len(matches)}")


if __name__ == "__main__":
    asyncio.run(main())
