# Walkthrough

> **Learning path · step 2 of 8** — Contributor / developer local-stack tour. Prev: [Home / README](https://github.com/winterop-com/dhis2w-utils/blob/main/README.md). Next: [`dhis2` CLI tutorial](guides/cli-tutorial.md). For end-user surface tutorials skip ahead to [Client tutorial](guides/client-tutorial.md) or [MCP tutorial](mcp/tutorial.md).

Step-by-step from a fresh clone to a fully working local DHIS2 development environment — docker stack, seeded profiles, codegen, and Playwright-minted PATs. Aimed at contributors who want to run the test suites + iterate on the workspace; end-user setup against an existing DHIS2 instance is shorter and lives in [Connecting to DHIS2](guides/connecting-to-dhis2.md).

Each step shows the exact shell command (or code snippet), what it does, and what you should expect to see. Update this file when a contributor-facing step changes.

---

## Step 1 — install the workspace

```bash
cd /Users/morteoh/dev/dhis2w-utils
make install
```

Runs `uv sync --all-packages --all-extras` at the workspace root. Installs all six members in editable mode plus dev tools (ruff, mypy, pyright, pytest, respx, mkdocs-material, mkdocs-claude-theme).

Expect: ~120 packages installed.

---

## Step 2 — verify the scaffold

```bash
make lint
make test
```

- `make lint` runs `ruff format`, `ruff check --fix`, `mypy --explicit-package-bases packages`, and `pyright`. All three must pass.
- `make test` runs pytest excluding `@pytest.mark.slow` tests.

Expect: both green. Roughly 1,180 tests collected (mocked tier runs in seconds; slow-marked tests skip here and run in `make test-slow` / the nightly integration workflow). The auto-counting source of truth is `uv run pytest --collect-only -q | tail -1`.

---

## Step 3 — spin up a local DHIS2 (recommended)

The `infra/` directory ships a docker-compose stack. Full details in [Local DHIS2 setup](local-setup.md).

```bash
make dhis2-run                 # foreground — Ctrl+C to stop
# or detached + auto-seeded auth (.env.auth is written for tests):
make dhis2-run
```

For niche targets (image discovery, readiness probe, log tail, PAT helper) `make -C infra help`.

Defaults to DHIS2 43, admin / district, http://localhost:8080. Use `DHIS2_VERSION=42` for the seeded v42 stack.

Verify with an authenticated call from `dhis2w-client` itself — no curl:

```bash
uv run python -c "
import asyncio
from dhis2w_client import Dhis2Client, BasicAuth
async def main():
    async with Dhis2Client('http://localhost:8080', auth=BasicAuth('admin','district'), allow_version_fallback=True) as client:
        info = await client.system.info()
        print('version:', info.version)
asyncio.run(main())
"
```

Expect: `version: 2.43.x` (or `2.42.x` if you ran with `DHIS2_VERSION=42`).

---

## Step 4 — generate the versioned client

DHIS2 schemas differ by version. `dhis2w-codegen` hits `/api/schemas` and emits pydantic models + typed CRUD accessors into `packages/dhis2w-client/src/dhis2w_client/generated/v{NN}/`.

```bash
uv run dhis2 dev codegen generate \
  --url http://localhost:8080 \
  --username admin \
  --password district
```

Expect (against the v43 default stack):

```
discovering http://localhost:8080
  version: 2.43.x (→ v43)
  schemas: 116
emitting packages/dhis2w-client/src/dhis2w_client/generated/v43
done — generated 116 schemas ...
```

The `v43/` folder now has `__init__.py` (with `GENERATED = True`), `resources.py` (CRUD per resource), `schemas_manifest.json` (audit trail), and `schemas/*.py` (one pydantic model per metadata type).

For codegen against the public play instances without booting docker, use `make dhis2-codegen-play` (regenerates v42 + v43 — only those two play.im instances are publicly mounted). For the full v41 + v42 + v43 refresh use `make dhis2-codegen-all`, which spins up a fresh docker stack per version (slow).

---

## Step 5 — verify the generated code compiles cleanly

```bash
make lint
make test
```

Expect: still green. Generated files pass ruff + mypy + pyright without any manual touch-up.

---

## Step 6 — use the typed resources

```python
import asyncio
from dhis2w_client import Dhis2Client, BasicAuth

async def main():
    async with Dhis2Client(
        base_url="http://localhost:8080",
        auth=BasicAuth("admin", "district"),
    ) as client:
        # system endpoints (hand-written)
        me = await client.system.me()
        print(me.username, me.authorities[:3] if me.authorities else [])

        # typed metadata list
        elements = await client.resources.data_elements.list(fields="id,name")
        print(f"{len(elements)} data elements")

        # typed get by UID
        if elements:
            de = await client.resources.data_elements.get(elements[0].id)
            print(de.name)

asyncio.run(main())
```

Expect: your username, first three authorities, a data-element count, and the first element's name.

---

## Step 7 — create a Personal Access Token

Two paths; pick based on what creds you have:

- **Plain API** — `dhis2 profile pat create` hits `POST /api/apiToken` with Basic admin auth. Fast, no Chromium, no browser. Default recommendation.
- **Playwright** — `dhis2 browser pat` drives the React login form + mints the PAT inside the resulting session. Use when Basic API auth is disabled server-side, or when you're already in a browser workflow.

```bash
dhis2 browser pat \
    --url http://localhost:8080 \
    --username admin \
    --password district \
    --name "dhis2-utils-local" \
    --expires-in-days 30 \
    --allowed-method GET \
    --allowed-method POST \
    --allowed-method PUT \
    --allowed-method DELETE
```

The browser opens (visible by default — use `--headless` to hide). You'll see the login page auto-filled and submitted. After the redirect, the command prints the new token:

```
d2p_DVWAOHXvKTkyFFp96eABNHuqg51wo0yKWgBA6L4koepU4Bj8ab
```

Save this — DHIS2 shows it only once.

---

## Step 8 — use the PAT for auth

```python
import asyncio
from dhis2w_client import Dhis2Client, PatAuth

async def main():
    token = "d2p_..."
    async with Dhis2Client("http://localhost:8080", auth=PatAuth(token=token)) as client:
        me = await client.system.me()
        print(me.username)

asyncio.run(main())
```

The header sent is `Authorization: ApiToken d2p_...`. No username/password anywhere near the wire.

---

## Step 9 — run integration tests against the live instance

```bash
# optional: reuse the PAT from step 7 across test sessions
export DHIS2_LOCAL_PAT=d2p_...

make test-slow
```

If `DHIS2_LOCAL_PAT` is unset, the `local_pat` fixture auto-mints a fresh one via Playwright (~5s), then runs destructive CRUD tests (create/update/delete a test Constant) against localhost.

Expect: ~6–8 integration tests passing (3 public play/dev tests + 1 typed end-to-end against play/dev + PAT round-trip + destructive CRUD on localhost).

---

## Step 10 — set up a named profile (recommended over raw env)

Profiles replace the ad-hoc env-var approach with something declarative and switchable. One-time setup:

```bash
# Create a user-wide profile and make it the default. The PAT is prompted
# interactively (no flag — secrets never go on the command line) or read
# from DHIS2_PAT if set in the current shell.
dhis2 profile add prod \
  --global \
  --url https://dhis2.example.org \
  --auth pat \
  --default
# Personal Access Token: ********

# Verify it works
dhis2 profile verify prod
# → OK prod  https://dhis2.example.org  auth=pat  version=2.42.4  user=admin  182 ms

# List what you have
dhis2 profile list
```

After this, every CLI and MCP tool resolves the profile automatically. Override per-invocation with `dhis2 --profile NAME ...` or switch the default with `dhis2 profile default NAME`. See [Profiles](architecture/profiles.md) for the full resolution chain.

## Step 11 — use the CLI

With a profile set (or the seeded `.env.auth` sourced for the old-school path), the CLI has a wide surface covering system / metadata / aggregate / tracker / analytics:

```bash
dhis2 --help
# → 18 top-level domains on a fresh install:
#   analytics, apps, browser, data, dev, doctor, files, maintenance, messaging,
#   metadata, profile, route, schema, security, system, user, user-group, user-role
# Plus any external plugins registered via entry_points (group="dhis2.plugins").

# system — auth + version probe
dhis2 system whoami
dhis2 system info

# metadata — wraps 119 generated CRUD resources
dhis2 metadata type list
dhis2 metadata list dataElements --limit 10
dhis2 metadata get dataElements fbfJHSPpUQD

# aggregate — data values
dhis2 data aggregate get --data-set X --org-unit Y --start-date 2024-01-01 --end-date 2024-12-31 --children
dhis2 data aggregate set --de X --pe 202401 --ou Y --value 42
dhis2 data aggregate push values.json --dry-run

# tracker — events, tracked entities, enrollments, bulk push
dhis2 data tracker event list --program X --org-unit Y --status COMPLETED
dhis2 data tracker push bundle.json --strategy CREATE_AND_UPDATE

# analytics — aggregated queries
dhis2 analytics query \
  --dim dx:fbfJHSPpUQD --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd --agg SUM

# target a different profile per call
dhis2 --profile staging metadata list dataElements --limit 10
```

Plugin-specific docs: [metadata](architecture/metadata-plugin.md), [aggregate](architecture/aggregate.md), [tracker](architecture/tracker.md), [analytics](architecture/analytics.md).

## Step 12 — use the MCP server

The same capabilities are available to AI agents via `dhis2w-mcp`. The server exposes roughly **304 tools across 13 plugin groups** — `profile` (4), `system` (5), `metadata` (197 — spans the authoring-triple sub-apps + options + attribute + program-rule + sql-view + viz + dashboard + map + legend-sets + core `list/get/patch/search/usage/export/import/diff/merge`), `data` (15 — aggregate + tracker), `analytics` (5), `route` (7), `maintenance` (15), `files` (5), `messaging` (11), `user` (16 — user + user-group + user-role), `customize` (7), `apps` (13), `doctor` (4). The auto-regenerated [MCP reference](mcp-reference.md) is the source of truth for the current counts.

### Option A — one server, select profile per tool call

```json
{
  "mcpServers": {
    "dhis2": {
      "command": "uv",
      "args": ["run", "dhis2w-mcp"]
    }
  }
}
```

Agent flow:

```
> profile_list
  [{"name": "prod", "default": true, ...}, {"name": "staging", ...}]

> profile_verify("staging")
  {"ok": true, "version": "2.42.4", ...}

> metadata_list(resource="dataElements", profile="staging")  # per-call override
```

### Option B — one server per instance, namespace-isolated

```json
{
  "mcpServers": {
    "dhis2-local": {
      "command": "uv", "args": ["run", "dhis2w-mcp"],
      "env": { "DHIS2_PROFILE": "local" }
    },
    "dhis2-prod": {
      "command": "uv", "args": ["run", "dhis2w-mcp"],
      "env": { "DHIS2_PROFILE": "prod" }
    }
  }
}
```

Agent sees two disjoint tool namespaces; no profile selection per call needed.

### Tool list

Profile-management (read-only via MCP): `profile_list`, `profile_verify`, `verify_all_profiles`, `profile_show`.

Domain tools: `whoami`, `system_info`, `metadata_type_list`, `metadata_list`, `metadata_get`, `data_aggregate_get`, `data_aggregate_push`, `data_aggregate_set`, `data_aggregate_delete`, `data_tracker_list`, `data_tracker_get`, `data_tracker_enrollment_list`, `data_tracker_event_list`, `data_tracker_relationship_list`, `data_tracker_push`, `analytics_query`, `analytics_query (shape=raw)`, `analytics_query (shape=dvs)`, `maintenance_refresh_analytics` / `maintenance_refresh_resource_tables` / `maintenance_refresh_monitoring`.

**Every domain tool accepts an optional `profile: str | None = None` kwarg**, giving the agent full per-call profile control.

See [dhis2w-mcp server](architecture/mcp.md) and [Profiles](architecture/profiles.md).

## Step 13 — browse the docs

```bash
make docs-serve
```

Opens `http://127.0.0.1:8000` with the mkdocs-claude-theme site. Architecture, codegen, PAT helper, testing strategy, decisions log, and lessons learned all live under `docs/`.

---

## Capability matrix

| Capability | Status | Where |
| --- | --- | --- |
| Async httpx client with pluggable auth | Done | `dhis2w-client` |
| Basic / PAT / OAuth2-PKCE providers | Done | `dhis2w-client/auth/` |
| Version-aware dispatch via `/api/system/info` | Done | `dhis2w-client/client.py` |
| `client.system.info()` / `client.system.me()` | Done | `dhis2w-client/system.py` |
| Codegen from `/api/schemas` → pydantic + CRUD | Done | `dhis2w-codegen`, output in `dhis2w-client/generated/` |
| Filesystem-scan version discovery | Done | `dhis2w-client/generated/__init__.py` |
| Playwright-minted PATs with options (name, expiry, IP/method/referrer allowlists) | Done | `dhis2w-browser/pat.py` |
| `dhis2 browser pat` CLI (plugin under `dhis2w-core`) | Done | `dhis2w-core/v42/plugins/browser/cli.py` |
| Plugin runtime (Protocol + built-in + entry-point discovery) | Done | `dhis2w-core/plugin.py` |
| Profile resolution from environment | Done | `dhis2w-core/profile.py` |
| First-party `system` plugin (CLI + MCP surfaces) | Done | `dhis2w-core/v42/plugins/system/` |
| `dhis2` CLI root with plugin mounting | Done | `dhis2w-cli/main.py` |
| `dhis2w-mcp` FastMCP server with plugin mounting | Done | `dhis2w-mcp/server.py` |
| Local Docker stack (DHIS2 + pgAdmin + Glowroot) | Done | `infra/` |
| Seeded auth: 6 PAT variations + OAuth2 client | Done | `infra/scripts/seed_auth.py` |
| Tests auto-source `infra/home/credentials/.env.auth` | Done | conftest fixtures |
| Unit tests (respx, CliRunner, in-process FastMCP Client) | Done | 42 passing |
| Integration tests against play/dev + localhost | Done | 12 passing |
| Destructive CRUD round-trip tests (constants) | Done | `test_integration_local_pat.py` |
| CLI end-to-end tests (`dhis2 system whoami/info` live) | Done | `test_cli_integration.py` |
| MCP end-to-end tests (in-process client calls `whoami`/`system_info`) | Done | `test_mcp_integration.py` |
| Tracker plugin (`/api/tracker/*` — tracked entities, enrollments, events, relationships) | Done | `dhis2w-core/v{N}/plugins/data/tracker_*`, `client.tracker` |
| Data values plugin (`/api/dataValueSets`, `/api/dataValues`, streaming) | Done | `dhis2w-core/v{N}/plugins/data/aggregate_*`, `client.data_values` |
| Analytics plugin (`/api/analytics*`, aggregate + events + enrollments + outlier + tracked-entity) | Done | `dhis2w-core/v{N}/plugins/analytics/`, `client.analytics` |
| Bulk metadata import / export / diff / merge | Done | `dhis2w-core/v{N}/plugins/metadata/service.py`, `client.metadata` |
| Profile system: `.dhis2/profiles.toml` + global + project-scoped + `dhis2 profile add/login/...` | Done | `dhis2w-core/profile.py`, `dhis2w-core/v{N}/plugins/profile/` |
| First-party metadata-domain plugins (orgUnits, dataElements, indicators, programIndicators, categoryOptions, legendSets, ...) | Done | `dhis2w-core/v{N}/plugins/metadata/` + matching `client.{resource}` accessors |
| Docs site with mkdocs-material (indigo) | Done | `docs/`, nav in `mkdocs.yml` |

For the current backlog see [Roadmap](roadmap.md).
