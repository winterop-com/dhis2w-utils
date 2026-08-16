"""Retry transient HTTP failures — `RetryPolicy` wired into the direct-client path.

Real-world shape: batch workflows that hit a live DHIS2 instance sometimes
see transient 5xxs (503 during an analytics refresh) or connection resets
(TCP keepalive drops on long idle periods). `RetryPolicy` wraps the httpx
transport with exponential-backoff retries so a single blip doesn't fail
the whole job.

Default policy: 3 attempts, base_delay=0.5s with jitter, retries on
429/502/503/504 + connection-level errors. Non-idempotent methods
(POST/PATCH) are skipped unless you opt in — double-writes can create
DHIS2-side duplicates.

`RetryPolicy` is a field on `Dhis2Client`, not on `Profile` — the direct
client is where it plugs in. For profile-based callers, construct
`Dhis2Client` directly for the retry case OR let the service layer handle
it (future work: thread `retry_policy` through `open_client`).

Usage:
    uv run python examples/client/retry_policy.py
"""

from __future__ import annotations

import asyncio
import os

from _runner import run_example
from dhis2w_client import BasicAuth, Dhis2Client, PatAuth, RetryPolicy


async def main() -> None:
    """Walk three retry patterns: default, aggressive, POST-safe opt-in."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080")

    # 1. Default policy — 3 attempts, sensible defaults for ad-hoc scripts.
    print("--- 1. Default RetryPolicy: 3 attempts, 0.5s base, jitter=0.1 ---")
    default_policy = RetryPolicy()
    print(f"  {default_policy.model_dump()}")

    # 2. Aggressive: 5 attempts, faster retry cycle, retry on an extra status set.
    print("\n--- 2. Aggressive policy for a batch job against a flaky server ---")
    batch_policy = RetryPolicy(
        max_attempts=5,
        base_delay=0.2,
        backoff_factor=2.0,
        max_delay=5.0,
        jitter=0.15,
        retry_statuses=frozenset({408, 425, 429, 500, 502, 503, 504}),
    )

    token = os.environ.get("DHIS2_PAT")
    auth = PatAuth(token=token) if token else BasicAuth(username="admin", password="district")

    async with Dhis2Client(base_url, auth=auth, retry_policy=batch_policy) as client:
        # Fire a small batch concurrently. Transient failures are retried
        # transparently; the gather sees only successful responses.
        data_elements = await client.resources.data_elements.list(page_size=3, fields="id,name")
        tasks = [client.resources.data_elements.get(de.id, fields="id,name") for de in data_elements]
        fetched = await asyncio.gather(*tasks)
        for de in fetched:
            print(f"  got: {de.id}  {de.name}")

    # 3. Opt-in retry for non-idempotent endpoints. Only safe for jobs that
    # kick off a background DHIS2 task and return a task-ref — the side
    # effect is "start one analytics refresh", and two starts are a no-op
    # because DHIS2 de-dupes by job type.
    print("\n--- 3. retry_non_idempotent=True for analytics-refresh-style kick-offs ---")
    analytics_policy = RetryPolicy(
        max_attempts=3,
        base_delay=0.5,
        retry_non_idempotent=True,
    )
    async with Dhis2Client(base_url, auth=auth, retry_policy=analytics_policy) as client:
        # The call itself is safe to demo since it just lists; the policy is
        # the point.
        me = await client.system.me()
        print(f"  connected with retry_non_idempotent=True; user={me.username}")

    print("\n--- done ---")


if __name__ == "__main__":
    run_example(main)
