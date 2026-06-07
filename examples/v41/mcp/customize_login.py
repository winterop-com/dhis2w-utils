"""Brand a DHIS2 instance from an MCP agent — logos + login-page copy.

Usage:
    uv run python examples/v41/mcp/customize_login.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dhis2w_mcp.server import build_server
from fastmcp import Client

LOGIN_DIR = Path(__file__).resolve().parents[3] / "infra" / "login-customization"


async def main() -> None:
    """Drive the `customize_*` MCP tools against the default profile."""
    async with Client(build_server()) as client:
        # Read the current state.
        snapshot = await client.call_tool("customize_show", {})
        payload = snapshot.structured_content or {}
        print(f"current title: {payload.get('applicationTitle')}")

        # Upload a branded front logo (also flips keyUseCustomLogoFront=true).
        await client.call_tool(
            "customize_logo_front",
            {"path": str(LOGIN_DIR / "logo_front.png")},
        )

        # Bulk-set the login copy.
        await client.call_tool(
            "system_settings_set_many",
            {
                "settings": {
                    "applicationTitle": "dhis2-utils local",
                    "keyApplicationIntro": "Seeded fixture.",
                    "keyApplicationNotification": "Development instance.",
                    "keyApplicationFooter": "Powered by dhis2-utils",
                },
            },
        )

        # Or apply the committed preset directory in one call.
        await client.call_tool(
            "customize_apply",
            {"directory": str(LOGIN_DIR)},
        )


if __name__ == "__main__":
    asyncio.run(main())
