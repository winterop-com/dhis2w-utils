"""Exercise the `apps_*` MCP tools via an in-process FastMCP Client.

Calls the read verbs (`apps_list`, `apps_hub_list`) to show every tool
lands typed shapes on the wire. Writes (`apps_install_from_*`,
`apps_uninstall`, `apps_update*`) are in the tool surface — skipped here
because installing + uninstalling apps against the shared local stack
is disruptive.

Usage:
    uv run python examples/mcp/apps.py
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
        installed = await client.call_tool("apps_list", {"profile": profile})
        apps = installed.data or installed.structured_content or []
        print(f"apps_list returned {len(apps)} rows")

        hub = await client.call_tool("apps_hub_list", {"profile": profile})
        hub_rows = hub.data or hub.structured_content or []
        print(f"apps_hub_list returned {len(hub_rows)} catalog rows")


if __name__ == "__main__":
    asyncio.run(main())
