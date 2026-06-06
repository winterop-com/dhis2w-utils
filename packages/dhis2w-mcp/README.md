# dhis2w-mcp

FastMCP server that exposes every `dhis2w-core` plugin as MCP tools. Same service functions as the CLI; different I/O shape.

A connected agent (Claude Desktop, Claude Code, Cursor, …) sees roughly 304 typed tools grouped by plugin: `metadata_*`, `data_aggregate_*`, `data_tracker_*`, `analytics_*`, `route_*`, `user_*`, `apps_*`, `system_*`, `messaging_*`, `files_*`, `maintenance_*`, `customize_*`, `profile_*`, `doctor_*`. Counts age with each release; the auto-regenerated `docs/mcp-reference.md` is the source of truth.

## Install

### From PyPI (recommended)

```bash
# As a global tool — drops `dhis2w-mcp` on $PATH (one-time fetch, instant launches)
uv tool install dhis2w-mcp

# Update to the latest release
uv tool upgrade dhis2w-mcp

# Force re-install (after PyPI publish issues / cache weirdness)
uv tool install --reinstall dhis2w-mcp

# Remove
uv tool uninstall dhis2w-mcp

# Or run on demand without installing — fetches into the uv cache on first run
uvx dhis2w-mcp

# Force a refresh (pulls latest published version, bypasses cache)
uvx --refresh dhis2w-mcp
```

The PyPI distribution name and the binary name match (`dhis2w-mcp` for both), so unlike `dhis2w-cli` (whose binary is `dhis2`), no `--from` dance is needed.

### From a workspace checkout (for active development)

```bash
git clone git@github.com:winterop-com/dhis2w-utils.git
cd dhis2w-utils
uv sync --all-packages
```

This puts `dhis2w-mcp` on the workspace venv's path. `uv run dhis2w-mcp` from anywhere inside the repo speaks MCP over stdio.

## Configure your MCP client

The server speaks MCP over stdio and reads its DHIS2 connection from either a profile (the workspace's `.dhis2/profiles.toml` / `~/.config/dhis2/profiles.toml`) or environment variables (`DHIS2_URL` + auth — `DHIS2_PASSWORD`, `DHIS2_PAT`, or OAuth2). Pick whichever fits your client.

### Claude Desktop

Edit your config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "uvx",
      "args": ["dhis2w-mcp"],
      "env": {
        "DHIS2_URL": "https://play.im.dhis2.org/dev-2-43",
        "DHIS2_USERNAME": "admin",
        "DHIS2_PASSWORD": "district"
      }
    }
  }
}
```

For PAT auth, swap the username/password env vars for `"DHIS2_PAT": "d2p_..."`. Restart Claude Desktop after editing.

### Claude Code

`claude mcp add` registers the server with the Claude Code CLI. Three options depending on how you installed it:

```bash
# Option 1 — uvx (no install, fetches from PyPI on each run)
claude mcp add dhis2 -s user \
  -e DHIS2_URL=https://play.im.dhis2.org/dev-2-43 \
  -e DHIS2_USERNAME=admin \
  -e DHIS2_PASSWORD=district \
  -- uvx dhis2w-mcp

# Option 2 — installed via `uv tool install dhis2w-mcp`
claude mcp add dhis2 -s user \
  -e DHIS2_URL=https://play.im.dhis2.org/dev-2-43 \
  -e DHIS2_PAT=d2p_... \
  -- dhis2w-mcp

# Option 3 — workspace checkout (recommended for active development)
claude mcp add dhis2 -s user \
  -- uv run --directory /absolute/path/to/dhis2w-utils dhis2w-mcp
```

`-s user` makes the server available across every Claude Code project; drop it for project-only. Verify:

```bash
claude mcp list           # confirm 'dhis2' shows up
claude mcp get dhis2      # see the resolved command + env
```

Inside a Claude Code session the tools land as `mcp__dhis2__system_whoami`, `mcp__dhis2__metadata_data_element_list`, etc. The `mcp__dhis2__` prefix is added by Claude Code; the part after is the bare tool name registered by FastMCP.

### Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "uvx",
      "args": ["dhis2w-mcp"],
      "env": {
        "DHIS2_URL": "https://play.im.dhis2.org/dev-2-43",
        "DHIS2_USERNAME": "admin",
        "DHIS2_PASSWORD": "district"
      }
    }
  }
}
```

Reload Cursor after editing.

### Generic stdio client

Any MCP host that speaks the stdio transport can launch `dhis2w-mcp`. The server runs the standard MCP handshake on stdin/stdout, so the host config just needs:

- `command`: `uvx` (or `dhis2w-mcp` if installed via `uv tool install`)
- `args`: `["dhis2w-mcp"]` (omit for the installed-tool form)
- `env`: DHIS2 connection vars (see below)

## Authentication

Three patterns, in order of preference for production:

### 1. Profile (the workspace flavour)

If your config has a `.dhis2/profiles.toml` (created by `dhis2 profile bootstrap` or `dhis2 profile add`), the server auto-discovers it. Pin one for the agent with `DHIS2_PROFILE`:

```json
"env": { "DHIS2_PROFILE": "prod" }
```

### 2. Direct env vars (Basic / PAT)

```json
"env": {
  "DHIS2_URL": "https://dhis2.example.org",
  "DHIS2_USERNAME": "agent-bot",
  "DHIS2_PASSWORD": "..."
}
```

…or PAT (preferred over basic — narrower scope, revocable):

```json
"env": {
  "DHIS2_URL": "https://dhis2.example.org",
  "DHIS2_PAT": "d2p_..."
}
```

### 3. OAuth2 / OIDC

Configure the OAuth2 client in a named profile (`dhis2 profile add ... --auth oauth2`), run `dhis2 profile login <name>` once to seed the token, then point the MCP server at that profile via `DHIS2_PROFILE`. The server uses the cached refresh token; the agent never sees a credential.

If the server starts without a usable profile **and** without env-var auth, every tool call fails with an actionable error pointing at `dhis2 profile bootstrap`.

## Tool naming

All tools follow `<plugin>_<resource>_<verb>` in snake_case, verb-last:

```
metadata_data_element_list
metadata_data_element_get
metadata_data_element_create
user_role_authority_list
system_calendar_get
system_calendar_set
data_aggregate_push
```

See `docs/architecture/conventions.md` for the full verb table (list, get, create, delete, rename, update, patch, set, add_<thing>, remove_<thing>) and `docs/mcp-reference.md` for every tool with its parameter schema.

## Picking up code changes (workspace checkout only)

`uv run --directory ...` runs `uv sync` before launching the script (a fast no-op when nothing changed) and installs workspace packages in editable mode, so Python imports source files directly from `packages/dhis2w-core/src/...`. There is no rebuild step:

| What you changed | What you have to do |
| --- | --- |
| Source code in `packages/*/src/...` (existing tools, new tools, new plugins, fixed bugs) | **Restart the MCP server** — end the Claude Code session and start a new one, or `/mcp` to reconnect. The new code is picked up automatically; `discover_plugins()` re-walks `dhis2w_core.v{41,42,43}.plugins.*` on each server start. |
| Added a new runtime dep (`uv add ...` from the repo root) | Nothing special. The lock file changes; next `uv run` re-syncs the venv before launching. |
| Moved the repo, changed the profile env var, or want to switch between configurations | **Re-run `claude mcp add`** (after `claude mcp remove dhis2`) — the invocation itself has to be re-recorded. |

The server is a long-lived process. Edits made while it's running are not visible until it restarts. For PyPI-installed users (`uv tool install dhis2w-mcp`), changes ship via `uv tool upgrade dhis2w-mcp`.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Agent reports no DHIS2 tools | MCP host didn't pick up the server | Reload host config; check `claude mcp list` / `cursor mcp logs` |
| Tools listed but every call fails with "no profile" | Server can't find a profile or env-var auth | Add `DHIS2_URL` + `DHIS2_PASSWORD` (or `DHIS2_PAT`) to the `env` block, or set `DHIS2_PROFILE` to a profile that exists |
| Connection works locally but fails for the agent | Working directory mismatch — `.dhis2/profiles.toml` lookup is CWD-relative | Pin `DHIS2_PROFILE` explicitly, or use `~/.config/dhis2/profiles.toml` (user-wide) |
| 401 Unauthorized on every call | Stale OAuth2 token | Re-run `dhis2 profile login <name>` to refresh; the cached `tokens.sqlite` updates in place |
| `uvx dhis2w-mcp` cold-starts slowly | First fetch from PyPI on each run | Switch to `uv tool install dhis2w-mcp` (one-time fetch, instant subsequent launches) |

## Architecture

`dhis2w-mcp` is a thin shell — it builds a `FastMCP` instance, walks every `dhis2w_core.v{41,42,43}.plugins.*` module, and calls each plugin's `register_mcp(server)`. Tool names, descriptions, and parameter schemas are derived from the registered Python function signatures + docstrings; return-type JSON schemas come from the annotated pydantic models. See `docs/architecture/mcp.md` for the deeper write-up.
