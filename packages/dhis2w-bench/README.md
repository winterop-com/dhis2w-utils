# dhis2w-bench

Local-LLM benchmark harness for DHIS2 agents. Workspace-only (not published to PyPI).

Three benchmarks, each driven by `make` targets that load/unload one local model at a time and score
objectively. Data sensitivity decides which stack a deployment uses (aggregate -> cloud + full MCP;
PII -> local + bridge), so all three matter:

- **coding** (`make bench-general`) — python + cli + multi-turn tooling, no DHIS2.
- **mcp-bridge** (`make bench-bridge`) — the single-tool `dhis2_cli` bridge: the model must *discover*
  the command surface. The PII-safe path.
- **full mcp** (`make bench-mcp`) — the whole dhis2-mcp server (~311 tools) loaded up front.

The local benchmarks have a **cloud peer** for the full-MCP surface:

- **cloud claude over full mcp** (`make bench-claude-mcp`) — a cloud Claude model drives the whole
  dhis2-mcp server through the Claude Agent SDK's native loop (not the local OpenAI loop). Auth is
  ambient (the logged-in Claude Code subscription) — no API key is read or stored. Read suite on
  `play42`, kept safe by a fail-closed read-only permission gate. Costs subscription budget.

Plus `make bench-list` (installed models), `bench-validate`, `bench-round`, `bench-matrix`,
`bench-composite`, `bench-longcontext`. See `docs/notes/benchmark-plan.md` and
`docs/notes/benchmark-results.md`.

## Backend abstraction

`dhis2w_bench.backend` isolates model lifecycle (list / load / unload / server) behind a
`ModelBackend` protocol. `LmStudioBackend` is the only implementation today; select via
`MODEL_BACKEND`. Ollama / llama.cpp drop in as new classes without touching the harnesses.

## Run

```bash
make bench-list
make bench-general MODELS="<key> ..."
make bench-bridge  MODELS="<key> ..."   # needs make dhis2-run (local_basic)
make bench-mcp     MODELS="<key> ..."   # loads at BENCH_CONTEXT (default 128k)
make bench-claude-mcp                   # cloud Claude (session default); or MODELS="opus sonnet"
```

`bench-claude-mcp` needs no local model server — just a logged-in Claude Code subscription
(`claude setup-token` or `/login`). Make sure `ANTHROPIC_API_KEY` is **unset** so it uses the
subscription rather than billing API credits.

Knobs: `BENCH_ORACLE` (oracle), `BENCH_MAX_TOKENS` (generation cap), `BENCH_CONTEXT` (load context),
`MODEL_BACKEND` (backend).
