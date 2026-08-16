"""MCP-driven metadata export + import — same round-trip as the CLI, through tools.

Usage:
    uv run python examples/mcp/metadata_export_import.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Drive `metadata_export` + `metadata_import` MCP tools."""
    async with Client(build_server()) as client:
        with TemporaryDirectory() as tmp:
            bundle_path = str(Path(tmp) / "bundle.json")

            # Export writes to disk so the bundle doesn't flow through the MCP
            # payload for big exports — return value is a {resource: count} summary.
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
                if key.startswith("_"):
                    continue
                print(f"  {key}: {value}")

            # Dry-run import — DHIS2 validates + preheats without committing.
            report = await client.call_tool(
                "metadata_import",
                {"bundle_path": bundle_path, "dry_run": True},
            )
            body = report.structured_content or {}
            print(f"\nimport status: {body.get('status') or body.get('httpStatus')}")


if __name__ == "__main__":
    asyncio.run(main())
