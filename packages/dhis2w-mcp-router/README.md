# dhis2w-mcp-router

A **domain-neutral MCP router**: front many upstream MCP servers behind two meta-tools so an agent gets
**lazy, searchable tool discovery** instead of a huge up-front tool payload.

It is the portable, MCP-native equivalent of the Claude Agent SDK's ToolSearch — but it works with *any*
MCP client (local models via LM Studio / Ollama / llama.cpp, or cloud agents), not just Claude's SDK.

## Why

A big MCP server (e.g. ~337 dhis2-mcp tools) dumps ~49k tokens of tool schemas into context up front —
which overflows small local models and costs cloud models on every call. The single-tool `dhis2_cli`
bridge avoids that by collapsing everything behind one tool, but then the agent must *discover* a CLI
(run `--help`, trial commands) — discovery overhead. The router is the middle ground:

| | tool payload | discovery | typed schemas | guardable chokepoint |
| --- | --- | --- | --- | --- |
| full MCP server | huge (all schemas) | none | yes | per-tool |
| single-tool bridge | tiny (1 tool) | high (learn a CLI) | no | yes (1 tool) |
| **router (this)** | **tiny (2 meta-tools)** | **low (search)** | **yes (search returns schemas)** | **yes (1 dispatch)** |

## The two tools

- `search_tools(query, limit)` — matching tools with their **namespaced** names (`server__tool`) and input schemas.
- `call_tool(name, arguments)` — dispatch one tool to its upstream and return the result.

`call_tool` is a single chokepoint, so a policy guard (read-only, host-protection) can sit there — the
same security property as the bridge, with typed discovery on top.

## Config

Point it at any MCP servers via a JSON config (env `MCP_ROUTER_CONFIG`, default `mcp-router.json`):

```json
{
  "servers": [
    {"name": "dhis2", "command": "uv", "args": ["run", "--directory", "/repo", "dhis2w-mcp"],
     "env": {"DHIS2_PROFILE": "play42"}}
  ]
}
```

Run it as a stdio MCP server: `uv run dhis2w-mcp-router`.

## Status

Experimental — not yet published. The core (`core.py`) is domain-neutral (FastMCP only, no `dhis2w-*`
imports), so it can graduate to PyPI or extract to a standalone repo without a rewrite.
