# `dhis2w-mcp-bridge` — single-tool CLI bridge for local models

`dhis2w-mcp-bridge` is a separate FastMCP server that exposes the entire `dhis2` CLI as a
**single** MCP tool, `dhis2_cli`. Where [`dhis2w-mcp`](index.md) registers ~304 typed tools
(≈50-65k tokens of schema loaded into the model's context up front), this server registers
one tool that shells out to the local `dhis2` binary.

For *why* it's one tool instead of many — the design reasoning and how the approach is
validated — see [Bridge design: one tool, not many](../architecture/mcp-bridge.md). This page
is the usage guide.

## When to reach for it

!!! tip "Rule of thumb: local model -> bridge, cloud model -> full server"
    Use **`dhis2w-mcp-bridge`** (this server, one `dhis2_cli` tool) for **small on-box local
    models** (LM Studio, Ollama, llama.cpp). Use the full **[`dhis2w-mcp`](index.md)** server
    (~304 typed tools) for **any capable cloud/hosted model** — Claude, GPT, Gemini, and the
    hosts that drive them (Claude Code, Claude Desktop, Cursor) do their own tool selection and
    benefit from the typed per-tool schemas and typed errors. The bridge is a deliberate
    trade-off for models that can't afford ~53k tokens of schema or reliably pick among hundreds
    of tools; a cloud model gives that up for nothing.

Use the bridge for **small local models running on-box against sensitive data** (LM Studio,
Ollama, llama.cpp): the data cannot go to a hosted model, and a modest local model cannot
spare ~53k tokens for tool schemas or reliably choose among hundreds of tools. The bridge
gives it one tool, which it drives by progressive discovery:

```
dhis2_cli(["--help"])                                  # list command groups
dhis2_cli(["metadata", "--help"])                      # drill into a group
dhis2_cli(["metadata", "list", "dataElements",
           "--filter", "name:ilike:malaria"])          # run a command
```

Everything stays local — the server spawns the `dhis2` subprocess and never sends data
anywhere. Use the full [`dhis2w-mcp`](index.md) server instead for hosts that do their own
progressive tool disclosure (e.g. Claude Code handles all 304 tools comfortably).

!!! note "MCP-client support"
    The bridge is consumed over MCP. **LM Studio** has a native MCP client and uses it
    directly. **Ollama** and **llama.cpp** do not speak MCP — they need a small host-loop
    agent (system prompt + one `run_dhis2` tool) to drive the CLI.

## The tool

```
dhis2_cli(args: list[str], profile: str | None = None) -> CliResult
CliResult = { exit_code: int, stdout: str, stderr: str }
```

`--json` is injected automatically, so on success (`exit_code == 0`) `stdout` is JSON.
`--help`/`--version` exit 0 with human text. Any non-zero exit is a failure with the message
on `stderr` (never JSON). `profile` is injected as `-p <profile>`.

## Install

The bridge depends on `dhis2w-cli`, so installing it also provides the `dhis2` binary it shells
out to. Published on PyPI as [`dhis2w-mcp-bridge`](https://pypi.org/project/dhis2w-mcp-bridge/).

### Global user install — recommended

`uv tool install` puts the `dhis2w-mcp-bridge` binary on uv's tool `PATH`, so LM Studio (and any
host) can launch it by name without knowing where it lives:

```bash
uv tool install dhis2w-mcp-bridge
dhis2w-mcp-bridge --version
```

Update or remove later:

```bash
uv tool upgrade dhis2w-mcp-bridge                          # latest
uv tool install --reinstall dhis2w-mcp-bridge==<version>   # pin a specific version
uv tool uninstall dhis2w-mcp-bridge                        # remove
```

If it isn't on `PATH` afterwards, run `uv tool update-shell` once and restart your terminal.

### One-shot via `uvx` (no install)

```bash
uvx dhis2w-mcp-bridge
```

Each `uvx` run rebuilds a temporary environment, so it's slower than `uv tool install` — use it
to try a single session.

### From the workspace checkout (developing the bridge)

```bash
git clone git@github.com:winterop-com/dhis2w-utils.git
cd dhis2w-utils && make install
uv run dhis2w-mcp-bridge --version
```

## Wire into LM Studio

LM Studio reads MCP servers from `~/.lmstudio/mcp.json`. With a global install, point it at the
binary by name:

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "dhis2w-mcp-bridge",
      "env": { "DHIS2_PROFILE": "local_basic", "DHIS2_MCP_READONLY": "1" }
    }
  }
}
```

From a workspace checkout instead, launch it through `uv run`:

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "uv",
      "args": ["run", "--directory", "/ABS/PATH/TO/dhis2w-utils", "dhis2w-mcp-bridge"],
      "env": { "DHIS2_PROFILE": "local_basic", "DHIS2_MCP_READONLY": "1" }
    }
  }
}
```

Connection and profile resolution are identical to the CLI (see
[Profile selection](index.md#profile-selection)).

## Read-only mode

`DHIS2_MCP_READONLY=1` restricts the bridge to read commands (and `--help`); writes are
refused before any subprocess runs. It is **fail-closed**: the allowlist of read-only command
paths is generated by introspecting the Typer command tree and is verified against the live
tree by the test suite, so it cannot silently drift, and ambiguous verbs default to denied.
This is a convenience guard — the authoritative control is the DHIS2 authorities of the
profile's credentials, so use a read-scoped PAT/user for a hard guarantee.

## Environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `DHIS2_MCP_READONLY` | unset | Truthy (`1`/`true`/`yes`/`on`) restricts to read commands + `--help`; writes refused (exit 126). |
| `DHIS2_CLI_BIN` | auto | Path to the `dhis2` executable (auto-discovered next to the interpreter, then on `PATH`). |
| `DHIS2_MCP_CLI_TIMEOUT` | `120` | Per-command timeout in seconds (exit 124 on timeout). |

Bridge exit-code conventions: `124` timeout, `126` refused by read-only mode, `127` CLI not
found; otherwise the CLI's own code (`0` success/JSON, `1` domain error, `2` usage error).
