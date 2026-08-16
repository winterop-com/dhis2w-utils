"""Exercise the `metadata_share` MCP tool via an in-process FastMCP Client.

Calls `metadata_share` in dry-run mode against a small cohort of data
sets — shows the typed result envelope without mutating the shared
local stack. Drop `dry_run=True` (and pass real UIDs / grants) to
actually apply.

Usage:
    uv run python examples/mcp/metadata_share.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and dry-run a bulk share."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        result = await client.call_tool(
            "metadata_share",
            {
                "profile": profile,
                "resource_type": "dataSet",
                "uids": ["DS_PLACEHOLDER_A", "DS_PLACEHOLDER_B"],
                "public_access": "r-------",
                "user_group_access": ["UG_PROG:rwrw----"],
                "dry_run": True,
            },
        )
        payload = result.data or result.structured_content or {}
        print(f"metadata_share dry-run returned {type(payload).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
