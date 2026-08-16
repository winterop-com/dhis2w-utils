"""Reverse metadata lookup via the MCP `metadata_usage` tool.

Agent workflow: given a UID from a log / audit line, find every object
that references it before proposing a metadata change. Pairs with
`metadata_search` — search finds the UID, usage tells you what breaks if
you delete it.

Usage:
    uv run python examples/mcp/metadata_usage.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Probe DE + viz references against the seeded stack."""
    server = build_server()
    async with Client(server) as client:
        # DataElement — widest reference set (datasets, viz, maps, program stages, ...)
        result: dict[str, Any] = (
            await client.call_tool("metadata_usage", {"uid": "s46m5MS0hxu"})
        ).structured_content or {}
        hits = result.get("hits") or {}
        total = sum(len(v or []) for v in hits.values())
        print(f"s46m5MS0hxu (BCG doses given) referenced by {total} objects:")
        for resource, rows in hits.items():
            print(f"  {resource}: {len(rows)}")

        # Viz -> dashboards
        result = (await client.call_tool("metadata_usage", {"uid": "Qyuliufvfjl"})).structured_content or {}
        dash_hits = (result.get("hits") or {}).get("dashboards") or []
        print(f"\nQyuliufvfjl on {len(dash_hits)} dashboard(s): {[h['name'] for h in dash_hits]}")


if __name__ == "__main__":
    asyncio.run(main())
