"""Call the read-only `fhir_validate` MCP tool - FHIR-safety of a DHIS2 instance's codes.

Scaffolding and generation are CLI-only (see examples/v43/cli/fhir_generate.sh);
the MCP surface answers the one data-shaped question an agent actually asks.

Usage:
    uv run python examples/v43/mcp/fhir.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Validate the active instance's codes and print the severity counts."""
    server = build_server()
    async with Client(server) as client:
        result = await client.call_tool("fhir_validate", {})
        report = result.structured_content or {}
        print(
            f"swept {report.get('object_count')} objects across {report.get('resource_type_count')} types; "
            f"{report.get('error_count')} errors, {report.get('warning_count')} warnings, "
            f"{report.get('info_count')} infos"
        )
        for finding in report.get("findings", [])[:10]:
            print(f"  {finding['severity']:8} {finding['category']:15} {finding['name']} code={finding['code']!r}")


if __name__ == "__main__":
    asyncio.run(main())
