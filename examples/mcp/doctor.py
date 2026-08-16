"""`doctor_run` MCP tool — structured probe results for an agent to inspect.

Usage:
    uv run python examples/mcp/doctor.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Call `doctor_run` and print a probe-by-probe summary."""
    async with Client(build_server()) as client:
        result = await client.call_tool("doctor_run", {})
        report = result.structured_content or {}
        print(f"DHIS2 {report.get('dhis2_version')} at {report.get('base_url')}")
        for probe in report.get("probes", []):
            status = probe.get("status", "?")
            print(f"  [{status}] {probe.get('name')}: {probe.get('message')}")


if __name__ == "__main__":
    asyncio.run(main())
