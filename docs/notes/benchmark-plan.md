# Benchmark testing plan (1.0 readiness)

The goal: before 1.0, know that **coding + mcp-bridge + full-mcp** model testing is solid, **across all
installed models**. Data sensitivity gates which stack a deployment uses (aggregate -> cloud + full
MCP; PII -> local + bridge), so all three benchmarks must be in place and trustworthy.

## Models under test

The installed LLMs (`make bench-list`) — embeddings and roleplay models excluded:

- `google/gemma-4-26b-a4b-qat` — the **oracle** (256K ctx, tool-trained)
- `google/gemma-4-12b-qat` (256K ctx)
- `google/gemma-4-e4b` (128K ctx)
- `qwen/qwen3.5-4b` (256K ctx, tool-trained — strong tool *format*, weak discovery)

Add candidates (`lms get ...`) as they come up — notably the agentic-coder MoEs
(`Qwen3-Coder-30B-A3B`, `GLM-4.7-Flash`). No roster edits needed; just pass `MODELS=`.

## The three benchmarks

| # | Benchmark | Command | What it measures | Status |
| --- | --- | --- | --- | --- |
| 1 | **coding** | `make bench-general` | python (14) + cli (3) + **multi-turn tooling (7)**, no DHIS2 | **ready** (extended; discriminates) |
| 2 | **mcp-bridge** | `make bench-bridge` (read+write), `bench-matrix` (discovery), `bench-composite` (hard writes) | single-tool `dhis2_cli`; the model must **discover** the ~200-command surface | **ready** |
| 3 | **full mcp** | `make bench-mcp` | the full dhis2-mcp server, all ~311 typed tools loaded up front | **ready** (loads at 128k; oracle passes) |
| 3c | **cloud claude over full mcp** | `make bench-claude-mcp` | the same full server, but driven by a cloud Claude model through the Agent SDK's native loop (not the local OpenAI loop) | **ready** (read suite on play42; ambient subscription auth; read-only gate) |

## bench-mcp — to build (with a safety guard)

Mirrors `bench-bridge` but drives the full FastMCP server (`uv run dhis2w-mcp`) instead of the single
tool. Two design points:

- **Write safety (critical):** the full server has **no readonly mode**, and its typed write tools do
  NOT pass through the bridge's host-guard. So the **read round on `play42` must expose only read-verb
  tools** (`*_get`/`*_list`/`*_count`/`*_find`/`*_search`/`system_*` info), never write tools — else a
  stray call could mutate the public demo. Writes run against `local_basic` only.
- **Scale (measured):** read-only tools = 119 / ~16k tokens; all = 311 / ~49k tokens. That overflows
  LM Studio's default 8192 load context (HTTP 400). So `bench-mcp` loads each model at `BENCH_CONTEXT`
  (default **128k**) via `ModelBackend.load(model, context)`. Finding so far: the oracle (26B MoE,
  256k-capable) *passes* all reads + the write at 128k — a strong local model with a big context CAN
  drive full MCP. Whether smaller models can is what the sweep settles. Context is now a test
  dimension (vary `BENCH_CONTEXT`).

## Sequence (runs are inherently serial — one model loaded at a time)

1. **Coding** across all models — *in progress*. Oracle 62/62 (clean); qwen3.5-4b 54/58.
2. **mcp-bridge** across all models (read + write) — **next** (start with the bridge).
3. **Build bench-mcp** (safe), then **full mcp** across all models.

Each run sets `BENCH_ORACLE=google/gemma-4-26b-a4b-qat` so the oracle flags any mis-specified task
(a oracle failure = fix the task, not the model).

## Safety (all benchmarks)

Reads -> `play42` (`DHIS2_MCP_READONLY=1` on the bridge; read-tool-only filter on full mcp); writes ->
`local_basic` (self-restoring). The bridge host-guard refuses writes to public hosts structurally.
`make dhis2-run` must be up for any write round.

## Output

A per-model x per-benchmark scorecard (correctness + timing + tok/s). "All testing is still good" =
the oracle is clean on every benchmark and the table reproduces across re-runs.
