"""Reverse-proxy GET via `client.routes.run(code, path)`.

DHIS2 routes proxy `/api/routes/{id}/run/<path>` through to an upstream
target URL declared on the Route metadata object. Users typically know
the Route by `code` (a short slug), not by its UID — `client.routes.run`
resolves the code once, caches the UID, and returns the raw
`httpx.Response` so callers can do their own status-based handling
(a 502 from the proxy means "DHIS2 reached, downstream didn't"; 200
means the upstream replied; 404 means the cached UID is stale and the
Route was probably renamed or deleted).

The example creates a throwaway Route pointing at `https://example.com/`,
exercises the helper twice (to demonstrate the code -> UID cache), then
deletes the Route.

Usage:
    uv run python examples/client/routes_run.py
"""

from __future__ import annotations

import os

from _runner import run_example
from dhis2w_client import BasicAuth, Dhis2Client


async def main() -> None:
    """Create a Route, run() it twice via code, then clean up."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080")
    auth = BasicAuth(
        username=os.environ.get("DHIS2_USERNAME", "admin"),
        password=os.environ.get("DHIS2_PASSWORD", "district"),
    )
    code = "example-com-probe"
    async with Dhis2Client(base_url, auth=auth) as client:
        existing = await client.get_raw(
            "/api/routes",
            params={"filter": f"code:eq:{code}", "fields": "id", "pageSize": "1"},
        )
        if existing.get("routes"):
            uid = existing["routes"][0]["id"]
        else:
            envelope = await client.post_raw(
                "/api/routes",
                body={
                    "name": f"example-com-probe-{os.getpid()}",
                    "code": code,
                    "url": "https://example.com/",
                    "auth": {"type": "http-basic", "username": "anon", "password": "anon"},
                },
            )
            uid = (envelope.get("response") or {}).get("uid")
            if not isinstance(uid, str):
                raise RuntimeError(f"unexpected create response: {envelope}")
        try:
            first = await client.routes.run(code)
            print(f"  run #1: HTTP {first.status_code}  content-type={first.headers.get('content-type', '?')}")
            second = await client.routes.run(code)
            print(f"  run #2 (cached uid): HTTP {second.status_code}")
        finally:
            await client.delete_raw(f"/api/routes/{uid}")


if __name__ == "__main__":
    run_example(main)
