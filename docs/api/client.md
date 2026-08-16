# Client + lifecycle

The async `Dhis2Client` is the entry point for every DHIS2 call. It owns the httpx connection pool, performs the version handshake on connect, binds the matching generated accessors, and exposes raw HTTP escape hatches for endpoints that don't have a typed wrapper yet.

## When to reach for it

- Standalone PyPI use (no profile system) — instantiate `Dhis2Client(base_url, auth=...)` directly.
- Inside `dhis2w-core` integrations — the canonical path is `dhis2w_core.client_context.open_client(profile)`, which returns the same `Dhis2Client` but wraps profile resolution + cleanup.
- Subclassing or wrapping for a custom workflow (the class is a `BaseModel`-free regular async class, not frozen).

## Worked example — standalone library use

```python
import asyncio
from dhis2w_client import BasicAuth, Dhis2Client, RetryPolicy

import httpx


async def main() -> None:
    """Connect to DHIS2 via plain Basic auth + a retry policy + bigger pool."""
    async with Dhis2Client(
        base_url="https://play.im.dhis2.org/dev-2-43",
        auth=BasicAuth("admin", "district"),
        retry_policy=RetryPolicy(),  # 429/5xx + connection errors
        http_limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    ) as client:
        print(f"version_key  = {client.version_key}")  # 'v42' / 'v43' / 'v41'
        print(f"raw_version  = {client.raw_version}")  # '2.43.0' etc.
        me = await client.system.me()
        print(f"as {me.username} ({me.displayName})")


asyncio.run(main())
```

## Worked example — workspace-integrated use (`dhis2w-core`)

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async with open_client(profile_from_env()) as client:
    me = await client.system.me()
```

The two paths return the same `Dhis2Client`; `open_client` just resolves the profile + chooses the matching `AuthProvider` for you. Every example under `examples/client/` uses this form because the workspace has profiles configured.

## Raw HTTP escape hatches

When an endpoint doesn't have a typed wrapper yet (or you want the literal wire shape for debugging), drop down to:

- `await client.get_raw(path, params=...)` -> `dict[str, Any]`
- `await client.post_raw(path, body=..., params=...)` -> `dict[str, Any]`
- `await client.put_raw(path, body=...)` -> `dict[str, Any]`
- `await client.patch_raw(path, body=...)` -> `dict[str, Any]`
- `await client.delete_raw(path)` -> `dict[str, Any]`
- `await client.get(path, model=MyBaseModel)` -> typed via your own pydantic model
- `await client.get_response(path, params=..., extra_headers=...)` -> `httpx.Response` (no raise on 4xx/5xx)

Keep the use of raw helpers narrow — every typed accessor `client.X.Y()` is preferable for production code (the typed return is what makes the rest of the codebase work). The architecture page [Client library](../architecture/client.md) covers the lifecycle states (`unconnected -> connecting -> connected -> closed`) and how `connect()` binds the version-specific accessors.

`get_response` is the only helper that bypasses the 4xx/5xx raise in `_request`. Use it when a non-2xx is a fact you want to report rather than an exception — health-checkers, SSO / proxy-page detection via `Content-Type`, or reverse-proxied routes under `/api/routes/<code>/run/...` where a 502 means "DHIS2 reached, downstream didn't".

## Constructor knobs for non-default lifecycles

The defaults (`verify=True`, full version probe on `connect()`, raise on 4xx/5xx) suit typed-accessor flows. Three opt-in kwargs unlock other shapes:

- `verify: bool | str = True` — TLS certificate verification. Threaded through the main httpx pool plus the canonical-URL and DHIS2-shape probes. Pass `False` for self-signed staging boxes or a path to a custom CA bundle.
- `skip_version_probe: bool = False` — when `True`, `connect()` opens the HTTP pool without the canonical-URL probe or the `/api/system/info` round-trip and returns. `version_key`, `raw_version`, and `resources` raise on access (the generated tree never binds), so only the raw-path methods (`get_raw`, `post_raw`, `get_response`, etc.) are usable. Suits health-checkers that want to *report* on those endpoints, very-low-privilege PATs that can't read `/api/system/info`, and tests injecting a mock transport.

See `examples/client/health_check.py` for the full health-checker pattern.

::: dhis2w_client.v42.client
    options:
      members:
        - Dhis2Client
