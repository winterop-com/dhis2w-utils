"""Call the `whoami` + `system_info` MCP tools in-process.

Boots the dhis2 FastMCP server via `build_server()` and connects with
FastMCP's in-process `Client(server)`. No stdio transport, no subprocess —
same pattern `packages/dhis2w-mcp/tests/test_mcp_integration.py` uses.

Usage:
    uv run python examples/mcp/whoami.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE pointing at a profiles.toml entry).
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the MCP server in-process and invoke whoami + system_info."""
    server = build_server()
    async with Client(server) as client:
        me = await client.call_tool("system_whoami")
        info = await client.call_tool("system_info")
    print("whoami:", me.structured_content or me.data)
    print("system_info:", info.structured_content or info.data)


if __name__ == "__main__":
    asyncio.run(main())
