"""Drive `d2w profile login --no-browser` end-to-end via Playwright.

This is the companion to `examples/v42/client/oidc_login.py` — that one runs
the OAuth 2.1 + PKCE flow interactively (opens your system browser, you
click through the IdP form). This one automates the same flow headlessly:
spawns the CLI with `--no-browser`, reads the authorize URL from stderr,
and a Chromium instance fills the DHIS2 login form on the user's behalf.

Useful as:

- An end-to-end OIDC regression test — all three stages (CLI subprocess,
  IdP form, loopback redirect + token exchange) run without human input.
- A template for CI harnesses that need to authenticate against DHIS2
  over OAuth2 (Remote Desktop / headless runners where the default
  browser either isn't set or points at the wrong display).

Requires the `[browser]` extra:
    uv add 'dhis2w-cli[browser]'
    playwright install chromium

Usage (against `make dhis2-run`):
    set -a; source infra/home/credentials/.env.auth; set +a
    uv run python examples/v42/client/oidc_playwright_login.py

Env:
    DHIS2_URL             default http://localhost:8080
    DHIS2_USERNAME        DHIS2 login username (default: admin)
    DHIS2_PASSWORD        DHIS2 login password (default: district)
    DHIS2_OAUTH_CLIENT_ID / DHIS2_OAUTH_CLIENT_SECRET / DHIS2_OAUTH_REDIRECT_URI / DHIS2_OAUTH_SCOPES
                          OAuth2 client registration — seeded by `make dhis2-seed` into .env.auth.
    DHIS2_HEADFUL=1       run Chromium with a visible window (debugging)

Usage:
    uv run python examples/v42/client/oidc_playwright_login.py
"""

from __future__ import annotations

import os

from _runner import run_example
from dhis2w_browser import drive_oauth2_login
from dhis2w_client import Dhis2Client
from dhis2w_core.client_context import build_auth_for_name
from dhis2w_core.v42.plugins.profile import service


async def main() -> None:
    """Register a throwaway oauth2 profile, drive the Playwright login, verify via /api/me."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080")
    client_id = os.environ.get("DHIS2_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("DHIS2_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "DHIS2_OAUTH_CLIENT_ID / DHIS2_OAUTH_CLIENT_SECRET must be set.\n"
            "Run `make dhis2-run` then `set -a; source infra/home/credentials/.env.auth; set +a` before this script.",
        )
    redirect_uri = os.environ.get("DHIS2_OAUTH_REDIRECT_URI", "http://localhost:8765")
    scope = os.environ.get("DHIS2_OAUTH_SCOPES", "ALL")
    username = os.environ.get("DHIS2_USERNAME", "admin")
    password = os.environ.get("DHIS2_PASSWORD", "district")

    # Stand up a temporary profile entry so the CLI has something to log into.
    # `add_profile` is idempotent — CREATE_AND_UPDATE semantics on repeat runs.
    profile_name = "playwright_oidc"
    from dhis2w_core.profile import Profile

    service.add_profile(
        profile_name,
        Profile(
            base_url=base_url,
            auth="oauth2",
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            redirect_uri=redirect_uri,
        ),
        scope="global",
    )

    result = await drive_oauth2_login(profile_name, username=username, password=password)
    print(f"OAuth2 login ok — {len(result.stderr.splitlines())} stderr lines, exit code {result.returncode}")
    print(f"  auth URL seen: {result.auth_url[:80]}...")

    # Prove the tokens landed and are usable on the next /api/me call.
    _, auth = build_auth_for_name(profile_name)
    async with Dhis2Client(base_url, auth=auth) as client:
        me = await client.system.me()
        print(f"  /api/me -> {me.username} ({me.displayName or '-'})")


if __name__ == "__main__":
    run_example(main)
