"""Exercise the `files_*` MCP tools via an in-process FastMCP Client.

Calls the read verb (`files_documents_list`) to show every tool lands
typed shapes on the wire. Writes (`files_documents_create_external`,
`files_documents_delete`) and the per-resource read tools
(`files_documents_get`, `files_resources_get`) are in the tool surface
— skipped here because mutating or per-UID lookups against the shared
local stack are disruptive without fixture coordination.

Usage:
    uv run python examples/mcp/files.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and call a couple of read tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        listing = await client.call_tool("files_documents_list", {"profile": profile, "page_size": 5})
        rows = listing.data or listing.structured_content or []
        print(f"files_documents_list returned {len(rows)} rows")


if __name__ == "__main__":
    asyncio.run(main())
