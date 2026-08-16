"""Browse DHIS2 metadata via the MCP `metadata` plugin.

Shows:
  - `list_metadata_types` — enumerate the 119 resources DHIS2 exposes.
  - `list_metadata`       — page through one resource type.
  - `get_metadata`        — fetch a single object by UID.

Usage:
    uv run python examples/mcp/metadata.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """List metadata types, list data elements, fetch one by UID."""
    server = build_server()
    async with Client(server) as client:
        # list_metadata_types returns a flat list (wrapped by fastmcp under "result").
        types = (await client.call_tool("metadata_type_list")).structured_content or {}
        all_types: list[str] = types.get("result", [])
        print(f"first 8 metadata types: {all_types[:8]}")

        # metadata_list takes `page_size` (and optionally filters/order/paging).
        listing = (
            await client.call_tool(
                "metadata_list",
                {"resource": "dataElements", "page_size": 5, "fields": "id,name,valueType"},
            )
        ).structured_content or {}
        items: list[dict[str, Any]] = listing.get("result", [])
        print("\ndataElements (first 5):")
        for item in items[:5]:
            print(f"  {item.get('id'):<12} {item.get('name'):<30} {item.get('valueType')}")

        # Fetch a seeded data element by UID.
        one = (
            await client.call_tool(
                "metadata_get",
                {"resource": "dataElements", "uid": "fClA2Erf6IO"},
            )
        ).structured_content or {}
        print(f"\nget_metadata(dataElements, fClA2Erf6IO): {one}")


if __name__ == "__main__":
    asyncio.run(main())
