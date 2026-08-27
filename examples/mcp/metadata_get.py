"""Fetch one metadata object by UID through the MCP `metadata_get` tool.

Usage:
    uv run python examples/mcp/metadata_get.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Read a seeded data element, then the same object narrowed by fields."""
    server = build_server()
    async with Client(server) as client:
        full = (
            await client.call_tool(
                "metadata_get",
                {"resource": "dataElements", "uid": "fClA2Erf6IO"},
            )
        ).structured_content or {}
        print(f"dataElements/fClA2Erf6IO carries {len(full)} keys")

        # `fields` narrows what DHIS2 sends, which is what an agent wants when the
        # object is large and only a couple of properties matter.
        narrow = (
            await client.call_tool(
                "metadata_get",
                {"resource": "dataElements", "uid": "fClA2Erf6IO", "fields": "id,name,valueType"},
            )
        ).structured_content or {}
        print(f"narrowed: {narrow}")


if __name__ == "__main__":
    asyncio.run(main())
