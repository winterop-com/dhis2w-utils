# Local-model bridge benchmark

Living benchmark for the models we drive `dhis2w-mcp-bridge` with. Re-run with **`make bridge-bench`**
(harness: `infra/scripts/bench_bridge_models.py`). Companion to the discovery notes in
[`small-model-bridge.md`](small-model-bridge.md).

## Roster (the tracked set)

We benchmark a curated list, not every downloaded model. Add to it on request — edit `ROSTER` in
`infra/scripts/bench_bridge_models.py`:

- `google/gemma-4-12b-qat` — primary recommendation
- `google/gemma-4-12b` — bf16 baseline (the only non-qat entry, kept for the qat-vs-bf16 comparison)
- `google/gemma-4-26b-a4b-qat` — larger MoE (qat); does the qat variant scale up?
- `google/gemma-4-e4b` — smallest that completes the write round
- `qwen2.5-7b-instruct` — reliable, fast reads
- `qwen/qwen3.5-4b` — fast reads, read-only in practice

Note: where a qat build exists we benchmark the qat variant (the `-qat` model key), not the bf16 —
the lone exception is `gemma-4-12b` (bf16), kept on purpose as the head-to-head against `12b-qat`.

## Method

- **Reads → `play42`** (`DHIS2_MCP_READONLY=1`); **writes → `local_basic`** (`READONLY=0`, the write
  round-trips `minPasswordLength` and restores it). Never the shared public demo.
- Each task runs through the **real bridge** (FastMCP client → `dhis2_cli`) with LM Studio's
  OpenAI-compatible API as the brain. Per task: pass/fail (heuristic), tool-call count, wall-clock,
  completion tokens. `read tok/s` is total read completion-tokens / total read wall-clock (approx).
- **Tasks:** `count` ("how many data elements" → 1037) · `schema` ("what fields does a data element
  have" → must call `dhis2 schema` and name real fields) · `filter` (ANC indicators) · `write` (set
  `minPasswordLength` to 10 with a command hint, then verify). Single representative runs; expect
  run-to-run variance, especially on the write (model nondeterminism).

## Latest results — 2026-06-06 (play42 / local_basic)

| model | count | schema | filter | write | read tok/s |
| --- | --- | --- | --- | --- | --- |
| **`google/gemma-4-26b-a4b-qat`** (MoE 26B/4B) | PASS 10.1s | PASS 10.2s | PASS 9.7s | **PASS** 21.6s/4c | ~19 |
| `google/gemma-4-12b-qat` | PASS 11.3s | PASS 16.1s | PASS 11.6s | **PASS** 42.6s/5c | ~16 |
| `google/gemma-4-12b` (bf16) | PASS 17.5s | PASS 17.5s | PASS 18.9s | **PASS** 77.2s/4c | ~14 |
| `google/gemma-4-e4b` (4B) | PASS 15.5s | PASS 18.2s | PASS 12.2s | **PASS** 33.7s/2c | ~21 |
| `qwen2.5-7b-instruct` | PASS 7.2s | PASS 19.4s | PASS 8.6s | found cmd, no confirm 38.0s | ~8 |
| `qwen/qwen3.5-4b` | PASS 8.2s | PASS 12.9s | PASS 13.5s | cmd not found 36.0s | ~34 |
| Claude Code (capable cloud agent) | PASS | PASS | PASS | PASS | n/a |

The Claude Code row is the correctness reference (a capable cloud agent — the oracle): it knows the
commands directly, no discovery flailing. Its wall-clock isn't comparable (remote, reasoning-
dominated), so it's left blank.

## Takeaways

- **Caveat on the `write` column — it is an easy task.** The write prompt is a *single* setting
  (`customize set minPasswordLength 10`) **with the command name hinted**, plus a verify read. It
  measures execution + arg-formatting, not discovery or multi-object composition. So "PASS write"
  here is a low bar; do not read it as "handles real writes". The hard writes are the composite
  scenarios (data set + N elements, program + N stages) — so far run only through the capable-agent
  oracle, not these local models. That is the test that will actually separate them.
- **`gemma-4-26b-a4b-qat` is the current pick** (on this easy bar): same 4/4 as `12b-qat` but faster
  on every task and ~2x faster on the (simple) write — the MoE's 4B active params keep it fast while
  the extra capacity helps. `12b-qat` is the close runner-up and beats its own bf16 sibling on every
  task at equal correctness ("qat seems amazing" holds).
- **`gemma-4-e4b`** is the smallest that completes the write round (and quickest write at 33.7s), but
  its tool-calling is flaky — one run 400'd mid-write before settling. Good when RAM is tight.
- **qwen reads are strong and fast** (`qwen2.5-7b` count in 7.2s), but **writes are the wall**:
  `qwen2.5-7b` finds `customize set` yet doesn't cleanly confirm; `qwen3.5-4b` never finds it even
  with a hint. Treat the qwens as read-only drivers.
- **All five now use `dhis2 schema`** for the schema task — the command + the bridge-docstring hint
  closed the field-hallucination gap across the board (see `small-model-bridge.md`).
- **The write wall is discoverability**, not capability: `customize set` is buried under `dev`.
  This is the standing system-setting-write discoverability item in `small-model-bridge.md`.

## Re-running

```bash
make bridge-bench                                              # the full roster
make bridge-bench MODELS="qwen2.5-7b-instruct google/gemma-4-e4b"   # a subset
```

Needs `lms server` running; the harness loads/unloads each model itself (one instance at a time, to
avoid the ambiguous-model-id 400). Per-model JSON is appended to `/tmp/bench_bridge_results.jsonl`.

## The cli-matrix grid is NOT a capability ranking

The full metadata×roster grid (`docs/notes/cli-matrix.md`, 1230 cells) finished. The "found the right
command" rates: bf16-12b **12%**, 12b-qat 10%, qwen3.5-4b 8%, **26b-a4b-qat 4%**, qwen2.5-7b 4%,
e4b 2%. The champion on read+write+perf (`26b-a4b-qat`) scored near the **bottom** — proof the grid
measures *vague-goal disambiguation* (pick the exact command among ~200 siblings from a one-line
goal), which is interpretation-noise-dominated, not capability. **Use `bridge-bench` (read+write+perf)
to judge models; the matrix is a discoverability stress-test of the help surface, not a leaderboard.**
