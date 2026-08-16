"""Tracker authoring workflow via the MCP `data_tracker_*` tools.

Agent workflow: register a patient, log an event, query outstanding.
Handles both tracker (with enrollment) and event-only programs via the
same `data_tracker_event_create` tool — the enrollment arg is optional.

Usage:
    uv run python examples/mcp/tracker_workflow.py

Env: DHIS2_URL + DHIS2_PAT (or DHIS2_PROFILE).
"""

from __future__ import annotations

import asyncio
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Demonstrate register -> event -> outstanding via MCP tools."""
    server = build_server()
    async with Client(server) as client:
        # 1. Grab a facility OU via the metadata_list tool.
        ou_result = (
            await client.call_tool(
                "metadata_list",
                {"resource": "organisationUnits", "filters": ["level:eq:4"], "page_size": 1},
            )
        ).structured_content or {}
        ou_id = (ou_result.get("items") or [{}])[0].get("id") or ou_result.get("result", [{}])[0].get("id")
        print(f"Facility OU: {ou_id}")

        # 2. Register a patient — tracker program IpHINAT79UW (Child Programme).
        result: dict[str, Any] = (
            await client.call_tool(
                "data_tracker_register",
                {
                    "program": "IpHINAT79UW",
                    "org_unit": ou_id,
                    "tracked_entity_type": "nEenWmSyUEp",  # Person
                    "attributes": {"w75KJ2mc4zz": "Fatmata", "zDhUuAYrxNC": "Sesay"},
                    "enrolled_at": "2025-06-01",
                },
            )
        ).structured_content or {}
        te_uid = result["tracked_entity"]
        enrollment = result["enrollment"]
        print(f"Registered TE={te_uid} enrollment={enrollment}")

        # 3. Log the Birth stage event (tracker program -> pass enrollment).
        event_result = (
            await client.call_tool(
                "data_tracker_event_create",
                {
                    "program": "IpHINAT79UW",
                    "program_stage": "A03MvHHogjR",
                    "org_unit": ou_id,
                    "enrollment": enrollment,
                    "tracked_entity": te_uid,
                    "occurred_at": "2025-06-02",
                },
            )
        ).structured_content or {}
        print(f"Logged Birth event {event_result['event']}")

        # 4. Outstanding: expect Baby Postnatal (ZzYYXq4fJie) to appear.
        outstanding = (
            await client.call_tool(
                "data_tracker_outstanding",
                {"program": "IpHINAT79UW", "org_unit": ou_id},
            )
        ).structured_content or {}
        rows = outstanding.get("result") or outstanding
        if isinstance(rows, list):
            mine = [r for r in rows if isinstance(r, dict) and r.get("enrollment") == enrollment]
            if mine:
                print(f"Still due on our enrollment: {mine[0].get('missing_stages')}")


if __name__ == "__main__":
    asyncio.run(main())
