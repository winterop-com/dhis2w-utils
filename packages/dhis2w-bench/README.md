# dhis2w-bench

Local-LLM benchmark harness for DHIS2 agents. Workspace-only (not published to PyPI).

Three benchmarks, each driven by `make` targets that load/unload one local model at a time and score
objectively. Data sensitivity decides which stack a deployment uses (aggregate -> cloud + full MCP;
PII -> local + bridge), so all three matter:

- **coding** (`make bench-general`) — python + cli + multi-turn tooling, no DHIS2.
- **mcp-bridge** (`make bench-bridge`) — the single-tool `dhis2_cli` bridge: the model must *discover*
  the command surface. The PII-safe path.
- **full mcp** (`make bench-mcp`) — the whole dhis2-mcp server (~311 tools) loaded up front.

The local benchmarks have **cloud peers** that drive the same surfaces with a cloud Claude model
through the Claude Agent SDK's native loop (not the local OpenAI loop). Auth is ambient (the
logged-in Claude Code subscription) — no API key is read or stored; costs subscription budget.

- **cloud claude on the coding suite** (`make bench-claude-general`) — python + cli + tooling, the cloud peer of `bench-general` (one-shot code-gen + an in-process SDK mock toolbox for the agentic tooling suite).
- **cloud claude over full mcp** (`make bench-claude-mcp`) — the whole dhis2-mcp server (typed tools).
- **cloud claude over the bridge** (`make bench-claude-bridge`) — the single `dhis2_cli` tool.

Both run three rounds (reusing the local tasks + scoring, so cloud and local are comparable): **read**
(`play42`, behind a fail-closed read-only gate), **write** (`local_basic`, restored after), and the
hard **composite** multi-object authoring scenarios (`local_basic`) — the real local/cloud
discriminator. Writes go to `local_basic` only (the bridge host-guard + the gate + the local-only
profile are the safety boundary). The write/composite rounds need `make dhis2-run`.

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
make bench-claude-general               # cloud Claude on the coding suite (python+cli+tooling)
make bench-claude-mcp                   # cloud Claude over full mcp (session default); MODELS="opus sonnet"
make bench-claude-bridge                # cloud Claude over the bridge; RUNS=3 repeats the composite
```

The `bench-claude-*` lanes need no local model server — just a logged-in Claude Code subscription
(`claude setup-token` or `/login`). Make sure `ANTHROPIC_API_KEY` is **unset** so they use the
subscription rather than billing API credits. Their write/composite rounds need `make dhis2-run`.

Knobs: `BENCH_ORACLE` (oracle), `BENCH_MAX_TOKENS` (generation cap), `BENCH_CONTEXT` (load context),
`MODEL_BACKEND` (backend).
