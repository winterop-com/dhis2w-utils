"""Exercise the `metadata_category_combo_*` MCP tools via an in-process FastMCP Client.

Calls the read tools (`metadata_category_combo_list`,
`metadata_category_option_combo_list`) — the safe read-only halves of
the surface. Writes (`metadata_category_combo_create` /
`_add_category` / `_rename` / `_delete` / `_wait_for_cocs`) are in
the tool surface but skipped here because creating a CategoryCombo
on the shared local stack triggers an async COC matrix regen and
mutates the disaggregation graph — disruptive without fixture
coordination.

Usage:
    uv run python examples/v41/mcp/category_combos.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Connect to the in-process MCP server and read CategoryCombos + their COCs."""
    profile = os.environ.get("DHIS2_PROFILE", "local_basic")
    async with Client(build_server()) as client:
        combos = await client.call_tool(
            "metadata_list", {"resource": "categoryCombos", "profile": profile, "page_size": 5}
        )
        rows = combos.data or combos.structured_content or []
        print(f"metadata_category_combo_list returned {len(rows)} rows")

        cocs = await client.call_tool(
            "metadata_list", {"resource": "categoryOptionCombos", "profile": profile, "page_size": 5}
        )
        coc_rows = cocs.data or cocs.structured_content or []
        print(f"metadata_category_option_combo_list returned {len(coc_rows)} rows")


if __name__ == "__main__":
    asyncio.run(main())
