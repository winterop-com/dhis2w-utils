# `dhis2w-mcp` MCP server

`dhis2w-mcp` exposes the same plugin-registered capabilities as the CLI, but through a FastMCP server that an AI agent can drive over stdio. The CLI and the MCP server share every service function — what differs is how they format I/O.

This is the full ~304-typed-tool server, aimed at capable hosted models. For small on-box local models there is a separate single-tool server, `dhis2w-mcp-bridge` — see [Bridge design: one tool, not many](mcp-bridge.md) for the reasoning and when to use which.

## Entry point

```toml
# packages/dhis2w-mcp/pyproject.toml
[project.scripts]
dhis2w-mcp = "dhis2w_mcp.server:main"
```

After `uv sync --all-packages`, a `dhis2w-mcp` console script is available. An agent launches it with `uv run dhis2w-mcp` (or configures an MCP stdio entry).

## The server

```python
# packages/dhis2w-mcp/src/dhis2w_mcp/server.py
def build_server() -> FastMCP:
    server = FastMCP(name="dhis2")
    for plugin in discover_plugins(resolve_startup_version()):
        plugin.register_mcp(server)
    _eager_rebuild_tool_return_types(server)
    return server


def main() -> None:
    build_server().run()
```

`resolve_startup_version()` reads the active profile's `version` field (or the `DHIS2_VERSION` env override) once at boot — that pins which `v{41,42,43}` plugin tree gets mounted for the lifetime of the process. To target a different DHIS2 major, restart with `DHIS2_VERSION=v43 dhis2w-mcp`. See [MCP intro: Active plugin tree](../mcp/index.md#active-plugin-tree) for the operational details.

`_eager_rebuild_tool_return_types` walks every pydantic class reachable from a tool return type and calls `model_rebuild()` so forward references resolve at server boot, not on the first tool call — keeps cold-start tool invocations from blocking on serializer construction.

`run()` defaults to stdio transport, which is what MCP clients (Claude Code, Cursor, etc.) expect.

## Registering tools

Each plugin's `mcp.py` decorates functions with `@mcp.tool()`:

```python
# dhis2w_core/plugins/system/mcp.py
def register(mcp: Any) -> None:
    @mcp.tool()
    async def whoami() -> Me:
        """Return the authenticated DHIS2 user for the current environment profile."""
        return await service.whoami(profile_from_env())

    @mcp.tool()
    async def system_info() -> SystemInfo:
        """Return /api/system/info for the current environment profile."""
        return await service.system_info(profile_from_env())
```

The tool name, description, and parameter schema are derived from the Python function signature + docstring. FastMCP also derives the return-type JSON schema from the annotated pydantic model, so agents see structured output.

## How an agent uses it

An MCP configuration entry (e.g. in Claude Code's `.mcp.json`) points at the installed binary:

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "uv",
      "args": ["run", "dhis2w-mcp"],
      "env": {
        "DHIS2_URL": "http://localhost:8080",
        "DHIS2_PAT": "d2p_..."
      }
    }
  }
}
```

The `env` block gives the MCP server a profile (via `profile_from_env()`). Without those vars the tools raise `NoProfileError` at first invocation, with a message telling the agent to ask the user to set them.

After the agent connects, it can:

```
> list_tools
  - whoami
  - system_info

> call_tool whoami
  { "username": "admin", "authorities": [...] }

> call_tool system_info
  { "version": "2.42.4", "revision": "eaf4b70", ... }
```

## Testing

FastMCP 3.x ships a `Client` that accepts a `FastMCP` instance directly for in-process testing. No subprocess, no stdio framing — the test opens a client against the server object and calls tools just like an external agent would.

### Surface test (no DHIS2)

```python
# packages/dhis2w-mcp/tests/test_mcp_surface.py
async def test_server_registers_expected_tools() -> None:
    server = build_server()
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
    assert "whoami" in names
    assert "system_info" in names
```

Runs in <100ms.

### Integration test (hits localhost)

```python
# packages/dhis2w-mcp/tests/test_mcp_integration.py
async def test_whoami_tool_returns_admin_user(
    local_url,
    local_pat,
    monkeypatch,
) -> None:
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` to populate")
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)

    server = build_server()
    async with Client(server) as client:
        result = await client.call_tool("whoami", {})

    payload = _extract_payload(result)
    assert payload["username"] == "admin"
```

`_extract_payload` tolerates variance in FastMCP's result shape across versions — it checks `structured_content`, then the pydantic `.data.model_dump()`, then falls back to parsing the text `content` block.

## Parity with the CLI

The system plugin's `service.whoami()` is called by both:

```
d2w system whoami           → Typer command in dhis2w_core/plugins/system/cli.py
                               → service.whoami(profile_from_env())
                               → prints formatted line

MCP tool "whoami"              → @mcp.tool() in dhis2w_core/plugins/system/mcp.py
                               → service.whoami(profile_from_env())
                               → returns pydantic Me to the agent
```

If we change `service.whoami()`, both surfaces change. If we add a new plugin, both surfaces pick it up (assuming the plugin implements both `register_cli` and `register_mcp`).

## Why not OpenAPI / REST?

OpenAPI + FastAPI would work, but an agent would need a generic HTTP-call tool to use it. MCP's stdio protocol gives agents first-class tool discovery and typed parameters for free — no HTTP boilerplate, no authentication dance, no versioning concerns (the MCP protocol handles capability negotiation).

A FastAPI surface is still on the table for a **web UI** (humans interacting with the tooling), which is a different audience. That'll land as a new workspace member when the need surfaces.
