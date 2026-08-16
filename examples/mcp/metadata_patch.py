"""MCP example — apply an RFC 6902 JSON Patch via the `metadata_patch` tool.

Agents call `metadata_patch(resource, uid, ops)` with a list of
`{op, path, value?, from?}` dicts. FastMCP validates each op through
`JsonPatchOpAdapter` server-side (via pydantic on the tool signature) so
wrong-shape ops fail with a clear error instead of silently shipping bad
JSON to DHIS2.

Usage:
    uv run python examples/mcp/metadata_patch.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client
from fastmcp.exceptions import ToolError


async def main() -> None:
    """Patch the first dataElement's description + code, then revert."""
    async with Client(build_server()) as mcp:
        # 1. Find a target dataElement via the list tool.
        elements_result = await mcp.call_tool(
            "metadata_list",
            {"resource": "dataElements", "page_size": 1, "fields": "id,name,description"},
        )
        elements = elements_result.structured_content or []
        if not isinstance(elements, list) or not elements:
            print("no dataElements available; seed the stack first")
            return
        uid = elements[0]["id"]
        print(f"target: dataElements/{uid}  (name={elements[0].get('name')!r})")

        # 2. Apply a patch: replace description + add a code value.
        print("\n--- apply patch")
        try:
            patch_result = await mcp.call_tool(
                "metadata_patch",
                {
                    "resource": "dataElements",
                    "uid": uid,
                    "ops": [
                        {"op": "replace", "path": "/description", "value": "Set by MCP metadata_patch"},
                        {"op": "add", "path": "/code", "value": "MCP_PATCH_EXAMPLE"},
                    ],
                },
            )
        except ToolError as exc:
            print(f"  metadata_patch failed: {exc}")
            return
        response = patch_result.structured_content or {}
        print(f"  WebMessageResponse.status={response.get('status')!r}")

        # 3. Verify via get.
        after_result = await mcp.call_tool(
            "metadata_get",
            {"resource": "dataElements", "uid": uid, "fields": "id,description,code"},
        )
        after = after_result.structured_content or {}
        print(f"  description after: {after.get('description')!r}")
        print(f"  code after: {after.get('code')!r}")

        # 4. Revert (keeps the example idempotent).
        print("\n--- revert cleanup")
        await mcp.call_tool(
            "metadata_patch",
            {
                "resource": "dataElements",
                "uid": uid,
                "ops": [
                    {"op": "remove", "path": "/description"},
                    {"op": "remove", "path": "/code"},
                ],
            },
        )
        print("  cleanup applied")


if __name__ == "__main__":
    asyncio.run(main())
