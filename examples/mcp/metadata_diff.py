"""MCP example — call the `metadata_diff` tool against two bundles on disk.

Compares two bundles structurally and prints per-resource change counts. Swap
`live=True` (and drop `right_path`) to compare a bundle against the live
instance instead.

Usage:
    uv run python examples/mcp/metadata_diff.py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from dhis2w_mcp.server import build_server
from fastmcp import Client
from fastmcp.exceptions import ToolError


def _write(path: Path, bundle: dict[str, object]) -> None:
    path.write_text(json.dumps(bundle), encoding="utf-8")


async def main() -> None:
    """Diff two locally-generated bundles through the MCP tool and print the per-resource deltas."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        left = tmp_path / "baseline.json"
        right = tmp_path / "candidate.json"
        _write(left, {"dataElements": [{"id": "abc0000001", "name": "Old"}]})
        _write(
            right,
            {
                "dataElements": [
                    {"id": "abc0000001", "name": "New"},
                    {"id": "xyz0000002", "name": "Fresh"},
                ]
            },
        )
        async with Client(build_server()) as client:
            try:
                result = await client.call_tool(
                    "metadata_diff",
                    {"left_path": str(left), "right_path": str(right)},
                )
            except ToolError as exc:
                print(f"metadata_diff failed: {exc}")
                return
        diff = result.structured_content or {}
        print(f"{diff.get('left_label')} -> {diff.get('right_label')}")
        for resource in diff.get("resources", []):
            print(
                f"  {resource['resource']}: "
                f"+{len(resource['created'])} ~{len(resource['updated'])} "
                f"-{len(resource['deleted'])} ={resource['unchanged_count']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
