---
title: Feature catalog
---

# Feature catalog

A complete Python toolkit for DHIS2 v41, v42, and v43 -- async client library,
CLI, MCP servers, browser automation, and codegen, organized as a `uv` workspace
with six publishable packages and one internal generator.

!!! note "Scope of this page"
    This is the user-facing capability inventory across all surfaces. The exact
    command and tool counts are regenerated per release; the auto-built
    [CLI reference](../cli-reference.md) and [MCP tool reference](../mcp-reference.md)
    are the source of truth when a number here drifts. For where the project is
    heading, see the [Roadmap](../roadmap.md) and the
    [security scanner plan](planning/security-scanner.md).

---

## Table of Contents

- [Client Library (dhis2w-client)](#client-library)
- [Plugin Runtime (dhis2w-core)](#plugin-runtime)
- [Command-Line Interface (dhis2w-cli)](#command-line-interface)
- [MCP Server (dhis2w-mcp)](#mcp-server)
- [MCP CLI Bridge (dhis2w-mcp-bridge)](#mcp-cli-bridge)
- [Browser Automation (dhis2w-browser)](#browser-automation)
- [Code Generator (dhis2w-codegen)](#code-generator)
- [Cross-Cutting Capabilities](#cross-cutting-capabilities)

---

## Client Library

**Package:** `dhis2w-client` | **Install:** `uv add dhis2w-client`

Pure async httpx + pydantic DHIS2 API client. Zero dependency on the plugin
runtime -- drop it into any async Python project.

### Authentication Providers

| Provider | Mechanism | Token Storage |
| --- | --- | --- |
| **Basic** | HTTP Basic (username/password, Base64) | None |
| **PAT** | Personal Access Token (`ApiToken` header) | None |
| **OAuth2/OIDC** | Authorization-code flow with PKCE against `/oauth2/authorize` and `/oauth2/token` | SQLite (`tokens.sqlite`) with auto-refresh |

All three implement the `AuthProvider` protocol. Custom providers (service-account
JWT, OIDC federation, proxy-injected headers) can be added by implementing the
same protocol without touching the client.

### Generated Type System

Two codegen pipelines feed typed models into the client:

- **`/api/schemas`** -- pydantic models + `StrEnum`s for every metadata resource
  (DataElement, Indicator, Program, OrgUnit, ...)
- **`/api/openapi.json`** -- instance-side shapes (tracker write payloads,
  response envelopes, auth scheme discriminators)

Each DHIS2 version (v41, v42, v43) has its own generated tree under
`dhis2w_client.generated.v{N}/`.

### Resource Accessors

Auto-generated typed CRUD for every metadata resource:

```python
elements = await client.resources.data_elements.list(filter="name:ilike:malaria")
element  = await client.resources.data_elements.get(uid)
await client.resources.data_elements.create(payload)
await client.resources.data_elements.patch(uid, operations)
await client.resources.data_elements.delete(uid)
```

### Domain APIs

| Domain | Methods |
| --- | --- |
| **System** | `me()`, `info()`, `calendar()`, `generate_uids()` |
| **Tracker** | `tracked_entities()`, `enrollments()`, `events()`, `relationships()`, `register()`, `enroll()`, `create_event()` |
| **Analytics** | `query()`, `events_query()`, `enrollments_query()`, `refresh()` |
| **Apps** | `list()`, `hub_list()`, `install()`, `uninstall()`, `update()` |
| **Files** | `documents()`, `file_resources()`, `upload()`, `download()` |
| **Messaging** | `conversations()`, `send()`, `reply()`, `mark_read()` |
| **Customization** | `logo_front()`, `logo_banner()`, `style()`, `system_setting()` |

### Bulk Operations

- `patch_bulk(operations, concurrency=10)` -- JSON Patch with semaphore control
- `apply_sharing_bulk(objects, sharing, concurrency=10)` -- bulk sharing updates
- `stream_to(query, file)` -- stream large analytics results to disk

### Utilities

- **Period math:** `parse_period()`, `next_period_id()`, `previous_period_id()`, `period_start_end()`
- **UID generation:** `generate_uids(count)` -- offline, CSPRNG-based
- **Retry transport:** honors `Retry-After`, retries 429/502/503/504 automatically

---

## Plugin Runtime

**Package:** `dhis2w-core` | **Install:** `uv add dhis2w-core`

Shared runtime that bridges the pure client with user-facing surfaces (CLI, MCP).
Provides profile discovery, plugin registry, auth factory, and token store.

### Profile System

Connection profiles are discovered automatically:

1. `./.dhis2/profiles.toml` -- project-local (CWD walk-up)
2. `~/.config/dhis2/profiles.toml` -- user-wide
3. Environment variables: `DHIS2_URL`, `DHIS2_USERNAME`/`DHIS2_PASSWORD`/`DHIS2_PAT`
4. `DHIS2_PROFILE` env to pin a named profile

Each profile stores: name, base URL, auth type (basic/pat/oauth2), and DHIS2
version (v41/v42/v43).

### Token Store

SQLite-backed (`aiosqlite`) at `.dhis2/tokens.sqlite`, keyed by profile name.
Handles OAuth2 token caching and automatic refresh on expiry.

### First-Party Plugins

22 plugins, each with a service layer (`service.py`) and CLI commands
(`cli.py`); most also expose MCP tools (`mcp.py`). Every plugin exists in
three version trees (v41, v42, v43).

| Plugin | Domain |
| --- | --- |
| **metadata** | List, get, create, patch, delete all resource types. Bulk import/export, filter DSL, sharing, cross-resource search, usage reverse-lookup, bundle diff/merge across profiles. |
| **schema** | Generated-model introspection: describe any metadata or instance-side type's fields (prefers the OpenAPI tree). |
| **data** | Router to aggregate + tracker subdomains. |
| **aggregate** | Data value fetch, push, set, delete. Bulk import with `importStrategy` and dry-run. |
| **tracker** | Tracked entities, enrollments, events, relationships. Register, enroll, create events, list outstanding follow-ups. |
| **analytics** | Aggregated, event, enrollment, and tracked-entity queries. Outlier detection. |
| **user** | List, get, invite, reinvite, reset-password. Mounts `group` and `role` sub-apps. |
| **user-group** | CRUD + member management + sharing (mounted as `d2w user group`). |
| **user-role** | CRUD + authority grants (mounted as `d2w user role`). |
| **route** | Integration routes: register, run, inspect, delete. Five auth-scheme types. |
| **apps** | List installed, browse App Hub, install from file or hub, uninstall, update with semver picking, snapshot/restore. |
| **datastore** | Key-value store: namespaces, keys, get/set/delete on `/api/dataStore` + `/api/userDataStore`. |
| **files** | Documents + fileResources: upload, download, list. |
| **messaging** | Message conversations: list, get, send, reply, mark read/unread, ticket-workflow priority/status/assignment. |
| **maintenance** | Background tasks, cache clear, data-integrity checks, soft-delete cleanup, validation runs, predictor runs, analytics-table rebuild. |
| **doctor** | Health probes: ~100+ metadata checks, DHIS2 data-integrity checks, BUGS.md workaround drift detection. |
| **security** | Read-only security posture: password policy and registration settings, account authority risk categorisation, and a step-by-step audit runner (`security audit`) that streams a live progress display and writes a report to disk in Markdown, plaintext, CSV, and HTML (resumable). A `security report` command re-renders an existing run's report files from its JSONL spine without re-scanning. GET-only against a tested allowlist; CLI-only until its MCP surface lands. |
| **system** | System info, current user (whoami), calendar, system-settings read/write. |
| **customize** | Brand + theme an instance: login logos, banner, CSS, preset apply. |
| **profile** | Profile CRUD, verification, OAuth2 login/logout, OIDC discovery, PAT + OAuth2-client provisioning. |
| **browser** | Playwright-driven UI automation (PAT creation, login, screenshots). Requires `[browser]` extra. |
| **dev** | Developer tools: UID generation, codegen, sample-data fixtures. |

### External Plugin Discovery

Third-party plugins register via `importlib.metadata.entry_points(group="dhis2.plugins")`
and are discovered automatically at startup.

---

## Command-Line Interface

**Package:** `dhis2w-cli` | **Install:** `uv tool install dhis2w-cli`

Typer console script `d2w` that wraps every plugin as CLI subcommands.

### Command Tree

```
d2w profile         Manage connection profiles
  list | show | default | verify
  add | remove | rename
  bootstrap             One-shot: provision a PAT or OAuth2 client + save a profile
  login | logout        OAuth2 token flows
  oidc-config           Discover a DHIS2 instance's OIDC endpoints into a profile
  pat                   Provision Personal Access Tokens on DHIS2
  oauth2                Manage DHIS2 OAuth2 clients on the server (admin ops)

d2w system          System information
  whoami                Everything DHIS2 reports about the authenticated user
  info                  Server version, build, analytics state
  calendar              Show or change the active calendar
  settings              Read/write DHIS2 system settings

d2w schema          Describe a generated type's fields (metadata or instance-side)

d2w metadata        Metadata inspection + CRUD
  list | get            Browse resources with filters, fields, paging
  search                Cross-resource metadata search
  usage                 Reverse lookup: what references this UID?
  export | import       Bulk metadata bundles (with strategy + dry-run)
  patch | rename | retag
  share                 Apply one sharing block across many UIDs
  diff | diff-profiles | merge

d2w data            Data values
  aggregate get | push | set | delete
  tracker list | get | type | push | delete
  tracker register | enrollment | event | relationship
  tracker outstanding   List outstanding follow-ups

d2w analytics       Analytics queries
  query                 Run an aggregate analytics query
  events | enrollments | tracked-entities
  outlier-detection     Flag statistical anomalies in data values

d2w user            User administration
  list | get | invite | reinvite | reset-password
  group                 User groups (CRUD, members, sharing)
  role                  User roles (CRUD, authority grants)

d2w route           Integration routes
  list | get | create | update | patch | delete
  run                   Execute a route (DHIS2 proxies to the target URL)

d2w apps            App management
  list | add | remove | update | reload
  snapshot | restore    Portable JSON snapshots of installed apps
  hub-list | hub-url    Browse the App Hub / manage its configured URL

d2w datastore       Key-value data store
  namespaces | keys | get | set | delete | delete-namespace

d2w files           File management
  documents list | get | upload | upload-url | download | delete
  resources upload | get | download

d2w messaging       Internal messaging
  list | get | send | reply | delete
  mark-read | mark-unread
  set-priority | set-status | assign | unassign

d2w maintenance     System maintenance
  task | cache | cleanup
  dataintegrity         DHIS2 data-integrity checks
  refresh               Regenerate analytics / resource / monitoring tables
  validation | predictors

d2w customize       Brand + theme an instance
  logo-front | logo-banner | style
  apply                 Apply a committed preset directory in one call
  show                  Current /api/loginConfig snapshot

d2w doctor          Health diagnostics
  metadata              ~100+ metadata health checks
  integrity             DHIS2 data-integrity checks
  bugs                  BUGS.md workaround drift detection

d2w security        Security posture (read-only)
  settings              Password policy, registration, lockout settings
  authorities           My effective authorities, categorised by risk
  audit                 Run all checks step by step, stream a report to disk
  report                Re-render an existing run's report from its spine

d2w browser         UI automation (requires [browser] extra)
  pat                   Mint a Personal Access Token via Playwright
  dashboard | viz | map Capture workflows (render to PNG)

d2w dev             Developer tools
  uid                   Generate DHIS2 UIDs (offline, CSPRNG)
  sample                Inject known-good fixtures (route, data, pat, oauth2-client)
  codegen generate | rebuild | oas-rebuild | diff
```

### Output Modes

- **Default:** Rich formatted tables with color
- **`--json`:** Raw JSON for scripting and piping
- **`--profile <name>`:** Override the active profile for a single command

### Query DSL

Available on all list commands:

```bash
d2w metadata list dataElements \
  --filter 'name:ilike:malaria' \
  --filter 'valueType:eq:NUMBER' \
  --root-junction AND \
  --fields id,name,shortName,valueType \
  --order name:asc \
  --page 1 --page-size 25
```

---

## MCP Server

**Package:** `dhis2w-mcp` | **Install:** `uv tool install dhis2w-mcp`

FastMCP server (`dhis2`) exposing every plugin as typed MCP tools: 313 tools
across 14 plugin groups. The full catalog is auto-generated into
`docs/mcp-reference.md` (`make docs-mcp`).

### Tool Naming

Snake-case, verb-last: `<plugin>_<resource>_<verb>`

```
metadata_attribute_find
data_aggregate_get
analytics_enrollments_query
user_group_add_member
system_calendar_set
maintenance_cache_clear
doctor_integrity
```

### Supported Hosts

| Host | Configuration |
| --- | --- |
| **Claude Desktop** | `claude_desktop_config.json` |
| **Claude Code** | `claude mcp add dhis2 -s user -- ...` |
| **Cursor** | `~/.cursor/mcp.json` |
| **Generic** | Any stdio-based MCP client |

### Transport

Stdio transport. Lazy plugin discovery on startup. Tool names, descriptions, and
schemas auto-derived from function signatures and docstrings.

---

## MCP CLI Bridge

**Package:** `dhis2w-mcp-bridge` | **Install:** `uv tool install dhis2w-mcp-bridge`

FastMCP server (`dhis2w-mcp-bridge`) that exposes the whole `d2w` CLI as a
single `dhis2_cli` tool: one tool schema instead of ~313, sized for small
local models (LM Studio, Ollama, llama.cpp) that drive it by progressive
`--help` discovery. Supports a read-only mode via `DHIS2_MCP_READONLY=1`.
Use the full `dhis2w-mcp` server for capable cloud models; the design
rationale lives in `docs/architecture/mcp-bridge.md`.

---

## Browser Automation

**Package:** `dhis2w-browser` | **Install:** `uv add dhis2w-browser`

Playwright-based DHIS2 UI automation. Separated from the client so API-only
installs never pull Chromium.

### Library API

| Function | Purpose |
| --- | --- |
| `logged_in_page()` | Async context manager returning a `(BrowserContext, Page)` logged into DHIS2 |
| `session_from_cookie()` | Fast-path: inject a pre-minted `JSESSIONID` cookie |
| `create_pat()` | Mint a Personal Access Token through a browser session (DHIS2 returns the token value only once) |
| `drive_oauth2_login()` | Full OIDC flow via Chromium: authorize URL, React login, Spring AS consent, loopback redirect |
| `drive_login_form()` | Lower-level: navigate to authorize URL, fill login + consent, wait for redirect |
| `capture_dashboard()` | Render a dashboard to PNG |
| `capture_visualization()` | Render a visualization to PNG |
| `capture_map()` | Render a map to PNG |

### Display Modes

- **Headless** (default for automation): no visible browser window
- **Headful** (`DHIS2_HEADFUL=1` or `--headful`): visible browser for debugging

### Why Browser?

- PAT creation requires a session cookie -- DHIS2 gates `/api/apiToken` behind it
- OAuth2 login requires driving the React login form and Spring Authorization
  Server consent screen
- Dashboard/visualization/map rendering requires the full DHIS2 web app

---

## Code Generator

**Package:** `dhis2w-codegen` | **Workspace-only** (not published to PyPI)

Version-aware generator that emits typed Python code into `dhis2w-client`.

### Pipelines

| Pipeline | Source | Output |
| --- | --- | --- |
| **Schemas** | `/api/schemas` on a live DHIS2 instance | Pydantic models + `StrEnum`s for every metadata resource |
| **OpenAPI** | `/api/openapi.json` on a live DHIS2 instance | Instance-side shapes (tracker writes, envelopes, auth schemes) |

### Commands

```bash
d2w dev codegen generate --url <DHIS2> --username <u> --password <p>
d2w dev codegen rebuild          # regenerate from committed manifest
d2w dev codegen oas-rebuild      # re-emit OpenAPI-based types
d2w dev codegen diff <from> <to> # structural diff between versions
```

### Architecture

- `discover.py` -- fetch `/api/schemas`, normalize to `SchemasManifest`
- `emit.py` -- walk manifest, render pydantic models via Jinja templates
- `oas_emit.py` -- emit OpenAPI-based shapes with spec patches
- `spec_patches.py` -- apply fixes for things DHIS2's OpenAPI spec omits
- `diff.py` -- cross-version structural diff (e.g., v42 vs v43)

---

## Cross-Cutting Capabilities

### Multi-Version Support

All three DHIS2 major versions (v41, v42, v43) are supported with separate
plugin trees and generated code. Version resolution:

1. `profile.version` field in `profiles.toml`
2. `DHIS2_VERSION` environment variable
3. Default: `v42`

`d2w --version` shows which plugin tree booted and where the version came from.

### Async-First Architecture

Every client method is async. The entire runtime uses `async/await` with `httpx`
as the HTTP transport.

```python
async with Dhis2Client(base_url, auth=PatAuth(token)) as client:
    me = await client.system.me()
    elements = await client.resources.data_elements.list()
```

### Three-Surface Plugin Model

Every feature ships as a plugin with three surfaces sharing one service layer:

```
plugin/
  service.py   <-- async business logic (shared)
  cli.py       <-- Typer commands
  mcp.py       <-- FastMCP tool definitions
  models.py    <-- pydantic view-models
  tests/       <-- pytest suite
```

Adding a new plugin automatically wires it into both the CLI and MCP server.

### Pydantic Everywhere

All structured data uses `pydantic.BaseModel`. No raw dicts cross module
boundaries. No dataclasses. DHIS2 resource models, service return values, CLI
output shapes, MCP tool returns, error bodies, and configuration are all typed.

### Metadata Query DSL

Available across CLI, MCP, and library:

- Multi-filter with OR/AND junction
- Field selector (equivalent to DHIS2's `fields=` parameter)
- Multi-column ordering
- Paging with page/page-size

### Health and Diagnostics

`d2w doctor` runs ~100+ metadata health checks, DHIS2's own data-integrity
checks, and BUGS.md workaround drift detection. Available via CLI and MCP.

### Examples

Three parallel example trees (`examples/v41/`, `examples/v42/`, `examples/v43/`),
each with three surfaces:

- **`client/`** -- 27+ Python examples (whoami, CRUD, analytics, OIDC, bulk
  import, tracker lifecycle, sharing, error handling, ...)
- **`cli/`** -- 15+ shell scripts covering every CLI domain
- **`mcp/`** -- 14+ Python examples showing MCP tool usage

---

## Dependency Graph

```
dhis2w-cli --------> dhis2w-core ------> dhis2w-client
dhis2w-mcp --------> dhis2w-core            |
dhis2w-mcp-bridge -> dhis2w-cli             |
                       |                     |
dhis2w-browser --------+---------------------+
                       |
              (optional [browser] extra)

dhis2w-codegen   workspace-only generator
```

No dependency cycles. `dhis2w-client` is standalone. Browser automation is
always optional.

