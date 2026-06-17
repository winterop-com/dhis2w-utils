# Benchmark results — 2026-06-17

A full sweep of every installed local LLM across all three benchmarks (coding, mcp-bridge, full mcp),
run overnight with `google/gemma-4-26b-a4b-qat` as the oracle. **The oracle was clean on all three**
(it passed every task), so the tasks are well-formed and the weaker-model numbers are trustworthy.

Reproduce: `make bench-general`, `make bench-bridge`, `make bench-mcp` (each `MODELS="..."`); the raw
tables are in `/tmp/sweep_{coding,bridge,mcp}.out`.

## TL;DR

- **All four serious candidates — `gemma-4-26b-a4b-qat`, `gemma-4-12b-qat`, `gemma-4-e4b`,
  `qwen3.5-4b` — passed all three benchmarks**, including the *full* MCP server (~311 tools) at 128k
  context. The assumption that "only cloud frontier models can drive full MCP" does **not** hold for
  these read+write tasks: capable local models handle it, given enough context.
- **`gemma-4-e4b` (4B, 6.9 GB) wins reads, easy writes, and speed** — near-perfect everywhere cheap,
  fastest on the easy/MCP writes. But it **cannot do the hard composite writes** (0/2 — see below).
- **`gemma-4-12b-qat` is the authoring winner.** It looks "dominated" on speed/easy tasks, but it is
  the **only** model that reliably completes the hard multi-object writes (2/2 composite) — the test
  that actually matters for a DHIS2 authoring agent. So **do not delete it.**
- **Easy writes don't rank models; the composite (hard) writes do** — and they invert the ranking
  (the champion fails the dataset composite; the speed winners score 0/2).
- **Two real bugs were caught by the oracle and fixed mid-run** (see Findings): a stale bridge
  write-command, and the full-MCP context-window requirement. A third (the composite oracle itself)
  was caught when its deterministic run failed.

## Coding (`bench-general`) — 62 objective cases (python 52, cli 3, tooling 7)

| model | python | cli | tooling | total | time | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| `gemma-4-26b-a4b-qat` (oracle) | 52/52 | 3/3 | 7/7 | **62/62** | 612s | 60 |
| `gemma-4-12b-qat` | 52/52 | 3/3 | 7/7 | **62/62** | 936s | 35 |
| `gemma-4-e4b` | 48/49 | 3/3 | 7/7 | **58/59** | 346s | 52 |
| `qwen3.5-4b` | 44/46 | 2/3 | 7/7 | **53/56** | 471s | 85 |

- The two qats are perfect; `e4b` drops one python case; `qwen3.5-4b` drops a couple of python cases
  (the LRU-cache class) plus a `wc` command.
- **All four pass 7/7 tooling** — including the four multi-turn agentic chains (look-up-then-email,
  read-then-count, fetch-rate-then-calc, look-up-then-ticket). So a 4B model (`qwen3.5-4b`, `e4b`)
  handles multi-turn tool *chaining* fine; size is not the bottleneck there.

## mcp-bridge (`bench-bridge`) — single-tool discovery, read + write

| model | count | schema | filter | write | read tok/s |
| --- | --- | --- | --- | --- | --- |
| `gemma-4-26b-a4b-qat` | PASS | PASS | PASS | **PASS** 15.7s | ~21 |
| `gemma-4-12b-qat` | PASS | PASS | PASS | **PASS** 20.3s | ~17 |
| `gemma-4-e4b` | PASS | PASS | PASS | **PASS** 21.4s | ~30 |
| `qwen3.5-4b` | PASS | PASS | PASS | **PASS** 10.1s | ~33 |

- **All four candidates pass every read and the write** (after the write-command fix below). Notably
  `qwen3.5-4b` passes the write *fastest* (10.1s) — earlier in the session it "couldn't find" the
  command, but that was the *stale-command* bug, not the model.

## Full MCP (`bench-mcp`) — the whole dhis2-mcp server, read-only-filtered reads, 128k context

| model | count | filter | whoami | write | tools | read tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| `gemma-4-26b-a4b-qat` | PASS | PASS | PASS | **PASS** 80.3s | 119 | ~21 |
| `gemma-4-12b-qat` | PASS | PASS | PASS | **PASS** 222.1s | 119 | ~7 |
| `gemma-4-e4b` | PASS | PASS | PASS | **PASS** 54.1s | 119 | ~33 |
| `qwen3.5-4b` | PASS | PASS | PASS | **PASS** 122.8s | 119 | ~13 |

- **All four candidates drive the full MCP server end-to-end** — selecting the right tool among 119
  read tools (and ~311 on the write round) and completing a write. This is the surprising result of
  the night: full MCP is *not* exclusively a cloud-frontier capability.
- It is **much slower** than the bridge (e.g. champion MCP write 80s vs bridge 16s) and needs a big
  load context — so the bridge is still the right default for PII/local, but full MCP is viable.

## Composite writes (`bench-composite`) — the HARD, multi-object authoring test

The reads and the single-setting writes above are easy (everyone passes), so they don't rank models.
The real test is a **multi-object authoring** workflow driven through the bridge: "create a Monthly
data set with two new data elements attached", and "create an event program with two stages". Each
run is verified (find the named object, count its children) and cleaned up.

| model | dataset + elements | program + stages | hard-write score |
| --- | --- | --- | --- |
| `gemma-4-26b-a4b-qat` (champion) | **FAIL** (never created it; 11 calls, 393s) | PASS (6 calls, 48s) | 1/2 |
| `gemma-4-12b-qat` | **PASS** (2/2, 70s) | **PASS** (2/2, 88s) | **2/2** |
| `gemma-4-e4b` | **FAIL** (never created; 226s) | **FAIL** (0/2, looped to limit) | 0/2 |
| `qwen3.5-4b` | **FAIL** (set created, 0 elements attached) | **FAIL** (0/2 stages) | 0/2 |

**This inverts the rest of the results.** On easy + full-MCP writes all four pass; on hard writes
**only `gemma-4-12b-qat` succeeds on both**, and the models that win elsewhere are the worst here:

- The **champion *fails* the dataset composite** — 6.5 min, 11 calls, never built it. Best at
  reads/easy-writes is not best at authoring.
- **`e4b` and `qwen3.5-4b` (the efficiency/speed winners) score 0/2** — they stall (e4b looped to the
  20-call limit) or give up after a partial build (qwen made the set but attached nothing).
- **`gemma-4-12b-qat` — earlier flagged "dominated, prime delete" — is the only reliable author.**

So for the **PII-write path** (the whole reason local exists), the pick is **`gemma-4-12b-qat`**, not
`e4b`. Caveat: 2 scenarios, single runs, model nondeterminism — but the pattern is strong.

## Context-window dimension (full MCP, `gemma-4-e4b`)

The full-MCP payload is the gate, so loaded context decides what works (read tools ~16k tokens, the
write round's full toolset ~49k):

| loaded context | reads (119 tools) | write (311 tools) |
| --- | --- | --- |
| 8k (LM Studio default) | fail (HTTP 400 — payload > context) | fail |
| 32k | **pass** | fail (loops; 49k payload doesn't fit) |
| 64k | pass\* | **pass** |
| 128k | pass | pass |

So full-MCP **reads need roughly ≥32k** context and **writes need ≥64k**; 128k is comfortably safe
(the default `BENCH_CONTEXT`). (\*the 64k read FAILs in one run were small-model answer-variance, not
a context effect — they pass at 32k and 128k.) Vary `BENCH_CONTEXT` to test other models/levels.

## Token-budget dimension (coding at `BENCH_MAX_TOKENS=2048`)

Tightening the generation budget from 16384 to 2048 **inverts the ranking**:

| model | full (16384) | tight (2048) | behaviour |
| --- | --- | --- | --- |
| `gemma-4-26b-a4b-qat` | 62/62 | **47/51** | collapses |
| `gemma-4-12b-qat` | 62/62 | **42/48** | collapses |
| `gemma-4-e4b` | 58/59 | **54/56** | holds |
| `qwen3.5-4b` | 53/56 | **52/56** | holds (140s — fastest) |

The reasoning models (`champion`, `12b-qat`) spend the budget on chain-of-thought and **truncate the
actual code** on the hard tasks (`lru_cache`, `rpn_eval`, `word_break`, `edit_distance`), so under
token pressure the **small models win** — `e4b` and `qwen3.5-4b` barely move, and `qwen` is ~3x faster
(140s vs 471s). Practical rule: **pick the model for the budget** — generous budget favours the qats
(perfect but slow); tight budget / low latency favours `e4b` or `qwen`.

Note on the oracle: the SUSPECT banner *did* fire at 2048 (champion failed 4 tasks). That is a **true**
signal here, not a task bug — the oracle's "champion passes everything" assumption only holds at a
generous budget; deliberately handicapping the champion is expected to break it.

## Findings (what the night taught us)

1. **The oracle caught a real test bug.** The bridge write task hinted `dev customize set <key>
   <value>` — a command the CLI **removed** (it moved to the discoverable `system settings set`).
   Every model parroted the dead command and looped to the step limit, and the *champion* failed too
   → SUSPECT banner. Fixed the task; the champion now passes the write in 3 calls. This is exactly
   what the oracle is for: catching benchmark drift against an evolving CLI.
2. **Context window is the gate for full MCP, not raw capability.** The tool payload is ~49k tokens
   (311 tools); LM Studio's default 8192 load context rejects it outright (HTTP 400). Loading at
   **128k** (`BENCH_CONTEXT`) makes full MCP work for every candidate. So "can this model do full
   MCP" is really "is it loaded with enough context" — a config decision, now a test dimension.
3. **Multi-turn tool chaining is not size-bound.** Both 4B models pass all four multi-turn tool
   scenarios. The thing that actually separates models on the *bridge/MCP* is discovery + speed, not
   tool mechanics.

## Recommendations

| Use case | Pick | Why |
| --- | --- | --- |
| **PII authoring** (multi-object writes — the real local job) | **`gemma-4-12b-qat`** | The **only** model that reliably completes the hard composite writes (2/2). `e4b`/`qwen` score 0/2; the champion 1/2. |
| **PII reads + easy writes, fast** | `gemma-4-e4b` | Passes reads + the easy/MCP writes, smallest (6.9 GB), fastest — but **not** for composite authoring. |
| **Full MCP, if going local** | `gemma-4-e4b` or champion | All candidates handle reads + the easy write at 128k; `e4b` fastest. (Hard writes not tested through full MCP yet.) |
| **Coding** | champion or `e4b` | 62/62 and 58/59; `qwen3.5-4b` for speed with weaker class/edge-case coding. |

## Prune decision (2026-06-17)

- **Keep all four serious candidates** — the composite results show they are *not* redundant: each
  wins a different axis. `gemma-4-12b-qat` (authoring), `gemma-4-e4b` (efficiency/reads),
  `gemma-4-26b-a4b-qat` (oracle / max headroom), `qwen3.5-4b` (fastest tool driver).
- **Reversal:** the earlier "delete `gemma-4-12b-qat`" call was **wrong** — it's the only reliable
  composite author, which is the capability that matters most for a local PII-write agent.
