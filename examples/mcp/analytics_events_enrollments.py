"""Call the `analytics_events_query` + `analytics_enrollments_query` MCP tools.

Mirrors examples/client/analytics_events_enrollments.py but goes through
the MCP server in-process. Demonstrates the two tracker-side analytics shapes
an agent can query — distinct from the aggregate `analytics_query` tool.

Uses the seeded Child Programme (`IpHINAT79UW`) from the e2e dump.

Runs on v41 and v42. DHIS2 v43's event-analytics SQL emitter rejects the
2024 event data this fixture carries (BUGS.md #36), so `make verify-examples`
skips this one on a v43 stack.

Usage:
    uv run python examples/mcp/analytics_events_enrollments.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client

PROGRAM_UID = "IpHINAT79UW"  # Child Programme — seeded tracker program.
ORG_UNIT_UID = "ImspTQPwCqd"  # Sierra Leone root.


async def main() -> None:
    """Run both tools against the seeded tracker program."""
    server = build_server()
    async with Client(server) as client:
        events = await client.call_tool(
            "analytics_events_query",
            {
                "program": PROGRAM_UID,
                "dimensions": [f"ou:{ORG_UNIT_UID}", "pe:LAST_12_MONTHS"],
                "output_type": "EVENT",
                "page_size": 5,
                "skip_meta": True,
            },
        )
        payload = events.structured_content or events.data or {}
        rows = (payload.get("result") or payload).get("rows", [])
        print(f"event rows: {len(rows)}")
        for row in rows[:3]:
            print("  ", row[:6], "...")

        enrollments = await client.call_tool(
            "analytics_enrollments_query",
            {
                "program": PROGRAM_UID,
                "dimensions": [f"ou:{ORG_UNIT_UID}", "pe:LAST_12_MONTHS"],
                "page_size": 5,
                "skip_meta": True,
            },
        )
        payload = enrollments.structured_content or enrollments.data or {}
        rows = (payload.get("result") or payload).get("rows", [])
        print(f"\nenrollment rows: {len(rows)}")
        for row in rows[:3]:
            print("  ", row[:6], "...")


if __name__ == "__main__":
    asyncio.run(main())
