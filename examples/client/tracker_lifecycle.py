"""Tracker lifecycle — low-level `/api/tracker` write path with typed models.

Shows the raw bundle-build pattern: one atomic POST creates a tracked
entity, its enrollment in a program, and the first event against that
enrollment, all stitched together via `TrackerBundle` /
`TrackerTrackedEntity` / `TrackerEnrollment` / `TrackerEvent` models.

For the everyday workflow, reach for `client.tracker.register(...)` +
`client.tracker.add_event(...)` (see
`examples/client/tracker_clinic_intake.py`). This example stays on the
raw typed-model path — useful when you need full control over a
multi-object bundle (events across stages, pre-set UIDs, opinionated
data-value shapes, etc.) or are building your own higher-level helper.

Targets the seeded Child Programme by default. Override via env to hit
another instance.

Usage:
    uv run python examples/client/tracker_lifecycle.py

Env (all optional — fall back to seeded Sierra Leone UIDs):
    PROGRAM_UID   tracker program UID (default IpHINAT79UW, Child Programme)
    ORG_UNIT_UID  OU UID in admin's capture scope (default ImspTQPwCqd)
    TET_UID       TrackedEntityType UID (default nEenWmSyUEp, Person (Play))
"""

from __future__ import annotations

import os
from datetime import datetime

from _runner import run_example
from dhis2w_client import WebMessageResponse

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.tracker import (
    EnrollmentStatus,
    EventStatus,
    TrackerBundle,
    TrackerEnrollment,
    TrackerEvent,
    TrackerTrackedEntity,
)
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Create a tracked-entity bundle + read it back against the seeded Child Programme."""
    program_uid = os.environ.get("PROGRAM_UID", "IpHINAT79UW")
    ou_uid = os.environ.get("ORG_UNIT_UID", "ImspTQPwCqd")
    tet_uid = os.environ.get("TET_UID", "nEenWmSyUEp")

    now = datetime.now()
    bundle = TrackerBundle(
        trackedEntities=[
            TrackerTrackedEntity(
                trackedEntityType=tet_uid,
                orgUnit=ou_uid,
                enrollments=[
                    TrackerEnrollment(
                        program=program_uid,
                        orgUnit=ou_uid,
                        status=EnrollmentStatus.ACTIVE,
                        enrolledAt=now,
                        occurredAt=now,
                        events=[
                            TrackerEvent(
                                program=program_uid,
                                orgUnit=ou_uid,
                                status=EventStatus.COMPLETED,
                                occurredAt=now,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    async with open_client(profile_from_env()) as client:
        print("POST /api/tracker (importStrategy=CREATE_AND_UPDATE)")
        raw = await client.post_raw(
            "/api/tracker",
            bundle.model_dump(by_alias=True, exclude_none=True, mode="json"),
            params={"importStrategy": "CREATE_AND_UPDATE", "atomicMode": "ALL"},
        )
        response = WebMessageResponse.model_validate(raw)
        print(f"  status={response.status}  message={response.message}")
        counts = response.import_count()
        if counts is not None:
            print(f"  imported={counts.imported} updated={counts.updated} ignored={counts.ignored}")
        for conflict in response.conflicts()[:5]:
            print(f"  conflict: {conflict.property} = {conflict.value} [{conflict.errorCode}]")

        # Read the full tracked-entity population for the program.
        raw_read = await client.get_raw(
            "/api/tracker/trackedEntities",
            params={
                "program": program_uid,
                "pageSize": 3,
                "fields": "trackedEntity,trackedEntityType,orgUnit,enrollments",
            },
        )
        entities = raw_read.get("instances", [])
        print(f"\ntracked entities in program {program_uid}: {len(entities)}")
        for entity in entities[:3]:
            print(f"  uid={entity.get('trackedEntity')}  type={entity.get('trackedEntityType')}")


if __name__ == "__main__":
    run_example(main)
