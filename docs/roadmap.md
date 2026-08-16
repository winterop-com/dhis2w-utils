# Roadmap

A running inventory of what the workspace covers today, gaps surfaced during use, and the near-term plan. Every item is a judgment call about priority, not a commitment.

The FHIR plugin keeps its own plan: roadmap, settled and open decisions, review dimensions, and build measurements all live in the [FHIR roadmap and review guide](project/fhir-roadmap.md), and this page does not restate them.

## Current state

### Workspace surface

| Package | Role |
| --- | --- |
| `dhis2w-client` | Async HTTP client, pluggable auth, typed responses via generated models. Retry policy, task awaiter, connection-pool tuning all first-class. |
| `dhis2w-codegen` | `/api/schemas` → pydantic emitter + OAS spec-patches framework (synthesises Jackson discriminators upstream DHIS2 omits) |
| `dhis2w-core` | Plugin runtime + shared services (profiles, CLI errors, task watch, client context) |
| `dhis2w-cli` | Typer root that discovers every plugin (first-party + entry-point) |
| `dhis2w-mcp` | FastMCP server that mounts the same plugins (the full typed surface) |
| `dhis2w-mcp-bridge` | Single-tool (`dhis2_cli`) MCP bridge for small on-box models; read-only + host write-guard |
| `dhis2w-mcp-router` | Search+dispatch MCP router fronting upstream servers (portable ToolSearch); domain-neutral core, published from 1.2.0 (whether it becomes the default surface for all clients is still data-gated) |
| `dhis2w-browser` | Playwright session helpers (auth through the DHIS2 login form) |
| `dhis2w-bench` | Local/cloud LLM benchmark harness (workspace-only, unpublished) |

### CLI surface

Twenty-one top-level domains: `analytics`, `apps`, `browser`, `customize`, `data`, `datastore`, `dev`, `doctor`, `files`, `maintenance`, `messaging`, `metadata`, `profile`, `query`, `route`, `schema`, `security`, `system`, `user`, `user-group`, `user-role`. Each plugin shares a `service.py` between the CLI and MCP sides; the same typed call from both surfaces.

`d2w metadata` has the full workflow surface:

- **Core CRUD**: `list` / `get` / `patch` (RFC 6902) / `rename` (bulk name/shortName/description add + strip prefix/suffix, `--dry-run`) / `retag` (bulk ref-field + enum rewrites: categoryCombo, optionSet, legendSets, aggregationType, domainType) / `share` (bulk read-merge-write sharing across many UIDs, with `--public-access` / `--user-access UID:access` / `--user-group-access UID:access`, stdin UID input via `-`, `--dry-run`) / `merge-bundle` (import a saved JSON bundle file into a target profile — sibling to the source-profile `merge` verb).
- **Cross-resource search**: `d2w metadata search <query>` — fans out three concurrent `/api/metadata?filter=<field>:ilike:<q>` calls (`id`, `code`, `name`) and merges by UID. Full UID, partial UID, business code, or name fragment all flow through one verb.
- **Bundle operations**: `export` / `import` / `diff` (file-vs-file and file-vs-live) with per-resource filters + dangling-reference warning on export; `diff-profiles` for staging-vs-prod drift.
- **Authoring sub-apps**: `options get / find / sync` for OptionSet sync; `attribute get / set / delete / find` for cross-resource AttributeValue workflows; `program-rule get / vars-for / validate-expression / where-de-is-used`; `sql-view list / get / execute / refresh / adhoc`; `viz list / get / create / clone / delete`; `dashboard list / get / add-item / remove-item`; `map list / get / create / clone / delete`; `legend-sets list / get / create / clone / delete`; four full `X / XGroup / XGroupSet` authoring triples with canonical DHIS2 naming — `organisation-units` / `organisation-unit-groups` / `organisation-unit-group-sets` (plus `organisation-unit-levels` for per-depth rename), `data-elements` / `data-element-groups` / `data-element-group-sets`, `indicators` / `indicator-groups` / `indicator-group-sets`, and `category-options` / `category-option-groups` / `category-option-group-sets`; plus the `program-indicators` + `program-indicator-groups` pair (DHIS2 has no `programIndicatorGroupSet`). Aggregate data-set surface: `data-sets list / get / create / add-element / remove-element / delete` + `sections list / get / create / add-element / remove-element / reorder / delete`. Authoring flip side of maintenance runs: `validation-rules {list,show,create,delete}` + `validation-rule-groups` + `predictors {list,show,create,delete}` + `predictor-groups`. Tracker-schema authoring complete end-to-end: `tracked-entity-attributes` + `tracked-entity-types` (with TETA linkage) + `programs {list,show,create,rename,add-attribute,remove-attribute,add-to-ou,remove-from-ou,delete}` + `program-stages {list,show,create,rename,add-element,remove-element,reorder,delete}`. Category-dimension authoring complete end-to-end: `categories {list,show,create,rename,add-option,remove-option,delete}` + `category-combos {list,show,create,rename,add-category,remove-category,wait-for-cocs,delete,build}` (the `build` verb is the one-pass create-or-reuse helper for the full stack, fed a JSON `CategoryComboBuildSpec`) + read-only `category-option-combos {list,show,list-for-combo}`.

`d2w doctor` runs ~100 checks on a live instance (20 metadata-health probes + 81 DHIS2 integrity checks + BUGS tripwires).

### MCP surface

Roughly 318 tools across 16 plugin groups (`analytics_*`, `apps_*`, `customize_*`, `data_*`, `datastore_*`, `doctor_*`, `files_*`, `maintenance_*`, `messaging_*`, `metadata_*` (~197), `profile_*`, `query_*`, `route_*`, `security_*`, `system_*`, `user_*`). Counts age with each release; the auto-regenerated [MCP reference](mcp-reference.md) is the source of truth. Most operational CLI commands have a matching MCP tool; `d2w dev`, `d2w browser`, and profile mutations are intentionally CLI-only (see the [capability matrix](index.md#capability-matrix)).

There are **three MCP surfaces** over this tool set — the full server, the single-tool bridge, and the search+dispatch router. The [MCP surfaces map](architecture/mcp-surfaces.md) compares them and explains how to choose; all three carry a `*_READONLY` guard.

### Typed models shipped

Via `/api/schemas` codegen (`generated/v{41,42,43}/schemas/`):

- 100+ metadata resources (DataElement, DataSet, OrganisationUnit, Indicator, Program, …) with full CRUD accessors including the RFC 6902 `patch(uid, ops)` method
- 77+ `StrEnum`s for CONSTANT properties (ValueType, AggregationType, DataElementDomain, …)
- A shared `Reference` with both `id` and `code` fields

Via `/api/openapi.json` codegen (`generated/v{N}/oas/`, currently populated on v41, v42, v43):

- Every `components/schemas` entry — 562 classes + 260 StrEnums + 104 aliases on v42; 984 classes on v43.
- Consumers in `dhis2w-client`: `envelopes.py`, `auth_schemes.py`, `aggregate.py`, `system.py`, `maintenance.py`, and `generated/v42/tracker.py` are all thin shims over the OAS output.
- Emitter is deterministic + version-scoped; `d2w dev codegen oas-rebuild --version v{N}` regenerates from the committed `openapi.json` without network.
- **Spec-patches framework** for known-upstream OAS gaps (`dhis2w_codegen.spec_patches`). Each patch is idempotent + carries a `bugs_ref` pointer; the rebuild log names which gap was worked around. Current patches: `*AuthScheme` discriminators (BUGS.md #14 — still unfixed in v43).

Remaining hand-written in `dhis2w-client` (by design):

- `WebMessageResponse` subclass + `DataIntegrityReport` / `DataIntegrityResult` / `Me` / `Notification` — helper methods and client-side convenience shapes that aren't in OpenAPI.
- `AnalyticsMetaData` — typed parser helper over `Grid.metaData` (a bare `dict[str, Any]` on the wire). `Grid` / `GridHeader` come straight from the OAS codegen.
- `TrackerBundle` — the `POST /api/tracker` envelope isn't in OpenAPI under that name. Thin wrapper on OAS tracker models.
- `PeriodType` + `RelativePeriod` StrEnums (24 period frequencies + 45 rolling windows; upstream Java enums the OpenAPI schema doesn't expose — see BUGS.md #28).

### Typing posture

The four-PR typing sweep (#71-#74) plus the codegen discriminator synthesis (#76) eliminated every `dict[str, Any]` signature that crosses module boundaries outside the explicit HTTP-boundary carveouts. Every service-layer function returns a typed pydantic model; MCP tools dump at the edge via `_dump_model`; CLI handlers dump for JSON output or Rich tables. The CLAUDE.md "no dict[str, Any] across module boundaries" rule is enforced workspace-wide.

### Runtime features

- `--profile/-p` global override + `~/.config/dhis2/profiles.toml` or `./.dhis2/profiles.toml` auto-discovery
- `--debug/-d` global flag → stderr HTTP trace lines via `dhis2w_client.http` logger
- `--watch/-w` on job-kicking commands (`analytics refresh`, `maintenance dataintegrity run`) + standalone `maintenance task watch` with Rich progress UI
- `--json` opt-in on every write command; concise one-line summary by default
- Typed `Dhis2ApiError.web_message` parses the envelope on 4xx so the CLI surfaces `conflicts[]` / `importCount` / `rejectedIndexes[]` detail
- Client-side UID generation (`generate_uid`, `generate_uids`); no `/api/system/id` round-trip
- External plugin loading via `importlib.metadata.entry_points(group="dhis2.plugins")` — see `examples/plugin-external/` for a minimal runnable reference
- **Retry policy** with exponential backoff + jitter + `Retry-After` header honouring. Idempotent-only by default; opt in for POST/PATCH per policy. Threads through `Dhis2Client(retry_policy=...)` and `open_client(profile, retry_policy=...)`.
- **Library-level task awaiter** — `client.tasks.await_completion(task_ref)` blocks until DHIS2 reports `completed=True`; `iter_notifications` for streaming renderers.
- **Connection-pool tuning** — `Dhis2Client(http_limits=httpx.Limits(...))` / `open_client(profile, http_limits=...)` for sizing against the real DHIS2 capacity.
- **Data-integrity streaming iterator** — `client.maintenance.iter_integrity_issues(...)` yields `IntegrityIssueRow`s (issue + owning check's name / displayName / severity) as a flat stream.
- **Files plugin** — `d2w files documents {list,get,upload,upload-url,download,delete}` + `d2w files resources {upload,get,download}`.
- **System metadata cache** — TTL-bounded per-client in-memory cache on `client.system` for `info()` / `default_category_combo_uid()` / `setting(key)`. 300 s default TTL.
- **Bulk delete on `client.metadata`** — `delete_bulk(resource_type, [uids])` + `delete_bulk_multi({...})` wrap `POST /api/metadata?importStrategy=DELETE`.
- **`client.metadata.search`** — cross-resource UID / code / name search; three concurrent `/api/metadata?filter=<field>:ilike:<q>` calls merged client-side with UID dedup. Typed `SearchResults(query, hits: {resource: [SearchHit, ...]}, total)`.
- **`client.visualizations`** — `VisualizationSpec` typed builder (chart type, data elements, indicators, periods, relative periods, legend set, placement overrides) + `create_from_spec / clone / list / delete` accessor. `RelativePeriod` StrEnum covers the 45 rolling windows upstream OpenAPI exposes as boolean flags.
- **`client.maps`** — `MapSpec` + `MapLayerSpec` typed builder with `indicators`, `legend_set`, thematic / boundary / facility layer kinds; parallels the viz accessor.
- **`client.dashboards`** — `DashboardSlot` + `add_item` / `remove_item` on the dashboards accessor, no round-trip of the whole dashboard.
- **Streaming data-value-set import** — `client.data_values.stream(source, content_type=...)` feeds httpx's chunked transfer directly from a `Path`, `bytes`, sync / async iterable, or async generator. JSON / XML / CSV / ADX.
- **Streaming analytics export** — `client.analytics.stream_to(destination, *, params, endpoint="/api/analytics.json")` pipes httpx's chunked response straight to disk via `aiter_bytes`.
- **Multi-instance metadata diff** — `d2w metadata diff-profiles <a> <b> -r <resource>` exports two registered profiles concurrently and diffs them structurally.

### Seed fixture

The committed e2e dump (`infra/v42/dump.sql.gz`) mirrors DHIS2 Play's Sierra Leone immunization demo with workspace-local additions: 1332 org units with GeoJSON geometries, 67 data elements, 3 indicators, 3 programs (Child Programme + Antenatal = tracker; Supervision visit = event), 2 datasets, 3 dashboards, 23 visualizations built programmatically via `VisualizationSpec` + 1 `EventVisualization` for the supervision program attached to the Immunization data dashboard, 8 maps built via `MapSpec`, 188k aggregate data values, 500 tracker entities, 12 sample supervision events covering 2024 monthly, 6 program rules + 10 program indicators. Workspace fixtures layered on top (`infra/scripts/seed/workspace_fixtures.py`): `SNOMED_CODE` attribute, `VACCINE_TYPE` option set with 5 fixed-UID options, 3 SqlViews (VIEW / QUERY / MATERIALIZED_VIEW), 2 BCG predictors + PredictorGroup + 2 output DEs, 2 BCG validation rules + ValidationRuleGroup, 4 named OrganisationUnitLevel records (Country / Province / District / Facility), 1 LegendSet (`LsDoseBand1`) attached to the Measles + Penta-1 monthly column charts. `make refresh-and-verify` wipes the stack, rebuilds the dump, runs every non-interactive example end-to-end, and reports a pass/fail summary as the regression gate. Skipped examples are the ones that need a real browser session (OIDC-login flows including the Playwright-driven variant), out-of-process screenshots, very long-running analytics jobs, or external network deps — the make target prints the per-run count.

### CI

- `.github/workflows/ci.yml` runs `make lint && make test && make docs-build` on every PR
- `.github/workflows/e2e.yml` nightly — full DHIS2 stack + seeded fixtures + slow integration tests

Public distribution is now active — every workspace member (except `dhis2w-codegen`) publishes to PyPI under its own name. Tags use the `vX.Y.Z` scheme + a `CHANGELOG.md` lives at the repo root. See [Releasing to PyPI](releasing.md) for the cut workflow.

### Docs

- Auto-generated **CLI reference** (`docs/cli-reference.md`, ~10,300 lines from the Typer app) + **MCP reference** (`docs/mcp-reference.md`, roughly 318 tools across 16 groups from the FastMCP server). Both regenerated on every `make docs-build`; the counts age with each release.
- **Narrative tutorials**: `docs/guides/cli-tutorial.md`, `docs/guides/client-tutorial.md`, `docs/guides/visualizations.md` (step-by-step viz + dashboard composition).
- **Examples index** (`docs/examples.md`) catalogues the canonical v42 example set spread across cli / client / mcp on the v42 tree; v41 + v43 mirror most of them. Per-version totals printed by `ls examples/{cli,client,mcp}/` (the source of truth). Tracker-schema authoring examples (steps 1 / 2 / 3 under `examples/cli/tracker_*.sh`) round-trip the full chain end-to-end.
- **Architecture docs** cover every plugin, the client, auth, profiles, codegen, typed schemas, plugins runtime, external plugins, MCP, versioning, browser automation.
- **`BUGS.md`** — over 70 upstream DHIS2 quirks with live `curl` repros + v43 re-audit status (entry count drifts as new ones land; the file itself is the source of truth).

### Test coverage

Roughly 4,500 tests collected (`uv run pytest --collect-only -q | tail -1` is the source of truth); the mocked tier runs in seconds via `make test`, and the slow-marked + contract tiers run in `make test-slow` / `make test-contract` against a live stack (Playwright PAT creation, dashboard screenshot capture, Playwright-driven OIDC login, contract tests against `play.im.dhis2.org/dev-2-{42,43}`). Unit + CliRunner + respx-mocked HTTP; integration paths use in-process FastMCP `Client` against the real plugin tree. `make coverage` runs branch-coverage locally + on every CI run (produces `coverage.xml` as an artifact); the per-PR floor is set at 70%.

Detailed test gaps + the planned next moves are in [Testing roadmap](#testing-roadmap) below.

### Upstream quirks tracked

Roughly seventy entries in the repo-root `BUGS.md` (the file is the source of truth — `grep -c '^- \[#' BUGS.md` prints the live count); the security-scanner cycle added the #50-#61 cluster. Recent additions cover the seed / workflow cycle: DataSet Hibernate flush ordering (#23), Person-TET built-in name collisions (#24), admin OU scope cached per session (#26), fresh-install flakiness on first metadata import (#27), `RelativePeriods` OAS schema shape (#28), `/api/metadata` ignoring `rootJunction` (#29 — the reason `metadata search` has to fan out N requests instead of one), App Hub `versions[*].created` returning epoch-millis ints instead of ISO-8601 strings (#30), and the predictor-expression parser rejecting uppercase aggregators (#31 — forces `avg()` / `sum()` lowercase even though DHIS2 docs use uppercase). The v43-specific cluster (#33–#38) plus the v41 OAuth2 wire-shape quirk (#39) round out the recent set.

## Gaps surfaced during use

### Authoring surfaces

The organisation-unit PR (#174) set a template — canonical DHIS2 resource names, hand-written accessors, per-item membership shortcuts, no `*Spec`. The triples sweep (#174 / #175 / #176 / #180 / #181), aggregate data-set surface (#185), validation-rule + predictor CRUD (#186), the full tracker-schema stretch (TET + TEA #188, Program + PTEA + OU #189, ProgramStage + PSDE #194), and the category-dimension stack (Category #205, CategoryCombo + read-only CategoryOptionCombo #208, the one-pass `CategoryComboBuilder` helper #209) have all landed on top of it. **No metadata-authoring gaps remain on the main workflow paths.**

Optional `ProgramStageSection` grouping (rarely used in practice) is still unauthored; reach for `metadata patch` for it. That's the only known absence and it stays parked unless a concrete caller surfaces.

### Security plugin: read-only posture scanner

`d2w security` ships a read-only DHIS2 security scanner. Alongside `settings` (the
security slice of `/api/systemSettings`) and `authorities` (the caller's effective
authorities, categorised), the headline command is `d2w security audit`: it runs the
full 14-check catalog step by step, streams a crash-safe, resumable report to a run
folder in four human formats (md/txt/csv/html) plus a JSONL machine spine, and
prints a severity scorecard. `d2w security report <folder>` re-renders any format
from the spine without re-scanning.

The 14 checks (in run order): version, transport, settings, authorities, roles,
hygiene, credential-probe, guest, apps, sharing, auth-methods, tokens, routes,
audit-config. Highlights: an opt-in `admin/district` default-credential probe (one
Basic `GET /api/me`, never retried); an opt-in interactive d3 sharing explorer
(`--sharing-graph`); a routes SSRF check that flags Route destinations on
private/internal/cloud-metadata hosts; a PAT posture check; an external login-methods
(OIDC + OAuth2 client) inventory; and an `audit-config` check whose optional
`--dhis-conf PATH` parses a local copy of `dhis.conf` with secret redaction enforced
by construction. The whole scan is GET-only against an allowlist, with the
credential probe the single deliberate exception (one login attempt) and the release
feed the single external egress. The
[security plugin page](architecture/security-plugin.md) carries the architecture and
the extension recipe.

The cheap MCP read surface has shipped (`security_settings` / `security_authorities` /
`security_version`, read-only single-request tools mirroring the CLI; the long-running
`audit` stays CLI-only). The full 14-check catalog plus the auditor-app gap checks (CSP
directive grading, runtime CORS response headers, HSTS max-age, cross-origin-isolation
headers, all-account hygiene aggregates, password-age, and the route-management
dangerous-authority category) have all landed. The one remaining check item is opt-in
js-x-ray static analysis of installed-app JavaScript bundles, deferred as a post-release
sub-project with its own same-origin bundle-fetch guardrail surface.

Follow-ups deferred from the PR #452 review, in priority order:

- **Make the HTML report bundle genuinely self-contained.** `support.js` loads React +
  ReactDOM UMD builds from unpkg.com at page open (SRI-pinned, but offline the report
  renders a blank page, and opening it phones out to unpkg), and `report.dc.html`
  pulls three font families from Google Fonts. Vendor the two React UMD files beside
  the bundle the way the sharing explorer vendors `d3.min.js`, and vendor or drop the
  web fonts. Highest priority of this list: a security audit report is exactly the
  artifact opened inside restricted or air-gapped networks.
- **Strip the dormant remote-code machinery from `support.js`.** The `x-import`
  subsystem fetches arbitrary external JS/JSX URLs, loads `@babel/standalone` from
  unpkg, and executes fetched code via `new Function(...)`; an editor bridge
  `postMessage`s report metadata to any embedding parent with origin `"*"`. None of it
  is reachable from the shipped template today, but it is live, unreferenced attack
  surface inside a security deliverable. The report only needs the template compiler
  and the escaping path. While in there, reword the file header to state provenance
  honestly (adopted transpiler output as source; no build step exists).
- **Sync the feature catalog with the review-round severity changes.**
  `docs/project/features.md` and the CHANGELOG tokens entry still describe the
  pre-review verdicts (expired-but-undeleted PAT as HIGH under the non-expiring
  finding, a MEDIUM token inventory, zero-protection HSTS as WARN) and omit the
  `tokens-expired-not-deleted` control.

Writes (rotating credentials, toggling registration, editing security settings) stay
out of scope until a concrete caller needs them.

### OIDC / OAuth2 polish

- Token refresh is tested in code but undocumented for end users.
- `Local OIDC` login-page button is non-functional for browser clicks (CLI-only `redirect_url`); no per-provider "hide from login UI" flag in DHIS2 v42 — documented in `docs/architecture/auth.md`.
- Bearer-to-JSESSIONID path for browser workflows on OIDC profiles is unverified (flagged in `authenticated_session` docstring).

### d2path evaluator: sharp edges surfaced by the example sweep

Writing evaluator-verified examples for every registry function (the d2path-examples catalog) exposed
three behaviours worth a decision — the examples document actual behaviour, so fixing any of these
means updating the affected catalog entries in the same PR:

- **Literal negative and computed indices raise.** `scores[-1]` and `scores[1 + 1]` fail with
  "index must be an integer" because unary minus / arithmetic always produce a float (`-1.0`), which
  `_eval_index` and `_int_arg` reject — while the bounds check explicitly anticipates negative
  indices, so the intent was for `[-1]` to work. Fix shape: arithmetic on integer operands should
  yield an int (or the index/argument checks should accept integral floats). The same coercion breaks
  `take(-1)`-style arguments.
- **`union()` / `combine()` arguments evaluate against the navigated focus, not the row root.**
  `a.union(b)` over `{a: [1,2], b: [2,3]}` yields `[1,2]` (b resolves to `[]` against the int focus),
  so neither "merge two sibling fields" nor "union with a literal set" works as a naive user expects —
  and an array-literal argument arrives as one nested element (`a.union([3,4])` appends `[3,4]`
  whole). Decide whether args should get root/parent scope (likely a spec question) or whether the
  docs stance (use sub-selections of the same focus) is the intended semantics; either way the
  cookbook and catalog steer users to working forms today.
- **Out-of-bounds vs negative index asymmetry.** OOB returns `[]` silently; negative raises — the
  visible symptom of the float-coercion bug above. Resolves with it.
- **Singleton-only string functions return `[]` silently over multi-element focus.**
  `name.upper()` over two rows yields `[]` (the `_string` helper requires a singleton), while
  `name.select(upper())` maps correctly. Silent-empty is the sharp part — an EvaluationError
  ("upper() needs a singleton; map with select()") would turn a confusing no-op into a teachable
  error. The dhis2w-ql README documents the `select(...)` idiom in the meantime.

### Session-cookie auth: follow-ups

The session auth kind (#438) plus its parity pass (browser workflows, verify diagnostics, cookie
validation, env caveat — #439) leave these open, none blocking:

- **Expired-session verify signal.** The client maps only HTTP 401 to `AuthenticationError`; a DHIS2
  that answers an expired-cookie `/api/*` request with a 302-to-login surfaces as a confusing
  `Dhis2ApiError(302)` / empty-body error instead of the 401-flavored failure the kodo panel's expiry
  detector expects. Needs a live test against a genuinely expired cookie per supported DHIS2 version;
  if the redirect is real, map redirect-to-login on API calls to an auth-flavored error (and log the
  server behaviour in `BUGS.md`).
- **Non-TTY fail-fast for secret prompts.** All four `profile add` secret branches (pat / basic /
  oauth2 / session) fall into an interactive hidden prompt when the env var is unset or empty; in a
  non-TTY subprocess that blocks on an open stdin pipe or dies with a generic `Aborted.`. A shared
  capture helper should fail fast with "set <ENV_VAR> or run interactively" when stdin is not a TTY.
- **Per-auth-kind descriptor table before the next kind lands.** Adding `session` meant touching five
  enumerations per tree (provider factory, probe auth, colorize, env export, add branch) and initially
  missed two more (show masking, browser mint). Consolidate the per-kind knowledge — provider
  constructor, secret field, env var, prompt label, table color — into one descriptor before a
  service-account JWT or OIDC-federation kind repeats the scatter. `_build_probe_auth` restating
  `build_auth_provider` folds into the same cleanup.
- **`dhis2://target` MCP resource on the bridge.** kodo currently gets bound-state/expiry data by
  polling the `dhis2_cli` tool with `profile verify`; a proper MCP resource is the cleaner long-term
  shape for "what instance/user am I bound to".
- **Direct unit test for `pat_registration.register_pat`.** The self-service PAT mint (kodo's primary
  path) is only exercised indirectly today.
- **Cookie storage escape hatch.** If rotation frequency ever makes `profiles.toml` rewrites a
  problem, the sqlite token store's columns already fit (cookie -> access_token, expires_at); recorded
  as an option, not a plan.
- **Profile test-tree conftest.** The `TREES` parametrization + `_isolated` env fixture exist as four
  verbatim copies (and have already drifted on which env vars they strip); promote them to
  `packages/dhis2w-core/tests/profile/conftest.py`.

### Metadata listing consolidation

Listing collapsed onto one surface — generic `metadata list <type>` + the `metadata_list` MCP tool (see the 2026-06-04 decisions-log entry). Three follow-ups remain:

- **Re-expose type-specific list filters + curated columns.** The dropped typed lists had ergonomic filters (`--domain-type`, `--program-type`, `--period-type`, viz `--type`, …) and resource-aware columns. They currently round-trip through the generic `--filter <prop>:<op>:<value>` DSL. Design how to surface the common ones on the canonical command/tool (named convenience flags? a per-resource filter registry?) before migrating docs/examples, so the rewrites aren't redone.
- **Guard the `/api/metadata?<resource>=true` bundle export against giant payloads.** For organisation units this can embed geojson geometry and balloon to a size that can overload the server. Needs a size/field guard (or a refusal with a `--fields` hint) on `metadata export`; warrants a `BUGS.md` entry once characterized with a repro.
- **Migrate docs/examples** — largely done. The stale references were swept: the removed `metadata_<type>_list` MCP example calls moved to the generic `metadata_list(resource=...)`, the removed `option-sets attribute` CLI subgroup to `metadata attributes`, and `user-group` / `user-role` to `user group` / `user role`; the showcase doc examples were fixed. `infra/scripts/check_example_refs.py` (wired into `make check-examples` + CI) now resolves every example's CLI command paths against the Typer tree and every `call_tool` name against the live MCP tool set, so this class of drift fails the fast suite instead of surfacing only in nightly e2e.

### Small-model bridge: CLI read-surface follow-ups

Surfaced by the `dhis2w-mcp-bridge` gap probes (small local models driving the CLI). Shipped: camelCase discovery + did-you-mean, `type list --json`, `show`→`get` help, the rewritten `dhis2_cli` docstring (incl. `search`/`usage`/field-presets/nested-filters/export-warning + a WRITES primer), single-string-arg tolerance, paging help, `--filter` nested/`in`/`null` help, read-only allowlist for `metadata usage`/`export`, the analytics/tracker/aggregate help-text fills, the tracker `--program` fix, malformed-UID pre-validation on `metadata get` (BUGS #47), relationship mutators + deletes honor `--json`, headless `route create` (`--no-auth` + clean ValidationError), `files documents list --details` (no more filename-as-FR-UID), and `metadata share` accepting the plural type. See `docs/notes/small-model-bridge.md` + `docs/notes/bridge-verification.md`. Remaining:

- **Removed typed `list` discoverability** — point `metadata <subapp> list`/`show` at `metadata list <type>` / `get` (hidden redirect commands or epilog).
- ~~**Missing authoring verbs: `optionSets` + `userGroups` `create`/`delete`**~~ Shipped: `metadata option-sets create/delete` + `user-group create/delete` (build the schema, POST via `resources.<accessor>.create`, return a typed WebMessageResponse). v41/v42/v43 + tests + examples.
- ~~**Inline tracker delete**~~ Shipped: `data tracker delete` / `event delete` / `enrollment delete` via `delete_tracker_objects` (minimal bundle + importStrategy=DELETE). v41/v42/v43 + tests + examples.
- **`data aggregate get` is keyed by dataSet, `set` by dataElement** — can't verify a write with the same key; consider a `--de` filter on `get`.

## Near-term plan (next 3–5 PRs)

Latest cycle closed the **category-dimension strategic option** (Category #205, CategoryCombo + read-only CategoryOptionCombo #208, the one-pass `CategoryComboBuilder` create-or-reuse helper #209) plus the smaller `metadata merge-bundle` verb (#206). With every authoring path on the main workflow now covered, the codegen emitters fully regen-stable, and bulk verbs (rename / retag / share) shipped on top of `patch_bulk` / `apply_sharing_bulk`, the obvious tactical sweep is complete.

**The near-term slate is once again open.** The multi-version CI integration matrix (long-standing carry-over) and the `*Spec`-class audit are both resolved — the matrix runs `e2e.yml` across `dhis2_version: [41, 42, 43]` nightly; the spec audit settled on `VisualizationSpec` / `MapSpec` + `MapLayerSpec` / `LegendSetSpec` + `LegendSpec` (the rule for when a spec is justified is documented on `api/legend-sets.md`).

The natural next direction is one of:

- **Pick one of the two remaining strategic options** below and commit to a multi-PR body of work (data approval workflow, or audit log reader).
- **Promote a medium-term tactical item** (client cold-open latency, the A4 filter-DSL / URL property tests) for a focused 1-PR cycle.
- **Land the security-report follow-ups** (vendored React + fonts, `support.js` trim) — see the security plugin section above.
- **Start A6** (plugin coverage gaps) — the main remaining Tier A testing item.

Demoted / parked:

- `apps snapshot` example + CI hook — the feature works, just the `restore --dry-run` demo still isn't in `examples/cli/apps.sh`. Low value without an active need.
- `ProgramStageSection` grouping — rarely used in practice; `metadata patch` covers the occasional need. Promote if a concrete caller surfaces.

BUGS.md #15 (undiscriminated `JobConfiguration.jobParameters` + `WebMessage.response` unions) stays off the near-term list: the sibling-field discriminator pattern doesn't fit the AuthScheme-style spec-patches approach, and the scheduler plugin isn't an active workflow. Revisit when someone hits a real-world need.

## Strategic options (pick one before the next cycle)

Two independent directions — the right order depends on where the pain is. Each would be a multi-PR body of work.

### 1. Data approval workflow plugin

`/api/dataApprovals` + `/api/dataApprovalLevels` + `/api/dataApprovalWorkflows` cover multi-level aggregate approval (district → zone → ministry sign-off). Common in humanitarian + government reporting pipelines. Surface:

- `d2w dataapproval status <ds> <pe> <ou>` — which level is this cell at? `APPROVED_HERE / APPROVED_ABOVE / UNAPPROVED_READY / UNAPPROVED_WAITING`.
- `d2w dataapproval approve / unapprove / accept / unaccept` — the four write verbs.
- `d2w dataapproval bulk-status <ds> <pe>` — every org unit for one dataset-period, exit-on-incomplete mode for CI.
- Typed `DataApprovalStatus` enum + level-aware state machine.

### 2. Audit log reader

DHIS2's `/api/audits/*` endpoints track every write by user / timestamp / entity-uid (for DE values, tracker payloads, metadata changes). No wrapper today; integrations that need a "who changed X and when" history have to hand-build URLs.

- `d2w audit data-values --de <uid> [--ou <uid>] [--pe <pe>]` — stream every change for a cell.
- `d2w audit metadata --klass DataElement --uid <uid>` — metadata edit history for one resource.
- `d2w audit tracker-entity <uid>` — tracker write audit.
- `client.audit.iter_data_values(...)` / `iter_metadata(...)` async iterators for library callers.

Niche but valuable for compliance + forensics use cases.

## Medium-term

- **Multi-version CI matrix** — shipped (#236). `e2e.yml` runs nightly across `dhis2_version: [41, 42, 43]` matrix.
- **Cold-open / import latency (priority: client > MCP > bridge).** What matters is how fast a *process* becomes usable — library scripts (`from dhis2w_client import Dhis2Client`), each `dhis2w-mcp-bridge` spawn, and the MCP server boot — not `d2w --help`. Measured with `python -X importtime` on the venv interpreter (post-#395):
  - **`from dhis2w_client import Dhis2Client` — ~530 ms** (bare `import dhis2w_client` is already ~3 ms via the package's PEP 562 `__getattr__`). `importtime` attributes **~458 ms to `dhis2w_client.generated.v42.oas`**: importing the client pulls `generated/v42/resources.py`, which does `from .schemas.<x> import <Class>` at module top for every accessor → all 562 generated schema classes load eagerly, even though a given call touches a handful. **This is the top lever in the repo.** Fix: lazy schema imports on the resource accessors (PEP 562 `__getattr__` on `generated/v{N}/resources.py` + `schemas/__init__.py`, or per-accessor deferred import), so client cold-open falls toward the ~60 ms httpx+pydantic floor. Target **< 100 ms**. Effort: medium — codegen-template change across v41/v42/v43, and must keep FastMCP forward-ref resolution working (the `MockValSer`/`SchemaSerializer` trap that sank the earlier `perf/lazy-oas-init` branch — siblings must still resolve when only one schema submodule is loaded).
  - **MCP `build_server()` — ~2.0 s** — `_eager_rebuild_tool_return_types()`'s `model_rebuild()` loop (~900 ms) + the 458 ms client/OAS import + fastmcp/mcp framework. Fixing the client lazy-import removes the 458 ms for free; the rebuild stays correct-by-necessity (FastMCP serialises tool returns without prior validation) but could be narrowed to only classes reachable from a registered tool, or deferred to first-serialise per class. One-time on a long-lived server → second priority.
  - **`import dhis2w_mcp_bridge` — ~440 ms** — `fastmcp` (~196 ms) + `mcp` (~152 ms) framework import; the bridge shells out to `d2w` so it never touches the OAS tree. Matters because every local-model bridge round cold-opens the process. Less actionable (third-party); defer the `fastmcp` import until the server starts, or trim to the minimal MCP server surface. Lowest of the three.
  - **Stale claim corrected:** the old "`d2w --help` ~2 s, target < 400 ms" no longer holds — post-#395, `d2w --version` and `d2w metadata --help` are ~0.6 s. The remaining real cost is the client OAS import above, not Typer/plugin construction.
- **Other measured perf items** (independent; from a sweep — file:line + rough effort/payoff):
  - **`apps update_all` is sequential** (`v42/plugins/apps/service.py:213`) — N installed apps updated one POST at a time; `asyncio.gather` them. ~5 min, saves N-1 round-trips.
  - **HTTP pool defaults untuned** (`dhis2w-client/v42/client.py`) — httpx defaults (100 max / 20 keepalive) cap high-fan-out `asyncio.gather` callers; document/raise `http_limits` for bulk workflows.
  - **Browser screenshot loops sleep a fixed 2 s/item** (`v42/plugins/browser/service.py:346,465`) — poll for render (Playwright `wait_for_load_state`) instead; ~1-2 s/item on large map/visualisation runs.
  - **`verify-examples` runs strictly sequentially** (`infra/scripts/verify_examples.py` `run_suite` loop) — ~1000 s for ~180 examples against one shared stack. Read-only examples (~60%) could run under a bounded asyncio semaphore (3-4×) with writes kept serial; biggest CI/dev-loop win but medium effort + write-race risk.
  - **`verify-examples` `.py` examples spawn `uv run python`** — pin the venv interpreter once and invoke it directly to shave per-spawn `uv` resolution (~30-50 s across the suite).
  - **`make lint` mypy/pyright are non-incremental** — add mypy `incremental = true` (and optionally `dmypy`) for 3-10× faster local re-lints (CI cold-cache unaffected).
  - **CI e2e installs Playwright Chromium on every matrix leg** — cache `~/.cache/ms-playwright` across the v41/v42/v43 legs (~2-6 min/run).
- **Property-based testing on filter / order DSL parsing.**

## Long-term / exploratory

- **Further `dhis2w-browser` workflows**, layered on `authenticated_session`: Maintenance app driving (actions that don't have REST), Org-unit-tree drag-drop edits. Dashboard creation is covered by the REST `DashboardsAccessor.add_item`; layout drag-drop is UI-only but deferred until a concrete need appears.
- **Scheduled jobs plugin (`/api/jobConfigurations`)** — blocked on BUGS.md #15 (undiscriminated `jobParameters` + `WebMessage.response` unions). Revisit when the OAS discriminator is fixed upstream, or when a concrete scheduling workflow forces us to hand-roll typed payloads for the common job types.
- **Interactive aggregate-data-entry TUI** — `d2w data entry <ds> <pe> <ou>` launches a terminal spreadsheet bound to one data set × period × org unit. Questionary or textual for the UI; posts via `client.data_values.stream` on save. Powerful offline-capable data-entry fallback when the UI is down.
- **`dhis2w-chrome` — local-LLM browser extension (PII-safe).** A Chrome extension that drives DHIS2 from the browser using a **local** LLM — it `fetch`es the user's on-box OpenAI-compatible endpoint (LM Studio / Ollama on `localhost`) instead of a cloud API, so patient/tracker data never leaves the machine. The competitive wedge over cloud-based competitor extensions: those are legally unusable for PII deployments (health-data law), where a local extension is the *only* option. Reuses the local-inference foundation (the `ModelBackend` story, model selection, the bridge's discovery lessons). Same decision boundary as everywhere else — local for PII, cloud for aggregate. Alternative in-browser routes (WebLLM/transformers.js via WebGPU; Chrome's built-in Prompt API / Gemini Nano) are weaker and parked. A new product surface (the repo has `dhis2w-browser` for Playwright automation, not an extension); post-1.0.
- **Router as the default MCP surface for *all* clients (cloud + local)?** — `dhis2w-mcp-router` (search+dispatch over upstream MCP servers; see [surfaces](architecture/mcp-surfaces.md) + [design](architecture/mcp-router.md)) is a strong candidate to become the *recommended* entry point for everyone, not just small local models. It future-proofs against tool-surface growth (more DHIS2 tools never inflate the model's context — search is lazy), gives one chokepoint for read-only/host/audit policy, federates multiple servers, and offers typed discovery (validated: `gemma-4-26b-a4b-qat` drove the full 311-tool surface through it at 16k context). **But "for all" is not yet earned** — it has real trade-offs vs connecting to the full server directly: a `search_tools` round-trip per task (extra latency a capable cloud model holding the full payload avoids), a proxy hop + failure point, and a hard dependence on search *quality* (keyword ranking is crude today — a missed search = a tool the model can't reach; the full surface has no "search missed it" failure mode). The decision is **gated on data**: the `bench-router` lane (local models over router vs direct full-mcp vs bridge) plus embeddings-based ranking should settle whether router-for-all holds, or whether the honest answer is "router default for local + growing surfaces; direct full server as the low-latency escape hatch for capable cloud; bridge as the max-simplicity/max-security option." Don't promote it to default-for-all until the numbers say so — same measure-don't-assert discipline as the oracle.
- **Multi-backend `ModelBackend` (Ollama / llama.cpp)** — the local-model validation harness (`packages/dhis2w-bench/src/dhis2w_bench/backend.py`) abstracts model lifecycle (list / load / unload / server / chat-url) behind a `ModelBackend` Protocol, with `LmStudioBackend` the only implementation today (selectable via `MODEL_BACKEND`). Adding `OllamaBackend` (auto-loads on first request, evicts by keep-alive, size via `/api/tags`) and `LlamaCppBackend` (one model per `llama-server` process, or llama-swap) would let the benches drive any local runtime. The inference call is already portable (OpenAI-compatible `/v1`); only lifecycle differs. This is really a standalone-tool concern — the general bench + `ModelBackend` + `bench-list` are DHIS2-agnostic and could extract out of the workspace entirely (only `bench-bridge` is inherently dhis2w). Interesting side project; parked until a non-LM-Studio runtime is actually in play.

## Testing roadmap

The unique shape of this project — **we generate code from a moving REST API, then hand-write CLI / MCP / auth layers on top** — dictates the testing surface. Bugs slip in at five layers, each best caught with a different tool.

### Layered overview

| Layer                  | What can break                                                  | Today                                                                       | Strongest tool                                |
| ---------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------- |
| Static                 | Type errors, unused imports, dead code                          | ruff + mypy + pyright (good)                                                | + add `deptry` for unused / missing deps      |
| Unit                   | Pure logic, parsers, builders                                   | ~4,500 tests, respx-mocked HTTP (good)                                      | + property-based + mutation                   |
| Codegen                | Generator emits wrong code                                      | Snapshot tests on the emitted tree pin the diff per PR                      | + mutation tests on the templates             |
| Schema contract        | Generated code stops matching live API                          | `@pytest.mark.contract` suite hits `play.im.dhis2.org/dev-2-{42,43}`        | Widen to more resources + nightly cron        |
| Live integration       | End-to-end against real DHIS2                                   | E2E workflow matrix runs `make test-slow` against docker stack v41/v42/v43  | Add a read-only per-PR contract pass          |
| Examples               | Documented usage drifts from reality                            | `make verify-examples` (nightly E2E) + `check_example_refs.py` resolves every example's CLI/MCP reference in fast CI | Snapshot stdout for diff-against-baseline     |
| Upstream bugs          | Workaround breaks; fix lands and we don't notice                | `@pytest.mark.upstream_bug` pairs bug-still-present + workaround halves     | Lifecycle automation: open issue when bug clears |

### Tier A — high leverage, ~1 PR each

**A1. Schema contract tests against the live play instances (per-PR, read-only).** — **shipped.**
`@pytest.mark.contract` suite + `.github/workflows/contract.yml` cover representative resources against `play.im.dhis2.org/dev-2-{42,43}`. Each test fetches one real instance and runs it through the generated pydantic model, asserting it validates. Catches DHIS2 ship-day API changes before users do. Next iteration: widen the resource set + add a nightly cron alongside the PR-trigger.

**A2. `BUGS.md` regression-suite scaffolding.** — **shipped.**
`@pytest.mark.upstream_bug` marker pairs bug-still-present + workaround halves; see `packages/dhis2w-client/tests/test_upstream_bugs.py`. `make test-upstream-bugs` runs the whole catalogue. Next iteration: lifecycle automation (open a tracking issue when a bug-still-present test starts failing — the signal to delete the workaround).

**A3. Multi-version CI matrix** — **shipped.**
`.github/workflows/e2e.yml` runs nightly across `dhis2_version: [41, 42, 43]`. Each matrix job pulls the matching `infra/v{N}/dump.sql.gz`, brings up `dhis2/core:{N}`, seeds, and runs `make test-slow`. `fail-fast: false` so one version's hiccup doesn't cancel the other; per-job concurrency keyed on the matrix value so matrix jobs don't fight over the run-slot.

**A4. Property-based tests for the parser-shaped code paths.** — **partially shipped.**
`packages/dhis2w-client/tests/test_parser_properties.py` covers UID generation/validation, period parsing round-trips, and the JSON Patch builder with hypothesis strategies. Remaining targets, one PR per parser:

- Filter DSL (`name:ilike:foo`, `code:in:[a,b]`, nested `attributeValues.attribute.id:eq:UID`).
- URL construction — no double-slashes, correct encoding, `.json` suffix on `/api/analytics/*` (BUGS.md #1).

**A5. Generated-code golden snapshots.** — **shipped.**
`packages/dhis2w-codegen/tests/test_snapshots.py` loads each committed `schemas_manifest.json`, runs `emit()` + `emit_from_openapi()` into a tmp dir, and asserts byte-for-byte equality against the committed `generated/v{N}/` tree. Parameterised over v41 / v42 / v43. CI fails the moment codegen drifts from the committed tree.

**A6. Fill plugin coverage gaps (3–5 PRs of test writing).**
Two whole plugins + half a dozen CLIs are far below the 70 % workspace floor. The workspace gate stays green only because the well-covered codegen + client surface averages it out. Per-package gates (B2) would fail these immediately:

| Plugin / file | Current | Notes |
| --- | --- | --- |
| `plugins/aggregate/cli.py` | 33 % | Service is at 76 %; the CLI + MCP wrappers around it lack respx-driven coverage. |
| `plugins/aggregate/mcp.py` | 33 % | Same gap, MCP side. |
| `plugins/dev/admin_auth.py` | 24 % | Highest-priority — admin Basic-auth bootstrap, tested only by integration. |
| `plugins/dev/sample.py` | 20 % | 442 LOC across five sub-modules, no respx tests on the sample-data emitters. |
| `plugins/dev/pat.py` | 40 % | PAT mint / list / revoke through MCP. |
| `plugins/dev/oauth2.py` | 55 % | OAuth2 client CRUD + Bearer-mint paths. |
| `plugins/tracker/cli.py` | 22 % | The most surface-area CLI — register + enroll + event + relationship verbs. |
| `plugins/profile/cli.py` | 25 % | Multi-flow CLI (basic / PAT / OAuth2 / OIDC) — most flows exercised only via the end-to-end example suite. |
| `plugins/route/cli.py` | 37 % | `/api/routes` lifecycle wrappers. |
| `plugins/user/cli.py` | 31 % | User CRUD verbs. |
| `plugins/user_group/cli.py` | 26 % | UserGroup CRUD verbs. |

Each plugin gets one PR: respx-driven happy-path + error-shape tests at the service layer, `typer.testing.CliRunner` smoke tests for every CLI verb, in-process `httpx.AsyncClient` integration through the FastMCP server for the MCP wrappers. Estimate: 5–7 PRs total, ~3–4 days of focused work. Worth doing before pinning per-package gates (B2).

### Tier B — medium leverage, ~2-3 PRs

**B1. Mutation testing nightly.**
`mutmut` or `cosmic-ray` against `packages/dhis2w-client/src/` and `packages/dhis2w-core/src/plugins/*/service.py`. Surface mutations that survive — each survivor is either a missing test or dead code. Run weekly (it's slow); fail when survivor count goes up vs baseline.

**B2. Per-package coverage gates.**
`make coverage` is workspace-wide at 70 %. That hides the case where `dhis2w-client` is at 95 % and a peripheral plugin is at 30 %. Split into per-package thresholds; show a coverage diff in PR comments via codecov / coveralls / a simple gh-action. Pin `dhis2w-client` higher than the rest since it's the public-API surface.

**B3. Tracker write end-to-end test suite.**
Tracker is the most error-prone area (envelope shapes, atomic / non-atomic modes, `importStrategy` semantics, soft-delete behaviour). An integration suite that creates a tracked entity with enrollment + events, updates each via PATCH, deletes them, verifies cleanup. Run nightly across the matrix to catch tracker-specific drift between versions.

**B4. MCP tool catalogue contract test.**
Walk every tool registered by FastMCP, assert:

- Tool input schema is valid JSON Schema.
- Docstring is non-empty.
- Tool name follows `<plugin>_<resource>_<verb>` convention.
- Return-type annotation is a `BaseModel`.

Stops the MCP surface from quietly degrading (missing docstrings, untyped returns).

**B5. Live-instance smoke tests against play, parallel matrix.**
Beyond contract tests (A1) — actual `d2w system whoami`, `d2w metadata list dataElements --limit 5`, etc., run against `play.im.dhis2.org/dev-2-{42,43}` in parallel. Catches "we shipped a release that actually works against real DHIS2."

### Tier C — exotic / specialty

**C1. Snapshot example stdout.**
`make verify-examples` reports PASS / FAIL but doesn't pin output. Add `--snapshot` mode that records stdout into `examples/.snapshots/`. CI fails when output drifts unexpectedly. Catches "still passes" examples that produce subtly different / wrong output.

**C2. Schema drift watcher (weekly cron).**
Cron job that runs `d2w dev codegen diff` against the live play instances. If the committed manifest no longer matches what live reports, post an issue. The "DHIS2 just shipped 2.43.2" early-warning system.

**C3. Performance benchmarks + regression detection.**
`pytest-benchmark` for:

- Client cold-open import time (~530 ms today via the eager OAS tree; target < 100 ms — see the medium-term latency item).
- MCP `list_tools` latency.
- Generated-code import time (the 562 OAS classes pydantic-rebuilds).
- Bulk fetch (1 k metadata items).

Store baselines in CI; fail PRs that regress > 20 %.

**C4. Hypothesis-driven fuzzer for the OAS generator.**
Generate adversarial OpenAPI specs (deeply nested `oneOf`, missing discriminators, recursive refs). Run `oas_emit` against them; assert it doesn't crash; collect cases where it does. One-time investment that finds latent `oas_emit.py` bugs.

**C5. Browser / UI tests.**
Playwright is a runtime dep (for screenshot capture, OIDC login automation), not a test surface. The screenshot output IS the test today — compare PNG to a golden — and that's enough.

### What we're explicitly skipping

- **Load testing.** Not a server; the bottleneck is always the upstream DHIS2 instance, not our client. Premature.
- **Contract testing via Pact / Schemathesis.** The OpenAPI spec is too unreliable (BUGS.md #14, #15, #28 are spec-quality issues). Our own contract tests against live instances pay better.
- **Hypothesis-jsonschema for the OAS models.** Tempting, but the `extra="allow"` shapes spin Hypothesis on impossible negative cases.
- **Mutation testing on generated code.** Mechanically derived; mutations there don't tell us anything we can fix.

### Recommended order

A1, A2, A3, and A5 are shipped; A4 is partially shipped (UID / period / JSON Patch properties landed). The remaining order:

1. **A6 — plugin coverage gaps.** The last substantial Tier A item; do it before pinning per-package gates (B2).
2. **A4 leftovers — filter DSL + URL construction properties.** Small, independent PRs.

Tier B and C defer until Tier A is paying off.

## Reference: dhis2-java-client

Apache-2.0 Java client maintained by the DHIS2 org ([dhis2/dhis2-java-client](https://github.com/dhis2/dhis2-java-client)). Targeted comparison against this workspace as of this writing:

### Already covered here

- Typed `/api/sharing` — `Sharing`, `SharingBuilder`, `ACCESS_*` constants, `apply_sharing` / `get_sharing` helpers. Full parity with the Java client's sharing builder.
- User administration — `d2w user list / get / me / invite / reinvite / reset-password`. User-group + user-role plugins covering membership + authority-bundle flows.
- Branding / theming — `d2w customize logo-front/banner/style/set/apply/show` + `Dhis2Client.customize` accessor. No equivalent in the Java client.
- Auth providers (Basic, PAT, OAuth2); ours is async-first with a typed `AuthProvider` Protocol.
- Generated resource CRUD across v41, v42, v43 (Java is hand-maintained).
- WebMessageResponse envelope parsing; `.import_count()`, `.conflicts()`, `.rejected_indexes()`, `.task_ref()`, `.created_uid()`.
- Full metadata query surface; repeatable `--filter`, `--order`, `rootJunction=AND|OR`, `--page`/`--page-size`, `--all`, `--translate`/`--locale`, every `fields` selector form.
- Metadata bundle export / import / diff + RFC 6902 patch with per-resource filters + dangling-reference warning on export.
- Paging; `list_raw(..., paging=True)` returns the pager; `list(..., paging=False)` walks the full catalog.
- Typed filter values on enum fields; `ValueType.NUMBER` is a `StrEnum`, substitutable into filter strings directly.
- Client-side UID generation; matches the Java `CodeGenerator` algorithm exactly.
- Typed tracker writes; `TrackerBundle` + `TrackerTrackedEntity` / `TrackerEnrollment` / `TrackerEvent` models for `POST /api/tracker`.
- Event + enrollment analytics; outlier detection + tracked-entity analytics.

### Considered, not adopted

- **Fluent query builder (`.addFilter(Filter.eq("name", "Penta"))`)**: the Java client wraps DHIS2's `property:operator:value` string syntax in a chainable builder. Deliberately skipped — Python f-strings make `f"name:like:{name}"` already readable; the builder doesn't buy type safety on the stringly-typed value side; DHIS2's own docs teach the string form.

### Worth evaluating later (Java parity)

- **Domain-specific response types beyond `WebMessageResponse`**: Java has distinct `PagedResponse`, `Stats`, `Response` for different endpoint shapes. We collapse into `WebMessageResponse` + helpers. The OAS codegen already emits the specific shapes (`TrackerImportReport`, `ImportReport`, etc.) — swap on-demand when a specific call site hits friction.

### Beyond Java parity (already shipped)

Items that don't exist in the Java client and now exist here:

- **Retry / backoff** — `RetryPolicy` on `Dhis2Client` + `open_client` with exponential backoff, jitter, `Retry-After` honoured, idempotent-only by default.
- **Library-level task awaiter** — `client.tasks.await_completion(task_ref, ...)` + `client.tasks.iter_notifications(...)`.
- **Connection-pool tuning** — `http_limits` kwarg on `Dhis2Client` and `open_client`.
- **Typed codegen** across five DHIS2 versions via schema-driven emission; Java is hand-maintained.
- **OAS spec-patches framework** — synthesises the Jackson discriminators DHIS2's OpenAPI generator omits (`Route.auth` et al.).
- **Data-integrity streaming iterator** — `client.maintenance.iter_integrity_issues()` yields a flat stream of `IntegrityIssueRow`s tagged with owning-check metadata.
- **System metadata cache** — TTL-bounded in-memory cache on `client.system` for `info()` / `default_category_combo_uid()` / `setting(key)`.
- **Bulk metadata delete** — `client.metadata.delete_bulk(resource_type, uids)` + `delete_bulk_multi({...})`.
- **Cross-resource metadata search** — `client.metadata.search(query)` returns typed `SearchResults` grouped by resource; handles UID / partial UID / code / name in one verb.
- **Typed Visualization + Map + Dashboard builders** — `VisualizationSpec`, `MapSpec` + `MapLayerSpec`, `DashboardSlot`. Chart-type-aware dimension placement, typed data dimensions (DEs + indicators), `RelativePeriod` enum for rolling windows, legend-set support. CLI + MCP surfaces on top.
- **Per-viz + per-dashboard PNG capture** — `d2w browser viz screenshot` + `d2w browser dashboard screenshot` + `d2w browser map screenshot`, Chromium-driven via Playwright session helpers.
- **Typed bulk-save on every generated resource** — `client.resources.<resource>.save_bulk(items)`. Supports `import_strategy` + `atomic_mode` + `dry_run`.
- **`client.metadata.dry_run(by_resource)`** — cross-resource `importMode=VALIDATE` entry point.
- **Streaming analytics export** — `client.analytics.stream_to(destination, *, params, endpoint="/api/analytics.json")`.
- **Messaging plugin** — `d2w messaging {list,get,send,reply,mark-read,mark-unread,delete}` + `messaging_*` MCP tools + `client.messaging` accessor.
- **Validation + predictors workflow** — `d2w maintenance validation {run,result,validate-expression,send-notifications}` + `d2w maintenance predictors run`.
- **Streaming dataValueSets import** — `client.data_values.stream(source, content_type=...)`.
- **Multi-instance metadata diff** — `d2w metadata diff-profiles` exports two profiles concurrently + diffs them.
- **Files plugin** — CLI + MCP + `client.files` accessor over `/api/documents` + `/api/fileResources`.
- **SQL views runner** — `client.sql_views` + `d2w metadata sql-views {list, get, execute, refresh, adhoc}`.
- **Tracker authoring workflows** — `d2w tracker {register, enroll, add-event, outstanding}` verbs + the matching `client.tracker` helpers for operator flows beyond generic CRUD.
- **Rich conflict renderer** — `d2w metadata import` / `d2w data aggregate import` render `/api/metadata` and `/api/dataValueSets` error envelopes as a normalised `ConflictRow` table (object UID → offending property → server message).
- **Apps plugin** — `d2w apps {list, add, remove, update, update --all, reload, snapshot, restore, hub-list, hub-url}` + `apps_*` MCP tools + `client.apps` accessor over `/api/apps` and `/api/appHub`. `update --all --dry-run` previews available hub updates before installing; bundled core apps update in place. `hub-list --search` filters the catalog client-side. `hub-url` read/writes the `keyAppHubUrl` system setting so self-hosted hubs can be wired via CLI. `snapshot --output` pins an instance's app inventory to a portable JSON manifest; `restore <manifest>` reinstalls every hub-backed entry via `install_from_hub`, with a `--dry-run` preview that mirrors `update --all --dry-run`.
- **Metadata cross-instance merge** — `d2w metadata merge <source-profile> <target-profile> --resource ... [--dry-run]` orchestrates export+import in one pass, returning typed per-resource export counts plus the target import's `WebMessageResponse`. Pairs with `diff-profiles` (same resource+filter shape): diff to preview, merge to apply. Sharing blocks are stripped by default to avoid false-positive conflicts from per-instance user/group UIDs. Conflicts on the dry-run and applied paths render through the shared `ConflictRow` Rich table used by `metadata import` (#177), so preview output is immediately actionable without reaching for `--json | jq`.
- **Canonical `X / XGroup / XGroupSet` authoring triples** — sub-apps under `d2w metadata`, one client accessor per resource, following a single canonical-naming rule (lowercase + hyphenate the DHIS2 resource path). Shipped for `organisation-units` (#174), `data-elements` (#175), `indicators` (#176), and `category-options` (#181), plus the `program-indicators` pair (#180 — DHIS2 has no `programIndicatorGroupSet`). Each PR adds 15–19 MCP tools, full CLI verbs (`list` / `get` / `create` / rename-like / per-item membership), and hand-written accessors that return typed generated models. No `*Spec` builders — keyword args on the accessor (continues the spec-audit data point). The indicator accessor exposes `validate_expression(context="indicator")`, the program-indicator accessor `validate_expression(context="program-indicator")`, so callers can pre-flight numerator / denominator / expression references before a failed create. `category-options` additionally ships `set_validity_window(uid, start_date, end_date)` for the validity-window knob unique to that resource.
- **Aggregate data-set authoring** — `d2w metadata data-sets` + `sections` sub-apps (#185). `DataSetElement` + `Section.dataElements[]` are handled as join tables with round-trip helpers: `add_element(ds_uid, de_uid, category_combo_uid=...)` carries the per-set CC override; `sections.reorder(section_uid, [de_uids])` replaces the ordered DE list in one PUT. Docstring calls out the DSE self-ref strip for DHIS2's read/write asymmetry.
- **Validation-rule + predictor CRUD** — `d2w metadata validation-rules` + `predictors` + their groups (#186). Closes the author-then-run gap — `d2w maintenance validation run` / `predictors run` shipped long ago, but rules + predictors themselves couldn't be authored from CLI. Surface assembles `leftSide` / `rightSide` / `generator` Expression sub-objects from plain kwargs.
- **Bulk RFC 6902 patch** — `client.metadata.patch_bulk(resource, [(uid, ops), ...], concurrency=8)` + `patch_bulk_multi(...)` (#187). Client-side fan-out under a semaphore; per-UID failures land in `BulkPatchResult.failures` (with `uid` / `resource` / `status_code` / `message`) instead of raising. Building block for future CLI-level bulk verbs.
- **Bulk sharing** — `client.metadata.apply_sharing_bulk(resource_type, uids, sharing)` + `apply_sharing_bulk_multi(by_resource, sharing)` fan out one `SharingBuilder` payload across many UIDs under a concurrency semaphore. CLI surface as `d2w metadata share <type> [UID...]` with `--public-access` / `--user-access UID:access` / `--user-group-access UID:access` (repeatable) + stdin UID input via `-` so `metadata list ... \| jq -r .id \| xargs metadata share` composes. Per-UID failures land in `BulkSharingResult.failures` with the same row-level table renderer used by `rename` / `retag`.
- **Category dimension authoring (complete end-to-end)** — `d2w metadata categories` (#205) + `category-combos` + read-only `category-option-combos` (#208) + the one-pass `CategoryComboBuilder` helper (#209). Categories accept ordered `--option UID` flags on create + per-item `add-option` / `remove-option` shortcuts. CategoryCombos accept ordered `--category UID` flags + a `wait-for-cocs --expected N` matrix-poll barrier handling DHIS2's async COC regeneration (cold-start can take tens of seconds, especially under arm64 emulation). The `category-combos build --spec FILE` verb walks a declarative `CategoryComboBuildSpec` (JSON or stdin) and ensures every CategoryOption -> Category -> CategoryCombo exists; idempotent, returning a typed `CategoryComboBuildResult` with per-layer created-vs-reused breakdown.
- **Bundle-source metadata merge** — `d2w metadata merge-bundle <target> <bundle.json>` (#206) imports a saved JSON bundle into a target profile. Sibling to the source-profile `merge` verb; same `--strategy` / `--atomic` / `--include-sharing` / `--dry-run` knobs. Useful when the bundle came from a saved `metadata export`, was hand-crafted, or was produced by a non-DHIS2 tool. `MergeResult.source_base_url` is `bundle:<path>` for traceability.
- **Tracker-schema authoring (complete end-to-end)** — `d2w metadata tracked-entity-attributes` + `tracked-entity-types` (#188) covers the leaf resources; `tracked-entity-types add-attribute --mandatory --searchable` round-trips the TETA join table. `d2w metadata programs {list, get, create, rename, add-attribute, remove-attribute, add-to-ou, remove-from-ou, delete}` (#189) covers the middle layer — WITH_REGISTRATION / WITHOUT_REGISTRATION program flavours, PTEA enrollment form linkage, per-item OU shortcuts. `d2w metadata program-stages {list, get, create, rename, add-element, remove-element, reorder, delete}` (#194) covers the inner layer — each stage's ordered `programStageDataElements[]` join table with `compulsory` / `displayInReports` / `allowFutureDate` / `allowProvidedElsewhere` flags. Documents the DHIS2 `mergeMode=REPLACE` requirement on Program + ProgramStage PUT (nested-list removal is additive without it) as a typed client-side workaround.
- **Codegen + base-client gap closure** (#190–#192, #197). Generated `create(item, *, merge_mode, import_strategy, skip_sharing, skip_translation)` + `update(item, ...)` forward the write-flag query params. Every generated resource exposes `add_collection_item(parent_uid, collection, item_uid)` / `remove_collection_item(...)` for per-item POST/DELETE shortcuts. Base `Dhis2Client` ships typed `post(path, body, model=T)` + `put(path, body, model=T)` wrappers (parallels the existing typed `get`). Hand-written accessor sweep across 28+24+10 files replaced `_put_with_replace` / per-item loops / duplicated `_uid_from_webmessage` helpers / single-object `get_raw + model_validate` / paged `list_all` via `resources.X.list(...)` with the new surface. ~700 lines of duplication removed with no behavior change.
- **`d2w metadata rename` + `metadata retag` verbs** — bulk CLI verbs on top of `client.metadata.patch_bulk` (#195, #199, #200). `rename` handles label-field add / strip prefix + suffix (idempotent both directions — won't double-apply, won't no-op-fail). `retag` handles ref-field rewrites (`categoryCombo`, `optionSet`, `legendSets`) + enum field rewrites (`aggregationType`, `domainType`). Both take `--filter` (repeatable, same DSL as `metadata list`) + `--dry-run` + `--concurrency`. Per-UID failures land in the shared `ConflictRow` renderer used by `metadata import`, so operators see row-level detail on partial failures.
- **CI coverage gate + failure threshold** (#196, #202). `make coverage` replaces `make test` in the CI test step; every run uploads `coverage.xml` as an artifact retained 14 days, and fails the build if coverage drops under 70%. Current baseline 73% (85k statements / 7.5k branches).
- **Playwright-driven OIDC login** — `d2w profile login --no-browser` prints the auth URL for copy-paste; `dhis2w_browser.drive_oauth2_login(profile, user, pw)` drives the full flow via Chromium (React login → Spring AS consent → loopback redirect) for CI + headless use cases. `examples/cli/profile_oidc_login.sh` + `examples/client/oidc_login.py` auto-dispatch to the Playwright path when `DHIS2_USERNAME` / `DHIS2_PASSWORD` are in env.
- **Predictor + validation seed fixtures** — the Sierra Leone play42 snapshot now ships 2 BCG predictors (`avg` + `sum` over 3-month windows) + a PredictorGroup + 2 output DEs, plus 2 BCG validation rules + a ValidationRuleGroup that reliably produce violations. `d2w maintenance predictors run --group` and `d2w maintenance validation run --group` have concrete targets out of the box.
- **Interactive CLI pickers** — `d2w profile default` launches an arrow-key menu via `questionary`.

### Beyond Java parity (not yet)

(Empty — major Java-parity gaps are closed.)

## Explicit non-goals

- Python < 3.13. New typing features (StrEnum, TypeAliasType, PEP 604 unions, PEP 695 generics) justify the bump.
- DHIS2 outside v41 / v42 / v43. Older DHIS2 majors and unreleased ones aren't on the support matrix; every backport fork splits the code with no deployed users to justify the split.
- Flask / argparse / raw stdio MCP loops / hand-rolled TOML parsers; every slot has a chosen standard per the CLAUDE.md hard-requirements list in the repo root.
- A second filter DSL layered on top of DHIS2's `property:operator:value` string syntax. See the dhis2-java-client comparison above for the rationale.
- Synchronous client variant. `async` throughout is a hard requirement.
- `dict[str, Any]` crossing module boundaries. CLAUDE.md hard rule; enforced workspace-wide as of the typing sweep (#71-#74, #76). New code that proposes dict-in-signature needs explicit justification referencing a specific HTTP-boundary carveout.
- `d2w program-rule trace` / rule simulator — explicitly declined.

## How this file gets updated

Greenfield voice; edits describe the current state of the plan, not its history. When a near-term item ships, delete it from the "near-term" list (don't rewrite to "already shipped"). Use the PR's own description for the history; this file is always about what's next.
