"""Import a metadata bundle through the MCP `metadata_import` tool.

`bundle_path` reads the bundle off disk, so the same file an export wrote is what
an import takes and a multi-megabyte bundle never crosses the MCP channel
(`bundle_inline` takes a small one directly). `dry_run` is the posture an agent
should reach for first: DHIS2 validates and preheats, answers with the report a
real import would have produced, and writes nothing.

Usage:
    uv run python examples/mcp/metadata_import.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from dhis2w_client import generate_uid
from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Dry-run a one-object bundle, commit it, then take it back out."""
    async with Client(build_server()) as client:
        with TemporaryDirectory() as tmp:
            minted = generate_uid()
            bundle_path = Path(tmp) / "bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "indicatorTypes": [
                            {"id": minted, "name": f"Example import type {minted}", "factor": 1, "number": False},
                        ],
                    },
                ),
                encoding="utf-8",
            )
            print(f"bundle carries indicatorTypes/{minted}")

            dry = await client.call_tool(
                "metadata_import",
                {"bundle_path": str(bundle_path), "dry_run": True},
            )
            body = dry.structured_content or {}
            print(f"dry run: {body.get('status') or body.get('httpStatus')}")

            real = await client.call_tool(
                "metadata_import",
                {"bundle_path": str(bundle_path), "import_strategy": "CREATE_AND_UPDATE"},
            )
            body = real.structured_content or {}
            print(f"import:  {body.get('status') or body.get('httpStatus')}")

            teardown = await client.call_tool(
                "metadata_import",
                {"bundle_path": str(bundle_path), "import_strategy": "DELETE"},
            )
            body = teardown.structured_content or {}
            print(f"delete:  {body.get('status') or body.get('httpStatus')}")


if __name__ == "__main__":
    asyncio.run(main())
