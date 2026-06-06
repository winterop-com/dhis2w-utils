# `dhis2w-mcp` MCP server

`dhis2w-mcp` is a [FastMCP](https://github.com/jlowin/fastmcp) server that exposes most `dhis2w-core` plugins as typed [Model Context Protocol](https://modelcontextprotocol.io/) tools. When launched by an MCP host (Claude Desktop, Claude Code, Cursor, Continue, Cline, or anything that speaks stdio MCP), it registers around 304 tools sharing the same typed service functions as the CLI and the Python client. A handful of CLI surfaces (`dhis2 dev` codegen + sample fixtures, `dhis2 browser` Playwright automation, profile mutations like `add` / `login` / `remove`) are intentionally CLI-only — see the [capability matrix](../index.md#capability-matrix) for the full list.

## When to reach for it

- Driving DHIS2 from an LLM agent — "create a program with these attributes, link these org units, push a sample row."
- Building agent-assisted operations on a live DHIS2 stack where every tool call surfaces a typed result and a typed error.
- Auditing what an agent is doing against DHIS2 — every tool call is logged with its arguments.

This full server is the right choice for **any capable cloud/hosted model** (Claude, GPT, Gemini) and the hosts that drive them — they select among the ~304 typed tools well and get a typed result + typed error on every call. For **small on-box local models** that can't spare the schema budget, reach for the single-tool bridge instead (see the tip below).

For direct CLI use, the [CLI surface](../cli/index.md) is what you want. For Python integration, the [Python client](../client/index.md).

!!! tip "Small local models: use the CLI bridge"
    Running a small, context-limited local model (LM Studio, Ollama, llama.cpp) — e.g. for sensitive data that must stay on-box? The ~304 typed tools here cost ≈50-65k tokens of context up front. The separate [`dhis2w-mcp-bridge`](bridge.md) server exposes the whole CLI as a single `dhis2_cli` tool the model discovers via `--help`, with an optional read-only guard.

## Install

Two install paths depending on whether you want the binary on your global `PATH` or pinned inside a project.

### Global user install — recommended for AI host integration

`uv tool install` puts the `dhis2w-mcp` binary into uv's tool bin directory (which lives on `PATH` after `uv tool update-shell`). Every MCP host on your laptop can launch it without knowing where it's installed.

```bash
uv tool install dhis2w-mcp
dhis2w-mcp --version
```

Update later:

```bash
uv tool upgrade dhis2w-mcp                 # latest
uv tool install --reinstall dhis2w-mcp==<version>   # pin a specific version
uv tool uninstall dhis2w-mcp               # remove
```

If `dhis2w-mcp` isn't on `PATH` after install, run `uv tool update-shell` once and restart your terminal.

### One-shot via `uvx` (no install)

To launch the server without persisting it on disk (good for trying a single agent session):

```bash
uvx dhis2w-mcp
```

Each `uvx` invocation re-creates a temporary environment, so it's slower than the `uv tool install` path. Use `uv tool install` for daily use.

### Local-to-a-project (pinning a specific version)

When you want the server pinned in a project's `uv.lock` (e.g. a dev tools project that wraps your DHIS2 agent flows):

```bash
uv add --dev dhis2w-mcp
uv run dhis2w-mcp --version
```

The host launches it as `uv run --directory /path/to/project dhis2w-mcp` (see the host-specific configs below).

### From the workspace checkout (developing dhis2w-mcp itself)

If you cloned `dhis2-utils` to hack on the server:

```bash
git clone git@github.com:winterop-com/dhis2w-utils.git
cd dhis2w-utils
make install                               # uv sync --all-packages
uv run dhis2w-mcp --version
```

Host configs point at `uv run --directory <repo-path> dhis2w-mcp`.

## Wiring it into an AI host

The same `dhis2w-mcp` binary plugs into every MCP-aware host. Pick yours below.

### Claude Desktop

Config file location:

| Platform | Path |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Open the file (create it if it doesn't exist) and add:

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "dhis2w-mcp"
    }
  }
}
```

Quit + reopen Claude Desktop. The MCP server tray shows a green dot next to "dhis2"; click it to see the 304+ tools the agent has access to.

To pass extra env vars (e.g. pin the plugin tree or active profile):

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "dhis2w-mcp",
      "env": {
        "DHIS2_VERSION": "43",
        "DHIS2_PROFILE": "staging"
      }
    }
  }
}
```

If you installed locally to a project, point the host at `uv run`:

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/you/dev/your-agent-project", "dhis2w-mcp"]
    }
  }
}
```

### Claude Code

`claude` (the CLI) reads MCP servers from `~/.claude.json` (per-user) or `.claude/mcp_servers.json` (per-project). The shape is the same as Claude Desktop:

```bash
claude mcp add dhis2 dhis2w-mcp
# or, manually:
cat >> ~/.claude.json <<'JSON'
{
  "mcpServers": {
    "dhis2": { "command": "dhis2w-mcp" }
  }
}
JSON
```

Restart the Claude Code session (`exit` + relaunch) to pick up the new server.

### Cursor

In Cursor settings -> MCP -> "Edit config", add the same JSON block as Claude Desktop. Cursor stores it at `~/.cursor/mcp.json`.

### Continue / Cline / generic stdio hosts

Any MCP host that supports stdio takes:

```
command: dhis2w-mcp
args:    []
env:     { ... optional ... }
```

Drop those into the host's MCP config UI / file. If the host wants the full path to the binary, `uv tool which dhis2w-mcp` prints it.

## Verifying the wiring

In the agent, ask:

> Call `system_server_info` and show me the result.

Example response (your version numbers will differ):

```json
{
  "active_plugin_tree": "v43",
  "active_plugin_tree_source": "default (no profile.version, no DHIS2_VERSION env)",
  "dhis2w_core_version": "0.10.0",
  "dhis2w_mcp_version": "0.10.0"
}
```

If the agent says it has zero MCP tools, the host hasn't loaded the server — check the MCP panel / log for the start-up error.

## Profile selection

The server picks its DHIS2 profile from the standard `dhis2w-core` resolution chain (first match wins):

1. An explicit `profile` kwarg on the MCP tool call (overrides everything below per call).
2. `DHIS2_PROFILE` env in the server process (set via the host's `env:` block — see the Claude Desktop example above).
3. Raw `DHIS2_URL` + (`DHIS2_PAT` or `DHIS2_USERNAME` + `DHIS2_PASSWORD`) env — PAT or Basic only; OAuth2 needs a saved profile.
4. Project-local `.dhis2/profiles.toml` `default` (walking up from `cwd`).
5. User-global `~/.config/dhis2/profiles.toml` `default`.

The per-call `profile: str | None` kwarg means one running MCP server can target multiple DHIS2 profiles (e.g. local + staging) without restart — **as long as they all share the same DHIS2 major** (v41 / v42 / v43). The plugin tree is bound once at server startup based on `DHIS2_VERSION` env or the startup profile's `version` field; the per-call profile only swaps the wire client.

Two layers enforce the boundary so silent `v42-parses-v43-payload` bugs aren't possible:

1. **Profile-level**: if the resolved profile's `.version` pins a different major than the bound tree, `resolve_profile()` raises `ProfileVersionMismatchError` before any wire call.
2. **Wire-level** (covers profiles without a `version` pin, which is the common case): the bound tree is threaded into the wire client as `Dhis2Client(version=...)`, so the on-connect `/api/system/info` check raises `VersionPinMismatchError` whenever the server's reported major doesn't match the bound tree.

To target a different major, restart the server with `DHIS2_VERSION=43 dhis2w-mcp` (see [Active plugin tree](#active-plugin-tree) below). Call `system_server_info` to confirm the bound tree before issuing version-sensitive tools.

## Active plugin tree

`dhis2w-mcp` selects a plugin tree (v41 / v42 / v43) at startup. Override per-launch with the `DHIS2_VERSION` env var:

```bash
DHIS2_VERSION=43 dhis2w-mcp
```

In a host config, set it under the `env:` block (see Claude Desktop example above). Call `system_server_info` from the agent to see which tree is bound + which `dhis2w-*` package versions are installed.

## Filesystem trust model

Several tools read and write **arbitrary local filesystem paths** the agent provides:

- `metadata_export(output_path=...)` writes a metadata bundle to disk (`packages/dhis2w-core/src/dhis2w_core/v{N}/plugins/metadata/mcp.py`).
- `metadata_diff(left_path=...)`, `metadata_diff_profiles(...)`, `metadata_merge_bundle(...)` read bundle files from disk.
- `customize_apply(theme_path=...)`, `apps_install_from_file(file_path=...)`, `files_documents_create_external(...)` accept local file paths for upload.
- `apps_snapshot(output_path=...)` writes a tarball of installed apps to disk.

The server runs with the **same filesystem permissions as the user that launched it** — there is no sandboxing of paths the agent supplies. This is acceptable for the intended deployment (a local stdio MCP server you launched yourself), but worth being explicit about:

- **Run `dhis2w-mcp` from a constrained working directory** when a less-trusted agent will drive it. The TOML profile resolver walks up from `cwd`, so launching from `~/dhis2-work/` keeps profile lookups scoped there too.
- **Avoid running the server as a privileged user.** Standard "least privilege" — the MCP process inherits the launching shell's UID + permissions.
- **Don't paste an `output_path` an agent suggested into a host config without reading it.** An agent that hallucinates `output_path="/etc/cron.daily/metadata-dump"` will happily try to write there if the user owns the file.
- **The MCP server only mutates DHIS2 server state through tools that already require auth.** The filesystem surface is purely local; agents can't reach beyond what `dhis2w-mcp`'s host user can already do.

If you need stricter isolation, run `dhis2w-mcp` inside a container or a `nsjail`-style sandbox that pins `cwd` and limits writeable paths.

## Where next

- [Tutorial](tutorial.md) — your first MCP tool call from an agent.
- [Reference](../mcp-reference.md) — auto-generated catalog of every tool + parameter schema.
- [Architecture](../architecture/mcp.md) — how the FastMCP server mounts plugins, return-shape conventions.
- [Examples index](../examples.md) — Python scripts driving the in-process MCP server end-to-end.
