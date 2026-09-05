"""Read tracker data back: `client.tracker.tracked_entities`, `.enrollments`, `.events`.

The read side of `register` / `enroll` / `add_event`. Each accessor GETs the
matching `/api/tracker/*` endpoint with the standard query surface (program,
organisation unit and mode, status, field selector, paging, updated-after) and
returns the page envelope. Rows live under `instances` or, on older
minors, under the resource's own name; parse one with the generated tracker
model when a typed view is wanted.

Reads the seeded Child Programme below the Sierra Leone root.

Usage:
    uv run python examples/client/tracker_reads.py
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from _runner import run_example

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.tracker import TrackerEnrollment, TrackerEvent, TrackerTrackedEntity
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PROGRAM_UID = "IpHINAT79UW"  # Child Programme
ORG_UNIT_UID = "ImspTQPwCqd"  # Sierra Leone root


def _rows(page: dict[str, Any], resource_key: str) -> list[dict[str, Any]]:
    """Return the rows of a tracker page: `instances`, or the resource's own key on older minors."""
    rows = page.get("instances") or page.get(resource_key) or []
    return [row for row in rows if isinstance(row, dict)]


async def main() -> None:
    """Page through tracked entities, active enrollments, and recent events of one program."""
    today = datetime.now(tz=UTC).date()
    since = date(today.year - 1, 1, 1)

    async with open_client(profile_from_env()) as client:
        # Tracked entities enrolled in the program anywhere below the root.
        page = await client.tracker.tracked_entities(
            program=PROGRAM_UID,
            org_unit=ORG_UNIT_UID,
            ou_mode="DESCENDANTS",
            page_size=5,
        )
        entities = _rows(page, "trackedEntities")
        print(f"--- tracked entities: {len(entities)} ---")
        for row in entities:
            entity = TrackerTrackedEntity.model_validate(row)
            print(f"  {entity.trackedEntity}  type={entity.trackedEntityType}  orgUnit={entity.orgUnit}")

        # Active enrollments, newest first via the tracker `order` param.
        page = await client.tracker.enrollments(
            program=PROGRAM_UID,
            org_unit=ORG_UNIT_UID,
            ou_mode="DESCENDANTS",
            status="ACTIVE",
            page_size=5,
            extra_params={"order": "enrolledAt:desc"},
        )
        enrollments = _rows(page, "enrollments")
        print(f"--- active enrollments: {len(enrollments)} ---")
        for row in enrollments:
            enrollment = TrackerEnrollment.model_validate(row)
            print(f"  {enrollment.enrollment}  entity={enrollment.trackedEntity}  enrolled={enrollment.enrolledAt}")

        # Events that occurred this year. `occurred_after` takes a `date`, a
        # `datetime`, or an ISO string; `status` would filter by event status
        # here, where it filters by enrollment status on the two reads above.
        page = await client.tracker.events(
            program=PROGRAM_UID,
            org_unit=ORG_UNIT_UID,
            ou_mode="DESCENDANTS",
            occurred_after=since,
            page_size=5,
        )
        events = _rows(page, "events")
        print(f"--- events since {since}: {len(events)} ---")
        for row in events:
            event = TrackerEvent.model_validate(row)
            values = len(event.dataValues or [])
            print(f"  {event.event}  stage={event.programStage}  occurred={event.occurredAt}  values={values}")


if __name__ == "__main__":
    run_example(main)
