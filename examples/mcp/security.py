"""Exercise the cheap read-only `security_*` MCP tools via an in-process FastMCP Client.

Calls the three single-request read tools: `security_settings`, `security_authorities`,
and `security_version`. The long-running `d2w security audit` stays CLI-only and is not
an MCP tool.

Usage:
    uv run python examples/mcp/security.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and call the three security read tools."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        settings = await client.call_tool("security_settings", {"profile": profile})
        settings_payload = settings.data or settings.structured_content or {}
        print(f"security_settings returned {type(settings_payload).__name__}")

        authorities = await client.call_tool("security_authorities", {"profile": profile})
        authorities_payload = authorities.data or authorities.structured_content or {}
        print(f"security_authorities returned {type(authorities_payload).__name__}")

        version = await client.call_tool("security_version", {"profile": profile})
        version_payload = version.data or version.structured_content or {}
        print(f"security_version returned {type(version_payload).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
