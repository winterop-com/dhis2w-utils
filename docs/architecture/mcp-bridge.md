# MCP bridge — design rationale (one tool, not many)

`dhis2w-mcp-bridge` exposes the **entire `dhis2` CLI as a single MCP tool**, `dhis2_cli(args)`. This
is a deliberate inversion of the usual MCP shape, and the reasoning is worth writing down because
the pattern is unusual. For the *usage* (install, LM Studio wiring, read-only mode) see
[the bridge guide](../mcp/bridge.md); this page is the *why*.

## The problem with the default MCP shape

The conventional way to build an MCP server is **one typed tool per capability**. That is exactly what
the full [`dhis2w-mcp`](mcp.md) server does — it registers ~337 typed tools, one per CLI capability,
each with a JSON Schema for its parameters and return type. For a capable hosted model (Claude, GPT,
Gemini) that is the right design: the host streams all the schemas in, the model grounds on the typed
parameters, and every call comes back as a typed result or a typed error.

But the schemas are not free. ~337 tool definitions is **≈50-65k tokens of schema loaded into context
before the model has done anything**. And the model still has to *choose* the right tool out of
hundreds on every turn.

That is fine for a large cloud model. It is fatal for the use case the bridge targets: a **small
model running on-box** (LM Studio / Ollama / llama.cpp) **against data that cannot leave the
machine**. Such a model:

- cannot spare ~53k tokens of context just for tool schemas, and
- cannot reliably select the right tool among hundreds.

A privacy-sensitive DHIS2 instance can't send its data to a hosted model, so "just use a bigger
hosted model" is not available. The constraint is real, and the default MCP shape doesn't fit it.

## The pattern: one tool + a self-describing CLI + progressive discovery

The bridge registers **one** tool:

```
dhis2_cli(args: list[str], profile: str | None = None) -> CliResult
```

and the model discovers capability the way a human does at a terminal — by reading `--help` on demand:

```
dhis2_cli(["--help"])                         # what command groups exist?
dhis2_cli(["metadata", "--help"])             # drill into one
dhis2_cli(["metadata", "list", "--help"])     # a command's options
dhis2_cli(["metadata", "list", "dataElements", "--count"])   # run it
```

The CLI's own help text **is** the just-in-time documentation. The model pulls only the slice it needs,
when it needs it, instead of paying for every schema up front. Context cost drops from ~53k tokens to
roughly one tool definition plus whatever help the model chooses to read.

This works because we already invested in a genuinely good CLI — Typer sub-apps, one-line help on
every command and option, did-you-mean suggestions on typos, a `metadata type list` catalogue, and
a `dhis2 schema <type>` command that prints a type's fields. **The CLI is the API**; the bridge just
re-uses that surface as the model's affordance.

## Why this is a deliberate inversion (the "kinda new" part)

The conventional intuition is *more typed tools = more capability and better grounding*. For a
token- and selection-constrained model the opposite holds: **fewer tools + progressive discovery
wins**. The model's "which of 337 tools?" problem becomes a navigable "drill into `--help`" problem
it can solve incrementally, exactly like a person exploring an unfamiliar CLI.

Giving an agent a shell or a CLI is not itself new. What is deliberate here is packaging
*single-tool + progressive-discovery* as an **MCP server specifically for token-constrained local
models**, paired with:

- a **read-only mode** (`DHIS2_MCP_READONLY=1`) with a fail-closed, drift-tested allowlist, and
- **DHIS2-specific read-surface hardening** so a small model can actually succeed (see below).

The honest trade-off: you give up up-front per-tool schema validation. The bridge's correctness then
depends on the CLI's help and error text being good enough to *guide* a model — so the help surface
becomes load-bearing, not cosmetic. That is why a large share of the work has gone into the read
surface, not the bridge plumbing:

- bridge docstring rewritten for 3-4B models (output contract, top reads first, filter grammar),
- `metadata type list` emits the exact camelCase resource names,
- unknown-resource and unknown-`--fields` errors say *did you mean ...*,
- `dhis2 schema <type>` lets a model learn a type's fields (and enum values) instead of guessing,
- mutating verbs are reachable only with `READONLY` unset.

## Local vs cloud — which server

| | small **local** model (on-box, sensitive data) | capable **cloud** model |
| --- | --- | --- |
| Server | `dhis2w-mcp-bridge` (one tool) | `dhis2w-mcp` (~337 typed tools) |
| Why | can't afford schema tokens; can't pick among hundreds | does its own tool selection; benefits from typed schemas + errors |

Rule of thumb: **local model → bridge, cloud model → full server.** See the
[bridge guide](../mcp/bridge.md#when-to-reach-for-it) for the full decision.

## Safety and locality

- **Nothing leaves the machine.** The bridge spawns the local `dhis2` subprocess and returns its
  output; no data is sent anywhere.
- **Read-only mode is fail-closed.** The allowlist of read command paths is introspected from the
  Typer tree and verified by a drift test, so it can't silently drift; ambiguous verbs default to
  denied. It is a convenience guard — the authoritative control is still the DHIS2 authorities of the
  profile's credentials.

## How we know it works

The single-tool pattern is only as good as the model's ability to drive the CLI, so the approach is
backed by a deliberate test apparatus (all runnable from the `Makefile`):

- **Deterministic structural guard** — a test renders `--help` for every one of the ~363 leaf
  commands (exit 0). No broken or unregistered command. This is the 100% baseline.
- **Capable-agent oracle** — a capable agent (Claude Code / Codex) should form every command
  correctly; any command it *can't* is a real CLI defect (bad help, undiscoverable), not a model
  limitation. Composite write workflows (`make composite-scenarios`) are proven oracle-first.
- **Local-model gradient** — the models will never be 100%; we measure where they land:
  - `make bridge-bench` — the model roster over read + write + performance.
  - `make cli-matrix` — a command x model matrix: does each model find and form each command.
  - `make bridge-round` — drive one model through a round interactively.

Methodology, the tracked model roster, and latest results live in
[the model benchmark](../notes/model-benchmark.md); the running design log is in
[the small-model bridge notes](../notes/small-model-bridge.md).
