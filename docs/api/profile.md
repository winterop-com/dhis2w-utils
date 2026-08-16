# Profile + lightweight open_client

The `Profile` Pydantic model + `open_client(profile)` for PAT, Basic, and session-cookie auth live in `dhis2w-client` — no `dhis2w-core` install needed for library users embedding the client in their own Python tooling. OAuth2 still requires `dhis2w-core` because OAuth2 token refresh needs the concurrent-writer-safe token store; calling `dhis2w_client.open_client(oauth2_profile)` raises `NotImplementedError` pointing at `dhis2w_core.open_client`.

## When to reach for this surface

- **Embedding `dhis2w-client` in a third-party app** (FastAPI service, script, notebook) with PAT, Basic, or session-cookie auth — you don't want the full CLI/MCP runtime weight (Typer, FastMCP, SQLAlchemy, bcrypt, questionary).
- **OAuth2 auth?** Use `dhis2w_core.open_client(profile)` instead — same `Profile` model, full token-store-backed refresh.
- **Multi-profile TOML resolution?** That lives in `dhis2w-core`. Use `dhis2w_core.profile_from_env()` for the full precedence chain (TOML + env), or this module's `profile_from_env_raw()` for the env-only fallback that returns `None` instead of consulting TOML.

## Worked example — pure `dhis2w-client` use

```python
import asyncio

from dhis2w_client import NoProfileError, Profile, open_client, profile_from_env_raw


async def main() -> None:
    """Build a Profile (in-memory or from env) and open a connected client."""
    profile = profile_from_env_raw()
    if profile is None:
        # No DHIS2_URL+credentials env — construct one explicitly:
        profile = Profile(
            base_url="https://play.im.dhis2.org/dev-2-43",
            auth="pat",
            token="d2pat_yourtoken",
        )
    try:
        async with open_client(profile) as client:
            me = await client.system.me()
            info = await client.system.info()
            print(f"Connected to DHIS2 {info.version} as {me.username}")
    except NoProfileError as exc:
        print(f"misconfigured: {exc}")


asyncio.run(main())
```

See `examples/client/profile_pat_pure_client.py` for the runnable, version-pinned form.

## Profile model

::: dhis2w_client.profile.Profile

## Exceptions

::: dhis2w_client.profile.NoProfileError

::: dhis2w_client.profile.UnknownProfileError

::: dhis2w_client.profile.InvalidProfileNameError

## Constructors + helpers

::: dhis2w_client.profile.profile_from_env_raw

::: dhis2w_client.profile.validate_profile_name

## Open a client from a profile

`build_auth_provider(profile)` returns a `PatAuth`, `BasicAuth`, or `SessionCookieAuth` `AuthProvider`. `open_client(profile)` is the async context manager that wires that auth provider into a connected `Dhis2Client`. Both live at the top of `dhis2w_client` (re-exported from `dhis2w_client.v42.client_context`) and on each per-version surface (`dhis2w_client.v41`, `dhis2w_client.v42`, `dhis2w_client.v43`).

::: dhis2w_client.v42.client_context.build_auth_provider

::: dhis2w_client.v42.client_context.open_client
