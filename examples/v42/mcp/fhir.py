"""Call the `fhir` MCP tools — scaffold a SUSHI IG project and generate FSH from DHIS2 metadata.

Mirrors examples/v42/cli/fhir_generate.sh but via the MCP server.

Usage:
    uv run python examples/v42/mcp/fhir.py
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Scaffold a demo IG project, generate option-set and org-unit FSH, then clean up."""
    project_directory = Path("demo-ig").resolve()
    server = build_server()
    async with Client(server) as client:
        scaffold = await client.call_tool(
            "fhir_init",
            {
                "directory": str(project_directory),
                "ig_id": "dhis2.fhir.demo",
                "canonical": "http://example.org/fhir/demo",
                "publisher": "Demo Org",
            },
        )
        created = (scaffold.structured_content or {}).get("created_files", [])
        print(f"scaffolded {len(created)} files into {project_directory}")

        option_sets = await client.call_tool("fhir_generate_option_sets", {"project_directory": str(project_directory)})
        report = option_sets.structured_content or {}
        print(f"option sets: {report.get('option_set_count')} sets, {len(report.get('written_files', []))} files")

        org_units = await client.call_tool("fhir_generate_org_units", {"project_directory": str(project_directory)})
        report = org_units.structured_content or {}
        print(f"org units: {report.get('org_unit_count')} units, {report.get('location_count')} locations")

    shutil.rmtree(project_directory)


if __name__ == "__main__":
    asyncio.run(main())
