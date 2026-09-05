"""Build the analytics tables and follow the job one poll at a time.

`client.maintenance.run_analytics_tables(...)` POSTs `/api/resourceTables/analytics`
and returns the job-kickoff envelope. `client.tasks.poll_once(ref, cursor=...)`
then reads the job's notification feed once and returns what is new, which
fits a caller that polls on its own clock (an engine tick, a UI refresh) rather
than blocking in `await_completion`.

Each poll hands back a cursor. Passing it to the next poll keeps rows from
being reported twice. `completed` turns true when DHIS2 posts the terminal
notification.

The build is idempotent on the server, which de-duplicates concurrent triggers
by job type, so this example is safe to run again.

Usage:
    uv run python examples/client/analytics_tables_poll_once.py
"""

from __future__ import annotations

import asyncio
import time

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

POLL_INTERVAL_SECONDS = 2.0
DEADLINE_SECONDS = 600.0


async def main() -> None:
    """Kick off a one-year analytics build and print its notifications as they arrive."""
    async with open_client(profile_from_env()) as client:
        envelope = await client.maintenance.run_analytics_tables(last_years=1)
        ref = envelope.task_ref()
        if ref is None:
            print(f"no task in the response: {envelope.message}")
            return
        print(f"kicked off {ref[0]}/{ref[1]}  feed at {envelope.notifier_endpoint()}")

        cursor: frozenset[str] = frozenset()
        started = time.monotonic()
        while True:
            poll = await client.tasks.poll_once(ref, cursor=cursor)
            for notification in poll.new:
                level = (notification.level or "INFO").upper()
                marker = "[x]" if notification.completed else "[ ]"
                print(f"  {level:<5} {marker} {notification.message or '-'}")
            if poll.completed:
                print("done")
                return
            if time.monotonic() - started > DEADLINE_SECONDS:
                print(f"still running after {DEADLINE_SECONDS:.0f}s; poll again later with the cursor")
                return
            cursor = poll.cursor
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_example(main)
