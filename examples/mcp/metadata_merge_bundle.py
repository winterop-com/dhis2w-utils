"""Exercise the `metadata_merge_bundle` MCP tool via an in-process FastMCP Client.

Calls `metadata_merge_bundle` in dry-run mode against a tiny inline
bundle written to a temp file — shows the typed `MergeResult` envelope
without mutating the shared local stack. Drop `dry_run=True` to apply.

Usage:
    uv run python examples/mcp/metadata_merge_bundle.py
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and dry-run a bundle import."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    bundle = {
        "system": {"id": "demo"},
        "dataElements": [
            {
                "id": "DEdemo00001",
                "name": "Demo data element",
                "shortName": "DemoDE",
                "valueType": "INTEGER",
                "domainType": "AGGREGATE",
                "aggregationType": "SUM",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        bundle_path.write_text(json.dumps(bundle))
        async with Client(build_server()) as client:
            result = await client.call_tool(
                "metadata_merge_bundle",
                {
                    "target_profile": profile,
                    "bundle_path": str(bundle_path),
                    "dry_run": True,
                },
            )
            payload = result.data or result.structured_content or {}
            print(f"metadata_merge_bundle dry-run returned {type(payload).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
