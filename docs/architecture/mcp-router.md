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

The core depends only on FastMCP + httpx (the latter for the optional embedding ranker) — **zero `dhis2w-*` imports**. It knows nothing about DHIS2;
it fronts whatever MCP servers the config names. That is deliberate: the router is infrastructure, not a
DHIS2 feature. It ships to PyPI as `dhis2w-mcp-router` (from 1.2.0), and the same domain-neutral core
could extract to a standalone `mcp-router` repo without a rewrite.

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

Ranking is **pluggable** (`ranking.py`, the `Ranker` protocol). Two implementations:

- **`KeywordRanker`** (default, no deps, no IO) — tokenize the query, score each tool by how many terms
  appear in its `name + description`, top `limit`, ties broken by name. An empty query browses all
  (alphabetical). Crude: "data element count" ranks `analytics_query` above `metadata_count` because
  "data" hits the analytics description.
- **`EmbeddingRanker`** (optional) — ranks by cosine similarity against an OpenAI-compatible
  `/v1/embeddings` endpoint (e.g. a local embedder served by LM Studio / Ollama). It embeds every tool's
  `name + description` once at build time and the query per search. Enabled by an `embeddings` block in
  the config (`url` + `model`); absent ⇒ keyword.

Measured against a local `nomic-embed-text` embedder: embeddings **fix** the keyword mis-rank ("data
element count" → `metadata_count` first, vs `analytics_query` under keyword), but are not a silver
bullet — terse queries like "who am i" still rank `system_whoami` only mid-list, because the small
local embedder is weak on short tool-name-ish text. A larger embedder or a keyword+embedding hybrid is
the further upgrade. Note: better ranking helps models that *engage* search; it does **not** fix a model
that never calls `search_tools` (the e4b capability-floor case — that needs a more capable model).

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
  ],
  "embeddings": {"url": "http://localhost:1234/v1/embeddings", "model": "text-embedding-nomic-embed-text-v1.5"}
}
```

The `embeddings` block is optional (omit it for keyword ranking). Run it as a stdio MCP server:
`uv run dhis2w-mcp-router`.

## Federation

Because the core is domain-neutral, one router instance can list several upstreams and present them as a
single searchable surface, namespaced by server (`dhis2__…`, `tracker__…`). This is the Scope-B design:
the same router that fronts dhis2-mcp could front any MCP servers — which is why the core deliberately
avoids DHIS2 coupling.

## Limitations and roadmap

- **Ranking quality** — embeddings (shipped) fix the worst keyword mis-ranks but a small local embedder
  is weak on terse queries; a larger embedder or a keyword+embedding hybrid is the next step.
- **Capability floor** — the search→dispatch indirection is a step the weakest models don't take
  (`bench-router` shows `gemma-4-e4b` never calls `search_tools`); better ranking does not fix that.
- **Per-tool allow/deny lists** beyond read-only could layer on the same `call_tool` chokepoint.
- **Federation in anger** — the multi-upstream case (DHIS2 + non-DHIS2 servers) is built but not yet
  exercised end to end.

## Validation

Validated live against dhis2-mcp: **311 tools registered**, `search("create program stage")` ranks
`dhis2__metadata_program_stage_create` first, and `call("dhis2__metadata_count", {resource:
"dataElements"})` returns `total=1037`. End to end, `gemma-4-26b-a4b-qat` — loaded at just **16k
context** — drove that full 311-tool surface through the read-only router (`search_tools` → `call_tool`
→ answered `1037` on play42). That is the thesis proven: a small local model gets the lazy discovery a
cloud agent gets from ToolSearch, at a context budget it can actually afford, safely.
