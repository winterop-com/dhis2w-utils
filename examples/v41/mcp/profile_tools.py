"""Call the read-only `profile` MCP tools in-process.

Profile mutations (`add`, `remove`, `rename`, `switch`, `login`) are
CLI-only by design — you don't want an autonomous agent rewriting
your credential files. These four are what the MCP server exposes.

Usage:
    uv run python examples/v41/mcp/profile_tools.py

Env: profile must be discoverable (project or global profiles.toml, or raw DHIS2_URL + DHIS2_PAT).
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Exercise list_profiles / verify_profile / show_profile."""
    server = build_server()
    async with Client(server) as client:
        profiles = (await client.call_tool("profile_list")).structured_content
        print(f"list_profiles: {profiles}")

        # Pick the first profile and verify + show it.
        first = (profiles or {}).get("result", [None])[0]
        if first is None:
            print("(no profiles — run `d2w profile add ...` first)")
            return
        name = first["name"]

        verified = (await client.call_tool("profile_verify", {"name": name})).structured_content
        print(f"verify_profile({name!r}): {verified}")

        shown = (await client.call_tool("profile_show", {"name": name})).structured_content
        print(f"show_profile({name!r}): {shown}")


if __name__ == "__main__":
    asyncio.run(main())
