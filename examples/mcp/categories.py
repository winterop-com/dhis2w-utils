"""Exercise the `metadata_category_*` MCP tools via an in-process FastMCP Client.

Calls the read tools (`metadata_category_list`) to show the typed
shape on the wire. Writes (`metadata_category_create`,
`metadata_category_rename`, `metadata_category_add_option`,
`metadata_category_remove_option`, `metadata_category_delete`) are in
the tool surface — skipped here because mutating categories on the
shared local stack is disruptive without fixture coordination.

Usage:
    uv run python examples/mcp/categories.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and read the first page of Categories."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        listing = await client.call_tool(
            "metadata_list", {"resource": "categories", "profile": profile, "page_size": 5}
        )
        rows = listing.data or listing.structured_content or []
        print(f"metadata_category_list returned {len(rows)} rows")


if __name__ == "__main__":
    asyncio.run(main())
