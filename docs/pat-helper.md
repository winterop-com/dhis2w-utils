# Playwright PAT helper

`dhis2w-browser` ships a small Playwright helper that logs into DHIS2 via the web UI and creates a Personal Access Token. Two invocation paths share the same library call: the `d2w browser pat` CLI subcommand (mounted via the `browser` plugin in `dhis2w-core`) and the `dhis2w_browser.create_pat` library function.

## Why

Basic auth works but is clumsy for automation: credentials in env vars, no scoping, no revocation story. PATs are a cleaner long-lived credential for background jobs, CI, and the MCP server.

**Default PAT creation path is `d2w profile pat create`** — it hits `POST /api/apiToken` via plain Basic admin auth (no browser). The Playwright helper here exists for the edge case where Basic API auth is disabled server-side, or for existing browser flows that already have a session in hand. For the common case, prefer `d2w profile pat create` — faster, no Chromium.

## Usage

```bash
d2w browser pat \
    --url http://localhost:8080 \
    --username admin \
    --password district
```

Output (one line, the PAT):

```
d2p_UxW7txWKqLDIbVxf6b0oiVQo2oQ6W7Uth6Ez53To7XhB36MiWd
```

The CLI defaults to `--headful` so first-time users can watch the login flow; pass `--headless` (or set `DHIS2_HEADFUL=` to an empty / falsey value) to flip.

Programmatic:

```python
from dhis2w_browser import create_pat

token = await create_pat(
    "http://localhost:8080",
    "admin",
    "district",
    headless=True,
)
# → "d2p_..."
```

## What happens under the hood

1. Chromium launches (headless by default).
2. Playwright navigates to `{base_url}/dhis-web-login/`.
3. Fills `input[name="username"]` / `input[name="password"]`, clicks `button[type="submit"]`.
4. Waits for the redirect away from `/dhis-web-login` — DHIS2 sends the browser to the dashboard app on success.
5. The authenticated `page.request` POSTs to `/api/apiToken` with `{"attributes": [], "type": "PERSONAL_ACCESS_TOKEN_V2"}`.
6. Parses the response for the token value (key prefixed `d2p_`).
7. Browser closes.

## Using the PAT

```python
from dhis2w_client import Dhis2Client, PatAuth

async with Dhis2Client("http://localhost:8080", auth=PatAuth(token="d2p_...")) as client:
    me = await client.system.me()
    # -> Me(username="admin", authorities=[...])
```

The auth header sent: `Authorization: ApiToken d2p_...`.

## Integration-test fixture

Integration tests that hit the local instance use a session-scoped `local_pat` fixture. It:

1. Returns `DHIS2_LOCAL_PAT` env var if set (fast path — reuse across sessions).
2. Otherwise calls `create_pat(...)` via Playwright (slow — ~5s) and caches the result for the test session.
3. Falls back to Basic auth if the fixture hits an error (or if you pass `--basic-only`).

See `packages/dhis2w-client/tests/conftest.py` for the implementation.

## Open questions

- **Expiry.** We currently don't set an `expire` on the token — it lives forever (or until revoked). For CI we'd set something like 1 day. Add that when we wire this into automation.
- **Naming.** DHIS2 v2.42's PAT model doesn't appear to take a user-supplied display name — the token shows up in `/api/apiToken/me` with server-side metadata. Worth revisiting if the model changes.
- **Revocation on test teardown.** Currently we leak a new PAT per manual run. A future improvement is a `DELETE /api/apiToken/{id}` sweep at end of session.
