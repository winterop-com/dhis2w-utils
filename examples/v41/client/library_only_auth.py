"""Library-only auth — for PyPI consumers of `dhis2w-client` without `dhis2w-core`.

Most examples here use `open_client(profile_from_env())` from `dhis2w-core`,
which reads the workspace's `profiles.toml` and builds the right
`AuthProvider` automatically. That's the canonical path for scripts *inside*
this workspace.

If you're embedding `dhis2w-client` in a project that doesn't want the
profile / TOML layer, construct auth providers directly — the client
itself takes a base URL and any `AuthProvider` implementation. This
example shows Basic + PAT; see `oidc_login.py` for OAuth2.

Usage:
    DHIS2_PAT=... uv run python examples/v41/client/library_only_auth.py
    # or
    DHIS2_USERNAME=admin DHIS2_PASSWORD=district uv run python examples/v41/client/library_only_auth.py
"""

from __future__ import annotations

import os

from _runner import run_example
from dhis2w_client import AuthProvider, BasicAuth, Dhis2, Dhis2Client, PatAuth


def build_auth() -> AuthProvider:
    """Pick PAT when available, fall back to Basic. Pure `dhis2w-client` — no profile layer."""
    pat = os.environ.get("DHIS2_PAT")
    if pat:
        return PatAuth(token=pat)
    return BasicAuth(
        username=os.environ.get("DHIS2_USERNAME", "admin"),
        password=os.environ.get("DHIS2_PASSWORD", "district"),
    )


async def main() -> None:
    """Connect with hand-rolled auth and print the authenticated identity."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080")
    # `version=Dhis2.V41` pins the generated module; pass None for auto-detect via /api/system/info.
    async with Dhis2Client(base_url, auth=build_auth(), version=Dhis2.V41) as client:
        me = await client.system.me()
        info = await client.system.info()
        print(f"Connected to DHIS2 {info.version} at {base_url}")
        print(f"  authenticated as: {me.username} ({me.displayName or '-'})")
        print(f"  auth kind: {type(client._auth).__name__}")  # noqa: SLF001 — illustrative only


if __name__ == "__main__":
    run_example(main)
