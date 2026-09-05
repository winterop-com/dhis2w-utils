"""Event and enrollment analytics from the client: `client.analytics.event_query` / `.enrollment_query`.

Two line-list reads distinct from the aggregate `/api/analytics` pivot:

1. `event_query(program, ...)` GETs `/api/analytics/events/query/<program>`,
   one row per event.
2. `enrollment_query(program, ...)` GETs `/api/analytics/enrollments/query/<program>`,
   one row per enrollment.

Both take the dimension and filter tokens `/api/analytics` takes
(`pe:LAST_12_MONTHS`, `ou:<uid>`, `<deUid>:GT:5`) and return the parsed
`Grid`. The plugin service wraps the same calls for the CLI and MCP surfaces;
this is the library path.

Uses the seeded Child Programme. Runs on v41 and v42; v43's event-analytics
SQL emitter rejects the 2024 event data the fixture carries (BUGS.md #36), so
`make verify-examples` skips this one on a v43 stack.

Usage:
    uv run python examples/client/analytics_event_query.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import Grid
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PROGRAM_UID = "IpHINAT79UW"  # Child Programme
ORG_UNIT_UID = "ImspTQPwCqd"  # Sierra Leone root


async def main() -> None:
    """Run one event query and one enrollment query against the seeded tracker program."""
    async with open_client(profile_from_env()) as client:
        print(f"--- events: program={PROGRAM_UID} ou={ORG_UNIT_UID} ---")
        events = await client.analytics.event_query(
            PROGRAM_UID,
            dimension=[f"ou:{ORG_UNIT_UID}", "pe:LAST_12_MONTHS"],
            output_type="EVENT",
            page_size=5,
            extra_params={"skipMeta": "true"},
        )
        _print_grid(events)

        print(f"--- enrollments: program={PROGRAM_UID} ---")
        enrollments = await client.analytics.enrollment_query(
            PROGRAM_UID,
            dimension=[f"ou:{ORG_UNIT_UID}", "pe:LAST_12_MONTHS"],
            page_size=5,
            extra_params={"skipMeta": "true"},
        )
        _print_grid(enrollments)


def _print_grid(grid: Grid) -> None:
    """Print a `Grid` envelope as header names and its first rows."""
    headers = [header.name for header in grid.headers or []]
    rows = grid.rows or []
    print(f"  headers ({len(headers)}): {headers[:6]}")
    print(f"  rows: {len(rows)}")
    for row in rows[:3]:
        print(f"    {row[:6]}")


if __name__ == "__main__":
    run_example(main)
