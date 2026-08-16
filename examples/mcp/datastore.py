"""Drive the `datastore_*` MCP tools in-process.

Mirrors examples/client/datastore.py but goes through the MCP server: an agent sets a value,
reads it back, lists namespaces, then deletes the key. Values are arbitrary JSON.

Usage:
    uv run python examples/mcp/datastore.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client

NAMESPACE = "dhis2w_utils_demo"
KEY = "example"


async def main() -> None:
    """Set / get / list / delete a demo key through the datastore tools."""
    server = build_server()
    async with Client(server) as client:
        await client.call_tool("datastore_set", {"namespace": NAMESPACE, "key": KEY, "value": {"hello": "world"}})
        print(f"set {NAMESPACE}/{KEY}")

        got = await client.call_tool("datastore_get", {"namespace": NAMESPACE, "key": KEY})
        print(f"get {NAMESPACE}/{KEY} -> {got.data}")

        namespaces = await client.call_tool("datastore_list_namespaces", {})
        print(f"namespaces: {len(namespaces.data)}")

        await client.call_tool("datastore_delete", {"namespace": NAMESPACE, "key": KEY})
        print(f"deleted {NAMESPACE}/{KEY}")


if __name__ == "__main__":
    asyncio.run(main())
