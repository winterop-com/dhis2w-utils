"""Cross-resource metadata search via the MCP `metadata_search` tool.

Shows the single verb an agent needs to resolve a UID, a business code,
or a name fragment across every DHIS2 resource type in one call.

Usage:
    uv run python examples/mcp/metadata_search.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Run a name search, a UID resolve, and a partial-UID probe."""
    server = build_server()
    async with Client(server) as client:
        # Name fragment — broadest match, hits every resource type.
        name_result: dict[str, Any] = (
            await client.call_tool("metadata_search", {"query": "measles"})
        ).structured_content or {}
        total = name_result.get("total", 0) or sum(len(v or []) for v in (name_result.get("hits") or {}).values())
        hits = name_result.get("hits") or {}
        print(f"'measles' -> {total} objects across {len(hits)} resources")
        for resource, rows in hits.items():
            print(f"  {resource}: {len(rows)}")

        # Full UID — resolves to the owning resource.
        uid_result = (await client.call_tool("metadata_search", {"query": "s46m5MS0hxu"})).structured_content or {}
        flat = [hit for rows in (uid_result.get("hits") or {}).values() for hit in (rows or [])]
        if flat:
            hit = flat[0]
            print(f"\ns46m5MS0hxu -> {hit['resource']}/{hit['uid']}: {hit['name']}")

        # Partial UID + small page size — quick "what's in this instance" probe.
        prefix_result = (
            await client.call_tool("metadata_search", {"query": "imm", "page_size": 5})
        ).structured_content or {}
        prefix_hits = prefix_result.get("hits") or {}
        print(f"\n'imm' (page_size=5) -> {sum(len(v) for v in prefix_hits.values())} objects")


if __name__ == "__main__":
    asyncio.run(main())
