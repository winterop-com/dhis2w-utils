# dhis2w-client

Pure async DHIS2 API client for Python. Pluggable auth (Basic / PAT / OAuth2-OIDC PKCE), pydantic-typed models from both `/api/schemas` and `/api/openapi.json` codegen, retry policy, period math, analytics helper. DHIS2 v41, v42, and v43.

Standalone — no profile system, no plugin runtime. Drop it in any async Python project that needs to talk to a DHIS2 instance.

## Install

```bash
# Inside a uv-managed project
uv add dhis2w-client
```

## Quickstart

```python
from dhis2w_client import BasicAuth, Dhis2Client

async with Dhis2Client(
    base_url="https://play.im.dhis2.org/dev-2-43",
    auth=BasicAuth(username="admin", password="district"),
) as client:
    me = await client.system.me()
    print(me.username)

    elements = await client.resources.data_elements.list(fields="id,name", page_size=10)
    for de in elements:
        print(de.id, de.name)
```

PAT and OAuth2 (with token caching + refresh) work the same way:

```python
from dhis2w_client import Dhis2Client, OAuth2Auth

auth = OAuth2Auth(
    base_url="https://dhis2.example.org",
    client_id="my-app",
    client_secret="...",
    scope="ALL",
    redirect_uri="http://localhost:8765",
    token_store=my_token_store,
    store_key="profile:prod",
)
async with Dhis2Client("https://dhis2.example.org", auth=auth) as client:
    ...
```

## What's in the box

- **Async HTTP** via httpx with a pluggable retry transport (429 / 502 / 503 / 504 with `Retry-After` honoring).
- **Typed metadata accessors** for every resource DHIS2 exposes via `/api/schemas` — generated per DHIS2 version under `dhis2w_client.generated.v{41,42,43}`.
- **Tracker** read + write helpers (`client.tracker.register / enroll / event_create / outstanding`).
- **Analytics** — `client.analytics.aggregate(dx=..., pe=..., ou=...) -> Grid` for parsed responses, `stream_to(...)` for very large pivots.
- **Period math** — `parse_period`, `next_period_id`, `previous_period_id`, `period_start_end` across all six absolute period shapes.
- **Pluggable auth** — `BasicAuth`, `PatAuth`, `OAuth2Auth`. Add your own by implementing the `AuthProvider` Protocol.
- **Bulk operations** — `patch_bulk`, `apply_sharing_bulk`, fanned out over a pool of `concurrency` workers that pull records one at a time, so memory stays flat however long the input list is.

## Documentation

Full docs at https://winterop-com.github.io/dhis2w-utils/.

The `dhis2w-client` package is one member of the [`dhis2w-utils`](https://github.com/winterop-com/dhis2w-utils) workspace. The CLI (`dhis2w-cli`), MCP server (`dhis2w-mcp`), and Playwright helpers (`dhis2w-browser`) all build on this client.
