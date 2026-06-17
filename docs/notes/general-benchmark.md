# General-capability benchmark (axis 1)

Living benchmark for **general** model capability — independent of DHIS2. This is axis 1 of model
validation; axis 2 (driving the bridge) lives in [`model-benchmark.md`](model-benchmark.md). Re-run
with **`make bench-general`** (harness: `packages/dhis2w-bench/src/dhis2w_bench/general.py`).

## Choosing models

There is **no hardcoded roster** — you name the model(s) to benchmark. List what's installed with
`make bench-list`, then pass one or more keys via `MODELS=`:

- one model -> a single-model run
- several -> a side-by-side comparison table (they run one at a time through the same suites)

Optionally set `BENCH_ORACLE=<key>` to mark one of them as the oracle (see below). The harness skips
and logs any named model that isn't installed.

## Method

Three suites, all scored by **execution or structural match — never an AI judge**:

- **python** — the model writes one function/class; the harness extracts the fenced code block,
  `exec`s it, and runs hidden test cases. Tasks span easy (Roman numerals, balanced brackets) to
  harder (LRU cache class, longest-common-subsequence) so models actually separate.
- **cli** — the model writes a single shell command for a goal; the harness runs it in a
  **curated-PATH temp sandbox** and checks the effect (a created file, stdout). Only an allowlist of
  read/format tools is reachable (`echo`, `cat`, `wc`, `awk`, ... — no `rm`/`curl`/`sudo`), and
  commands with absolute paths / `~` / `..` are rejected before running. This bounds — it does not
  perfectly isolate — model shell; run it on a machine you trust.
- **tooling** — the model is given mock tool specs (`get_weather`, `send_email`, `search`) and a
  goal; the harness checks it emits the **right tool call with the right args**. This is the
  function-calling foundation the bridge depends on, so it predicts axis-2 competence.

Per-task: pass/fail (cases passed / total), wall-clock, completion tokens. Per-model JSON is appended
to `/tmp/bench_general_results.jsonl`.

**Token budget is a knob.** The roster models are reasoning models — they spend a long
chain-of-thought before the answer, so a low generation cap truncates the actual code/command (the
closing code fence never arrives). The cap defaults to a generous 16384 but is configurable via
`BENCH_MAX_TOKENS`. Lowering it is a deliberate stress test: at a generous budget the gemmas all
pass everything (no separation), so to tell them apart you tighten the budget and see which degrade
gracefully and which break first.

## The oracle (opt-in)

Set `BENCH_ORACLE=<key>` to designate one model in the run as the oracle — the should-pass bar.
The harness then asserts that model passed every task and prints a loud `SUSPECT TASK(S)` banner if
not; an oracle failure almost always means the **task** is mis-specified, not the model, so fix the
task before trusting the other columns. With no `BENCH_ORACLE` set there is no oracle check. Our
strongest local model, `google/gemma-4-26b-a4b-qat`, is the natural choice.

## Latest results — 2026-06-17 (extended suite: 62 cases)

| model | python | cli | tooling | total | time | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| `google/gemma-4-26b-a4b-qat` (oracle) | 52/52 | 3/3 | 7/7 | **62/62** | 612s | 60 |
| `google/gemma-4-12b-qat` | 52/52 | 3/3 | 7/7 | **62/62** | 936s | 35 |
| `google/gemma-4-e4b` | 48/49 | 3/3 | 7/7 | **58/59** | 346s | 52 |
| `qwen/qwen3.5-4b` | 44/46 | 2/3 | 7/7 | **53/56** | 471s | 85 |

Oracle clean. The two qats are perfect; `e4b` near-perfect and fast; `qwen3.5-4b` fast but drops the
LRU-cache class and a `wc` command. Both 4B models pass all four multi-turn agentic tool chains, so
chaining is not size-bound. Full write-up across all three benchmarks:
[benchmark-results.md](benchmark-results.md).

## Re-running

```bash
make bench-list                                              # what's installed
make bench-general MODELS="google/gemma-4-12b-qat"           # one model
make bench-general MODELS="gemma-4-12b-qat gemma-4-e4b"      # compare several
BENCH_MAX_TOKENS=2048 make bench-general MODELS="..."        # tighter token budget
BENCH_ORACLE=google/gemma-4-26b-a4b-qat make bench-general MODELS="..."   # with an oracle
make bench-validate MODEL=google/gemma-4-12b-qat            # this axis + the bridge axis together
```

Needs a running backend (LM Studio by default; set `MODEL_BACKEND` to switch — see
`packages/dhis2w-bench/src/dhis2w_bench/backend.py`). The harness loads/unloads each model itself, one at a time.
