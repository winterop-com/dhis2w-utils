"""User plugin MCP tools — list, get, me.

Write tools (`user_invite`, `user_reinvite`, `user_reset_password`) are
registered too; the example stays read-only to avoid hitting real DHIS2
state. Uncomment the tool calls at the bottom to exercise them.

Usage:
    uv run python examples/mcp/user_administration.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Walk through the read tools; print a few fields from each."""
    server = build_server()
    async with Client(server) as client:
        listing = await client.call_tool(
            "user_list",
            {
                "fields": "id,username,displayName,disabled,lastLogin",
                "filters": ["disabled:eq:false"],
                "order": ["lastLogin:desc"],
                "page_size": 5,
            },
        )
        users = listing.structured_content or listing.data or []
        if isinstance(users, dict):
            users = users.get("result", [])
        print(f"active users: {len(users)}")
        for user in users[:3]:
            print(f"  {user.get('id')}  {user.get('username')}  last_login={user.get('lastLogin')}")

        me = await client.call_tool("system_whoami", {})
        payload = me.structured_content or me.data or {}
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
        print(f"\nauthenticated as {payload.get('username')} ({payload.get('id')})")

        if users:
            get_result = await client.call_tool("user_get", {"uid_or_username": users[0]["username"]})
            one = get_result.structured_content or get_result.data or {}
            if isinstance(one, dict) and "result" in one:
                one = one["result"]
            print(f"\nget by username -> {one.get('username')} ({one.get('id')})")

        # Write tools — uncomment to exercise.
        #
        # await client.call_tool("user_invite", {
        #     "email": "alice@example.com",
        #     "first_name": "Alice",
        #     "surname": "Example",
        #     "username": "alice",
        #     "user_role_uids": ["<ROLE_UID>"],
        #     "org_unit_uids": ["ImspTQPwCqd"],
        # })
        # await client.call_tool("user_reset_password", {"uid": "<UID>"})


if __name__ == "__main__":
    asyncio.run(main())
