"""v43-only — override the Program UI labels shown in Capture / Tracker Capture.

DHIS2 2.43 lets each Program override the default "Enrollments" / "Events" /
"Program stages" terminology with domain-native vocabulary — e.g. "Visits",
"Encounters", "Care stages". Three optional fields on `Program`:
`enrollmentsLabel`, `eventsLabel`, `programStagesLabel` (2-255 chars each).

This example reads the first WITH_REGISTRATION program in the active
profile, sets a sample label triplet via the dedicated
`ProgramsAccessor.set_labels` helper, then re-reads to confirm the values
landed. Pairs with `program_set_change_log.py` (the unrelated audit
toggle) and `program_set_enrollment_category_combo.py` (the unrelated
alt-CC reference).

Usage:
    uv run python examples/client/v43/program_set_labels.py

Requires: a profile pointing at a DHIS2 v43 instance with at least one
WITH_REGISTRATION program; the seeded Sierra Leone fixture qualifies
(IpHINAT79UW — Child Programme).
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.client_context import open_client


async def main() -> None:
    """Override the three v43 UI label fields on the first tracker program."""
    async with open_client(profile_from_env()) as client:
        if client.version_key != "v43":
            print(f"skipping: this example targets v43; profile is on {client.version_key}")
            return

        programs = await client.programs.list_all(program_type="WITH_REGISTRATION", page_size=1)
        if not programs:
            print("skipping: no WITH_REGISTRATION programs found")
            return
        target = programs[0]
        if not target.id:
            print("skipping: first program has no id")
            return

        print(f"before: {target.id} name={target.name!r}")
        print(
            f"  enrollmentsLabel={target.enrollmentsLabel!r}\n"
            f"  eventsLabel={target.eventsLabel!r}\n"
            f"  programStagesLabel={target.programStagesLabel!r}"
        )

        updated = await client.programs.set_labels(
            target.id,
            enrollments_label="Visits",
            events_label="Encounters",
            program_stages_label="Care Stages",
        )

        print(f"after:  {updated.id} name={updated.name!r}")
        print(
            f"  enrollmentsLabel={updated.enrollmentsLabel!r}\n"
            f"  eventsLabel={updated.eventsLabel!r}\n"
            f"  programStagesLabel={updated.programStagesLabel!r}"
        )


if __name__ == "__main__":
    run_example(main)
