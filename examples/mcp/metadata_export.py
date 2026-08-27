"""Export a metadata bundle through the MCP `metadata_export` tool.

The tool writes the bundle to disk and returns a `{resource: count}` summary, so
a large export never flows through the MCP payload — the agent gets the shape of
what it pulled and a path to hand to the next step.

Usage:
    uv run python examples/mcp/metadata_export.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Export a narrow slice to a file and read the summary the tool answers with."""
    async with Client(build_server()) as client:
        with TemporaryDirectory() as tmp:
            bundle_path = str(Path(tmp) / "bundle.json")

            summary = await client.call_tool(
                "metadata_export",
                {
                    "resources": ["dataElements", "indicatorTypes"],
                    "fields": ":owner",
                    "output_path": bundle_path,
                },
            )
            payload = summary.structured_content or {}
            print(f"exported to {payload.get('_path')}")
            for key, value in payload.items():
                if key.startswith("_") or not isinstance(value, int):
                    continue
                print(f"  {key}: {value}")

            # A narrow slice leaves references pointing at objects it did not pull,
            # and the tool names them rather than letting the bundle fail on import.
            dangling = payload.get("dangling_references") or {}
            for item in dangling.get("items", []):
                print(f"  dangling {item['field_name']} -> {len(item['missing_uids'])} uid(s) not in the bundle")


if __name__ == "__main__":
    asyncio.run(main())
