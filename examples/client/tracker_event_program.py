"""Event-only program workflow — standalone events, no enrollment.

WITHOUT_REGISTRATION programs collect one-shot data without a tracked
entity: community surveys, case-investigation forms, supervision visits,
outbreak line-listings.

The same `client.tracker.add_event` method handles both kinds — omit
`enrollment` and `tracked_entity` for event programs. The POST body
becomes a pure `{events: [...]}` bundle with no enrollment / TE refs.

The Sierra Leone play42 seed doesn't ship an event program by default,
so this example looks one up dynamically (via `programType:eq:WITHOUT_REGISTRATION`).
If none are configured, it prints a skip message instead of erroring.

Usage:
    uv run python examples/client/tracker_event_program.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Log one event against the first WITHOUT_REGISTRATION program we find."""
    async with open_client(profile_from_env()) as client:
        # Find any event-only program via the typed accessor.
        programs = await client.resources.programs.list(
            fields="id,name,organisationUnits[id],programStages[id,name]",
            filters=["programType:eq:WITHOUT_REGISTRATION"],
            page_size=1,
        )
        if not programs:
            print("No WITHOUT_REGISTRATION programs on this instance — skip.")
            return
        program = programs[0]
        if not program.programStages:
            print(f"Event program {program.id} has no stage — skip.")
            return
        stage = program.programStages[0]
        stage_id = stage["id"] if isinstance(stage, dict) else stage.id
        stage_name = stage["name"] if isinstance(stage, dict) else stage.name

        # Pick an OU the program is assigned to (if any), else fall back to root.
        if program.organisationUnits:
            first = program.organisationUnits[0]
            org_unit = first["id"] if isinstance(first, dict) else first.id
        else:
            roots = await client.resources.organisation_units.list(
                fields="id",
                filters=["level:eq:1"],
                page_size=1,
            )
            org_unit = roots[0].id

        # Log the event. Note: no enrollment, no tracked_entity — standalone.
        result = await client.tracker.add_event(
            program=program.id,
            program_stage=stage_id,
            org_unit=org_unit,
            occurred_at="2024-09-15",
        )
        print(f"Logged event {result.event} on {program.name} ({program.id}) stage {stage_name}")


if __name__ == "__main__":
    run_example(main)
