# Plugin runtime

`dhis2w-core` is the shared runtime that both `dhis2w-cli` and `dhis2w-mcp` build on. Its central contract is the **plugin** — a tiny descriptor that every capability (system info, metadata CRUD, tracker, analytics, codegen, …) implements so the CLI and MCP surfaces never drift out of parity.

## The contract

```python
# packages/dhis2w-core/src/dhis2w_core/plugin.py
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Plugin(Protocol):
    """Dual-surface plugin descriptor registered with the CLI and/or MCP."""

    name: str           # stable id, e.g. "system"
    description: str    # one-line human-readable summary

    def register_cli(self, app: Any) -> None:
        """Mount this plugin's Typer sub-app on the root CLI."""
        ...

    def register_mcp(self, mcp: Any) -> None:
        """Register this plugin's tools on the FastMCP server."""
        ...
```

A plugin is a normal Python object — usually a frozen dataclass — with two `register_*` methods. Plugins that are CLI-only (e.g. `profile`, eventually) leave `register_mcp` as a no-op. MCP-only plugins leave `register_cli` as a no-op.

## Discovery

`discover_plugins()` returns every plugin instance available at runtime. Two sources:

1. **Built-ins** — `pkgutil.iter_modules(dhis2w_core.v42.plugins)` walks the first-party plugin folder. Each sub-module exposes a module-level `plugin = _MyPlugin()`. No registry list to maintain; adding a folder is enough.
2. **External** — `importlib.metadata.entry_points(group="dhis2.plugins")`. A separately-installed package can ship its own plugin by declaring:

    ```toml
    [project.entry-points."dhis2.plugins"]
    my-capability = "my_package.plugin:plugin"
    ```

    `dhis2w-codegen` already does this — its Typer sub-app is mounted as `d2w codegen` without any code living under `dhis2w-core`.

The order of discovery is deterministic (sorted built-ins, then entry points in install order). Duplicates by `plugin.name` are fine — last one wins; we don't currently de-dupe.

## Standard layout per plugin

Every first-party plugin lives in `packages/dhis2w-core/src/dhis2w_core/v42/plugins/<name>/`:

```
<name>/
├── __init__.py        # exports `plugin = _MyPlugin()`
├── service.py         # async pure functions — single source of truth
├── cli.py             # Typer sub-app + register(app) helper
├── mcp.py             # FastMCP tool registrations + register(mcp) helper
└── models.py          # (optional) plugin-internal pydantic view-models
```

- `service.py` holds the **real work** — async functions that take a `Profile` and return typed results.
- `cli.py` wraps `service.py` with Typer decorators + rich printing.
- `mcp.py` wraps `service.py` with `@mcp.tool()` decorators.

Both `cli.py` and `mcp.py` are thin — they format I/O and nothing else. The CLI and MCP surfaces cannot drift because they share the same underlying function.

## The `system` plugin as a reference

The smallest complete plugin lives at `dhis2w_core/plugins/system/`:

```python
# __init__.py
@dataclass(frozen=True)
class _SystemPlugin:
    name: str = "system"
    description: str = "DHIS2 system info and current-user access."

    def register_cli(self, app: Any) -> None:
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        mcp_module.register(mcp)


plugin = _SystemPlugin()
```

```python
# service.py
async def whoami(profile: Profile) -> Me:
    async with open_client(profile) as client:
        return await client.system.me()


async def system_info(profile: Profile) -> SystemInfo:
    async with open_client(profile) as client:
        return await client.system.info()
```

```python
# cli.py
@app.command("whoami")
def whoami_command() -> None:
    me = asyncio.run(service.whoami(profile_from_env()))
    typer.echo(f"{me.username} ({me.displayName or '-'})")
```

```python
# mcp.py
def register(mcp: Any) -> None:
    @mcp.tool()
    async def whoami() -> Me:
        return await service.whoami(profile_from_env())
```

That's a full capability in ~30 lines. Both `d2w system whoami` and an MCP agent's `whoami` tool call go through `service.whoami` end-to-end.

## Profile resolution

Plugins don't resolve profiles themselves. They call `profile_from_env()` at tool-call time, which walks the standard resolution chain (first match wins): an explicit `--profile <name>` arg → `DHIS2_PROFILE` env var → raw `DHIS2_URL` + (`DHIS2_PAT` | `DHIS2_USERNAME`+`DHIS2_PASSWORD`) env (PAT or Basic only — OAuth2 needs a saved profile) → project-local `.dhis2/profiles.toml` default → user-global `~/.config/dhis2/profiles.toml` default. This keeps the CLI and MCP surfaces completely symmetric — neither needs to thread "what DHIS2 should I talk to?" through arguments. See [Profiles](profiles.md) for the full chain.

## Why not inheritance?

`Plugin` is a `Protocol`, not a base class. Any object with `name`, `description`, `register_cli`, `register_mcp` satisfies it. External packages don't import a base class from `dhis2w-core`; they just produce compatible objects. Loose coupling and zero inheritance overhead.
