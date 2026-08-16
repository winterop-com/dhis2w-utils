"""Call the `route` MCP tools — list / create / run / delete an integration route.

Mirrors examples/cli/route_register_and_run.sh but via the MCP server. The created route
proxies to httpbin.org so the `run` call produces a visible round-trip.

Usage:
    uv run python examples/mcp/route_register_and_run.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Create a throwaway route, run it, clean up."""
    server = build_server()
    async with Client(server) as client:
        before = await client.call_tool("route_list", {})
        # `route_list` returns `list[Route]`; the typed list lives on `.data`.
        # `.structured_content` wraps the same payload in `{"result": [...]}`
        # because FastMCP's JSON schema serializer needs a top-level object.
        rows = before.data or []
        print(f"before: {len(rows)} routes")

        # Clean up any leftover route with the same code from a previous failed
        # run — DHIS2 enforces uniqueness on `code` + `name` so a stale entry
        # would 409 the create below. Makes the example idempotent.
        for row in rows:
            if getattr(row, "code", None) == "MCP_SMOKE":
                stale_uid = getattr(row, "id", None)
                await client.call_tool("route_delete", {"route": stale_uid})
                print(f"cleaned stale route {stale_uid}")

        created = await client.call_tool(
            "route_create",
            {
                "payload": {
                    "code": "MCP_SMOKE",
                    "name": "MCP smoke route",
                    "url": "https://httpbin.org/get",
                },
            },
        )
        envelope = created.structured_content or created.data or {}
        response_block = envelope.get("response") or {}
        uid = response_block.get("uid") or response_block.get("id")
        print(f"created uid={uid}")

        ran = await client.call_tool("route_run", {"route": uid})
        body = ran.structured_content or ran.data or {}
        print(f"ran     upstream returned: {list(body.keys())[:5]}")

        await client.call_tool("route_delete", {"route": uid})
        print(f"deleted {uid}")


if __name__ == "__main__":
    asyncio.run(main())
