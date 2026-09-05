"""Block on a DHIS2 background task from Python — `client.tasks.await_completion`.

`--watch` is the CLI equivalent; this is the library-level helper. Takes a
`(job_type, task_uid)` ref (or `"JOB_TYPE/uid"` string) from any
`WebMessageResponse.task_ref()` and polls until `completed=True` arrives
on the notification feed.

Demo pattern: kick off an analytics resource-table refresh + block on it.
The refresh is idempotent server-side (DHIS2 de-dupes concurrent triggers
by job type), so this example is safe to re-run.

Usage:
    uv run python examples/client/task_await.py
"""

from __future__ import annotations

from _runner import run_example

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.v42.tasks import TaskTimeoutError
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Kick off an analytics refresh + block until done via `client.tasks.await_completion`."""
    async with open_client(profile_from_env()) as client:
        # 1. Kick off the job. DHIS2 returns a WebMessage whose `task_ref()` is
        # the `(job_type, uid)` tuple the awaiter takes.
        envelope = await client.maintenance.run_analytics_tables(last_years=1)
        ref = envelope.task_ref()
        if ref is None:
            print("no task-ref in response — nothing to watch")
            return
        job_type, task_uid = ref
        print(f"kicked off {job_type}/{task_uid}")

        # 2. Block on it. `poll_interval` controls request cadence; `timeout`
        # caps total wait. Pass `timeout=None` for analytics jobs that can
        # take hours on large datasets.
        try:
            completion = await client.tasks.await_completion(
                ref,
                timeout=300.0,
                poll_interval=1.0,
            )
        except TaskTimeoutError as exc:
            print(f"timed out: {exc}")
            return

        # 3. Inspect the result.
        print(f"\ncompleted — {len(completion.notifications)} notifications")
        print(f"  final level: {completion.level}")
        print(f"  final message: {completion.message}")
        # Peek at the last few progress updates.
        for notification in completion.notifications[-5:]:
            level = (notification.level or "INFO").upper()
            marker = "[x]" if notification.completed else "[ ]"
            print(f"  {level:<5} {marker} {notification.message or '-'}")


if __name__ == "__main__":
    run_example(main)
