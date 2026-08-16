"""Health-checker pattern — `skip_version_probe` + `get_response` for caller-side status logic.

The defaults `connect()` enforces (canonical-URL probe + `/api/system/info` for
version detection) and the 4xx/5xx raise inside `_request` are right for
typed-accessor flows but wrong for a health-checker: those are exactly the
states the checker wants to report on as check results, not raise on.

Three opt-in knobs unlock the health-checker shape:

- `skip_version_probe=True` opens the HTTP pool with zero round-trips.
- `verify=False` (or a CA bundle path) loosens TLS for self-signed staging.
- `get_response()` returns the raw `httpx.Response` without raising on 4xx/5xx.

Usage:
    uv run python examples/client/health_check.py
"""

from __future__ import annotations

import os

from _runner import run_example
from dhis2w_client import BasicAuth, Dhis2Client


async def main() -> None:
    """Probe `/api/system/info` and `/api/me` and report each as a check result."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080")
    auth = BasicAuth(
        username=os.environ.get("DHIS2_USERNAME", "admin"),
        password=os.environ.get("DHIS2_PASSWORD", "district"),
    )
    async with Dhis2Client(
        base_url,
        auth=auth,
        skip_version_probe=True,
        verify=True,
    ) as client:
        for path in ("/api/system/info", "/api/me", "/api/routes/missing/run/health"):
            response = await client.get_response(path)
            content_type = response.headers.get("content-type", "?")
            print(f"  {response.status_code:>3}  {path}  ({content_type})")


if __name__ == "__main__":
    run_example(main)
