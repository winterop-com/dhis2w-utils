"""TTL-bounded in-memory cache on `client.system` — cut bootstrapping round-trips.

Every `Dhis2Client` ships with a per-client cache for three high-repetition
reads:

- `client.system.info()` — the `SystemInfo` payload. **Primed on `connect()`**,
  so the first call after connect is a free in-process read.
- `client.system.default_category_combo_uid()` — every DHIS2 instance ships
  one; scripts that create data elements without specifying a categoryCombo
  need it.
- `client.system.setting(key)` — `/api/systemSettings/{key}` reads are
  cached per key.

Default TTL is 300 s. Tune with `system_cache_ttl=...` on `Dhis2Client` /
`open_client`; pass `None` to disable. Call `invalidate_cache()` when you
know the upstream changed (setting updated through another process, Admin
UI rename of the default combo, etc.).

Usage:
    uv run python examples/client/system_cache.py
"""

from __future__ import annotations

import time

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def _time(label: str, fetch) -> None:  # type: ignore[no-untyped-def]
    """Time one async call and print elapsed ms — cheap demo harness."""
    start = time.monotonic()
    result = await fetch()
    elapsed_ms = (time.monotonic() - start) * 1000
    summary = result[:40] + "..." if isinstance(result, str) and len(result) > 40 else repr(result)[:60]
    print(f"  {label:42}  {elapsed_ms:6.1f} ms   {summary}")


async def main() -> None:
    """Demo: show the cache shaving HTTP round-trips across repeated reads."""
    async with open_client(profile_from_env()) as client:
        print("--- cached paths (default TTL = 300 s) ---")

        # `info()` is primed during connect(), so the first call is a cache hit.
        await _time("info() — primed by connect", client.system.info)
        await _time("info() — second call (cache hit)", client.system.info)
        await _time(
            "info(use_cache=False) — fresh fetch",
            lambda: client.system.info(use_cache=False),
        )

        # Default categoryCombo UID — handy when creating DEs without specifying a CC.
        async def _default_cc() -> str:
            return await client.system.default_category_combo_uid()

        await _time("default_category_combo_uid() — miss", _default_cc)
        await _time("default_category_combo_uid() — hit", _default_cc)

        # Per-key system settings.
        async def _title() -> str | None:
            return await client.system.setting("applicationTitle")

        await _time("setting('applicationTitle') — miss", _title)
        await _time("setting('applicationTitle') — hit", _title)

        # Invalidate + refetch.
        print("\n--- invalidate_cache() forces a refetch ---")
        client.system.invalidate_cache()
        await _time("info() after invalidate — refetch", client.system.info)
        await _time("info() — cached again", client.system.info)


if __name__ == "__main__":
    run_example(main)
