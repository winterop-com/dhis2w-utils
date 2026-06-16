# General-capability benchmark (axis 1)

Living benchmark for **general** model capability — independent of DHIS2. This is axis 1 of model
validation; axis 2 (driving the bridge) lives in [`model-benchmark.md`](model-benchmark.md). Re-run
with **`make bench-general`** (harness: `infra/scripts/bench_general_models.py`).

## Choosing models

There is **no hardcoded roster** — you name the model(s) to benchmark. List what's installed with
`make bench-list`, then pass one or more keys via `MODELS=`:

- one model -> a single-model run
- several -> a side-by-side comparison table (they run one at a time through the same suites)

Optionally set `BENCH_CHAMPION=<key>` to mark one of them as the oracle (see below). The harness skips
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

Set `BENCH_CHAMPION=<key>` to designate one model in the run as the oracle — the should-pass bar.
The harness then asserts that model passed every task and prints a loud `SUSPECT TASK(S)` banner if
not; an oracle failure almost always means the **task** is mis-specified, not the model, so fix the
task before trusting the other columns. With no `BENCH_CHAMPION` set there is no oracle check. Our
strongest local model, `google/gemma-4-26b-a4b-qat`, is the natural choice.

## Latest results — 2026-06-16

| model | python | cli | tooling | total |
| --- | --- | --- | --- | --- |
| `google/gemma-4-26b-a4b-qat` (champion) | 23/23 | 3/3 | 3/3 | **29/29** |
| `google/gemma-4-12b-qat` | 23/23 | 3/3 | 3/3 | **29/29** |
| `google/gemma-4-12b` (bf16) | 23/23 | 3/3 | 3/3 | **29/29** |
| `google/gemma-4-e4b` | 23/23 | 3/3 | 3/3 | **29/29** |

Oracle clean (champion 29/29, no `SUSPECT` banner). **At the default 16384-token budget the gemmas
are indistinguishable** — every model passes every task. To separate them, tighten `BENCH_MAX_TOKENS`
(e.g. `BENCH_MAX_TOKENS=2048`) and watch which degrade first: the reasoning models truncate their
code once the cap bites the chain-of-thought. (Calibration note: the first champion run flagged 5
SUSPECT tasks — that caught two real harness bugs, a 2048-token truncation and a `create_file` prompt
that sent the champion into a runaway reasoning loop; both fixed before recording the above.)

## Re-running

```bash
make bench-list                                              # what's installed
make bench-general MODELS="google/gemma-4-12b-qat"           # one model
make bench-general MODELS="gemma-4-12b-qat gemma-4-e4b"      # compare several
BENCH_MAX_TOKENS=2048 make bench-general MODELS="..."        # tighter token budget
BENCH_CHAMPION=google/gemma-4-26b-a4b-qat make bench-general MODELS="..."   # with an oracle
make bench-validate MODEL=google/gemma-4-12b-qat            # this axis + the bridge axis together
```

Needs a running backend (LM Studio by default; set `MODEL_BACKEND` to switch — see
`infra/scripts/_model_backend.py`). The harness loads/unloads each model itself, one at a time.
