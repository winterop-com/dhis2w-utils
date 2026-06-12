"""Minimal dhis2w-client example: connect via the default profile, call /api/me.

The `dhis2w-client` package itself is profile-agnostic (it takes a base URL
and an `AuthProvider`). For scripts, the canonical way to get a connected
client is `open_client(profile_from_env())` from `dhis2w-core` — the same
helper the CLI + MCP use internally. It walks the profile precedence chain
(`DHIS2_PROFILE` env -> `./.dhis2/profiles.toml` -> `~/.config/dhis2/profiles.toml`)
and builds the right `AuthProvider` based on `auth=` in the profile.

Usage:
    d2w profile add local --url http://localhost:8080 --auth basic \
        --username admin --password district --default
    uv run python examples/v41/client/whoami.py

See `library_only_auth.py` + `oidc_login.py` for the library-only path
(hand-rolled `BasicAuth` / `PatAuth` / `OAuth2Auth`) when embedding
`dhis2w-client` in a project that doesn't pull in `dhis2w-core`.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Connect to DHIS2 and print the authenticated user's identity."""
    async with open_client(profile_from_env()) as client:
        me = await client.system.me()
        info = await client.system.info()
        print(f"Connected to DHIS2 {info.version} ({info.systemName or 'unnamed'}) at {client.base_url}")
        print(f"  authenticated as: {me.username} ({me.displayName or '-'})")


if __name__ == "__main__":
    run_example(main)
