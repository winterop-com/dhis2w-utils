"""Client-level task awaiter for DHIS2 background jobs.

Every async DHIS2 operation (analytics refresh, metadata import, data-integrity
run, tracker async push) returns a `WebMessageResponse` carrying
`jobType` + task UID. Callers historically had two options: (a) roll
their own polling loop against `/api/system/tasks/{type}/{uid}`, or (b)
go through the plugin-layer CLI `--watch` flag. Neither works when you
want to block a library script on job completion.

`client.tasks.await_completion(task_ref)` is that helper. Polls the
task-status feed on the already-open HTTP connection (no new client per
poll, unlike the profile-based `watch_task` in `dhis2w-core`), de-dupes
notifications by their identifier, and returns a typed `TaskCompletion`
once `completed=True` lands.

Caveats:

- Poll interval defaults to 2.0s. DHIS2's notification feed updates at
  best every ~1s, so faster polling just burns request quota.
- Timeout defaults to 600.0s (10 min). Analytics refreshes on large
  instances can run longer — pass `timeout=None` to block forever, or
  `timeout=3600` etc.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_client.v43.maintenance import Notification

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client


class TaskTimeoutError(TimeoutError):
    """Raised when `await_completion` / `iter_notifications` exceed the timeout."""


class TaskCompletion(BaseModel):
    """Result of awaiting a DHIS2 background task — every notification + the terminal row."""

    model_config = ConfigDict(frozen=True)

    job_type: str
    task_uid: str
    notifications: list[Notification]
    final: Notification

    @property
    def level(self) -> str:
        """Level of the completing notification (typically INFO for success, ERROR for failure)."""
        return (self.final.level or "INFO").upper()

    @property
    def message(self) -> str:
        """Message from the completing notification — typically a short summary."""
        return self.final.message or ""


def parse_task_ref(task_ref: tuple[str, str] | str) -> tuple[str, str]:
    """Normalise `(job_type, uid)` or `"job_type/uid"` into a `(job_type, uid)` tuple.

    Convenience for callers that store task refs as a single string — matches
    what the CLI task-watch flag prints. Strings are split on the last `/`.
    """
    if isinstance(task_ref, tuple):
        return task_ref
    if "/" not in task_ref:
        raise ValueError(f"task_ref string must be 'JOB_TYPE/uid', got {task_ref!r}")
    job_type, _, uid = task_ref.rpartition("/")
    if not job_type or not uid:
        raise ValueError(f"task_ref string must be 'JOB_TYPE/uid' with both halves, got {task_ref!r}")
    return job_type, uid


class TaskPoll(BaseModel):
    """One non-blocking read of a task's notification feed — the rows new since a cursor.

    `poll_once` returns this so a caller polling on its own schedule (an engine
    tick, a UI refresh) reads the feed once and returns instead of blocking:
    `new` holds the notifications not seen under the passed cursor
    (chronological, ending at the completing row), `completed` is `True` once
    DHIS2's terminal notification has arrived, and `cursor` is what to pass to
    the next `poll_once` so only newer rows come back.
    """

    model_config = ConfigDict(frozen=True)

    job_type: str
    task_uid: str
    new: list[Notification]
    completed: bool
    cursor: frozenset[str]

    @property
    def relative_notifier_endpoint(self) -> str:
        """The `/api/system/tasks/{job_type}/{task_uid}` path this poll read."""
        return f"/api/system/tasks/{self.job_type}/{self.task_uid}"


class TaskModule:
    """Accessor bound to a `Dhis2Client` exposing background-task polling."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client — reuses its auth + HTTP pool for every poll."""
        self._client = client

    async def await_completion(
        self,
        task_ref: tuple[str, str] | str,
        *,
        timeout: float | None = 600.0,
        poll_interval: float = 2.0,
    ) -> TaskCompletion:
        """Block until the task completes; return a typed `TaskCompletion`.

        Polls `/api/system/tasks/{job_type}/{uid}` every `poll_interval`
        seconds until a notification with `completed=True` arrives. Raises
        `TaskTimeoutError` if `timeout` elapses first (pass `None` for no
        timeout). De-dupes notifications by `uid`/`id`/`time` so repeated
        polls don't surface the same entries twice.
        """
        notifications: list[Notification] = []
        async for notification in self.iter_notifications(task_ref, timeout=timeout, poll_interval=poll_interval):
            notifications.append(notification)
            if notification.completed:
                job_type, task_uid = parse_task_ref(task_ref)
                return TaskCompletion(
                    job_type=job_type,
                    task_uid=task_uid,
                    notifications=notifications,
                    final=notification,
                )
        # Unreachable: `iter_notifications` either yields a `completed=True` notification
        # (returned above) or raises `TaskTimeoutError` on its own deadline. This raise
        # only satisfies the `TaskCompletion` return type for the impossible fall-through.
        raise TaskTimeoutError(f"task {task_ref!r} did not complete within the iterator's timeout")

    async def poll_once(
        self,
        task_ref: tuple[str, str] | str,
        *,
        cursor: Iterable[str] | None = None,
    ) -> TaskPoll:
        """Read a task's notification feed once and return what's new — never blocks.

        GETs `/api/system/tasks/{job_type}/{uid}` a single time (no loop, no
        sleep) and returns a `TaskPoll`: the notifications not present in
        `cursor`, whether the task has completed, and the next cursor. Pass the
        previous poll's `cursor` back on the next call so only newer rows come
        through — this is the primitive an external scheduler polls once per
        tick instead of blocking in `await_completion` / `iter_notifications`,
        which are built on it.

        New rows come oldest-first and stop at the first `completed=True` row
        (DHIS2's terminal notification), which sets `completed`. A row without a
        stable identifier surfaces on every poll, matching the blocking path.
        """
        job_type, task_uid = parse_task_ref(task_ref)
        seen: set[str] = set(cursor or ())
        raw = await self._client.get_raw(f"/api/system/tasks/{job_type}/{task_uid}")
        data = raw.get("data")
        items: list[object] = data if isinstance(data, list) else []
        new: list[Notification] = []
        completed = False
        # DHIS2 returns newest-first; walk oldest-first so `new` reads chronologically.
        for entry in reversed(items):
            notification = Notification.model_validate(entry)
            identifier = (
                notification.uid
                or notification.id
                or (notification.time.isoformat() if notification.time is not None else "")
            )
            if identifier and identifier in seen:
                continue
            if identifier:
                seen.add(identifier)
            new.append(notification)
            if notification.completed:
                completed = True
                break
        return TaskPoll(
            job_type=job_type,
            task_uid=task_uid,
            new=new,
            completed=completed,
            cursor=frozenset(seen),
        )

    async def iter_notifications(
        self,
        task_ref: tuple[str, str] | str,
        *,
        timeout: float | None = 600.0,
        poll_interval: float = 2.0,
    ) -> AsyncIterator[Notification]:
        """Yield each notification as it arrives; stop when `completed=True` or timeout.

        Separate from `await_completion` so CLI renderers (Rich progress
        bars, server-sent-event bridges, etc.) can render each entry
        incrementally instead of waiting for the final result.
        """
        job_type, task_uid = parse_task_ref(task_ref)
        deadline = None if timeout is None else asyncio.get_running_loop().time() + timeout
        cursor: frozenset[str] = frozenset()
        while True:
            poll = await self.poll_once((job_type, task_uid), cursor=cursor)
            cursor = poll.cursor
            for notification in poll.new:
                yield notification
            if poll.completed:
                return
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                raise TaskTimeoutError(f"task {job_type}/{task_uid} did not complete within {timeout}s")
            await asyncio.sleep(poll_interval)


__all__ = ["TaskCompletion", "TaskModule", "TaskPoll", "TaskTimeoutError", "parse_task_ref"]
