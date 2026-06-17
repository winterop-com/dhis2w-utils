# MCP router (design)

`dhis2w-mcp-router` fronts one or more upstream MCP servers behind **two meta-tools** so an agent gets
**lazy, searchable tool discovery** instead of a huge up-front tool payload. It is the portable,
MCP-native equivalent of the Claude Agent SDK's **ToolSearch** — but it works with *any* MCP client
(local models via LM Studio / Ollama / llama.cpp, or cloud agents), not just Claude's SDK.

See [MCP surfaces](mcp-surfaces.md) for how it relates to the full server and the bridge. This page is
the router's internals.

## Why it exists

A big MCP server dumps every tool schema into context up front (≈49k tokens for the full dhis2-mcp
surface), which overflows small local models and costs cloud models on every turn. The two existing
answers each give up something:

- the **full server** keeps typed tools but pays the whole payload;
- the **bridge** collapses everything behind one tool, but then the model must *discover* a CLI (run
  `--help`, trial commands) — discovery overhead, and no typed schemas.

The router is the middle ground: a **tiny payload (2 tools)** + **typed discovery** (search returns real
schemas) + a **single dispatch chokepoint** for a guard. You keep the bridge's security property and the
full server's typed grounding at the same time.

## The two tools

- **`search_tools(query, limit)`** — ranks upstream tools by the query and returns the matches with
  their **namespaced names** (`server__tool`) and input schemas. The agent calls this first.
- **`call_tool(name, arguments)`** — dispatches one tool, by its namespaced name, to the upstream that
  owns it, and returns the result.

A typical agent turn: `search_tools("data element count") → call_tool("dhis2__metadata_count", {resource: "dataElements"})`.

## Domain-neutral core

The core (`core.py`) depends only on FastMCP — **zero `dhis2w-*` imports**. It knows nothing about DHIS2;
it fronts whatever MCP servers the config names. That is deliberate: the router is infrastructure, not a
DHIS2 feature, so it can graduate to PyPI or extract to a standalone `mcp-router` repo without a rewrite.
It lives in this workspace for now (same posture as `dhis2w-bench` / `dhis2w-codegen`) and is **not in
the pypi-publish matrix**.

Three small pydantic-backed pieces:

- **`UpstreamServer`** — a stdio MCP server to front (`name`, `command`, `args`, `env`, `readonly`).
  `client_config()` builds a FastMCP client config and **merges the parent environment** (a stdio child
  otherwise loses `PATH` and dies).
- **`ToolEntry`** — one upstream tool, namespaced, carrying its description + input schema + the upstream
  `readOnlyHint` annotation. `summary()` is the agent-facing shape; `is_read()` classifies it.
- **`Registry`** — holds the entries and the open upstream clients; does the search and dispatch.

## Connection lifecycle

The registry connects to every upstream **once**, on the first `search_tools`/`call_tool` call
(`ensure_built`), via an `AsyncExitStack` that keeps each FastMCP `Client` open for the process lifetime.
Subsequent dispatches reuse the open connection — no per-call subprocess spawn. Importing the server
module never requires a config (the registry is built lazily), so `--help` and tests work offline.

```
search_tools / call_tool
        │  (first call)
        ▼
   ensure_built ──► open Client(upstream) ×N  (AsyncExitStack, reused)
        │           └─ list_tools ──► namespace as server__tool ──► ToolEntry
        ▼
   search()  ── keyword rank over name+description (policy-filtered)
   call()    ── look up entry ──► its open client.call_tool(bare, args)
```

## Search ranking

Keyword for now: tokenize the query, score each tool by how many terms appear in its `name +
description`, return the top `limit`, ties broken by name for determinism. An empty query browses all
(alphabetical). This is crude — e.g. "data element count" can rank `analytics_query` above
`metadata_count` because "data" hits the analytics description — but the right tool is reliably in the
top results, and program-stage-style exact matches rank first. **Embeddings are the planned upgrade**
(rank by semantic similarity instead of substring hits).

## Read-only guard

`call_tool` is a single chokepoint, so the policy lives there. Read-only mode is enabled by
`MCP_ROUTER_READONLY=1` (global) or by marking a single upstream `"readonly": true` in the config. Under
it:

- **`search_tools` hides** write tools (the agent never sees them), and
- **`call_tool` refuses** a write with a `PermissionError`.

Classification is `readOnlyHint`-first, verb-fallback, **fail-closed**: if a tool carries an MCP
`readOnlyHint` annotation it is honored; otherwise the tool's trailing verb is checked against a
read-verb set (`get`/`list`/`count`/`find`/…), and anything unrecognized is treated as a write. Per-upstream
`readonly` is what makes federation safe: front a shared `play` host read-only and a `local` host
read-write in the **same** config, and the router enforces the split per server.

As always, this is a structural convenience guard — the authoritative control is the DHIS2 authorities
of the upstream profile's credentials.

## Configuration

Upstreams come from a JSON file (env `MCP_ROUTER_CONFIG`, default `mcp-router.json`):

```json
{
  "servers": [
    {"name": "dhis2", "command": "uv", "args": ["run", "--directory", "/repo", "dhis2w-mcp"],
     "env": {"DHIS2_PROFILE": "play42"}, "readonly": true}
  ]
}
```

Run it as a stdio MCP server: `uv run dhis2w-mcp-router`.

## Federation

Because the core is domain-neutral, one router instance can list several upstreams and present them as a
single searchable surface, namespaced by server (`dhis2__…`, `tracker__…`). This is the Scope-B design:
the same router that fronts dhis2-mcp could front any MCP servers — which is why the core deliberately
avoids DHIS2 coupling.

## Limitations and roadmap

- **Ranking** is keyword, not semantic — embeddings are the obvious upgrade.
- **A benchmark lane** comparing local models over the router vs the string-bridge vs the full server is
  the measurement that quantifies the win (a small experiment already shows it works — see Validation).
- **Per-tool allow/deny lists** beyond read-only could layer on the same `call_tool` chokepoint.

## Validation

Validated live against dhis2-mcp: **311 tools registered**, `search("create program stage")` ranks
`dhis2__metadata_program_stage_create` first, and `call("dhis2__metadata_count", {resource:
"dataElements"})` returns `total=1037`. End to end, `gemma-4-26b-a4b-qat` — loaded at just **16k
context** — drove that full 311-tool surface through the read-only router (`search_tools` → `call_tool`
→ answered `1037` on play42). That is the thesis proven: a small local model gets the lazy discovery a
cloud agent gets from ToolSearch, at a context budget it can actually afford, safely.
