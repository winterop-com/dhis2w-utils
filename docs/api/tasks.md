# Tasks module

`client.tasks` — block on DHIS2 background jobs (analytics refresh, metadata import, predictor runs, etc.). DHIS2's task endpoints (`/api/system/tasks/{jobType}` and `/api/system/taskSummaries/{jobType}`) report job progress as a stream of `Notification` entries; this module polls them, de-dupes, and resolves a typed `TaskCompletion` when `completed=True` lands on the feed.

## When to reach for it

- After kicking off any async DHIS2 endpoint (`POST /api/resourceTables/analytics`, `POST /api/predictors/run`, `POST /api/dataAnalysis/validationRules`, an `/api/metadata` import with `async=true`, …).
- When you want a Rich progress display in the terminal — call `iter_notifications` instead of `await_completion` and render each entry as it arrives.
- In a test that needs to wait for a real DHIS2 side-effect to land before asserting.

## Worked example — kick off + block + branch on completion

```python
from dhis2w_client.v42.tasks import TaskTimeoutError
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # 1. Kick off an analytics-table build. DHIS2 returns a WebMessage
    #    envelope; `.task_ref()` extracts the `(job_type, uid)` tuple
    #    await_completion takes.
    envelope = await client.maintenance.run_analytics_tables(last_years=1)
    ref = envelope.task_ref()
    if ref is None:
        print("no task-ref in response — nothing to watch")
        return
    job_type, task_uid = ref
    print(f"kicked off {job_type}/{task_uid}")

    # 2. Block until DHIS2 marks the job complete.
    try:
        completion = await client.tasks.await_completion(
            ref,
            timeout=300.0,
            poll_interval=2.0,
        )
    except TaskTimeoutError as exc:
        # The partial notification list is reachable via the iterator path,
        # not this exception — the exception only carries the timeout message.
        print(f"timed out: {exc}")
        return

    last = completion.final
    print(f"done in {len(completion.notifications)} notifications")
    print(f"  last: level={last.level} message={last.message!r}")
```

## Two failure shapes to handle

- **`TaskTimeoutError`** — the polling loop hit `timeout` before DHIS2 marked the job complete. Pass `timeout=None` for jobs that can legitimately take hours (full analytics rebuilds on large datasets).
- **`completion.final.level == "ERROR"`** — the job finished but DHIS2 marked it failed. The `notifications` list shows the trail; the last entry typically carries the actionable message.

```python
if completion.final.level == "ERROR":
    raise RuntimeError(f"task {job_type}/{task_uid} failed: {completion.final.message}")
```

## Streaming notifications (Rich progress / SSE bridges)

If you want to render each notification as it arrives instead of waiting for the final one, use `iter_notifications`:

```python
async for notification in client.tasks.iter_notifications(ref, timeout=600):
    print(f"  [{notification.level}] {notification.message}")
    if notification.completed:
        break
```

## One poll per tick (external schedulers)

`await_completion` and `iter_notifications` own the loop. A caller that already has a clock, such as a workflow engine polling once per tick or a UI refreshing on a timer, wants one read and a return. `poll_once` is that primitive, and the two blocking helpers are built on it:

```python
poll = await client.tasks.poll_once(ref)
for notification in poll.new:
    print(f"  [{notification.level}] {notification.message}")
if not poll.completed:
    later = await client.tasks.poll_once(ref, cursor=poll.cursor)
```

Each call GETs `/api/system/tasks/{job_type}/{uid}` once and returns a `TaskPoll`: `new` holds the notifications not covered by the cursor, oldest first and ending at DHIS2's terminal row when it has arrived, `completed` says whether that row has arrived, and `cursor` is what to pass next time so already-seen rows stay out. `relative_notifier_endpoint` is the path the poll read. The cursor is a frozenset of notification identifiers, so it survives being stored between ticks.

`parse_task_ref(...)` converts either a `(job_type, uid)` tuple or a `"JOB_TYPE/uid"` string into the canonical tuple form — handy when wiring the awaiter to call sites that get the ref from different shapes.

## Related examples

- [`examples/client/task_await.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/task_await.py) — end-to-end analytics-refresh kick-off + block.
- [`examples/client/analytics_tables_poll_once.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/analytics_tables_poll_once.py) — the same job followed with `poll_once` and a carried cursor.

::: dhis2w_client.v42.tasks
