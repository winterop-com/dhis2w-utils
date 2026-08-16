"""Event + enrollment analytics — typed Grid responses via the service layer.

Two analytics shapes distinct from the aggregate `/api/analytics` endpoint:

1. **Event analytics** (`/api/analytics/events/{query,aggregate}/{program}`) —
   line-listed events or grouped counts across a tracker/event program. Each
   row describes one event: psi, ps, eventdate, orgUnit, data-element values.
2. **Enrollment analytics** (`/api/analytics/enrollments/query/{program}`) —
   one row per tracker enrollment with its tracked-entity + attributes.

Both take the same dimension/filter DSL as `/api/analytics`:
`dx:<uid>`, `pe:LAST_12_MONTHS`, `ou:<uid>` (repeatable).

Uses the seeded Child Programme (`IpHINAT79UW`) from the e2e dump.

Runs on v41 and v42. DHIS2 v43's event-analytics SQL emitter rejects the
2024 event data this fixture carries (BUGS.md #36), so `make verify-examples`
skips this one on a v43 stack.

Usage:
    uv run python examples/client/analytics_events_enrollments.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.analytics import service

PROGRAM_UID = "IpHINAT79UW"  # Child Programme — seeded tracker program with immunization stages.
ORG_UNIT_UID = "ImspTQPwCqd"  # Sierra Leone root.


async def main() -> None:
    """Run one event-query and one enrollment-query against the seeded tracker program."""
    profile = profile_from_env()

    print(f"--- event analytics: program={PROGRAM_UID} ou={ORG_UNIT_UID} ---")
    events = await service.query_events(
        profile,
        program=PROGRAM_UID,
        mode="query",
        dimensions=[f"ou:{ORG_UNIT_UID}", "pe:LAST_12_MONTHS"],
        output_type="EVENT",
        page_size=5,
        skip_meta=True,
    )
    _print_grid(events)

    print(f"\n--- enrollment analytics: program={PROGRAM_UID} ---")
    enrollments = await service.query_enrollments(
        profile,
        program=PROGRAM_UID,
        dimensions=[f"ou:{ORG_UNIT_UID}", "pe:LAST_12_MONTHS"],
        page_size=5,
        skip_meta=True,
    )
    _print_grid(enrollments)


def _print_grid(grid: object) -> None:
    """Pretty-print a `Grid` envelope — header names + first few rows."""
    headers = [h.name for h in grid.headers or []]  # type: ignore[attr-defined]
    rows = grid.rows or []  # type: ignore[attr-defined]
    print(f"  headers ({len(headers)}): {headers[:6]}...")
    print(f"  rows: {len(rows)}")
    for row in rows[:3]:
        print(f"    {row[:6]}...")


if __name__ == "__main__":
    run_example(main)
