"""Call the `fhir_forward` MCP tool - drain a FHIR project's capture spool into DHIS2.

Dry run is the default and is what this example shows: every payload goes to the real
endpoint under its own validate-only mode, so DHIS2 decides each answer while nothing is
written and no receipt moves. Pass `dry_run=False` to commit.

Fill the spool first with examples/v42/cli/fhir_forward.sh, or any `d2w fhir serve` that
has been POSTed a QuestionnaireResponse.

Usage:
    uv run python examples/v42/mcp/fhir_forward.py [PROJECT_DIRECTORY]
"""

from __future__ import annotations

import asyncio
import sys

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Dry-run the spool of the given project (default: the nearest one) and print what each response became."""
    arguments: dict[str, object] = {"dry_run": True}
    if len(sys.argv) > 1:
        arguments["project_directory"] = sys.argv[1]
    server = build_server()
    async with Client(server) as client:
        result = await client.call_tool("fhir_forward", arguments)
        report = result.structured_content or {}
        outcomes = report.get("outcomes", [])
        counted = {
            kind: sum(1 for outcome in outcomes if outcome["kind"] == kind)
            for kind in ("accepted", "rejected", "refused", "unverifiable")
        }
        print(
            f"{'dry run' if report.get('dry_run') else 'import'}: {report.get('spooled')} spooled, "
            f"{counted['accepted']} accepted, {counted['rejected']} rejected, {counted['refused']} refused, "
            f"{counted['unverifiable']} unverifiable in a dry run "
            f"({report.get('coded_answer_mode')} coded answers)"
        )
        for outcome in outcomes[:10]:
            imported = outcome.get("import_outcome") or {}
            # A rejection carries one issue per rule DHIS2 found broken - errorCode, the object it
            # names, and the message itself - so "why" is answerable without opening the instance.
            reasons = [
                " ".join(part for part in (issue.get("error_code"), issue.get("subject"), issue.get("message")) if part)
                for issue in imported.get("issues", [])
            ]
            why = "; ".join(refusal["reason"] for refusal in outcome.get("refusals", [])) or "; ".join(reasons)
            print(f"  {outcome['kind']:9} {outcome['response_id']} {outcome.get('target_kind') or '':16} {why}")


if __name__ == "__main__":
    asyncio.run(main())
