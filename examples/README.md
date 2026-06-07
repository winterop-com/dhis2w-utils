# dhis2-utils examples

Three per-version example trees, each with three parallel surfaces:

```
examples/
  v41/   cli/  client/  mcp/      # DHIS2 v41 stack
  v42/   cli/  client/  mcp/      # DHIS2 v42 stack (canonical)
  v43/   cli/  client/  mcp/      # DHIS2 v43 stack
```

- `cli/` — `dhis2 ...` Typer CLI shell scripts (profile-resolved)
- `client/` — `dhis2w-client` Python library (low-level: you bring the auth)
- `mcp/` — `dhis2w-mcp` FastMCP server, called in-process

Every example targets the committed e2e fixture for that major — `make dhis2-run DHIS2_VERSION=42` (or `=41` / `=43`) ships with it out of the box, seeds auth, streams logs. Source `infra/home/credentials/.env.auth` in your shell and the examples pick it up automatically.

Filenames describe what each example shows — no sequential numbering. Every domain has a script per surface where possible (e.g. `tracker_reads.*`, `analytics_query.*`, `user_administration.*`).

The three trees are kept at parity wherever the DHIS2 surface allows; intentional drift is documented at the bottom of this README.

> **Canonical catalogue**: [`docs/examples.md`](../docs/examples.md) is the curated v42 example index — the headline examples per topic with links to the concept docs that explain each one. It's not exhaustive (some smaller examples ship without a catalogue entry); the source of truth for what's on disk is `ls examples/v{41,42,43}/{cli,client,mcp}/`. v41 and v43 mirror most v42 entries plus carry version-specific additions (see the drift section at the bottom).

## Which surface should I use?

| Surface | Best for | Auth handling |
| --- | --- | --- |
| `dhis2w-client` (library) | Your own Python tooling; scripts in-process | You pass `AuthProvider` explicitly (Basic, PAT, OAuth2) — no profile layer |
| `dhis2 <cmd>` (CLI) | Day-to-day dev, pipelines, human use | Reads `~/.config/dhis2/profiles.toml` + env; `dhis2 profile add/login` manages creds |
| `dhis2w-mcp` (MCP) | Agents, automation over the MCP protocol | Same profile layer as the CLI; both reads and mutations are exposed (every CLI command has a matching MCP tool) |

All three hit DHIS2 via `Dhis2Client` under the hood. Pick the shape that fits your caller. See [Workspace layout](../docs/architecture/workspace.md) for the dependency arrows.

## Running

```bash
make dhis2-run DHIS2_VERSION=42        # foreground DHIS2 + seeded auth (Ctrl+C stops)
# second terminal:
set -a; source infra/home/credentials/.env.auth; set +a

uv run python examples/v42/client/whoami.py
bash examples/v42/cli/whoami.sh
uv run python examples/v42/mcp/whoami.py
```

Swap the `v42` segment for `v41` or `v43` to target the matching stack. `make refresh-and-verify DHIS2_VERSION=43` runs every example in `examples/v43/{cli,client,mcp}/` against a seeded v43 instance.

## v42 client examples ([`v42/client/`](v42/client/))

| File | Shows | Auth |
| --- | --- | --- |
| `whoami.py` | minimal client lifecycle, `/api/me` + `/api/system/info` | PAT / Basic |
| `list_data_elements.py` | paginated raw GET with `fields=...` | PAT / Basic |
| `push_data_value.py` | bulk import to `/api/dataValueSets` | PAT / Basic |
| `oidc_login.py` | OIDC login — PKCE, FastAPI redirect receiver, SQLite token store, auto-refresh. Auto-dispatches to Playwright when `DHIS2_USERNAME`+`DHIS2_PASSWORD` are set. | OAuth2 / OIDC |
| `oidc_playwright_login.py` | Full end-to-end OIDC flow via Playwright | OAuth2 / OIDC |
| `apps.py` | `client.apps.list_apps / hub_list` + a `keyAppHubUrl` read | PAT / Basic |
| `org_unit_crud.py` | OU CRUD: create, read, JSON Patch update, delete | PAT / Basic |
| `data_set_crud.py` | dataset CRUD with DE + OU assignments in one POST | PAT / Basic |
| `analytics_query.py` | `/api/analytics` query + analytics-table refresh | PAT / Basic |
| `analytics_events_enrollments.py` | `/api/analytics/events/query` + `/enrollments/query` (v42 + v41 only — see drift) | PAT / Basic |
| `geojson_org_units.py` | `/api/organisationUnits.geojson`, validated with `geojson-pydantic` | PAT / Basic |
| `bootstrap_zero_to_data.py` | zero-to-data: OU → user scope → DE → DS → sharing → dataValue → cleanup | PAT / Basic |
| `metadata_bulk_import.py` | `/api/metadata` bulk import with `importStrategy` / `dryRun` | PAT / Basic |
| `metadata_filter_order_paging.py` | metadata filter DSL: multi-filter OR/AND, multi-order, paging, `--all` | PAT / Basic |
| `profile_resolver.py` | using `dhis2w-core`'s `open_client` to resolve a profile from Python | resolved via profile |
| `profile_pat_pure_client.py` | building a `Profile` and calling `open_client` via **`dhis2w-client` alone** — no `dhis2w-core` install needed for PAT/Basic | PAT |
| `tracker_lifecycle.py` | tracker `/api/tracker` — TE + enrollment + event in one atomic POST | PAT / Basic |
| `tracker_clinic_intake.py` | `client.tracker.register` + `add_event` + `outstanding` | PAT / Basic |
| `tracker_event_program.py` | event-only (WITHOUT_REGISTRATION) workflow | PAT / Basic |
| `metadata_search.py` | cross-resource UID / code / name search | PAT / Basic |
| `metadata_usage.py` | reverse lookup "what references this UID?" | PAT / Basic |
| `error_handling.py` | `Dhis2ApiError` / `AuthenticationError`, WebMessage conflicts | PAT / Basic |
| `indicator_crud.py` | typed `Indicator` with numerator/denominator | PAT / Basic |
| `task_polling.py` | poll `/api/system/tasks/<type>/<uid>` | PAT / Basic |
| `enum_round_trip.py` | generated `StrEnum`s | PAT / Basic |
| `user_administration.py` | list/get users, `/api/me`, invite + reset-password | PAT / Basic |
| `sharing.py` | typed `SharingBuilder` + `apply_sharing` | PAT / Basic |
| `user_groups_and_roles.py` | user groups, user roles, authorities | PAT / Basic |

## v42 CLI examples ([`v42/cli/`](v42/cli/))

| File | Commands |
| --- | --- |
| `whoami.sh` | `dhis2 system whoami`, `dhis2 system info` |
| `profile_list_verify.sh` | `dhis2 profile list / verify / show` |
| `metadata_list_get.sh` | `dhis2 metadata type list`, `dhis2 metadata list / get`, `dhis2 dev uid` |
| `aggregate_data_values.sh` | `dhis2 data aggregate get / set / delete / push` |
| `analytics_query.sh` | `dhis2 analytics query [--shape table\|raw\|dvs] / refresh` |
| `tracker_reads.sh` | `dhis2 data tracker type`, `list <TET>`, `get <uid>`, `{enrollment,event,relationship} list`, `push` |
| `tracker_register_and_followup.sh` | `dhis2 data tracker register / event create / outstanding` |
| `tracker_event_program.sh` | `dhis2 data tracker event create --program EVTsupVis01` |
| `metadata_search.sh` | `dhis2 metadata search` |
| `profile_oidc_login.sh` | `dhis2 profile add --auth oauth2 --from-env`, `dhis2 profile login` |
| `apps.sh` | `dhis2 apps {list, hub-list, hub-url, update --dry-run, update --all, reload}` |
| `map_screenshot.sh` | `dhis2 browser map screenshot` (requires `[browser]` extra) |
| `visualization_screenshot.sh` | `dhis2 browser viz screenshot` (requires `[browser]` extra) |
| `route_register_and_run.sh` | `dhis2 route list / add / get / run / delete` (all 5 auth types) |
| `profile_pat.sh` | `dhis2 profile pat create` (`-q` for capture) |
| `dev_sample.sh` | `dhis2 dev sample route / data-value / pat / oauth2-client / all` |
| `dev_codegen.sh` | `dhis2 dev codegen generate / rebuild / oas-rebuild` |
| `maintenance.sh` | `dhis2 maintenance task types/list/status/watch`, `cache`, `cleanup`, `dataintegrity list/run/result` |
| `user_administration.sh` | `dhis2 user list / get / me / invite / reinvite / reset-password` |
| `user_groups_and_roles.sh` | `dhis2 user group {...}`, `dhis2 user role {...}` |

## v42 MCP examples ([`v42/mcp/`](v42/mcp/))

| File | Tools |
| --- | --- |
| `whoami.py` | `system_whoami`, `system_info` |
| `profile_tools.py` | `profile_list`, `profile_verify`, `profile_show` (read-only by design) |
| `metadata.py` | `metadata_type_list`, `metadata_list`, `metadata_get` |
| `analytics_query.py` | `analytics_query` |
| `analytics_events_enrollments.py` | `analytics_events_query`, `analytics_enrollments_query` (v42 + v41 only — see drift) |
| `maintenance.py` | `maintenance_task_type_list`, `maintenance_dataintegrity_*`, `maintenance_cache_clear` |
| `aggregate_data_values.py` | `data_aggregate_get / set / delete` |
| `tracker_reads.py` | `data_tracker_type_list`, `data_tracker_list`, `data_tracker_event_list` |
| `tracker_workflow.py` | `data_tracker_register`, `data_tracker_event_create`, `data_tracker_outstanding` |
| `metadata_search.py` | `metadata_search` |
| `metadata_usage.py` | `metadata_usage` |
| `route_register_and_run.py` | `route_list`, `route_create`, `route_run`, `route_delete` |
| `user_administration.py` | `user_list / get / me / invite / reinvite / reset-password` |
| `user_groups.py` | `user_group_list`, `user_group_sharing_get` |
| `user_roles.py` | `user_role_list`, `user_role_authority_list` |
| `user_role.py` | `user_role_*` (covers the per-resource verbs alongside `user_roles.py`) |
| `apps.py` | `apps_list`, `apps_hub_list` (with `apps_install_from_{file,hub}`, etc.) |
| `customize_login.py` | `customize_*` — branding + login-page settings |
| `doctor.py` | `doctor_run`, `doctor_bugs`, `doctor_integrity`, `doctor_metadata` |

## Per-version drift (intentional)

| Tree | Difference | Why |
| --- | --- | --- |
| `examples/v43/client/dashboard_item_users.py`<br>`event_visualization_fix_headers.py`<br>`map_basemaps.py`<br>`program_set_labels.py`<br>`program_set_change_log.py`<br>`program_set_enrollment_category_combo.py`<br>`category_combo_coc_regen.py`<br>`removed_resources.py`<br>`section_user_removed.py`<br>`tracked_entity_attribute_favorites.py` | **v43-only** — demonstrate v43 schema changes + write-side setters that don't apply to v41 / v42 (renamed fields, removed resources, new typed attributes, the v43 Program label / change-log / enrollment-CC setters, the BUGS #33 CategoryCombo COC-regen workaround). | See [`docs/architecture/schema-diff-v41-v42-v43.md`](../docs/architecture/schema-diff-v41-v42-v43.md). |
| `examples/v42/client/analytics_events_enrollments.py`<br>`examples/v41/client/analytics_events_enrollments.py`<br>`examples/v42/mcp/analytics_events_enrollments.py`<br>`examples/v41/mcp/analytics_events_enrollments.py` | **Absent on v43** | DHIS2 v43 server-side bug — event-analytics SQL emitter rejects 2024 event data (BUGS.md #36). Workaround: skip the program at trigger time; running the example end-to-end on v43 fails. v41 + v42 are unaffected. |

## Environment

- `DHIS2_URL` — default `http://localhost:8080`
- `DHIS2_PAT` — a Personal Access Token
- `DHIS2_USERNAME`, `DHIS2_PASSWORD` — Basic auth fallback
- `DHIS2_OAUTH_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` / `_SCOPES` — for the OIDC example
- `DHIS2_PROFILE` — pick a named profile from `profiles.toml` without hardcoding creds
- `DHIS2_VERSION` — `41`, `42`, or `43` — picks which stack `make dhis2-run` boots and which example tree `verify_examples` walks
