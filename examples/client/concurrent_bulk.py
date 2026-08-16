"""Concurrent fan-out patterns — `asyncio.gather` against `Dhis2Client`.

Walks the three levels of concurrency control you end up needing on real
batch workflows:

1. **Naive gather** — fine for small batches (~tens of calls).
2. **Bounded semaphore** — for hundreds / thousands of items; caps
   simultaneous in-flight calls to match DHIS2's capacity.
3. **Tuned connection pool + semaphore** — when the default 100-connection
   httpx pool is either too big (small DHIS2 instance) or too small
   (high-concurrency writes).

The client's `httpx.AsyncClient` pool is shared across every concurrent
call on a single `Dhis2Client` instance, so there's no per-call handshake
cost — the bottleneck is DHIS2-side capacity + the configured pool limits.

Usage:
    uv run python examples/client/concurrent_bulk.py
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable

import httpx
from _runner import run_example
from dhis2w_client import Dhis2Client, RetryPolicy
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def _bounded_gather[T](
    items: Iterable[T],
    fn: Callable[[T], Awaitable[object]],
    *,
    max_concurrency: int,
) -> list[object]:
    """`asyncio.gather` with a Semaphore — caps simultaneous in-flight calls."""
    sem = asyncio.Semaphore(max_concurrency)

    async def _run(item: T) -> object:
        async with sem:
            return await fn(item)

    return await asyncio.gather(*(_run(item) for item in items))


async def _sequential_baseline(client: Dhis2Client, uids: list[str]) -> float:
    """Fetch each UID one at a time; return elapsed seconds — the baseline we're beating."""
    start = time.perf_counter()
    for uid in uids:
        await client.resources.data_elements.get(uid, fields="id,name")
    return time.perf_counter() - start


async def _naive_gather(client: Dhis2Client, uids: list[str]) -> float:
    """Unbounded `asyncio.gather` — fine for small batches; dangerous at scale."""
    start = time.perf_counter()
    await asyncio.gather(*(client.resources.data_elements.get(uid, fields="id,name") for uid in uids))
    return time.perf_counter() - start


async def _bounded(client: Dhis2Client, uids: list[str], *, limit: int) -> float:
    """Bounded concurrency — safe default for hundreds / thousands of items."""
    start = time.perf_counter()
    await _bounded_gather(
        uids,
        lambda uid: client.resources.data_elements.get(uid, fields="id,name"),
        max_concurrency=limit,
    )
    return time.perf_counter() - start


async def main() -> None:
    """Three gather patterns + one pool-tuned run. Times each against the seeded stack."""
    profile = profile_from_env()

    # Discover a batch of UIDs to fan out over. The seeded e2e fixture has ~13
    # data elements; we repeat each up to 10 times to give the pool real work.
    async with open_client(profile) as client:
        catalog = await client.resources.data_elements.list(page_size=20, fields="id")
    uids = [de.id for de in catalog if de.id]
    uids = (uids * 10)[:60]  # ~60 fetches — big enough to see concurrency pay off
    print(f"--- target workload: {len(uids)} data-element fetches ({len(set(uids))} unique) ---\n")

    # 1. Sequential baseline.
    async with open_client(profile) as client:
        seq_elapsed = await _sequential_baseline(client, uids)
    print(f"1. sequential:            {seq_elapsed * 1000:7.0f} ms")

    # 2. Naive unbounded gather — default pool (100 max / 20 keepalive) does the throttling.
    async with open_client(profile) as client:
        naive_elapsed = await _naive_gather(client, uids)
    print(f"2. gather (unbounded):    {naive_elapsed * 1000:7.0f} ms  ({seq_elapsed / naive_elapsed:.1f}x speedup)")

    # 3. Bounded semaphore — explicit cap so gather won't overrun DHIS2 capacity or hit pool limits.
    async with open_client(profile) as client:
        bounded_elapsed = await _bounded(client, uids, limit=10)
    print(f"3. gather (sem=10):       {bounded_elapsed * 1000:7.0f} ms  ({seq_elapsed / bounded_elapsed:.1f}x speedup)")

    # 4. Tuned pool + retries — what you'd use for a production batch job. Clamp the
    # pool below the semaphore limit so pool waits are impossible; retries cover
    # the transient 5xx / connection-reset edges.
    tight_pool = httpx.Limits(max_connections=15, max_keepalive_connections=5)
    retry = RetryPolicy(max_attempts=3, base_delay=0.1, jitter=0.1)
    async with open_client(profile, http_limits=tight_pool, retry_policy=retry) as client:
        tuned_elapsed = await _bounded(client, uids, limit=10)
    print(f"4. tuned pool + retries:  {tuned_elapsed * 1000:7.0f} ms  ({seq_elapsed / tuned_elapsed:.1f}x speedup)")

    print("\n--- takeaway ---")
    print("  * small batches (<~50): naive gather is fine.")
    print("  * larger batches: cap via Semaphore to protect DHIS2 + stay inside pool limits.")
    print("  * production: cap + tuned pool + RetryPolicy.")
    print("  * see docs/architecture/client.md for sizing guidance.")


if __name__ == "__main__":
    run_example(main)
