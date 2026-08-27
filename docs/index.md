# dhis2w

Python tooling for DHIS2. A `uv` workspace with an async client library, a Typer CLI, a FastMCP server, a Playwright browser helper, a code generator, and a shared plugin runtime.

## Where to start

Everything here talks to DHIS2. Pick the surface you want to talk to it *through* — each has its own tab, its own tutorial, and its own reference:

- **[Python client](client/index.md)** — async library for ETL scripts, embedded DHIS2 calls inside another service, and tests that need typed access. Pairs with the [Python library tutorial](client/tutorial.md).
- **[`d2w` CLI](cli/index.md)** — terminal use, shell pipelines, CI / cron jobs, day-to-day admin. Pairs with the [CLI tutorial](cli/tutorial.md).
- **[`dhis2w-mcp` MCP server](mcp/index.md)** — LLM-driven workflows (Claude Desktop, Claude Code, Cursor, Continue, Cline). Pairs with the [MCP tutorial](mcp/tutorial.md).
- **[`d2w fhir`](fhir/index.md)** — publish an instance's metadata as a FHIR Implementation Guide, serve it as a capture endpoint, and forward what it captures back into DHIS2. Graded 100-501, opening at the introduction; start at the [Introduction](fhir/100-introduction.md).
- **[d2ql query language](query/index.md)** — a pipeline query and transform language over DHIS2 data, with no DHIS2 runtime dependency of its own.

Whichever you pick:

- **New to the repo?** Skim the [Walkthrough](walkthrough.md), set up [a local DHIS2](local-setup.md), then pick a surface above.
- **Connecting to a remote DHIS2?** [Connecting to DHIS2](guides/connecting-to-dhis2.md) covers Basic / PAT / OAuth2 with profiles.
- **Looking for the architecture?** Start at [Overview](architecture/overview.md), then [Typed schemas](architecture/typed-schemas.md) + [Codegen](codegen.md).
- **Browsing by symbol?** The [API reference](api/index.md) auto-renders every `dhis2w-client` module's docstrings.

## Packages

| Package | Role | PyPI |
| --- | --- | --- |
| `dhis2w-client` | Async DHIS2 API client with pluggable auth and pydantic models | [`dhis2w-client`](https://pypi.org/project/dhis2w-client/) |
| `dhis2w-core` | Profile discovery, plugin registry, first-party plugins | [`dhis2w-core`](https://pypi.org/project/dhis2w-core/) |
| `dhis2w-cli` | Typer console script `d2w` (mounts plugins from `dhis2w-core`) | [`dhis2w-cli`](https://pypi.org/project/dhis2w-cli/) |
| `dhis2w-mcp` | FastMCP server `dhis2w-mcp` (mounts the same plugins) | [`dhis2w-mcp`](https://pypi.org/project/dhis2w-mcp/) |
| `dhis2w-mcp-bridge` | Single-tool MCP bridge exposing the `d2w` CLI for small local models | [`dhis2w-mcp-bridge`](https://pypi.org/project/dhis2w-mcp-bridge/) |
| `dhis2w-ql` | d2ql pipeline query + transform language (d2path engine), no DHIS2 runtime dependency | [`dhis2w-ql`](https://pypi.org/project/dhis2w-ql/) |
| `dhis2w-browser` | Playwright helpers (PAT creation, future UI automation) | [`dhis2w-browser`](https://pypi.org/project/dhis2w-browser/) |
| `dhis2w-codegen` | Version-aware client generator | _workspace-only_ |
| `dhis2w-bench` | Model benchmarking harness | _workspace-only_ |
| `dhis2w-mcp-router` | Search + dispatch over upstream MCP servers | [`dhis2w-mcp-router`](https://pypi.org/project/dhis2w-mcp-router/) |
| `dhis2w-fhir` | `d2w fhir`: generate an Implementation Guide from an instance, convert captures, drain the spool | [`dhis2w-fhir`](https://pypi.org/project/dhis2w-fhir/) |
| `dhis2w-fhir-serve` | The FHIR capture facade `d2w fhir serve` runs on, capture UI included | [`dhis2w-fhir-serve`](https://pypi.org/project/dhis2w-fhir-serve/) |
| `dhis2w-fhir-engine` | FHIRPath, CQL, and quality-measure evaluation over FHIR data, no DHIS2 dependency | [`dhis2w-fhir-engine`](https://pypi.org/project/dhis2w-fhir-engine/) |

Plus `infra/`, a docker-compose stack for running a local DHIS2 instance with pre-seeded PATs and an OAuth2 client.

## Capability matrix

The generated [MCP reference](mcp-reference.md) currently reports around 318 tools across 16 plugin groups (the auto-regenerated count is the source of truth; the per-group numbers below age with each release). 20 top-level CLI domains. Every MCP tool accepts an optional `profile: str | None` kwarg so an agent can target any configured profile per call. Most operational read/write commands ship as both a CLI command and a matching MCP tool sharing one typed service call. A few surfaces are intentionally CLI-only — they involve local-machine state, interactive prompts, or out-of-process subprocesses that don't fit the MCP stdio model:

- **`d2w dev`** — codegen, sample-fixture generation, ad-hoc UID minting. Local developer workflow; not exposed via MCP.
- **`d2w browser`** — Playwright-driven PAT mint, OIDC login, dashboard / viz / map screenshots. Runs Chromium out-of-process; not exposed via MCP.
- **`d2w profile add / remove / rename / login / logout / bootstrap`** — profile mutations touch local TOML + the OAuth2 token store and gate on interactive prompts. Profile **reads** (`list`, `verify`, `show`) are exposed as MCP tools; the four MCP profile tools cover those read paths.
- **`d2w fhir`** — scaffolds project trees, shells out to a dockerized IG publisher, and runs its own HTTP facade. The plugin registers no MCP tool at all; the served facade is the network surface an agent talks to instead.

| Domain | CLI | MCP tools | Docs |
| --- | --- | ---: | --- |
| Profile (list / verify / show / default / add / remove / rename, login / logout / bootstrap) | `d2w profile` | 4 | [Profiles](architecture/profiles.md) |
| System (whoami, info, server-info, calendar get/set) | `d2w system` | 5 | [System module](architecture/system.md) |
| Metadata — core surface (`list` / `get` / `patch` / `search` / `usage` / `export` / `import` / `diff` / `diff-profiles` / `merge`) | `d2w metadata` | 230 | [Metadata plugin](architecture/metadata-plugin.md) |
| Metadata — authoring triples (org-units, data-elements, indicators, program-indicators, category-options + legend-sets + options + attribute + program-rule + sql-view + viz + dashboard + map) | `d2w metadata <sub-app>` | — (part of metadata count above) | [Organisation units](api/organisation-units.md) / [Data elements](api/data-elements.md) / [Indicators](api/indicators.md) / [Program indicators](api/program-indicators.md) / [Category options](api/category-options.md) / [Legend sets](api/legend-sets.md) |
| Data (aggregate `dataValueSets` + `dataValues`, tracker entities / enrollments / events / relationships / push) | `d2w data aggregate` + `d2w data tracker` | 15 | [Aggregate plugin](architecture/aggregate.md) / [Tracker plugin](architecture/tracker.md) |
| Analytics (aggregate / event / enrollment / outlier / tracked-entity queries) | `d2w analytics` | 5 | [Analytics plugin](architecture/analytics.md) |
| Route (`/api/routes` integration proxies) | `d2w route` | 7 | [Auth schemes](api/auth-schemes.md) |
| Maintenance (tasks, cache, cleanup, data integrity, validation, predictors) | `d2w maintenance` | 15 | [Maintenance plugin](architecture/maintenance-plugin.md) |
| Files (documents + file resources) | `d2w files` | 5 | [Files plugin](architecture/files-plugin.md) |
| Data store (namespaces, keys, get / set / delete, delete-namespace, the shared store and the per-user one) | `d2w datastore` | 5 | [Data store](api/datastore.md) |
| Messaging (`/api/messageConversations` + ticket-workflow fields) | `d2w messaging` | 11 | [Messaging plugin](architecture/messaging-plugin.md) |
| User admin (users, groups, roles, sharing) | `d2w user` + `d2w user group` + `d2w user role` | 16 | [User plugin](architecture/user-plugin.md) / [User groups + roles](architecture/user-groups-and-roles.md) |
| Customize (login page / logos / CSS / system settings) | `d2w customize` | 7 | [Customize plugin](architecture/customize-plugin.md) |
| Apps (`/api/apps` + `/api/appHub` + snapshot/restore) | `d2w apps` | 13 | [Apps API](api/apps.md) |
| Doctor (BUGS tripwires + integrity checks + metadata health) | `d2w doctor` | 4 | [Doctor plugin](architecture/doctor-plugin.md) |
| Security posture (settings, authorities, audit, report) | `d2w security` | 3 | [Security plugin](architecture/security-plugin.md) |
| Dev (codegen, uid, pat, oauth2 client, sample fixtures) | `d2w dev` | — (dev-only) | [Codegen](codegen.md) |
| Browser automation (Playwright-driven PAT mint, screenshots, OIDC login) | `d2w browser` | — (runs out-of-process) | [Browser automation](architecture/browser.md) |
| FHIR (init / validate / generate / serve / forward / withdraw / doctor) | `d2w fhir` | — (CLI and its own HTTP facade) | [`d2w fhir`](fhir/index.md) |
| d2ql (run a query, explain one, evaluate a d2path expression) | `d2w query` | 3 | [Query language](query/index.md) |

Day-to-day workflows (`make install`, `make lint`, `make test`, `make docs-serve`) are documented in the repo root `README.md`.
