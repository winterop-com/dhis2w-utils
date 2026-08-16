"""Tracker clinic-intake workflow — end-to-end via `client.tracker`.

Walks through the canonical tracker authoring flow for a WITH_REGISTRATION
program:

  1. Register a new patient + enroll in one call (`register`).
  2. Add the first stage event (`add_event`).
  3. Query outstanding stages ('what's due').
  4. Log the follow-up event.
  5. Verify the enrollment is complete.

Against the Sierra Leone play42 seed, Child Programme (IpHINAT79UW) has
two non-repeatable stages: Birth (A03MvHHogjR) and Baby Postnatal
(ZzYYXq4fJie). A fresh registration lands with zero events, so the
`outstanding` query returns both stages until we log them.

Usage:
    uv run python examples/client/tracker_clinic_intake.py

Env: same as 01_whoami.py (DHIS2_PROFILE or DHIS2_URL + DHIS2_PAT).
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PROGRAM = "IpHINAT79UW"  # Child Programme
TRACKED_ENTITY_TYPE = "nEenWmSyUEp"  # Person
STAGE_BIRTH = "A03MvHHogjR"
STAGE_POSTNATAL = "ZzYYXq4fJie"
ATTR_FIRST_NAME = "w75KJ2mc4zz"
ATTR_LAST_NAME = "zDhUuAYrxNC"


async def main() -> None:
    """Register a patient, log two events, confirm outstanding hits zero."""
    async with open_client(profile_from_env()) as client:
        # 1. Pick a facility-level OU via the typed accessor.
        facilities = await client.resources.organisation_units.list(
            fields="id,name",
            filters=["level:eq:4"],
            page_size=1,
        )
        if not facilities:
            print("No level-4 org units on this instance — skip.")
            return
        org_unit = facilities[0]
        print(f"Registering at {org_unit.name} ({org_unit.id})")

        # 2. Register + enroll in one atomic POST /api/tracker call.
        registered = await client.tracker.register(
            program=PROGRAM,
            org_unit=org_unit.id,
            tracked_entity_type=TRACKED_ENTITY_TYPE,
            attributes={
                ATTR_FIRST_NAME: "Aminata",
                ATTR_LAST_NAME: "Kamara",
            },
            enrolled_at="2024-06-01",
        )
        print(f"Registered TE={registered.tracked_entity} enrollment={registered.enrollment}")

        # 3. Log the birth event.
        birth = await client.tracker.add_event(
            program=PROGRAM,
            program_stage=STAGE_BIRTH,
            org_unit=org_unit.id,
            enrollment=registered.enrollment,
            tracked_entity=registered.tracked_entity,
            occurred_at="2024-06-02",
        )
        print(f"Logged Birth event={birth.event}")

        # 4. Outstanding = "what's due" — expect Baby Postnatal to appear.
        outstanding = await client.tracker.outstanding(PROGRAM, org_unit=org_unit.id)
        ours = [o for o in outstanding if o.enrollment == registered.enrollment]
        if ours:
            missing = ours[0].missing_stages
            print(f"Our new enrollment still owes: {missing}")

        # 5. Log the postnatal event.
        postnatal = await client.tracker.add_event(
            program=PROGRAM,
            program_stage=STAGE_POSTNATAL,
            org_unit=org_unit.id,
            enrollment=registered.enrollment,
            tracked_entity=registered.tracked_entity,
            occurred_at="2024-08-15",
        )
        print(f"Logged Baby Postnatal event={postnatal.event}")

        # 6. Verify our enrollment is complete.
        outstanding = await client.tracker.outstanding(PROGRAM, org_unit=org_unit.id)
        ours = [o for o in outstanding if o.enrollment == registered.enrollment]
        print(f"Outstanding after follow-up: {len(ours)} (expect 0 for our enrollment)")


if __name__ == "__main__":
    run_example(main)
