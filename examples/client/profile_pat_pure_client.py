r"""Pure dhis2w-client example: build a Profile and connect via PAT, no dhis2w-core.

This example demonstrates that PAT and Basic auth library-users can run
against DHIS2 with **only `dhis2w-client` installed** — no `dhis2w-core`,
no Typer / FastMCP / SQLAlchemy / Alembic. Profile construction and
`open_client` for PAT/Basic live in `dhis2w-client` since v0.12.0.

The top-level import below detects the major from `/api/system/info`.
Import from `dhis2w_client.v41` / `.v42` / `.v43` instead to pin one.

Standalone install (outside this repo):

    uv add dhis2w-client

Usage:
    DHIS2_URL=http://localhost:8080 DHIS2_PAT=d2pat_xxx \
        uv run python examples/client/profile_pat_pure_client.py

OAuth2 callers need the token store in `dhis2w-core` — calling
`open_client(oauth2_profile)` from this module raises NotImplementedError
with an install hint.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dhis2w_client import Profile, open_client


async def main() -> None:
    """Connect to DHIS2 with a hand-built Profile (PAT) and print whoami."""
    base_url = os.environ.get("DHIS2_URL")
    pat = os.environ.get("DHIS2_PAT")
    if not base_url or not pat:
        print("error: set DHIS2_URL and DHIS2_PAT", file=sys.stderr)
        sys.exit(1)
    profile = Profile(base_url=base_url, auth="pat", token=pat)
    async with open_client(profile) as client:
        me = await client.system.me()
        info = await client.system.info()
        print(f"Connected to DHIS2 {info.version} at {client.base_url}")
        print(f"  authenticated as: {me.username} ({me.displayName or '-'})")


if __name__ == "__main__":
    asyncio.run(main())
