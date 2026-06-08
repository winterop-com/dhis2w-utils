"""Exercise the `system_*` MCP tools via an in-process FastMCP Client.

Calls the read tools: `system_whoami`, `system_info`, `system_settings_get`,
`system_settings_list`.

Usage:
    uv run python examples/v41/mcp/system.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and call both read tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        me = await client.call_tool("system_whoami", {"profile": profile})
        me_payload = me.data or me.structured_content or {}
        print(f"system_whoami returned {type(me_payload).__name__}")

        info = await client.call_tool("system_info", {"profile": profile})
        info_payload = info.data or info.structured_content or {}
        print(f"system_info returned {type(info_payload).__name__}")

        title = await client.call_tool("system_settings_get", {"key": "applicationTitle", "profile": profile})
        print(f"system_settings_get(applicationTitle) -> {title.data}")

        settings = await client.call_tool("system_settings_list", {"profile": profile})
        settings_payload = settings.data or settings.structured_content or {}
        print(f"system_settings_list returned {type(settings_payload).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
