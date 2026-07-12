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

`call_tool` is a single chokepoint, so a policy guard sits there — the same security property as the
bridge, with typed discovery on top.

## Read-only mode

Set `MCP_ROUTER_READONLY=1` (global) or mark a single upstream `"readonly": true` in the config to run
read-only: write tools are **hidden from `search_tools`** and **refused by `call_tool`** (a
`PermissionError`). Tools are classified by their `readOnlyHint` annotation when present, else by a
read-verb heuristic on the tool name (fail-closed). This is how a local model safely drives the surface
on a shared host — front `play` read-only and `local` read-write in the same config.

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

## Ranking

`search_tools` ranking is pluggable. The default `KeywordRanker` scores by query-term hits (no deps).
Add an `embeddings` block (`url` + `model`, an OpenAI-compatible `/v1/embeddings` endpoint — e.g. a
local embedder in LM Studio / Ollama) to rank by semantic similarity instead, which fixes keyword
mis-ranks (e.g. "data element count" → `metadata_count` first). It is not a silver bullet on terse
queries with a small local embedder; a larger embedder or a hybrid is the further upgrade.

## Status

Published to PyPI from 1.2.0, in lockstep with the rest of the `dhis2w-*` workspace. The core
(`core.py`) is domain-neutral (FastMCP + httpx only, no `dhis2w-*` imports), so the same code could
also extract to a standalone `mcp-router` repo without a rewrite. Whether the router should become the
*default* MCP surface for all clients (not just small local models) is still gated on the `bench-router`
numbers — see the roadmap.
