# Python client

`dhis2w-client` is the async Python library for talking to DHIS2 from code. It ships pydantic-typed responses, pluggable auth (Basic, PAT, OAuth2 + OIDC), and per-version typed accessors for DHIS2 v41 / v42 / v43 on top of an `httpx` wire layer with retries and connection pooling.

## When to reach for it

- Building an ETL / sync / migration script that touches DHIS2.
- Embedding DHIS2 calls inside another Python service or app.
- Driving a complex workflow that doesn't fit a single CLI command.
- Writing tests that need typed access to wire responses.

For one-shot operations from a terminal, the [CLI](../cli/index.md) is friendlier. For agent-driven workflows, the [MCP server](../mcp/index.md) is the right surface.

## Install

```bash
uv add dhis2w-client
```

For workspace integration (auto-discovered profiles via `.dhis2/profiles.toml`, plugin runtime, browser helpers) pair it with `dhis2w-core`:

```bash
uv add dhis2w-client dhis2w-core
```

## Your first call

```python
import asyncio
from dhis2w_client import BasicAuth, Dhis2Client


async def main() -> None:
    """Print the authenticated user + DHIS2 version."""
    async with Dhis2Client(
        "http://localhost:8080",
        auth=BasicAuth("admin", "district"),
    ) as client:
        me = await client.system.me()
        info = await client.system.info()
        print(f"hello {me.username} — connected to DHIS2 {info.version}")


asyncio.run(main())
```

When you have `dhis2w-core` installed and a profile configured, swap the explicit `Dhis2Client(...)` for the one-line `open_client(profile_from_env())`:

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    me = await client.system.me()
```

That's the pattern every example under [`examples/client/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/client) uses.

## Where next

- [Tutorial](tutorial.md) — step-by-step from "first call" through retries, streaming, and bulk imports.
- [API reference overview](../api/index.md) — every accessor + helper module on `Dhis2Client`.
- [Architecture](../architecture/client.md) — connect, version dispatch, accessor dispatch, retries.
- [Examples index](../examples.md) — runnable scripts grouped by topic.
