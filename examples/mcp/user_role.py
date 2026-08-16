"""Exercise the `user_role_*` MCP tools via an in-process FastMCP Client.

Calls the read verb (`user_role_list`) to show every tool lands typed
shapes on the wire. The per-UID reads (`user_role_get`,
`user_role_authority_list`) and writes (`user_role_add_user`,
`user_role_remove_user`) are in the tool surface — skipped here because
per-UID and mutating calls against the shared local stack are
disruptive without fixture coordination.

Usage:
    uv run python examples/mcp/user_role.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and call a read tool."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        listing = await client.call_tool("user_role_list", {"profile": profile, "page_size": 5})
        rows = listing.data or listing.structured_content or []
        print(f"user_role_list returned {len(rows)} rows")


if __name__ == "__main__":
    asyncio.run(main())
