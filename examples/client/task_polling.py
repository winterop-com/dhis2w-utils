"""Background-task polling — watch a `/api/resourceTables/analytics` job to done.

Every async DHIS2 op returns a `JobConfigurationWebMessageResponse` with
`response.jobType` and `response.id`. `WebMessageResponse.task_ref()` pulls
the `(job_type, task_uid)` tuple; `client.tasks.iter_notifications(ref)`
streams `/api/system/tasks/{type}/{uid}` notifications and terminates when
the job reports `completed=true`. For the "just block until done" path,
reach for `client.tasks.await_completion(ref)` instead.

Usage:
    uv run python examples/client/task_polling.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import WebMessageResponse
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Kick off an analytics refresh and stream its notifications."""
    async with open_client(profile_from_env()) as client:
        print("kicking off POST /api/resourceTables/analytics (lastYears=1)")
        raw = await client.post_raw("/api/resourceTables/analytics", params={"lastYears": 1})
        envelope = WebMessageResponse.model_validate(raw)
        ref = envelope.task_ref()
        if ref is None:
            print("  response had no jobType/id — can't watch")
            return
        job_type, task_uid = ref
        print(f"  kicked off {job_type}/{task_uid} — streaming notifications...\n")

        # Typed streaming: yields `Notification` objects (level, message,
        # completed) and stops automatically when `completed=True` arrives.
        async for notification in client.tasks.iter_notifications(ref, poll_interval=1.0):
            level = (notification.level or "INFO").upper()
            marker = "[x]" if notification.completed else "[ ]"
            print(f"  {level:<5} {marker} {notification.message or '-'}")


if __name__ == "__main__":
    run_example(main)
