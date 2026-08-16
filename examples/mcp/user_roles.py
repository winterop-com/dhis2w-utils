"""Browse DHIS2 user roles + their authorities via MCP tools.

Read-only agent walkthrough — lists every user role with its authority
count, then drills into the first role to print its full authority list.

User-group administration lives in the sibling `user_groups.py` example
(different DHIS2 resource: groups carry user memberships + sharing
grants, not authorities).

Write tools (`user_role_add_user`, `user_role_remove_user`) exist; this
example stays read-only to keep the seeded fixture clean.

Usage:
    uv run python examples/mcp/user_roles.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """List user roles + the authorities on the first one."""

    def _result(response: Any) -> Any:
        """Unwrap the `structured_content` wrapper from a FastMCP call_tool response."""
        payload = response.structured_content or response.data or {}
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    server = build_server()
    async with Client(server) as client:
        roles = _result(await client.call_tool("user_role_list", {"fields": "id,displayName,authorities,users"})) or []
        print(f"user roles: {len(roles)}")
        for role in roles[:3]:
            auth_count = len(role.get("authorities") or [])
            print(f"  {role.get('displayName')}  authorities={auth_count}")

        if roles:
            auths = _result(await client.call_tool("user_role_authority_list", {"uid": roles[0]["id"]})) or []
            print(f"\nfirst 10 authorities on {roles[0]['displayName']}:")
            for a in auths[:10]:
                print(f"  {a}")


if __name__ == "__main__":
    asyncio.run(main())
