"""Call the `maintenance` MCP tools — tasks, cache, cleanup, data-integrity.

Mirrors examples/cli/maintenance.sh but goes through the MCP server
in-process. The task-polling pattern is what an agent would use to follow
any long-running DHIS2 operation (analytics refresh, metadata import,
data-integrity run).

Usage:
    uv run python examples/mcp/maintenance.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Walk the full maintenance tool surface end-to-end."""
    server = build_server()
    async with Client(server) as client:
        types = await client.call_tool("maintenance_task_type_list", {})
        type_names = (types.structured_content or {}).get("result", []) or types.data or []
        print(f"task types: {len(type_names)} -> {type_names[:5]}...")

        checks = await client.call_tool("maintenance_dataintegrity_checks", {})
        check_list = (checks.structured_content or {}).get("result", []) or checks.data or []
        print(f"data-integrity checks: {len(check_list)}")

        run = await client.call_tool(
            "maintenance_dataintegrity_run",
            {"checks": ["orgunits_invalid_geometry"]},
        )
        envelope = run.structured_content or run.data or {}
        task_uid = (envelope.get("response") or {}).get("id")
        print(f"kicked off DATA_INTEGRITY task: {task_uid}")

        await asyncio.sleep(2)
        result = await client.call_tool(
            "maintenance_dataintegrity_result",
            {"checks": ["orgunits_invalid_geometry"]},
        )
        print("dataintegrity_result:", result.structured_content or result.data)

        clear = await client.call_tool("maintenance_cache_clear", {})
        print("cache_clear:", clear.structured_content or clear.data)


if __name__ == "__main__":
    asyncio.run(main())
