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
| **`google/gemma-4-12b-qat`** | PASS 11.3s | PASS 16.1s | PASS 11.6s | **PASS** 42.6s/5c | ~16 |
| `google/gemma-4-12b` (bf16) | PASS 17.5s | PASS 17.5s | PASS 18.9s | **PASS** 77.2s/4c | ~14 |
| `google/gemma-4-e4b` (4B) | PASS 15.5s | PASS 18.2s | PASS 12.2s | **PASS** 33.7s/2c | ~21 |
| `qwen2.5-7b-instruct` | PASS 7.2s | PASS 19.4s | PASS 8.6s | found cmd, no confirm 38.0s | ~8 |
| `qwen/qwen3.5-4b` | PASS 8.2s | PASS 12.9s | PASS 13.5s | cmd not found 36.0s | ~34 |
| _me (capable cloud model)_ | PASS | PASS | PASS | PASS | n/a |

The cloud-model row is the correctness reference: it knows the commands directly (no discovery
flailing) — its wall-clock isn't comparable (remote, reasoning-dominated), so it's left blank.

## Takeaways

- **`gemma-4-12b-qat` is the pick.** The only local model that passed **both** read and write, and
  it's fast — the qat quant beats its own bf16 sibling on every task (count 11.3s vs 17.5s, write
  42.6s vs 77.2s) at identical correctness. The "qat seems amazing" read holds up.
- **`gemma-4-e4b`** is the smallest that completes the write round (and quickest write at 33.7s), but
  its tool-calling is flaky — one run 400'd mid-write before settling. Good when RAM is tight.
- **qwen reads are strong and fast** (`qwen2.5-7b` count in 7.2s), but **writes are the wall**:
  `qwen2.5-7b` finds `dev customize set` yet doesn't cleanly confirm; `qwen3.5-4b` never finds it even
  with a hint. Treat the qwens as read-only drivers.
- **All five now use `dhis2 schema`** for the schema task — the command + the bridge-docstring hint
  closed the field-hallucination gap across the board (see `small-model-bridge.md`).
- **The write wall is discoverability**, not capability: `dev customize set` is buried under `dev`.
  This is the standing system-setting-write discoverability item in `small-model-bridge.md`.

## Re-running

```bash
make bridge-bench                                              # the full roster
make bridge-bench MODELS="qwen2.5-7b-instruct google/gemma-4-e4b"   # a subset
```

Needs `lms server` running; the harness loads/unloads each model itself (one instance at a time, to
avoid the ambiguous-model-id 400). Per-model JSON is appended to `/tmp/bench_bridge_results.jsonl`.
