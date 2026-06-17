# Local-model bridge benchmark

Living benchmark for the models we drive `dhis2w-mcp-bridge` with. Re-run with **`make bench-bridge`**
(harness: `packages/dhis2w-bench/src/dhis2w_bench/bridge.py`). Companion to the discovery notes in
[`small-model-bridge.md`](small-model-bridge.md).

This is **axis 2** of model validation (driving the bridge: read + write). **Axis 1** — general
capability (python / cli / tooling, no DHIS2) — is [`general-benchmark.md`](general-benchmark.md).
Validate one model across both axes at once with `make bench-validate MODEL=<key>`.

## Choosing models

There is **no hardcoded roster** — you name the model(s) to benchmark. List what's installed with
`make bench-list`, then pass one or more keys via `MODELS=` (one model = a single run; several = a
side-by-side comparison, run one at a time). The harness skips and logs any named model that isn't
installed. Set `BENCH_CHAMPION=<key>` to designate an oracle (see below).

## Method

- **Reads → `play42`** (`DHIS2_MCP_READONLY=1`); **writes → `local_basic`** (`READONLY=0`, the write
  round-trips `minPasswordLength` and restores it). Never the shared public demo.
- Each task runs through the **real bridge** (FastMCP client → `dhis2_cli`) with LM Studio's
  OpenAI-compatible API as the brain. Per task: pass/fail (heuristic), tool-call count, wall-clock,
  completion tokens. `read tok/s` is total read completion-tokens / total read wall-clock (approx).
- **Tasks:** `count` ("how many data elements" → 1037) · `schema` ("what fields does a data element
  have" → must call `d2w schema` and name real fields) · `filter` (ANC indicators) · `write` (set
  `minPasswordLength` to 10 with a command hint, then verify). Single representative runs; expect
  run-to-run variance, especially on the write (model nondeterminism).

## Latest results — 2026-06-17 (play42 / local_basic)

| model | count | schema | filter | write | read tok/s |
| --- | --- | --- | --- | --- | --- |
| **`google/gemma-4-26b-a4b-qat`** (oracle) | PASS 8.9s | PASS 9.9s | PASS 9.0s | **PASS** 15.7s | ~21 |
| `google/gemma-4-12b-qat` | PASS 10.5s | PASS 14.9s | PASS 10.7s | **PASS** 20.3s | ~17 |
| `google/gemma-4-e4b` | PASS 10.4s | PASS 12.6s | PASS 13.5s | **PASS** 21.4s | ~30 |
| `qwen/qwen3.5-4b` | PASS 8.2s | PASS 9.1s | PASS 25.8s | **PASS** 10.1s | ~33 |
| `mn-violet-lotus-12b` | FAIL 6.0s | FAIL 6.3s | PASS 5.5s | cmd-not-found | ~20 |

All four serious candidates pass every read + the write round (oracle clean); `qwen3.5-4b` writes
fastest. `mn-violet-lotus` (roleplay) fails discovery. Note: this run also caught + fixed a stale
write-command in the task itself (`dev customize set` → `system settings set`) — see
[benchmark-results.md](benchmark-results.md) for the full three-benchmark write-up.

## The oracle (opt-in)

Set `BENCH_CHAMPION=<key>` to designate one model in the run as the correctness reference — the
should-pass bar. The harness then asserts that model passed every task and prints a loud
`SUSPECT TASK(S)` banner if it didn't, because an oracle failure almost always means the **task** is
mis-specified, not the model. With no `BENCH_CHAMPION` set there is no oracle check. The natural
choice is the strongest local model, `google/gemma-4-26b-a4b-qat`. This is a local, reproducible
oracle (no cloud agent in the loop).

## Writes need local infra (and the bridge refuses public hosts)

The write round targets `local_basic`, so the harness **preflights** it with a cheap read and exits
loud (`make dhis2-run`) if the stack is down — it never silently skips the write. Independently, the
bridge itself refuses any mutating command whose resolved host is a shared public DHIS2 demo
(`play.*.dhis2.org`, `debug.dhis2.org`) regardless of read-only mode — a structural backstop so no
harness can write to the public demo by mis-wiring a profile. Override with
`DHIS2_MCP_PROTECTED_HOSTS` (empty value disables it).

## Takeaways

- **All four gemmas pass both axes.** On reads + the (easy) write round they're equivalent on
  correctness; only speed separates them. So neither axis at full budget is a *capability* ranking
  for these four — it's a confirmation that all are viable bridge drivers.
- **Caveat on the `write` column — it is an easy task.** A *single* hinted setting plus a verify
  read; it measures execution + arg-formatting, not discovery or multi-object composition. "PASS
  write" is a low bar. The hard writes are the composite scenarios (`make bench-composite`).
- **`e4b` is the efficiency surprise**: fastest reads (~28 tok/s) and the fastest write (31.2s, in a
  single tool call) despite being the smallest (4B / 6.86 GB).
- **bf16 `gemma-4-12b` is strictly dominated** by its qat sibling: same correctness, ~2x slower write
  (112.8s vs 55.9s), nearly 2x the disk (12.84 vs 7.15 GB).

## Prune decision — 2026-06-16

Validation across both axes (this page + [`general-benchmark.md`](general-benchmark.md)) settles the
keep/delete question:

- **Keep** `google/gemma-4-26b-a4b-qat` (oracle), `google/gemma-4-12b-qat` (runner-up),
  `google/gemma-4-e4b` (fast, low-RAM).
- **Delete** `google/gemma-4-12b` (bf16) — strictly dominated by `12b-qat` on speed and size at
  identical correctness. The only reason it was kept was the qat-vs-bf16 head-to-head, which is now
  settled.

Because all four tie on correctness at full token budget, the general suite no longer *separates*
them — to do that, tighten `BENCH_MAX_TOKENS` (see `general-benchmark.md`).

## Re-running

```bash
make bench-list                                                       # what's installed
make bench-bridge MODELS="google/gemma-4-12b-qat"                     # one model
make bench-bridge MODELS="gemma-4-12b-qat gemma-4-e4b"                # compare several
BENCH_CHAMPION=google/gemma-4-26b-a4b-qat make bench-bridge MODELS="..."   # with an oracle
```

Needs the backend running and `local_basic` up for the write round (`make dhis2-run`). The harness
loads/unloads each model itself (one instance at a time, to avoid the ambiguous-model-id 400).
Per-model JSON is appended to `/tmp/bench_bridge_results.jsonl`.

## The bench-matrix grid is NOT a capability ranking

The full metadata×roster grid (`docs/notes/cli-matrix.md`, 1230 cells) finished. The "found the right
command" rates: bf16-12b **12%**, 12b-qat 10%, qwen3.5-4b 8%, **26b-a4b-qat 4%**, qwen2.5-7b 4%,
e4b 2%. The champion on read+write+perf (`26b-a4b-qat`) scored near the **bottom** — proof the grid
measures *vague-goal disambiguation* (pick the exact command among ~200 siblings from a one-line
goal), which is interpretation-noise-dominated, not capability. **Use `bench-bridge` (read+write+perf)
to judge models; the matrix is a discoverability stress-test of the help surface, not a leaderboard.**
