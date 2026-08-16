"""v43-only — toggle the per-Program change-log audit flag.

DHIS2 2.43 added `Program.enableChangeLog` — a behavioural switch that
gates whether DHIS2 records enrollment + event change-logs surfaced via:

- `/api/tracker/enrollments/{uid}/changeLogs`
- `/api/tracker/events/{event}/changeLogs`
- `/api/tracker/trackerEvents/{event}/changeLogs`
- `/api/tracker/singleEvents/{event}/changeLogs`
- `/api/tracker/trackedEntities/{te}/changeLogs`

Default off. This is a runtime audit-tracking toggle — orthogonal to the
v43 UI label overrides demoed in `program_set_labels.py` and the alt-CC
reference in `program_set_enrollment_category_combo.py`. The accessor
exposes it through the dedicated `set_change_log_enabled(uid, enabled)`
helper.

Usage:
    uv run python examples/client/v43/program_set_change_log.py

Requires: a profile pointing at a DHIS2 v43 instance with at least one
WITH_REGISTRATION program; the seeded Sierra Leone fixture qualifies
(IpHINAT79UW — Child Programme).
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.client_context import open_client


async def main() -> None:
    """Flip `enableChangeLog` on for the first tracker program, then back off."""
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

        print(f"before: {target.id} name={target.name!r} enableChangeLog={target.enableChangeLog}")

        enabled = await client.programs.set_change_log_enabled(target.id, True)
        print(f"after enable:  enableChangeLog={enabled.enableChangeLog}")

        # Flip back so this example is idempotent across re-runs.
        disabled = await client.programs.set_change_log_enabled(target.id, False)
        print(f"after disable: enableChangeLog={disabled.enableChangeLog}")


if __name__ == "__main__":
    run_example(main)
