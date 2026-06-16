# AI agent testing

This toolkit is built to be **driven by AI agents** — the CLI, the MCP server, and the single-tool
[bridge](architecture/mcp-bridge.md) all exist so a model can operate a DHIS2 instance. This page is
how we verify that actually works, which models can do it, and what we learned. The detailed run
logs are linked at the bottom.

## Two questions

**1. Does every command work for an agent?** — answered deterministically, not by a model:

- A test renders `--help` for **all ~363 leaf commands** (exit 0). No broken or unregistered
  command. This is the structural 100% baseline (`packages/dhis2w-cli/tests/test_cli_surface.py::test_every_command_renders_help`).
- A **capable agent is the oracle**: Claude Code / Codex should form every command correctly. Any
  command a capable agent *can't* drive is a real CLI defect (bad help, undiscoverable) — not a model
  limitation. Composite write workflows (`make bench-composite`) are proven oracle-first.

**2. Which local models can drive it, and how well?** — measured as a gradient (small local models
will never be 100%). This is the privacy use case: a small model on-box, against data that can't
leave the machine, driving the bridge.

## The harnesses

All runnable from the `Makefile`; the model roster lives in `infra/scripts/bench_bridge_models.py`
(`ROSTER`). Reads run against `play42` (read-only); writes against `local_basic` (self-cleaning).

| Command | What it measures |
| --- | --- |
| `make bench-bridge` | The roster over **read + write + performance** — the primary capability benchmark. |
| `make bench-matrix` | A **command × model grid**: does each model find and form each CLI command. |
| `make bench-composite` | Multi-object **write workflows** (data set + elements, program + stages), oracle reference. |
| `make bench-round` | Drive one model through a read / write / benchmark round interactively. |

## Headline findings

- **Best local driver: `google/gemma-4-26b-a4b-qat`.** On read + write + performance it passes
  everything and is fast — the MoE (26B / 4B active) keeps 12b-class speed with more capability. The
  qat builds beat their bf16 siblings at equal correctness. The qwens are strong, fast *read-only*
  drivers — they stall on writes.
- **Writes are the ceiling.** A single hinted setting is easy for everyone. A **multi-object write**
  (a data set + 10 data elements, wired together) **defeats every local model** — the *attach* step
  (correlating many just-created UIDs) is the wall, and more turns don't help (it's a coherence
  limit, not a budget one). The capable-agent oracle does the same write 100%. That gap is the story:
  trivial for a capable agent, a wall for local models.
- **The command×model grid is a stress-test, not a leaderboard.** On the 1,230-cell `bench-matrix`,
  "found the right command" sits at ~10% for everyone, and the best driver (`26b-a4b-qat`) scored
  *near the bottom* — because the metric is "pick the exact command among ~200 siblings from a vague
  one-line goal", which is interpretation noise, not capability. Judge models with `bench-bridge`;
  read the grid as a discoverability stress-test of the help surface.

## Why this shapes the design

The findings drive the [bridge design](architecture/mcp-bridge.md): because a small model can't carry
~304 tool schemas or pick among hundreds of tools, the bridge gives it **one** tool and a
self-describing CLI to discover progressively — which is only as good as the help/errors, hence the
read-surface hardening (did-you-mean, `metadata type list`, `d2w schema <type>`, `--fields`
warnings). See [MCP servers — which one?](mcp/index.md#two-servers-which-one).

## Detailed logs

The full run records (working notes — raw data, per-round findings):

- [Model benchmark](notes/model-benchmark.md) — the roster, the read/write/perf table, the rankings.
- [Small-model bridge notes](notes/small-model-bridge.md) — the design log: read-surface hardening and Rounds 1-6 (incl. the multi-object write ceiling).
- [CLI command × model matrix](notes/cli-matrix.md) — the 1,230-cell discovery grid + the not-a-ranking caveat.
- [Bridge verification](notes/bridge-verification.md) — the earlier capable-agent + qwen benchmark (tool-call parse reliability).
