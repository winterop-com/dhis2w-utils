"""Browse DHIS2 user groups + their sharing block via MCP tools.

Read-only agent walkthrough — lists every user group, prints member
counts, then reads the sharing block for the first group (public access,
per-user grants, per-group grants).

User-role administration lives in the sibling `user_roles.py` example
(different DHIS2 resource: roles carry authorities, not memberships).

Write tools (`user_group_add_member`, `user_group_remove_member`, the
sharing-grant flow via CLI) exist; this example stays read-only to keep
the seeded fixture clean.

Usage:
    uv run python examples/mcp/user_groups.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """List user groups + their sharing surface."""

    def _result(response: Any) -> Any:
        """Unwrap the `structured_content` wrapper from a FastMCP call_tool response."""
        payload = response.structured_content or response.data or {}
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    server = build_server()
    async with Client(server) as client:
        groups = _result(await client.call_tool("user_group_list", {"fields": "id,displayName,users"})) or []
        print(f"user groups: {len(groups)}")
        for group in groups[:3]:
            members = group.get("users") or []
            print(f"  {group.get('displayName')}  ({group.get('id')})  members={len(members)}")

        if groups:
            first_uid = groups[0].get("id")
            sharing = _result(await client.call_tool("user_group_sharing_get", {"uid": first_uid})) or {}
            print(f"\nsharing for user group {first_uid}:")
            print(f"  publicAccess={sharing.get('publicAccess')}")
            print(f"  userAccesses={len(sharing.get('userAccesses') or [])}")
            print(f"  userGroupAccesses={len(sharing.get('userGroupAccesses') or [])}")


if __name__ == "__main__":
    asyncio.run(main())
