"""Exercise the `metadata_share` MCP tool via an in-process FastMCP Client.

Resolves two data sets and one user group off the instance, then calls
`metadata_share` in dry-run mode - the typed result envelope without
mutating the shared local stack. Drop `dry_run=True` to actually apply.

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
        # The share is read-merge-write, so even a dry run reads each object -
        # the UIDs have to be real. Resolve them the way an agent would.
        data_sets = await client.call_tool(
            "metadata_list",
            {"profile": profile, "resource": "dataSets", "fields": "id,name", "page_size": 2},
        )
        uids = [row["id"] for row in data_sets.data or []]
        groups = await client.call_tool(
            "metadata_list",
            {"profile": profile, "resource": "userGroups", "fields": "id,name", "page_size": 1},
        )
        group_uid = (groups.data or [{}])[0].get("id")

        result = await client.call_tool(
            "metadata_share",
            {
                "profile": profile,
                "resource_type": "dataSet",
                "uids": uids,
                "public_access": "r-------",
                "user_group_access": [f"{group_uid}:rwrw----"],
                "dry_run": True,
            },
        )
        payload = result.data or result.structured_content or {}
        print(f"metadata_share dry-run over {len(uids)} data set(s): {type(payload).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
