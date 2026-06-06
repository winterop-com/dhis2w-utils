# dhis2w

Python tooling for DHIS2. A `uv` workspace with an async client library, a Typer CLI, a FastMCP server, a Playwright browser helper, a code generator, and a shared plugin runtime.

## Where to start

Pick the surface that matches what you're building:

- **[Python client](client/index.md)** — async library for ETL scripts, embedded DHIS2 calls inside another service, and tests that need typed access. Pairs with the [Python library tutorial](guides/client-tutorial.md).
- **[`dhis2` CLI](cli/index.md)** — terminal use, shell pipelines, CI / cron jobs, day-to-day admin. Pairs with the [CLI tutorial](guides/cli-tutorial.md).
- **[`dhis2w-mcp` MCP server](mcp/index.md)** — LLM-driven workflows (Claude Desktop, Claude Code, Cursor, Continue, Cline). Pairs with the [MCP tutorial](mcp/tutorial.md).

Other entry points:

- **New to the repo?** Skim the [Walkthrough](walkthrough.md), set up [a local DHIS2](local-setup.md), then pick a surface above.
- **Connecting to a remote DHIS2?** [Connecting to DHIS2](guides/connecting-to-dhis2.md) covers Basic / PAT / OAuth2 with profiles.
- **Looking for the architecture?** Start at [Overview](architecture/overview.md), then [Typed schemas](architecture/typed-schemas.md) + [Codegen](codegen.md).
- **Browsing by symbol?** The [API reference](api/index.md) auto-renders every `dhis2w-client` module's docstrings.

## Packages

| Package | Role | PyPI |
| --- | --- | --- |
| `dhis2w-client` | Async DHIS2 API client with pluggable auth and pydantic models | [`dhis2w-client`](https://pypi.org/project/dhis2w-client/) |
| `dhis2w-core` | Profile discovery, plugin registry, first-party plugins | [`dhis2w-core`](https://pypi.org/project/dhis2w-core/) |
| `dhis2w-cli` | Typer console script `dhis2` (mounts plugins from `dhis2w-core`) | [`dhis2w-cli`](https://pypi.org/project/dhis2w-cli/) |
| `dhis2w-mcp` | FastMCP server `dhis2w-mcp` (mounts the same plugins) | [`dhis2w-mcp`](https://pypi.org/project/dhis2w-mcp/) |
| `dhis2w-browser` | Playwright helpers (PAT creation, future UI automation) | [`dhis2w-browser`](https://pypi.org/project/dhis2w-browser/) |
| `dhis2w-codegen` | Version-aware client generator | _workspace-only_ |

Plus `infra/`, a docker-compose stack for running a local DHIS2 instance with pre-seeded PATs and an OAuth2 client.

## Capability matrix

The generated [MCP reference](mcp-reference.md) currently reports around 304 tools across 13 plugin groups (the auto-regenerated count is the source of truth; the per-group numbers below age with each release). 16 top-level CLI domains. Every MCP tool accepts an optional `profile: str | None` kwarg so an agent can target any configured profile per call. Most operational read/write commands ship as both a CLI command and a matching MCP tool sharing one typed service call. A few surfaces are intentionally CLI-only — they involve local-machine state, interactive prompts, or out-of-process subprocesses that don't fit the MCP stdio model:

- **`dhis2 dev`** — codegen, sample-fixture generation, ad-hoc UID minting. Local developer workflow; not exposed via MCP.
- **`dhis2 browser`** — Playwright-driven PAT mint, OIDC login, dashboard / viz / map screenshots. Runs Chromium out-of-process; not exposed via MCP.
- **`dhis2 profile add / remove / rename / login / logout / bootstrap`** — profile mutations touch local TOML + the OAuth2 token store and gate on interactive prompts. Profile **reads** (`list`, `verify`, `show`) are exposed as MCP tools; the four MCP profile tools cover those read paths.

| Domain | CLI | MCP tools | Docs |
| --- | --- | ---: | --- |
| Profile (list / verify / show / default / add / remove / rename, login / logout / bootstrap) | `dhis2 profile` | 4 | [Profiles](architecture/profiles.md) |
| System (whoami, info, server-info, calendar get/set) | `dhis2 system` | 5 | [System module](architecture/system.md) |
| Metadata — core surface (`list` / `get` / `patch` / `search` / `usage` / `export` / `import` / `diff` / `diff-profiles` / `merge`) | `dhis2 metadata` | 230 | [Metadata plugin](architecture/metadata-plugin.md) |
| Metadata — authoring triples (org-units, data-elements, indicators, program-indicators, category-options + legend-sets + options + attribute + program-rule + sql-view + viz + dashboard + map) | `dhis2 metadata <sub-app>` | — (part of metadata count above) | [Organisation units](api/organisation-units.md) / [Data elements](api/data-elements.md) / [Indicators](api/indicators.md) / [Program indicators](api/program-indicators.md) / [Category options](api/category-options.md) / [Legend sets](api/legend-sets.md) |
| Data (aggregate `dataValueSets` + `dataValues`, tracker entities / enrollments / events / relationships / push) | `dhis2 data aggregate` + `dhis2 data tracker` | 15 | [Aggregate plugin](architecture/aggregate.md) / [Tracker plugin](architecture/tracker.md) |
| Analytics (aggregate / event / enrollment / outlier / tracked-entity queries) | `dhis2 analytics` | 5 | [Analytics plugin](architecture/analytics.md) |
| Route (`/api/routes` integration proxies) | `dhis2 route` | 7 | [Auth schemes](api/auth-schemes.md) |
| Maintenance (tasks, cache, cleanup, data integrity, validation, predictors) | `dhis2 maintenance` | 15 | [Maintenance plugin](architecture/maintenance-plugin.md) |
| Files (documents + file resources) | `dhis2 files` | 5 | [Files plugin](architecture/files-plugin.md) |
| Messaging (`/api/messageConversations` + ticket-workflow fields) | `dhis2 messaging` | 11 | [Messaging plugin](architecture/messaging-plugin.md) |
| User admin (users, user-groups, user-roles, sharing) | `dhis2 user` + `dhis2 user-group` + `dhis2 user-role` | 16 | [User plugin](architecture/user-plugin.md) / [User groups + roles](architecture/user-groups-and-roles.md) |
| Customize (login page / logos / CSS / system settings) | `dhis2 dev customize` | 7 | [Customize plugin](architecture/customize-plugin.md) |
| Apps (`/api/apps` + `/api/appHub` + snapshot/restore) | `dhis2 apps` | 13 | [Apps API](api/apps.md) |
| Doctor (BUGS tripwires + integrity checks + metadata health) | `dhis2 doctor` | 4 | [Doctor plugin](architecture/doctor-plugin.md) |
| Dev (codegen, uid, pat, oauth2 client, sample fixtures) | `dhis2 dev` | — (dev-only) | [Codegen](codegen.md) |
| Browser automation (Playwright-driven PAT mint, screenshots, OIDC login) | `dhis2 browser` | — (runs out-of-process) | [Browser automation](architecture/browser.md) |

Day-to-day workflows (`make install`, `make lint`, `make test`, `make docs-serve`) are documented in the repo root `README.md`.
