# dhis2w

[![CI](https://github.com/winterop-com/dhis2w-utils/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/winterop-com/dhis2w-utils/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dhis2w-cli?color=2C6693&label=PyPI)](https://pypi.org/project/dhis2w-cli/)
[![Python](https://img.shields.io/pypi/pyversions/dhis2w-client?color=3776AB)](https://pypi.org/project/dhis2w-client/)
[![DHIS2](https://img.shields.io/badge/DHIS2-41%20%7C%2042%20%7C%2043-2C6693)](https://winterop-com.github.io/dhis2w-utils/architecture/versioning/)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey)](LICENSE)

A Python toolkit for DHIS2 — pure client library, CLI, MCP server, Playwright browser automation, and a shared plugin runtime, all in one `uv` workspace. Targets DHIS2 v41, v42, and v43.

The repo lives at `winterop-com/dhis2w-utils`; PyPI ships the ten publishable members under the `dhis2w-*` prefix. Not affiliated with DHIS2.

> **Learning path · step 1 of 8** — You are here. Quick install + profile + first CLI / Python call below. Next: the [contributor walkthrough](docs/walkthrough.md) for the local docker stack, or jump to a surface-specific tutorial — [CLI](docs/guides/cli-tutorial.md), [Python](docs/guides/client-tutorial.md), [MCP](docs/mcp/tutorial.md).

## Why this toolkit?

DHIS2 already has a lightweight, official Python client that returns plain JSON dictionaries — ideal when you want a thin wrapper and a few lines in a notebook. `dhis2w` is built for a different need: a typed, multi-surface toolkit you can depend on across instances and versions.

- **Typed, not stringly-typed.** Every response is a Pydantic model generated from DHIS2's own OpenAPI spec, so your editor autocompletes fields and the type checker catches a misspelled key before you run. No guessing dictionary keys against the docs.
- **One core, four surfaces.** The same typed client powers a Python library, a `d2w` CLI, an MCP server, and Playwright browser automation — all sharing one `service.py` per domain, so behaviour never drifts between them.
- **Built for AI agents.** The MCP server exposes ~304 typed tools, one per CLI command, so any MCP host (Claude, Cursor) can drive a DHIS2 instance directly.
- **Version-aware by design.** Detects v41 / v42 / v43 on connect and binds the matching hand-written tree, so one codebase works across instances instead of branching on the wire shape yourself.
- **Real auth.** Basic, PAT, and OAuth2/OIDC with PKCE, behind a pluggable `AuthProvider` protocol, with a profile system for juggling multiple instances.
- **Production posture.** Strict ruff + mypy + pyright, ~1,150 tests, an mkdocs-material site, and runnable examples for every supported version.

Reach for the official client when you want the smallest possible dependency and raw JSON. Reach for `dhis2w` when you want types, a CLI, agent tooling, and version coverage in one place. Note that `dhis2w` is third-party.

## Workspace members

| Package | PyPI | Purpose |
| --- | --- | --- |
| [`dhis2w-client`](https://pypi.org/project/dhis2w-client/) | `uv add dhis2w-client` | Pure async httpx + pydantic DHIS2 client with pluggable auth (Basic, PAT, OAuth2/OIDC). Typed models from both `/api/schemas` and `/api/openapi.json` codegen. |
| [`dhis2w-core`](https://pypi.org/project/dhis2w-core/) | `uv add dhis2w-core` | Shared runtime: profile discovery, plugin registry, auth factory, token store, first-party plugins. |
| [`dhis2w-cli`](https://pypi.org/project/dhis2w-cli/) | `uv tool install dhis2w-cli` | Typer console script `d2w`. |
| [`dhis2w-mcp`](https://pypi.org/project/dhis2w-mcp/) | `uv tool install dhis2w-mcp` | FastMCP server `dhis2w-mcp`. |
| [`dhis2w-mcp-bridge`](https://pypi.org/project/dhis2w-mcp-bridge/) | `uv tool install dhis2w-mcp-bridge` | FastMCP server `dhis2w-mcp-bridge` — exposes the whole `d2w` CLI as a single `dhis2_cli` tool for small local models. |
| [`dhis2w-browser`](https://pypi.org/project/dhis2w-browser/) | `uv add dhis2w-browser` | Playwright helpers for DHIS2 UI automation — PAT minting, Playwright-driven OIDC login + consent, dashboard / viz / map screenshot capture. Mounted under `d2w browser` when the `[browser]` extra is installed on `dhis2w-cli`. |
| [`dhis2w-ql`](https://pypi.org/project/dhis2w-ql/) | `uv add dhis2w-ql` | The d2ql query + transform language: tokenizer, parser, evaluator, planner. Pure engine with a FHIRPath-compatible expression core — no DHIS2 runtime dependency. Powers `d2w query`. |
| [`dhis2w-fhir`](https://pypi.org/project/dhis2w-fhir/) | `uv add dhis2w-fhir` | FHIR IG generation: `init` scaffolds a SUSHI project as a uv project with a pinned toolchain and `init --refresh` brings an existing project's scaffold-managed files up to date without dropping an edit; `generate foundation / option-sets / categories / questionnaires / examples / org-units / pages / all` emits FSH, pre-built R4 JSON, and narrative from DHIS2 metadata, including the capture contract (QuestionnaireResponse profiles + a D2CaptureServer CapabilityStatement); `validate` checks an instance's codes for FHIR-safety with md/csv/pdf reports; `generate load-set` writes a synthetic QuestionnaireResponse corpus; `doctor` runs the whole chain against an instance in a throwaway workspace and reports what it breaks; `serve` runs the IG as a FHIR read + capture facade (through `dhis2w-fhir-serve`); `forward` drains the capture spool back into DHIS2, dry run by default. Mounts `d2w fhir` via the plugin entry point. |
| [`dhis2w-fhir-serve`](https://pypi.org/project/dhis2w-fhir-serve/) | `uv add dhis2w-fhir-serve` | The FHIR facade behind `d2w fhir serve`: a FastAPI app that serves one generated IG's resources (compiled off disk, or built live off a DHIS2 instance at startup), publishes the instance's tracked entities as a register, answers `$translate` over the ConceptMaps, and receives `QuestionnaireResponse` captures, storing each as a receipt. `--ui` mounts a browser capture UI at `/`. Installed with the `[serve]` extra on `dhis2w-cli`. |
| `dhis2w-codegen` | _workspace-only_ | Generator that emits pydantic models + `StrEnum`s + CRUD accessors into `dhis2w_client.generated.v{N}/`. Two source-of-truth paths: `/api/schemas` for metadata resources, `/api/openapi.json` for instance-side shapes (tracker writes, envelopes, auth schemes). |
| `dhis2w-bench` | _workspace-only_ | Local-LLM benchmark harness for DHIS2 agents: coding, mcp-bridge, and full-mcp suites. |
| [`dhis2w-mcp-router`](https://pypi.org/project/dhis2w-mcp-router/) | `uv tool install dhis2w-mcp-router` | Domain-neutral MCP router — fronts many upstream MCP servers behind two meta-tools (search + dispatch) so an agent gets lazy, searchable tool discovery instead of a huge up-front tool payload. |

All ten publishable packages release together (lockstep versioning); see [`docs/releasing.md`](docs/releasing.md).

## Install

### Use the CLI

The CLI command is named **`d2w`** but the PyPI distribution is **`dhis2w-cli`** — that's why every install command spells out the package name explicitly.

```bash
# Install once, run forever — drops `d2w` on $PATH
uv tool install dhis2w-cli

# With Playwright UI automation (browser screenshots, OIDC login, PAT minting)
uv tool install 'dhis2w-cli[browser]'
playwright install chromium    # one-time, after the install above

# With the full-screen d2ql REPL (textual TUI behind `d2w query repl`)
uv tool install 'dhis2w-cli[tui]'

# Update to the latest release
uv tool upgrade dhis2w-cli

# Force a re-install (handy after PyPI publish issues / cache problems)
uv tool install --reinstall dhis2w-cli

# Check what's installed
uv tool list

# Remove
uv tool uninstall dhis2w-cli
```

After `uv tool install dhis2w-cli`, run the CLI directly:

```bash
d2w --help
d2w --version  # also: -V — shows package version + active plugin tree
d2w system info --url https://play.im.dhis2.org/dev-2-43 --username admin --password district
```

`d2w --version` surfaces which plugin tree (`v41` / `v42` / `v43`) the CLI booted with and where that came from in the resolution chain (`profile.version` → `DHIS2_VERSION` env → default `v42`). Helps debug "which DHIS2 major is this CLI talking to" without reading the profile by hand.

#### One-shot runs without installing — `uvx`

`uvx` is uv's "run-and-forget" runner — it fetches the package into a cache and runs the binary, with no permanent install:

```bash
# uvx <command>           # works when the binary name == the package name
# uvx --from <pkg> <cmd>  # required when they differ — that's our case

uvx --from dhis2w-cli d2w --help
uvx --from dhis2w-cli d2w system info --url https://play.im.dhis2.org/dev-2-43 --username admin --password district

# With the browser extra
uvx --from 'dhis2w-cli[browser]' d2w browser pat --url ...

# Force a cache refresh — pulls the latest published version
uvx --refresh --from dhis2w-cli d2w --help
```

`uv tool install` keeps the install in its own dedicated venv (separate from any project venv), so the `d2w` binary on your `$PATH` can't be perturbed by a `uv sync` somewhere else.

### Use the client library in your own project

```bash
# Inside a uv-managed project
uv add dhis2w-client
```

```python
from dhis2w_client import BasicAuth, Dhis2Client

async with Dhis2Client(
    base_url="https://play.im.dhis2.org/dev-2-43",
    auth=BasicAuth(username="admin", password="district"),
) as client:
    me = await client.system.me()
    print(me.username)
```

`dhis2w-client` is standalone — no dependency on `dhis2w-core` or the profile system. PyPI users who want the typed async client + generated metadata models stop here.

### Use the MCP server

`dhis2w-mcp` exposes ~304 typed tools (one per CLI command) over the MCP stdio transport when connected to a DHIS2 v42 instance; v43 adds a handful more for the v43-only schema fields. Connect any MCP host — Claude Desktop, Claude Code, Cursor, or anything that speaks stdio MCP.

The PyPI distribution name **is** the binary name here (`dhis2w-mcp`), so the `--from` dance isn't needed:

```bash
# Install once — drops `dhis2w-mcp` on $PATH
uv tool install dhis2w-mcp

# Update later
uv tool upgrade dhis2w-mcp

# Or run on demand without installing
uvx dhis2w-mcp

# Force a fresh fetch (after a new PyPI release)
uvx --refresh dhis2w-mcp
```

**Claude Desktop** — edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

Restart Claude Desktop. PAT auth works the same way — replace the username/password pair with `"DHIS2_PAT": "d2p_..."`.

**Claude Code** — register from any shell:

```bash
claude mcp add d2w -s user \
  -e DHIS2_URL=https://play.im.dhis2.org/dev-2-43 \
  -e DHIS2_PAT=d2p_... \
  -- uvx dhis2w-mcp
```

`-s user` makes the server available across every project. Tools land in-session as `mcp__dhis2__system_whoami`, `mcp__dhis2__metadata_data_element_list`, etc.

**Cursor** — edit `~/.cursor/mcp.json` with the same JSON shape as Claude Desktop and reload.

The full per-client setup, profile-based auth (`.dhis2/profiles.toml` for OAuth2 / OIDC), tool-naming convention, and troubleshooting are in [`packages/dhis2w-mcp/README.md`](packages/dhis2w-mcp/README.md).

### Use the MCP bridge (small local models)

For a **small model running on-box** (LM Studio / Ollama / llama.cpp) against data that can't leave the machine, `dhis2w-mcp-bridge` exposes the whole CLI as a **single** tool, `dhis2_cli`, that the model drives by progressive discovery — ~one tool schema instead of ~304. (Why one tool, not many: [Bridge design](docs/architecture/mcp-bridge.md). Use the full `dhis2w-mcp` server above for capable cloud models.)

```bash
uv tool install dhis2w-mcp-bridge          # or run on demand: uvx dhis2w-mcp-bridge
```

**LM Studio** (native MCP client) — `~/.lmstudio/mcp.json`:

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

The model then drives the CLI like a terminal, pulling help on demand:

```
dhis2_cli(["--help"])                                        # discover command groups
dhis2_cli(["metadata", "list", "dataElements", "--count"])   # {"resource":"dataElements","total":1037}
dhis2_cli(["schema", "dataElement"])                         # the type's fields (+ enum values)
```

`--json` is injected automatically; `DHIS2_MCP_READONLY=1` refuses writes (fail-closed). Full usage + read-only details: [the bridge guide](docs/mcp/bridge.md).

### Use the profile layer (env / TOML config)

The `dhis2w-cli` and `dhis2w-mcp` packages share a profile system that walks `DHIS2_PROFILE` env → `./.dhis2/profiles.toml` → `~/.config/dhis2/profiles.toml`:

```bash
# One-shot bootstrap: prompts for URL + auth, saves a profile
d2w profile bootstrap mywork

# List what's known
d2w profile list

# Switch the default
d2w profile default mywork
```

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    me = await client.system.me()
    print(me.username)
```

PyPI consumers who want the library without the profile layer can construct `Dhis2Client(url, auth=BasicAuth(...))` directly — see `examples/v42/client/library_only_auth.py`.

## CLI surface

Nineteen top-level domains; every plugin shares a `service.py` between the CLI and MCP sides so one typed call answers both surfaces.

| Command | What it covers |
| --- | --- |
| `d2w profile` | Manage DHIS2 profiles (Basic / PAT / OAuth2) + the default precedence chain |
| `d2w system` | `/api/system/info`, `/api/me`, minted UIDs |
| `d2w metadata` | List / get / export / import any metadata resource, with DHIS2's full filter + fields selector |
| `d2w data` | Aggregate data values + tracker reads + pushes |
| `d2w analytics` | Aggregated, event, enrollment, outlier-detection, and tracked-entity analytics + table rebuild |
| `d2w user` | List / get / me / invite / reinvite / reset-password |
| `d2w user-group` / `d2w user-role` | Membership + authority administration |
| `d2w route` | Integration routes (`/api/routes`) — register, run, inspect |
| `d2w maintenance` | Background tasks, cache clear, data-integrity, soft-delete cleanup, validation-rule runs, predictor runs, analytics-table refresh |
| `d2w files` | `/api/documents` + `/api/fileResources` — upload / download / list binary attachments |
| `d2w messaging` | `/api/messageConversations` — send, reply, list, mark read/unread |
| `d2w apps` | `/api/apps` + `/api/appHub` — install / uninstall / update installed apps, browse the App Hub catalog, point DHIS2 at a custom App Hub |
| `d2w query` | Run d2ql queries against the instance — one-shot or in the interactive REPL |
| `d2w fhir` | FHIR IG generation (via `dhis2w-fhir`) — scaffold a SUSHI project as a pinned uv project (`fhir init`, with `--refresh` to bring an existing project's scaffold up to date), generate the whole IG in one run (`fhir generate`) or one target at a time (`fhir generate foundation / option-sets / categories / questionnaires / examples / org-units / pages`) covering identifier systems, the nineteen D2 extensions, the capture contract, option-set / category / attribute-option-combo terminology and the tracked-entity-type map, forms with example responses, the organisation-unit registry carrying each unit's DHIS2 attribute values, and the narrative pages, check codes for FHIR-safety with md/csv/pdf reports (`fhir validate`), run the whole chain against an instance for one verdict (`fhir doctor`), write a synthetic load set (`fhir generate load-set`), serve the compiled or live IG as a FHIR read + capture facade with an optional browser capture UI (`fhir serve`, via the `[serve]` extra), and drain captures back into DHIS2 (`fhir forward`) |
| `d2w doctor` | One-command preflight — ~100 metadata-health + integrity checks against a live instance |
| `d2w browser` | Playwright-driven UI automation (PAT minting, dashboard / viz / map screenshot capture, automated OIDC login) — only registers when the `[browser]` extra is installed |
| `d2w dev` | Codegen, UID gen, PAT / OAuth2 seed helpers, branding (`dev customize`), sample data |

Full per-command reference: `d2w --help` (or `uvx --from dhis2w-cli d2w --help` — the package is `dhis2w-cli` but the binary is `d2w`, so `uvx --from` is required).

## Query with d2ql

**d2ql** is the toolkit's query + transform language: one readable pipeline instead of endpoint-specific `filter=` / analytics / tracker parameters, with pushdown to DHIS2 where the server can express the work:

```bash
d2w query eval 'dataElements | where domainType = "AGGREGATE" and name like "ANC" | select id, name | limit 10'

# Interactive REPL — full-screen TUI with the [tui] extra, plain line mode without
d2w query repl
```

The engine lives in the standalone [`dhis2w-ql`](packages/dhis2w-ql/) package (FHIRPath-compatible expression core, no DHIS2 runtime dependency) and backs the CLI, the MCP `query_*` tools, and the Python API. Start at the [query-language docs](docs/query/index.md); the full stage/source/sink reference is [`docs/guides/d2ql.md`](docs/guides/d2ql.md).

## Working on the workspace itself

```bash
git clone git@github.com:winterop-com/dhis2w-utils.git
cd dhis2w-utils

make install      # sync workspace deps (uv sync --all-packages --all-extras)
make lint         # ruff + mypy + pyright
make test         # pytest across all members
make docs-serve   # local mkdocs-material

# Bring up a fully-seeded DHIS2 v43 on :8080 (Flyway-bootstraps; v42 still has a seeded e2e dump)
make dhis2-run

# Refresh codegen against the public play instances (no docker needed)
make dhis2-codegen-play
```

## Connecting to a DHIS2 instance

See [`docs/guides/connecting-to-dhis2.md`](docs/guides/connecting-to-dhis2.md) for the full end-to-end walkthrough covering Basic, PAT, and OAuth2/OIDC — including the `dhis.conf` keys the OAuth2 path needs on the DHIS2 server, manual OAuth2 client registration without the seed script, the `openId` user field, and a troubleshooting matrix of every failure mode.

## Documentation + examples

- Architecture + plugin walkthroughs: `docs/architecture/`
- API reference (mkdocstrings-rendered): `docs/api/`
- Releasing: [`docs/releasing.md`](docs/releasing.md)
- Roadmap: [`docs/roadmap.md`](docs/roadmap.md)
- Upstream DHIS2 quirks we've tripped over: [`BUGS.md`](BUGS.md)
- Runnable examples: three trees (`examples/v41/`, `examples/v42/`, `examples/v43/`), each with `cli/`, `client/`, and `mcp/` subfolders. `examples/v43/client/` carries seven divergence-focused examples that exist only on v43 (`removed_resources.py`, `section_user_removed.py`, `category_combo_coc_regen.py`, `event_visualization_fix_headers.py`, etc.) — see [`docs/architecture/schema-diff-v41-v42-v43.md`](docs/architecture/schema-diff-v41-v42-v43.md) for the underlying schema drift. `examples/v41/client/` carries v41-only quirks (`oauth2_cid_field.py`, `grid_rows_wire_shape.py`, `apps_display_name.py`).

Hard requirements, conventions, and the plugin / auth / workspace model are documented in `CLAUDE.md` and the `docs/` site.
