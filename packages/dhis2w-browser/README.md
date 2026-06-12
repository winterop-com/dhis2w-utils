# dhis2w-browser

Playwright-based helpers for DHIS2 UI automation. Separate from `dhis2w-client` so API-only callers never pull in Chromium.

## Install

```bash
uv add 'dhis2w-cli[browser]'            # pulls dhis2w-browser alongside the main CLI
playwright install chromium           # one-off; pulls the actual browser driver
```

Library-only consumers (no CLI) can install `dhis2w-browser` on its own.

## Surface

The CLI lives on the main `d2w` entry point as a plugin; there's no separate `dhis2w-browser` binary. Workflows mount under `d2w browser <subcommand>`:

```bash
d2w browser pat --url http://localhost:8080 --username admin --password district
d2w browser dashboard screenshot --output-dir /tmp/out --only <uid>
d2w browser viz screenshot --output-dir /tmp/out --only <uid>
d2w browser map screenshot --output-dir /tmp/out --only <uid>
```

Library callers import from `dhis2w_browser` directly:

| Entry point | Purpose |
| --- | --- |
| `dhis2w_browser.logged_in_page(url, username, password)` | Async context manager yielding a `(BrowserContext, Page)` tuple logged into DHIS2 via the React login form. |
| `dhis2w_browser.session_from_cookie(url, jsessionid)` | Fast-path variant — inject a pre-minted `JSESSIONID` instead of driving the login form. |
| `dhis2w_browser.create_pat(url, username, password, options=...)` | Mint a Personal Access Token V2 (`POST /api/apiToken`) through an authenticated browser session. Returns the `d2p_...` token string. DHIS2 only returns the token value once — store it immediately. |
| `dhis2w_browser.drive_oauth2_login(profile_name, *, username, password)` | Run `d2w profile login <name> --no-browser` end-to-end — spawns the CLI, reads the authorize URL from its stderr, and drives Chromium through the DHIS2 React login + Spring AS consent screen + loopback redirect. Returns an `OAuth2LoginResult` model. |
| `dhis2w_browser.drive_login_form(auth_url, *, username, password)` | Lower-level companion to `drive_oauth2_login` — navigates Chromium to an already-built authorize URL, fills the login form + consent screen, waits for the loopback redirect. For wiring Playwright into an in-process `OAuth2Auth.redirect_capturer`. |
| `dhis2w_browser.capture_dashboard(...)` / `capture_visualization(...)` / `capture_map(...)` | Render a DHIS2 dashboard / chart / map as a PNG via the respective web app. Banner + background-trim helpers available for report-friendly output. |

## Headless vs headful

Headless by default. Two ways to flip to visible:

1. **Env var:** `DHIS2_HEADFUL=1` (or `true`/`yes`/`on`) — applies to every Playwright entry point in this package.
2. **Explicit kwarg:** `logged_in_page(..., headless=False)` — overrides env.

The `d2w browser pat` CLI command defaults to **headful** (`--headful`) so first-time users can watch the login; pass `--headless` to flip.

Why: automation wants headless for speed; humans debugging a flow want to see it. One env var covers every caller (CLI, library, tests) uniformly. See `docs/decisions.md` 2026-04-17.

## Example

```python
import asyncio
from dhis2w_browser import PatOptions, create_pat

async def main() -> None:
    token = await create_pat(
        "http://localhost:8080",
        "admin",
        "district",
        options=PatOptions(
            name="automation-bot",
            expires_in_days=90,
            allowed_methods=["GET", "POST"],
        ),
    )
    print(token)  # d2p_...

asyncio.run(main())
```

## Architecture

See `docs/architecture/browser.md` for the longer write-up: why PAT creation has to go through a browser (DHIS2 gates `/api/apiToken` behind a session cookie), how `logged_in_page` drives the React login form, and what's on the roadmap.
