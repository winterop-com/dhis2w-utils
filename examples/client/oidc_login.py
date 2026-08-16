"""OAuth 2.1 authorization-code flow with PKCE — library-level `OAuth2Auth`.

Stands up `OAuth2Auth` directly (no profile, no plugin). `dhis2w-core`
injects a FastAPI-backed redirect receiver via `redirect_capturer`; the
first run opens a browser, captures the redirect, and writes tokens to
a local SQLite store. Subsequent runs reuse the cached tokens (and
silently refresh near expiry). Delete `./tokens.sqlite` to force a
fresh flow.

Three ways to complete the login, picked in priority order:

1. `DHIS2_USERNAME` + `DHIS2_PASSWORD` set → Playwright drives the
   DHIS2 React login form + Spring AS consent screen headlessly.
   Requires the `[browser]` extra (`uv add 'dhis2w-cli[browser]'`).
2. `DHIS2_OAUTH_NO_BROWSER=1` → the authorize URL prints to stderr for
   copy-paste into any browser; the receiver still completes the flow.
3. Otherwise → `webbrowser.open(auth_url)` launches the system browser.

Usage (against `make dhis2-run`):
    set -a; source infra/home/credentials/.env.auth; set +a
    uv run python examples/client/oidc_login.py

Env:
    DHIS2_URL                     default http://localhost:8080
    DHIS2_OAUTH_CLIENT_ID         from .env.auth
    DHIS2_OAUTH_CLIENT_SECRET     from .env.auth
    DHIS2_OAUTH_REDIRECT_URI      default http://localhost:8765
    DHIS2_OAUTH_SCOPES            default ALL
    DHIS2_USERNAME / DHIS2_PASSWORD   enables the Playwright path
    DHIS2_OAUTH_NO_BROWSER=1      print auth URL instead of opening a browser

Usage:
    uv run python examples/client/oidc_login.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _runner import run_example
from dhis2w_client import Dhis2Client

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.v42.auth.oauth2 import OAuth2Auth, capture_code
from dhis2w_core.token_store import SqliteTokenStore


async def main() -> None:
    """Run the OAuth2 flow (on first run) and call /api/me with the resulting access token."""
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
    username = os.environ.get("DHIS2_USERNAME")
    password = os.environ.get("DHIS2_PASSWORD")
    open_browser_env = os.environ.get("DHIS2_OAUTH_NO_BROWSER", "0") == "0"
    token_store = SqliteTokenStore(Path("./tokens.sqlite"))

    # Playwright-driven path: concurrent receiver + IdP form automation.
    # Only available when DHIS2_USERNAME + DHIS2_PASSWORD are set AND the
    # `[browser]` extra is installed. Any import error falls through to
    # the non-Playwright path below.
    async def playwright_capturer(auth_url: str, expected_state: str) -> str:
        """Run the FastAPI receiver + Chromium login form concurrently; return the captured code."""
        from dhis2w_browser import drive_login_form

        code_task = asyncio.create_task(
            capture_code(redirect_uri, expected_state, auth_url=auth_url, open_browser=False),
        )
        # uvicorn binds to the port before this wait completes — the Playwright
        # cold-start adds 1–2s on top, so the receiver is always ready before
        # the form submit triggers the localhost redirect.
        await asyncio.sleep(0.5)
        assert username is not None  # guarded by the outer branch
        assert password is not None
        await drive_login_form(auth_url, username=username, password=password, headless=True)
        return await code_task

    async def manual_capturer(auth_url: str, expected_state: str) -> str:
        """Default capturer — webbrowser.open (or print to stderr when no-browser)."""
        return await capture_code(
            redirect_uri,
            expected_state,
            auth_url=auth_url,
            open_browser=open_browser_env,
        )

    capturer = playwright_capturer if (username and password) else manual_capturer

    auth = OAuth2Auth(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        redirect_uri=redirect_uri,
        token_store=token_store,
        store_key="examples:04_oauth2",
        redirect_capturer=capturer,
    )
    try:
        # No `version=`: the client detects the major from /api/system/info, so this example
        # runs against any of v41 / v42 / v43. An explicit pin refuses a different-major server.
        async with Dhis2Client(base_url, auth=auth) as client:
            me = await client.system.me()
            print(f"OAuth2 login ok — authenticated as {me.username} ({me.displayName or '-'})")
    finally:
        await token_store.close()


if __name__ == "__main__":
    run_example(main)
