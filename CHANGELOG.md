# Changelog

## 1.3.0 — 2026-07-12

All publishable packages ship at 1.3.0 in lockstep; inter-package pins move to `>=1.3.0,<2.0`.

### MCP tool annotations

- **Every MCP tool advertises a `readOnlyHint` annotation.** The full `dhis2-mcp` server stamps each
  of its ~315 typed tools with `readOnlyHint` (reads `True`, writes `False`), derived at build time
  from the same read/write name classifier the read-only middleware already uses; the router hints its
  `search_tools` read-only and leaves `call_tool` (the write chokepoint) unhinted. A host that honours
  the annotation — e.g. one that skips its per-action write confirmation for read-only-hinted tools —
  gets frictionless reads while writes still prompt, with no per-tool configuration. A hand-set hint is
  never overwritten, and the hint is present regardless of the `DHIS2_MCP_READONLY` switch. Because the
  name classifier now drives an always-on hint that a client may use to skip confirmations, a
  registry-wide guard asserts no write tool is ever hinted read-only.

## 1.2.0 — 2026-07-12

All publishable packages ship at 1.2.0 in lockstep; inter-package pins move to `>=1.2.0,<2.0`.

### New package

- **`dhis2w-mcp-router` ships to PyPI.** The domain-neutral MCP router — front many upstream MCP
  servers behind two meta-tools (`search_tools` + `call_tool`) so an agent gets lazy, searchable tool
  discovery instead of a huge up-front tool payload — joins the published set as the eighth member.
  Its core depends only on FastMCP + httpx + pydantic (no `dhis2w-*` imports). Install with
  `uv tool install dhis2w-mcp-router`; run it as a stdio MCP server. Read-only mode
  (`MCP_ROUTER_READONLY=1` or per-upstream `"readonly": true`) hides and refuses write tools, and
  ranking is pluggable (keyword by default, optional embedding ranker against an OpenAI-compatible
  `/v1/embeddings` endpoint). Whether the router becomes the default MCP surface for all clients
  remains gated on the `bench-router` numbers.

## 1.1.0 — 2026-07-12

All publishable packages ship at 1.1.0 in lockstep; inter-package pins move to `>=1.1.0,<2.0`.

### Session auth

- **Optional CSRF token for session profiles.** `auth="session"` gains an optional `xsrf_token`
  carrying DHIS2's double-submit CSRF value. When set, `SessionCookieAuth` echoes it as an
  `X-XSRF-TOKEN` header alongside the `Cookie`, which write endpoints on CSRF-enforcing instances
  require; read-only sessions leave it unset and are unaffected. `profile add` reads it from
  `DHIS2_SESSION_XSRF`, `profile env` exports it, and `profile show` masks it like every other
  credential. An empty or whitespace-only value normalizes to unset (header omitted); a non-empty
  value carrying control characters is rejected at construction rather than emitting a malformed
  header at send time.

## 1.0.0 — 2026-07-12

First stable release. All seven publishable packages ship at 1.0.0 in lockstep; the imported
`dhis2w_client` surface, the `d2w` command set, and the MCP tool catalogue are committed under
SemVer from here — breaking changes require a 2.0.

### Data safety

- **Tracker `--dry-run` validates instead of committing.** A dry-run push now sends
  `importMode=VALIDATE`; the previous `dryRun` query parameter was ignored by `/api/tracker`, so a
  validate-only push committed. Pushes are synchronous by default, so per-object import errors
  surface inline instead of behind an async job reference.
- **Destructive commands confirm before acting.** `data tracker delete` (and the event/enrollment
  variants), `maintenance cleanup`, and `files documents delete` / `route delete` / `profile remove`
  prompt for confirmation, with a `--yes` flag to skip. The tracked-entity prompt spells out the
  cascade to enrollments and events.
- **Bulk metadata rename/retag refuse a whole-catalogue mutation.** A no-filter `metadata rename` /
  `metadata retag` requires an explicit opt-in (`--all` plus confirmation); the MCP tools default to
  a dry-run preview.
- **Aggregate data-value writes address the attribute combo correctly** via `cc` + `cp`
  (`--attribute-combo` / `--attribute-option`), matching `/api/dataValues` (see BUGS.md #50).

### Credentials

- Credential fields on the auth providers and `Profile` stay out of `repr()` and are masked in
  `model_dump()` by default; real values are revealed only through an explicit serialization context
  that the `profiles.toml` writer and the OAuth2 token store pass. Secrets no longer leak through
  tracebacks or logs.
- `profile oidc-config` and `browser pat` read secrets from the environment or a hidden prompt
  instead of an argv option.

### Client

- The retry transport now honours `verify` and connection limits; `connect()` closes the HTTP pool
  when the version probe fails; `open_client` accepts a `verify` passthrough; `VersionPinMismatchError`
  is exported at the top level.
- `build_auth_for_basic` is now `build_auth_provider` (it builds PAT, Basic, and SessionCookie
  providers from a profile).

### MCP and bridge

- The read-only guard (`DHIS2_MCP_READONLY`) classifies tools by explicit write verbs, so group
  membership and status writes are refused; the CLI bridge decides read-versus-write by the command
  verb rather than by help/version tokens appearing as option values.

### Query engine (d2ql)

- `matches()` rejects catastrophic-backtracking patterns; numeric coercion raises `D2qlError` rather
  than a raw `OverflowError` / `ValueError`; `read()` and file sinks are gated behind an opt-in flag
  for library embedders (the CLI keeps them enabled).

### Packaging

- Every publishable package carries license metadata, project URLs, and production classifiers;
  the workspace-only `dhis2w-codegen`, `dhis2w-bench`, and `dhis2w-mcp-router` are marked
  no-upload. Inter-package pins move to `>=1.0.0,<2.0`.

## 0.99.1 — 2026-07-11 (dhis2w-ql only)

- **A standalone PyPI face for `dhis2w-ql`**: the README leads with the no-DHIS2-required story —
  install, a verified d2path quickstart over plain JSON, a full pipeline quickstart with
  `QueryEngine` + `InMemoryBinder`, a collection-semantics primer, and links to the docs site
  including the 140-example evaluator-verified d2path catalog. The package description drops the
  FHIRPath framing in line with the language docs (d2path stands on its own semantics). Only
  `dhis2w-ql` bumps; the sibling packages stay at 0.99.0 and their `>=0.99.0` pins resolve to this
  release.

## 0.99.0 — 2026-07-11

First tagged release since 0.23.0. Everything below plus the two unpublished snapshot sections
(1.0.0.dev1, 1.0.0.dev0) ships in this release; 1.0.0 follows once the remaining roadmap items
under "Session-cookie auth: follow-ups" and the release-blocking checks settle.

### Session-cookie auth (new)

- **A fourth auth kind: `session`.** `Profile` gains `auth = "session"` + a `cookie` field holding the raw
  `Cookie` header value (name included, e.g. `JSESSIONID=abc123`, so the client stays cookie-name-agnostic),
  and `SessionCookieAuth` ships in all three `dhis2w_client.v{41,42,43}.auth` trees alongside Basic/PAT/OAuth2.
  `d2w profile add --auth session` reads the secret from `DHIS2_SESSION_COOKIE` (or a hidden prompt — never
  argv), `profile env` exports it, and `profile verify` probes session profiles. This is the fallback binding
  for instances where PAT creation is unavailable (pre-2.38, disabled, or 403 for the user); the driving
  consumer is the kodo Chrome extension's "use my login" flow, which upserts a session profile from the
  browser's live DHIS2 session and re-runs the upsert on cookie rotation.
- **Session profiles drive browser capture workflows** (dashboards, maps, visualizations): the stored
  Cookie header is parsed pair-by-pair (`parse_cookie_header`) and injected into the Playwright context
  directly via the new `dhis2w_browser.session_from_cookie_header` — no login form, no mint. Banner
  usernames for session profiles resolve via `GET /api/me`.
- **`profile verify` names the missing auth material and its remedy** — a known auth kind with an
  incomplete profile (session without cookie, pat without token, basic without credentials) reports
  what is missing and the `d2w profile add` command that re-binds it; "verification does not yet
  support auth type ..." is reserved for genuinely unknown kinds.
- **Session cookies are trimmed and validated at capture time**: surrounding whitespace is stripped and
  values with embedded control characters (newlines, carriage returns, tabs) are rejected with a clear
  message at profile-add/model-validation time instead of failing later inside httpx. Multi-pair values
  stay accepted; the design remains cookie-name-agnostic.
- **`profile env` prints a caveat for session profiles**: `DHIS2_SESSION_COOKIE` has no raw-env path —
  a session profile must exist in `profiles.toml` (mirrors the oauth2 note).

### d2ql / d2path query language (new)

- **New `dhis2w-ql` workspace member + a `query` plugin across all three version trees.** d2ql is a pipeline
  query/transform language with an embedded expression core (d2path): tokenizer + recursive-descent parser
  producing a pydantic AST, a d2path evaluator with collection semantics over dicts or pydantic models, and an
  engine with source binding, a pushdown planner (where/order/paging compile to native DHIS2 list parameters),
  a local executor for residual stages, define/define-function resolution, and json/ndjson/csv sinks. CLI
  (`d2w query eval/run/explain/ast/d2path/repl`) and MCP (`query_eval` / `query_explain` / `query_d2path`)
  share one service layer; a curated samples catalog and a combinatorial example generator ship alongside (#404).
- **Language semantics spec**, verified by conformance tests (#409); tutorial, cookbook, and a full d2path
  reference under a clean QL nav (#406).
- **Parser + scoping rules:** source-position function calls parse as expressions; duplicate projection
  columns, recursive / duplicate definitions, and duplicate object keys are rejected; `implies`
  right-associates; user-defined functions evaluate in caller scope and reject recursion + duplicate
  parameters; the FHIRPath framing is dropped from docs and errors — d2path stands on its own semantics
  (#407, #408, #413, #414).
- **d2path string subscript** (`x["field name"]`) reads fields whose names aren't identifiers (#411).
- **Pushdown correctness + performance:** `~` filters stay local when the match value carries SQL wildcards
  (#412); `count` reads the DHIS2 pager total instead of fetching every row (#420); an unreachable catch-all
  arm in stage dispatch is removed (#410).
- **Call sources:** `analytics(...)` routes analytics options (`aggregationType`, `outputIdScheme`,
  `includeNumDen`, `startDate` / `endDate`, ...) to the analytics service instead of treating them as
  dimensions (#416); `dataValues(...)` threads its full selection through to `get_data_values` (#425).
- **`--file/-f` on `eval` / `explain` / `ast`**, with a clear pointer at `--file` when a bare file path is
  passed as an inline program (#415).

### Query REPL (Textual TUI)

- **A Textual TUI REPL** for `d2w query repl`: Enter runs, Shift+Enter / Ctrl+J inserts a newline (#419); the
  plain REPL accumulates multi-line input until a blank line or `;` (#418).
- **Collapsible JSON-tree result view** (Ctrl+T) and render-format cycling (Ctrl+F) (#423); format changes
  surface as a top-right toast instead of a log line (#424).
- **Sink format decoupled from destination:** `>> stdout as ndjson`, bare `>> csv` shorthand, and
  `>> "out.txt" as csv` extension override; CLI and REPL render through a shared `serialize_rows` (#422).

### Aggregate

- **Follow-up flag on a data value:** `d2w data aggregate followup --de --pe --ou --on/--off` + the
  `data_aggregate_followup` MCP tool drive `PUT /api/dataValues/followup` and return a typed
  `FollowUpResult`; the PUT body is built at the HTTP boundary because the v43 OAS mis-types `period`
  (BUGS.md #49) (#427).
- **Read filters:** `get_data_values` exposes `org_unit_group`, `include_deleted`, and `last_updated`
  (date or duration like `7d`) on every read surface — the d2ql `dataValues(...)` call source, the CLI
  `get` flags, and the `data_aggregate_get` MCP tool (#426).

### Examples / docs

- **A generated, evaluator-verified d2path example reference** (`docs/query/d2path-examples.md`): a typed
  catalog of 140 examples covering every registered d2path function plus the operator, literal, and
  navigation surface — each entry is parsed and evaluated in CI against the real evaluator, and a hard
  coverage gate fails the suite if a registry function ships without examples. Rendered by
  `make docs-d2path` (chained into `docs-build`).
- **Every d2ql / d2path fence in the QL docs is machine-validated**: fenced blocks tagged `d2ql` or
  `d2path` across the tutorial, references, cookbook, semantics, and index pages are parsed in CI
  (68 validated fences); pseudo-notation stays on `text` fences.
- **Guide depth**: date/datetime literal semantics (`@2026-06-23`, ISO-string comparisons — the
  semantics page previously framed these as future work), `read(...)` file sources with an
  export-then-reread chain, library files with `--define`/`--file` worked examples, string building
  (`+` concat vs `join()`), arithmetic (`/` vs `div`, `mod`), existential comparison, the full five-label
  `is` type test, native pager-total `count`, and a gotchas list (index rules, depth and regex caps).
- **20 new `.d2ql` sample programs** (read-*, date-*, string-*, subset-*, convert-*, library-run) with
  local JSON/NDJSON fixtures under `examples/d2ql/data/`, 16 new cookbook recipes, and 15 new entries
  in the curated SAMPLES registry — all parse-tested in CI.
- File-export CLI examples bundled under an `export-*` family (#417); the three FHIR Bundle examples share a
  `fhir-bundle-*` prefix (#415).
- Nested-relationship "join" examples; the cookbook clarifies `transform` vs `fold` (#421).
- Ten aggregate analytics d2ql examples — named output, indicator numerator/denominator, aggregation
  override, category-option-combo breakdown, org-unit-level rollup, date windows, multi-period,
  multi-org-unit, and a CSV export sink (#416).

### Fixes

- Tracker contract discovery skips programs the play user can't read, so the live suite can't flake on
  sharing settings (#405).

## 1.0.0.dev1

Development snapshot. Not a published release — no tag, no PyPI upload.

### Profiles + version selection

- **`d2w profile env [NAME]`** prints `export DHIS2_*` lines for a profile, so its connection settings load
  into a shell or CI via `eval "$(d2w profile env NAME)"`. Offline read; values printed as-is (already
  plaintext in `profiles.toml`) — `d2w profile show` remains the redacted view.
- **`verify-examples` follows the active profile's version.** The harness resolves the example tree via the
  same `resolve_startup_version()` chain the CLI/MCP use, so a v41-pinned profile runs `examples/v41/...`.

### DHIS2_VERSION standardized on the vXX form (strict)

- `DHIS2_VERSION` now uses the `vXX` key (`v41` | `v42` | `v43`) everywhere — matching the profile `version`,
  the plugin trees, `examples/`, and the `infra/` dump dirs. A bare digit is rejected; infra hard-errors with
  a "use vXX" message.

### DHIS2 image pins + bump tooling

- `make dhis2-versions-check` reports whether any pinned minor is behind the latest Docker Hub patch;
  `make dhis2-versions-bump` rewrites `versions.env` to the latest non-held patches. A weekly
  `version-bump-check` workflow opens reviewed bump + codegen-regen PRs.
- Bumped v41 to `2.41.8.2` and v43 to `2.43.0.1` (pure-bugfix patches, no schema change); v42 held at
  `2.42.4.1` (mapView, BUGS.md #43). `--pull always` on the codegen boot uses the exact registry image.

### Fixes

- `make dhis2-run` exits cleanly on Ctrl+C instead of `Error 130`.
- The v41 and v43 plugin trees now accept `d2w profile add --version v42` (a tree-copy sed had corrupted the
  validator allow-list).
- The v41 and v43 `openapi_manifest.json` files match their emitted trees, and every codegen run rebuilds the
  OAS tree (#401).

### Dependencies

- Dependabot rounds: the actions group (2 updates) and the python-deps group (7 updates) (#402, #403).

## 1.0.0.dev0

Development snapshot on the road to 1.0.0. Not a published release — no tag, no PyPI upload. The version
is stamped to mark the surface as feature-frozen for 1.0; the remaining work is hardening, not new features.

### Coverage parity across v41 / v42 / v43

- **The v41 and v43 core plugin trees are now backed by counted coverage, not just import smoke tests.**
  Parametrized parity tests exercise every plugin service, CLI command, and MCP registration against all
  three version trees, so "v41 / v42 / v43 equally supported" is measured rather than asserted. The
  `metadata` plugin — the one tree with a genuine wire divergence — carries per-version expectations.
- The two broad `v41/*` / `v43/*` coverage omit globs are replaced by a narrow, documented per-module list
  (interactive/Playwright command surfaces and pure data models only).

### CI hardening

- Every workflow runs with an explicit least-privilege `permissions:` block (`contents: read` by default;
  the publish job keeps only the `id-token: write` it needs for PyPI Trusted Publishing).

## 0.23.0 — 2026-06-17

Minor release. A bridge write-guard for shared hosts, a local-model validation harness, and broader contract tests.

### Bridge safety (new)

- **The MCP bridge refuses mutating commands against shared public DHIS2 hosts**, independent of `DHIS2_MCP_READONLY`. When the active profile resolves to a protected host (`play.dhis2.org`, `play.im.dhis2.org`, `debug.dhis2.org` by default), any non-read-only `dhis2_cli` invocation is refused with a clear message; reads still pass. The host set is overridable via `DHIS2_MCP_PROTECTED_HOSTS` (comma-separated; empty disables). This is a structural guard so no benchmark or agent can accidentally write to the shared demo, regardless of how the profile is wired.

### Testing / tooling

- **New `dhis2w-bench` workspace member (unpublished)** — a backend-agnostic harness for validating local LLMs across the surfaces that matter for the local/PII path: coding (python + cli + multi-turn agentic tooling), the mcp-bridge (single-tool discovery, read + write), the full MCP server (~311 tools at 128k context), composite multi-object writes, and long-context needle-in-a-haystack retrieval. Model lifecycle sits behind a `ModelBackend` Protocol (LM Studio today; Ollama / llama.cpp are documented extension points). The strongest local model runs first as the oracle: if it fails a task, the harness flags the task as suspect rather than counting it against weaker models. Make targets: `bench-general`, `bench-bridge`, `bench-mcp`, `bench-composite`, `bench-longcontext`, `bench-list`.
- **Contract tests cover every listable resource** (not a curated subset), exercise `TrackerEvent` on v42 + v43 instead of skipping it, and discover an event program at runtime so the suite can't flake on seed data.

### Workspace packages

All six publishable members + `dhis2w-bench` and `dhis2w-codegen` bumped 0.22.0 -> 0.23.0. Inter-package pins shifted `>=0.22.0,<0.23` -> `>=0.23.0,<0.24`.

## 0.22.0 — 2026-06-16

Minor release. A new `security` plugin, smarter App Hub installs, and a round of CI / dependency hardening.

### Security (new)

- **`d2w security authorities`** + `security_*` MCP tools across all three version trees — reads `/api/me/authorization` and reports the account's effective authorities, superuser flag, and risk-category matches (a dangerous-authority taxonomy of 8 risk categories), as a table or `--json`. Backed by a new version-invariant `dhis2w_core.security_core` (authority taxonomy, severity tiers + `AuditFinding`, and the responsible-use guardrail contract encoded as code: GET-only allowlist, no-lockout, egress, identifiable-traffic, version floor). A guardrail test enforces the contract against every public security service function in v41/v42/v43, with a completeness check that fails the suite when a service function ships without guardrail coverage.

### Apps

- **`d2w apps add` (and the `apps_install_from_hub` MCP tool) now accept an App Hub app id, not just a version id.** The id is resolved against the configured catalog (`GET /api/appHub`): a version id installs directly; an app id resolves to that app's latest version; an id matching neither raises a clean one-line error instead of an opaque proxied 404. App Hub app ids and version ids are both bare UUIDs and trivially confused (DHIS2 quirk recorded as BUGS.md #46). `service.install_from_hub` returns a typed `InstallTarget`, and the MCP tool's argument is renamed `version_id` -> `app_or_version_id`.
- **`d2w apps hub-versions <app-id>`** + the `apps_hub_versions` MCP tool — list every published version of one App Hub app (`version` / `id` / `channel` / DHIS2 `min->max`), newest first. Pairs with the app-id resolution above: list the versions, then `apps add <version-id>` to pin a specific one. `AppHubVersion` now maps the wire's `minDhisVersion` / `maxDhisVersion` compatibility fields.

### CI / tooling

- Dependabot version updates enabled; GitHub Actions bumped to Node 24 and `setup-uv` v7; two rounds of `python-deps` updates.
- `dhis2w-core` test tree regrouped into per-domain directories.

### Docs

- BUGS.md gains #45 (v41 `GET /api/authorities` returns 500) and #46 (App Hub install id-kind 404).
- `dhis.conf` infra comment references `d2w route create`.

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.21.0 → 0.22.0. Inter-package pins shifted `>=0.21.0,<0.22` → `>=0.22.0,<0.23`. The `uv.lock` re-syncs the `dhis2w-core` sqlalchemy spec (`>=2.0`) with its `pyproject.toml`.

## 0.21.0 — 2026-06-12

Minor release. The CLI console script is now `d2w`.

### CLI

- **The console script is `d2w`** (was `dhis2`): `uv tool install dhis2w-cli` drops `d2w` on `PATH`, and every command reads `d2w <group> <command> ...`. The rename reaches every surface that spoke the old name: the MCP bridge resolves the `d2w` binary (the `DHIS2_CLI_BIN` override is unchanged), `dhis2w-browser` spawns `d2w profile login` for the Playwright OAuth2 flow, codegen templates stamp `d2w codegen` into generated-file headers, the publish workflow smoke-tests `d2w --help`, and all docs, examples, and error hints (`NoProfileError` -> `d2w profile add`) use the new name.
- Unchanged: the `dhis2` FastMCP server name, the `dhis2_cli` bridge tool name, profile config paths (`.dhis2/`, `~/.config/dhis2/`), and the `dhis2.plugins` entry-point group.

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.20.0 → 0.21.0. Inter-package pins shifted `>=0.20.0,<0.21` → `>=0.21.0,<0.22`.

## 0.20.0 — 2026-06-09

Minor release. A far richer `system whoami`, a new read surface for `system settings`, and a cleaner datastore error path.

### System

- **`dhis2 system whoami` now exposes everything DHIS2 reports about the authenticated user.** It fetches the full persisted `/api/users/{id}` record and merges in the effective authorities from `/api/me`, then renders every field in plain mode — roles / groups / org units as `name (uid)`, the complete authority list (with a superuser hint when `ALL` is present), plus `passwordLastUpdated`, `externalAuth`, `disabled`, `twoFactorType`, and the org-unit scopes. `--json` emits the whole `Me` object. The `Me` model gains `userRoles`, `teiSearchOrganisationUnits`, `disabled`, `externalAuth`, `twoFactorType`, `passwordLastUpdated`.
- **`dhis2 system settings get` + `list` (alias `ls`)** + `system_settings_get` / `system_settings_list` MCP tools — read a single key or the full `/api/systemSettings` snapshot. Pairs with the existing `set` / `set-many`. The bridge classifies the reads under read-only mode.

### Fixes

- **`datastore`** — a failed read now raises `Dhis2ApiError` carrying DHIS2's own `message` (e.g. `Namespace not found: 'x'`) instead of the raw JSON body.
- **`system whoami --json`** now honors the flag (emits the `Me` object rather than the plain-text form).

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.19.0 → 0.20.0. Inter-package pins shifted `>=0.19.0,<0.20` → `>=0.20.0,<0.21`.

## 0.19.0 — 2026-06-07

Minor release. A new `datastore` surface for DHIS2's key-value store, plus docs + CI hardening.

### Data store (new)

- **`dhis2 datastore`** + `Dhis2Client.datastore` + `datastore_*` MCP tools — namespaced get / set / delete / list over `/api/dataStore` (shared) and `/api/userDataStore` (per-user, `--user`). Stored values are arbitrary JSON; `set` is create-or-update. The bridge allows the reads (namespaces / keys / get) under read-only mode. (There is no `/api/systemDataStore`; instance-wide config stays `dhis2 system settings`.)
- The previously-unbound `routes` accessor now rebinds per DHIS2 major alongside `datastore`.

### Docs + CI

- Migrate the remaining stale typed-list command examples to the generic `metadata list`.
- Add `make check-examples` (wired into CI): every v42 example must have a v41 + v43 counterpart.
- Fix two metadata type-list integration tests that asserted snake_case where the wire emits camelCase (`dataElements`); slow/e2e-only, so fast CI never caught the drift.

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.18.0 → 0.19.0. Inter-package pins shifted `>=0.18.0,<0.19` → `>=0.19.0,<0.20`.

## 0.18.0 — 2026-06-07

Minor release. CLI consolidation — the three top-level `user-*` domains collapse into one.

### CLI (breaking)

- **`user-group` and `user-role` are now subgroups of `user`**: `dhis2 user group` (was `user-group`) and `dhis2 user role` (was `user-role`), dropping the redundant `user-` prefix. The user-management verbs (list / get / invite / reset-password / …) stay directly under `dhis2 user`. MCP tools are unchanged (`user_group_*`, `user_role_*`).

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.17.0 → 0.18.0. Inter-package pins shifted `>=0.17.0,<0.18` → `>=0.18.0,<0.19`.

## 0.17.0 — 2026-06-07

Minor release. A CLI reorganization for a consistent, discoverable command surface, plus a cross-version exception fix in the client. Pre-1.0, so the command renames land as breaking changes in a minor bump.

### CLI reorganization (breaking)

- **Metadata resource groups are plural**, matching the rest of the surface: `metadata dashboards`, `metadata maps`, `metadata attributes`, `metadata program-rules`, `metadata sql-views`. The two abbreviated groups are spelled out: `metadata visualizations` (was `viz`) and `metadata option-sets` (was `options`, now distinct from `category-options`). MCP tools follow (`metadata_visualization_*`, `metadata_option_set_*`).
- **`dev` is now just developer tooling** (codegen / uid / sample). Its operator + auth utilities moved to where they belong: **`dhis2 customize`** is a top-level domain (was `dev customize`); **`dhis2 profile pat`** and **`dhis2 profile oauth2`** mint PATs / register OAuth2 clients (were under `dev`) — auth setup lives with profiles.
- **System settings live under `system`**: `dhis2 system settings set` / `set-many` (were `dev customize set` / `settings`), matching DHIS2's "System Settings" vocabulary. `customize` keeps the branding surface (logos, style, apply, login-config show).
- **One home per concept**: `dhis2 system whoami` is the single current-user command (`user me` removed).

### Client

- **One shared exception hierarchy.** `Dhis2ClientError` / `Dhis2ApiError` / `AuthenticationError` are defined once in `dhis2w_client.errors`, not per version tree — so `except dhis2w_client.Dhis2ApiError` catches errors from a client bound to any DHIS2 major (v41/v42/v43), not just the baseline.
- **`list_all` on every resource accessor.** Added `client.option_sets.list_all()` and `client.routes.list_all()`; renamed `program_rules.list_rules` / `sql_views.list_views` → `list_all` for a uniform listing verb.

### Testing

- The v41/v43 client accessor trees are now exercised across all three versions (mocked parametrization, coverage omit removed), plus a live read/write parity tier against play41/42/43 + local stacks.

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.16.0 → 0.17.0. Inter-package pins shifted `>=0.16.0,<0.17` → `>=0.17.0,<0.18`.

## 0.16.0 — 2026-06-06

Minor release. A new top-level `dhis2 schema` command for type introspection, plus an unknown-`--fields` guard on `metadata list` — together they let a small local model discover and verify field names instead of guessing them.

### Schema command (new)

- **`dhis2 schema <type>`** — describe a generated type's fields (name, type, required, description) by introspecting the **local generated models**, not the server's live schema. Resolves any modeled type, metadata or instance-side: `dataElement`, plural `dataElements`, `WebMessage`, or tracker write shapes like `TrackerEvent` / `TrackerTrackedEntity`. Case-insensitive; an unknown name prints a did-you-mean list (exit 2).
- **Version is auto-detected from the connected server** (`/api/system/info`, SNAPSHOT-safe), then the matching generated tree is introspected — so `dhis2 -p <profile> schema dataElement` shows that server's major automatically, with no `version` pin or `DHIS2_VERSION`. "Schema" is the toolkit's own typed view: the OpenAPI-derived `oas` tree (preferred — the maturing source of truth) with the `/api/schemas`-derived `schemas` tree as the interim complement, selectable via `--source`.
- Top-level (not under `metadata`) because it spans more than the metadata CRUD vocabulary. CLI-only plugin across v41 / v42 / v43; added to the `dhis2w-mcp-bridge` read-only allowlist, and the bridge's `dhis2_cli` docstring now points models at it for "what fields does X have".

### Metadata

- **`metadata list <type> --fields ...` warns on unknown field names.** DHIS2 silently drops unrecognized `--fields`, so a caller that mistypes (or hallucinates) a field never learns it was wrong. The command now emits a soft YELLOW stderr warning naming any requested field absent from the generated model (union of the oas / schemas / tracker trees). Conservative and non-blocking: only plain comma-lists of simple identifiers are checked — preset (`:owner`), wildcard, `!exclusion`, nested (`a[b]`), and dotted (`a.b`) expressions are skipped, and the query still runs.

### Workspace packages

All six publishable members + `dhis2w-codegen` bumped 0.15.0 → 0.16.0. Inter-package pins shifted `>=0.15.0,<0.16` → `>=0.16.0,<0.17`.

## 0.15.0 — 2026-06-06

Minor release. Two new surfaces — a single-tool MCP bridge for small local models and a read-only `security` plugin — plus codegen hardening and a workspace dependency bump. Pre-1.0, so the minor bump carries the new packages and the read-surface changes together.

### CLI bridge for local models (new package: `dhis2w-mcp-bridge`)

- **`dhis2w-mcp-bridge` exposes the whole `dhis2` CLI as a single MCP tool, `dhis2_cli`.** Where `dhis2w-mcp` registers ~337 typed tools (≈50-65k tokens of schema up front), the bridge registers one tool that shells out to the local `dhis2` binary, so a modest on-box model (LM Studio / Ollama / llama.cpp) drives the CLI by progressive discovery (`--help` → group → command). Everything stays local — the server spawns the subprocess and sends data nowhere. `--json` is injected automatically; `profile` is injected as `-p <profile>`.
- **`DHIS2_MCP_READONLY=1` restricts the bridge to read commands** (and `--help`); writes are refused (exit 126) before any subprocess runs. Fail-closed: the read-only allowlist is introspected from the Typer tree and verified by a drift test, so it cannot silently drift. `security settings` is included in the allowlist as a pure read (it is a read under `security` but a write under `dev customize`, so it is allowed by explicit path, not by verb).
- **Read-surface hardening for small models**: `metadata list <type> --count` (one-request totals), `--output <file>` for bulk dumps, `metadata type list` (JSON array of camelCase wire names), did-you-mean errors on unknown resource types, and a bridge docstring rewritten for 3-4B models (output contract, top reads first, filter-operator grammar). Typed per-resource `list` commands are consolidated onto the generic `metadata list <type>`.

### Security plugin (new)

- **`dhis2 security settings`** — read-only display of the security slice of `/api/systemSettings` (password policy, credential expiry, registration, lockout). CLI-only plugin (no MCP surface yet); ships across the v41 / v42 / v43 trees. `SecuritySettings` is a deliberate typed projection of the generated `SystemSettings` because the live endpoint returns `keyAnalysisDisplayProperty` lowercase, which the generated `DisplayProperty` enum rejects (BUGS.md #42). An extension guide (`docs/architecture/security-plugin.md`) walks through adding the next command (#361, #362).

### Codegen

- **Inline string enums are lifted to `Literal[...]` instead of degrading to `str`.** Preserves the allowed-value set on the emitted models across all three version trees (#356).
- **`schemas_manifest.json` ordering is canonicalized across re-fetches**, so re-running codegen produces a stable, diff-friendly manifest (#358).

### Tooling + tests

- **`make bench-round`** (+ `packages/dhis2w-bench/src/dhis2w_bench/round.py`) — repeatable rig that drives `dhis2w-mcp-bridge` with a local LM Studio model for read / write / benchmark rounds.
- **BUGS.md #42 tripwire** — paired mocked + live tests that fire when DHIS2 stops returning lowercase `keyAnalysisDisplayProperty`, signalling the `SecuritySettings` projection can collapse into the generated model.
- Nightly E2E repointed at the local docker stack (#357); Material for MkDocs build notice silenced.

### Workspace packages

All publishable members + `dhis2w-codegen` and the new `dhis2w-mcp-bridge` bumped 0.14.2 → 0.15.0. Inter-package pins shifted `>=0.14.0,<0.15` → `>=0.15.0,<0.16` (minor bump = new upper bound, pre-1.0 policy). Workspace dependencies refreshed to latest (#359).

## 0.14.2 — 2026-05-15

Additive feature patch on top of 0.14.1 — one new typed accessor on `Dhis2Client` for callers that proxy GETs through DHIS2's `/api/routes/{id}/run` reverse-proxy endpoint.

### Client

- **`Dhis2Client.routes.run(code, path) -> httpx.Response`.** Typed helper around `/api/routes/<id>/run[/<path>]`. Resolves the user-set `Route.code` to its UID once via `GET /api/routes?filter=code:eq:<code>` and caches the mapping for the lifetime of the connection, then delegates the actual proxy GET to `Dhis2Client.get_response()` so callers see the raw `httpx.Response` and can do their own status-based handling — a 502 from the proxy means "DHIS2 reached, downstream didn't", which is a fact health-checkers want to report rather than an exception to raise. `use_cache=False` forces a fresh lookup; `invalidate_cache(code=None)` drops one mapping (or every mapping) for callers that know a Route was renamed or re-pointed. `LookupError` raised when no Route matches the code. Applied identically across the v41 / v42 / v43 client trees. Motivated by `chap-checker` hand-building these paths in two checks.

### Documentation + examples

- **`docs/api/routes.md`** — new mkdocs page in the "Plugin accessors" section, autodocs the v42 `routes` module.
- **`examples/v{41,42,43}/client/routes_run.py`** — worked example: create a throwaway Route pointing at `https://example.com/`, run it twice via code (to demonstrate the cache), then clean up. Added to `infra/scripts/verify_examples.py::SKIP_BY_DEFAULT` since it depends on external egress out of the local DHIS2 docker.

### Workspace packages

All five publishable members + `dhis2w-codegen` bumped 0.14.1 → 0.14.2. Inter-package pins unchanged (the existing `>=0.14.0,<0.15` already permits 0.14.2).

## 0.14.1 — 2026-05-15

Patch on top of 0.14.0 — one user-visible v43 fix in `dhis2w-browser`, plus four nightly-E2E reconciliations that don't ship code (test/CI/docs only). Discovered while triaging the 2026-05-15 nightly red run.

### Browser

- **`logged_in_page` (and therefore `create_pat`) works against v43.** The helper waited for the page URL to stop containing `/dhis-web-login`. DHIS2 v43 server-redirects `/dhis-web-login/` to `/login/` *before* the form is even submitted, so the condition matched immediately and the helper returned an unauthenticated `(context, page)` tuple. Subsequent `page.request.post("/api/apiToken", ...)` calls then followed DHIS2's 302 to `/login/` and got the login app HTML back, which `response.json()` choked on as `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`. Replaced the URL-match wait with an `await GET /api/me` poll (with `Accept: application/json`) — the only stable cross-version signal for "the server treats my cookie as authenticated". `pat.py` also gains an explicit `Accept: application/json` on the create-PAT POST as a defensive header (#353).

### Tests + CI

- **Verifier shape drift on the v41 nightly leg.** Six `test_bug_*_live_verifier` tests asserted on v42/v43-specific internal OAS / wire shapes and reported flips that weren't actually upstream fixes. Reshaped to assert on the load-bearing symptom (does the codegen workaround still need to fire?) so they're now stable across all three majors. See BUGS.md for per-entry detail (#352, #353).
  - **#13** — `OutlierDetectionAlgorithm` standalone schema is absent from v41; enum moved inline to `OutlierDetectionMetadata.properties.algorithm`. Same `{Z_SCORE, MIN_MAX, MOD_Z_SCORE, INVALID_NUMERIC}` values.
  - **#14** — every `*AuthScheme` schema now has a `type: {type: string}` property on v41, but `Route.auth` is still a bare `oneOf` with no `discriminator` block. Codegen spec-patch stays.
  - **#15** — `WebMessage.response` collapsed to `{"type": "object"}` on v41 (less info, not more). Codegen `dict[str, Any]` flatten stays.
  - **#2** — verifier's `dataSetElements:!empty` filter rejected by v41 with `400 E1003`. Switched to client-side filtering.
  - **#10** — v41 returns `409 "Key is not supported"`; v42/v43 still return `404 "Setting does not exist" E1005`. Verifier now accepts either.
  - **#39** — v41 `2.41.8.1` rejects the v42-shape `clientId` body with `409 E4000 "Missing required property cid"` instead of silently persisting an empty `cid`. Verifier renamed `test_bug_39_v41_live_oauth2_clientid_persists_empty` -> `test_bug_39_v41_live_oauth2_rejects_v42_shape` and accepts either path.

- **CLI integration tests.** `test_system_info_live` previously hardcoded `"2.42"` in the assertion (broke on v41 and v43 legs); `test_metadata_types_lists_resources` asserted on the stale `"types available"` string that no rendering produced. Both now assert on cross-version-stable structural facts (#351).

- **Nightly E2E job pins the MCP server's plugin tree.** The `make test-slow` step did not export `DHIS2_VERSION`, so `dhis2w_mcp.server.build_server()` fell back to `DEFAULT_VERSION_KEY = "v42"`. MCP integration tests on the v41 and v43 legs then raised `VersionPinMismatchError` on every tool call. The `up-seeded` and `verify-examples` steps already export the var; `test-slow` was the missing leg (#351).

- **PyPI publish smoke-test retries.** The v0.14.0 publish was actually successful but the post-publish verify jobs raced PyPI's simple index against uv's resolver and reported `No solution found`. The smoke-test step now retries up to 12x5s with `--refresh` (#351).

### Documentation

- **BUGS.md retest log** gains two 2026-05-15 entries (one OAS shape sweep against `play.im.dhis2.org/dev-2-41`, one write-path sweep against a local `2.41.8.1` stack) plus `Status on v41` lines on six bug entries.

### Workspace packages

All five publishable members + `dhis2w-codegen` bumped 0.14.0 → 0.14.1. Inter-package pins unchanged (the existing `>=0.14.0,<0.15` already permits 0.14.1).

## 0.14.0 — 2026-05-14

One feature PR on top of 0.13.1 — three additive escape hatches on `Dhis2Client` so it can be used as transport in lifecycles that don't fit the default connect-then-raise flow (health-checkers, very-low-privilege PATs, tests with injected transports).

### Client

- **`Dhis2Client(verify=...)`, `Dhis2Client(skip_version_probe=...)`, and `Dhis2Client.get_response()`.** Three opt-in additions on the client, defaults preserve current behaviour. `verify: bool | str = True` threads TLS verification through the main httpx pool plus the canonical-URL and DHIS2-shape probes (pass `False` for self-signed staging or a CA-bundle path). `skip_version_probe: bool = False` opens the HTTP pool without the canonical-URL probe or `/api/system/info` round-trip — `version_key` / `raw_version` / `resources` continue to raise on access, only raw-path methods are usable. `get_response(path, *, params=None, extra_headers=None) -> httpx.Response` is a no-raise GET escape hatch returning the raw response so callers can do their own content-negotiation / status-based handling — health-checkers in particular want a 502 from `/api/routes/<code>/run/...` to surface as a fact, not an exception. Applied identically across the v41 / v42 / v43 client trees. Motivated by [chap-checker](https://github.com/dhis2-chap/chap-checker), a DHIS2 health-check CLI (#349).

### Documentation

- **`docs/api/client.md`** lists `get_response` in the escape-hatch section and documents `verify` / `skip_version_probe` constructor knobs (#349).

### Examples

- **`examples/v{41,42,43}/client/health_check.py`** — health-checker pattern showing `skip_version_probe=True` + `get_response()` against `/api/system/info`, `/api/me`, and a deliberately-missing reverse-proxied route, treating each non-2xx as a reportable fact (#349).

### Workspace packages

All five publishable members + `dhis2w-codegen` bumped 0.13.1 → 0.14.0; inter-package pins bumped `>=0.13.0,<0.14` → `>=0.14.0,<0.15`.

## 0.13.1 — 2026-05-13

Audit follow-up — four PRs landed on top of 0.13.0 the same day. One real silent-mismatch fix that PR #338 left half-open, plus three doc / hygiene cleanups.

### MCP + client

- **MCP guards mismatched profiles even when the per-call profile has no `.version` pin.** PR #338 added a `ProfileVersionMismatchError` guard at profile-resolution time, but it returned early when `profile.version is None` and `open_client` then opened the wire client unpinned. An MCP server bound to v42 plus a per-call profile without `version` could still silently parse a v43 server's payloads through v42 schemas — and real-world profiles rarely declare `version`, so this was the more common failure mode than the documented one. `open_client` now threads the bound tree as `Dhis2Client(version=...)` so the on-connect `/api/system/info` check from PR #339 raises `VersionPinMismatchError` regardless of whether the profile pins a version (#343).

### Documentation

- **MCP docs overclaim cleanup.** `docs/mcp/index.md`'s intro paragraph said `one MCP tool per CLI command — about 337 in total` — false, since `dhis2 dev` / `dhis2 browser` / profile mutations are intentionally CLI-only. The per-call-profile paragraph also said silent mismatches were impossible, which was only true for profiles with an explicit `.version` pin. Both rewritten to match reality (#344).
- **Roadmap refresh.** `docs/roadmap.md` said codegen ships v40/v41/v42/v43/v44 (repo has v41/v42/v43), and the testing-layer table marked codegen snapshots, schema-contract tests, and the verify-examples matrix as 'None' or v42-only when all three are shipped (snapshot tests in `dhis2w-codegen/tests/test_snapshots.py`, `@pytest.mark.contract` + `contract.yml`, and the nightly v41/v42/v43 verify-examples matrix from PR #337). Tier A1 + A2 also marked shipped with concrete file paths (#345).

### CLI

- **Debug-logging handler is idempotent.** `_enable_debug_logging()` in the `dhis2` CLI always added a fresh `RichHandler` to the root logger. Normal CLI use exits after one invocation so it didn't matter, but `CliRunner` reuses the same process across `invoke()` calls and `make docs-cli` imports the module repeatedly — duplicate handlers accumulated, producing duplicate HTTP/debug stderr lines on every request. The handler now carries a stable name; repeat calls return early (#346).

### Workspace packages

All five publishable members + `dhis2w-codegen` bumped 0.13.0 → 0.13.1. Inter-package pins unchanged (the existing `>=0.13.0,<0.14` already permits 0.13.1).

## 0.13.0 — 2026-05-13

Hardening release driven by a multi-pass audit. Eleven PRs landed across CLI behaviour, MCP safety, client robustness, docs accuracy, CI coverage, and workspace plumbing. No new product surfaces — every change tightens an existing one.

### Client + plugins

- **`Dhis2Client(version=...)` raises on server mismatch.** Pinning v43 against a v42 server used to silently bind the v43 generated tree on top of v42 wire payloads, round-tripping renamed/added fields wrong. `connect()` now compares the reported `/api/system/info` version's major against the pin and raises a new `VersionPinMismatchError` (subclass of `UnsupportedVersionError`). Opt out with `allow_version_mismatch=True` if you've audited the schema overlap yourself (#339).
- **Cross-origin canonical-URL redirects require DHIS2 confirmation.** `_resolve_canonical_base_url` used to follow `play.dhis2.org` → `play.im.dhis2.org` migrations but would also follow an SSO IdP redirect, leaving subsequent `/api/...` calls pointed at the IdP host. Cross-origin redirects are now probed against `/api/system/info` (DHIS2 always returns JSON regardless of auth state) before being adopted; IdP redirects fall back to the original URL (#334).
- **OAuth2 authorization-code exchange wraps failures into `OAuth2FlowError`.** Used to leak raw `httpx.HTTPStatusError` on bad client_secret / redirect mismatch / DHIS2 OAuth2 misconfig. Now mirrors the refresh path: RFC 6749 `error` / `error_description` re-emitted when DHIS2 returns them, or a truncated body snippet otherwise, plus a common-causes hint (#341).

### CLI

- **`dhis2 --profile NAME ...` applies before plugin discovery.** `app = build_app()` ran at module-import time, freezing the plugin tree at whatever the default profile pinned (typically v42) before argv was parsed. `dhis2 --profile v43p --version` would print `plugin tree: v42`, and v43-only commands stayed hidden. `main()` now pre-scans `sys.argv` for `--profile` / `-p` / `--profile=NAME` and sets `DHIS2_PROFILE` before building the app (#333).
- **`docs/cli-reference.md` regenerates correctly** — the typer-docs introspection used by `make docs-cli` needs a module-level `app` instance, which #333 had removed. Restored the module-level `app = build_app()` with a comment clarifying it's only consumed at docs-build time; the entry point uses `main()` which builds its own fresh app after the argv pre-scan (folded into #335).

### MCP

- **Per-call profile guarded against bound plugin tree.** A v42-booted server invoked with a v43-pinned profile used to parse v43 server payloads through v42 schemas silently. `dhis2w_core.profile.bind_version_tree()` is called once at `build_server()` time; `resolve_profile()` now raises `ProfileVersionMismatchError` with a restart hint (`Restart with DHIS2_VERSION=v43 dhis2w-mcp ...`) on any mismatched per-call profile (#338).

### Workspace + packaging

- **Root `pyproject.toml` switched to bare-workspace form.** The `[project]` table at the repo root was unused metadata that drifted on every release — dropped along with `[tool.uv] package = false`. `uv lock` removes the meaningless `dhis2-utils v0.1.0` entry (#332).

### Documentation

- **MCP single-major + filesystem-trust + stale claims.** `docs/mcp/index.md` now spells out that one running server targets a single DHIS2 major (per-call profile only swaps profiles within that major; `ProfileVersionMismatchError` enforces it). New filesystem-trust section covering `metadata_export(output_path)`, `metadata_diff(left_path)`, `customize_apply`, `apps_install_from_file`, `apps_snapshot` — unsandboxed local-path I/O, with recommendations for constrained cwd / container isolation. `docs/architecture/mcp.md` refreshed to show `resolve_startup_version()` + `_eager_rebuild_tool_return_types()` in the `build_server()` snippet. `docs/testing.md` drops the stale `Tracker / data values / analytics don't exist yet` claim (#335).
- **MCP parity claim softened.** `docs/index.md` previously read _'every CLI command has a matching MCP tool (and vice versa)'_ — reality: `dhis2 dev` / `dhis2 browser` / profile mutations are intentionally CLI-only. Replaced with _'most operational commands ship as both'_ + an enumerated exclusion list (#340).

### Testing + CI

- **Per-version smoke matrix.** New `tests/test_v{41,43}_smoke.py` (dhis2w-client, 8 tests) covers top-level imports, `build_auth_for_basic` dispatch, and `open_client` handshake binding the right tree. New `tests/test_v{41,43}_plugin_smoke.py` (dhis2w-core, 6 tests) verifies `discover_plugins("v{N}")` returns the full plugin set with v{N}-bound modules. Provides structural guardrails on hand-written v41/v43 trees that currently sit under coverage omits (#336).
- **Example matrix in nightly E2E.** The E2E workflow already runs `make test-slow` against a docker stack per DHIS2 major. Appended `make verify-examples` to the same matrix job so the ~150-example surface per version gets exercised nightly. `SKIP_BY_DEFAULT` entries (browser / OIDC / fixture-gap) still skip per the script's policy (#337).

### Workspace packages

All five publishable members + `dhis2w-codegen` bumped 0.12.0 → 0.13.0, inter-package pins refreshed to `>=0.13.0,<0.14`.

### Migration notes

- Library users on `Dhis2Client(version=...)`: a previously silent mismatch will now raise. If you depended on cross-major binding (rare), pass `allow_version_mismatch=True` explicitly. The new default is the safer one.
- MCP host operators: if a per-call profile pins a different DHIS2 major than the server booted with, you'll see `ProfileVersionMismatchError` with a restart hint. The fix is one line: `DHIS2_VERSION=<major> dhis2w-mcp`.
- Library users embedding `dhis2w-client` for OAuth2 flows: token-endpoint failure messages changed shape. The wrapping is now `OAuth2FlowError` (was `httpx.HTTPStatusError`); update any string-matching error handlers.

## 0.12.0 — 2026-05-13

Boundary-refinement release. `Profile` + a PAT/Basic `open_client(profile)` now live in `dhis2w-client`, so library users embedding the client for PAT or Basic auth no longer need to install `dhis2w-core` (and its Typer / FastMCP / SQLAlchemy / bcrypt / questionary deps). OAuth2 still requires `dhis2w-core` because OAuth2 token refresh genuinely needs concurrent-writer safety on the token store. Strict back-compat: every `from dhis2w_core.profile import Profile` / `from dhis2w_core.client_context import build_auth, open_client` import keeps working via re-export — CLI, MCP, plugins, examples unchanged. Also drops the unused `alembic` dep from `dhis2w-core`.

### Client + plugins

- **`Profile` Pydantic model lives in `dhis2w-client`** (`dhis2w_client.profile.Profile`). Exception classes (`NoProfileError`, `UnknownProfileError`, `InvalidProfileNameError`), `validate_profile_name()`, and `PROFILE_NAME_MAX_LEN` come with it (#329).
- **`profile_from_env_raw()` is the new pure-env constructor** in `dhis2w-client` — returns `Profile | None` from `DHIS2_URL` + `DHIS2_PAT` / `DHIS2_USERNAME` + `DHIS2_PASSWORD` env vars. The full TOML+env precedence chain (`dhis2w_core.profile_from_env`) is unchanged (#329).
- **`open_client(profile)` and `build_auth_for_basic(profile)` ship in `dhis2w-client`** for PAT and Basic auth. Available at top-level (`dhis2w_client.open_client`) and per-version (`dhis2w_client.v{41,42,43}.open_client`). Calling either with `auth="oauth2"` raises `NotImplementedError` pointing at `dhis2w_core.open_client` (#329).
- **`dhis2w-core` `open_client` / `build_auth` are strict supersets.** PAT/Basic delegate to the new `dhis2w-client` helpers; the OAuth2 path with `_build_oauth2` + `token_store_for_scope` stays here (#329).

### Workspace packages

- **`dhis2w-core` drops `alembic>=1.18`.** Was a declared dep but unused — no `alembic.ini`, no migrations dir; the OAuth2 token store schema is created via `Base.metadata.create_all()` (#329).
- All five publishable members + `dhis2w-codegen` bumped 0.11.0 → 0.12.0 and inter-package pins refreshed to `>=0.12.0,<0.13`.

### Examples

- **`examples/v{41,42,43}/client/profile_pat_pure_client.py`** — three new examples demonstrating the `uv add dhis2w-client`-only install path (no `dhis2w-core` needed). Build `Profile(auth="pat", ...)` and call `open_client(profile)` directly (#329).

### Documentation

- **`docs/guides/client-tutorial.md`** install section rewritten — `uv add dhis2w-client` now genuinely covers PAT/Basic library use; `uv add dhis2w-core` becomes required only for OAuth2 token persistence or the CLI/MCP profile layer.
- **`docs/architecture/profiles.md`** — new "Profile model location" paragraph at the top.
- **`docs/architecture/workspace.md`** — dependency-arrow comments updated for the refined boundary.
- **`docs/architecture/auth.md`** — note on `build_auth_for_basic` as the lightweight entry point for the two non-OAuth2 schemes.
- **`docs/decisions.md`** — new entry recording the lift, the rationale (transitive PyPI weight, not cycle avoidance), and the alembic-drop cleanup.

### Migration notes

- Library users on PAT or Basic: switch `from dhis2w_core import open_client, Profile` to `from dhis2w_client import open_client, Profile` to drop the `dhis2w-core` install. Same `Profile(...)` constructor; same `async with open_client(profile)` shape.
- Library users on OAuth2: no change — keep using `from dhis2w_core import open_client, Profile`.
- CLI, MCP, plugin authors: no edits needed — every `from dhis2w_core.*` import keeps working via re-export.

## 0.11.0 — 2026-05-13

Follow-up to the v0.10.0 per-version split: v43-only Program setters land end-to-end, MCP gains a server-introspection tool, hand-written v41 enum stubs replace the last cross-version imports, and the docs site gets a full restructure — 5 top tabs (Get started / Architecture / Client / CLI / MCP), per-surface introductions, indigo theme, +400 lines of worked Python examples on the API reference pages, and an explicit "Learning path · step N of 8" framing across the canonical reading order.

### Client + plugins

- **v43-only Program setters wired end-to-end.** `programs.set_labels` (UI overrides), `programs.set_change_log_enabled` (audit toggle), `programs.set_enrollment_category_combo` (alt CC at enrollment time) — three focused methods covering the v43 `Program` schema additions (`enableChangeLog`, `enrollmentsLabel`, `eventsLabel`, `programStagesLabel`, `enrollmentCategoryCombo`). Matching CLI commands (`dhis2 metadata program set-labels / set-change-log / set-enrollment-category-combo`) and MCP tools (`metadata_program_set_labels` / `metadata_program_set_change_log_enabled` / `metadata_program_set_enrollment_category_combo`). v41/v42 don't expose these methods because the fields don't exist on those schemas (#315, #316).
- **`system_server_info` MCP tool.** Process-local introspection returning the active plugin tree (`v41` / `v42` / `v43`), the resolution chain step that picked it (`profile.version` / `DHIS2_VERSION` env / default), and the bound `dhis2w-*` package versions. Useful for agents that want to detect plugin-tree mismatch before issuing version-sensitive calls (#312).
- **v41 enum stubs.** `dhis2w_client.generated.v41.oas._enum_stubs` ships the six `StrEnum`s the v41 server doesn't surface (`AtomicMode`, `FlushMode`, `ImportStrategy`, `MergeMode`, `PreheatIdentifier`, `PreheatMode`). v41's metadata plugin no longer reaches into `generated.v42.*` to find them (#311).
- **Tracker contract tests.** Live-schema test suite extended to cover `/api/tracker/*` endpoints (trackedEntities, enrollments, events) — pulls one row from each via the corresponding accessor on `dev-2-{42,43}` and asserts it round-trips through the typed model (#313).
- **Hypothesis property tests** on the hand-written parser DSLs (UID generator + validator round-trip, period parsing + arithmetic for every absolute period kind, JsonPatch op discriminator dispatch). 17 properties run as part of the mocked test tier (#314).

### Examples

- **Three v43-only Program setter examples** (`program_set_labels.py`, `program_set_change_log.py`, `program_set_enrollment_category_combo.py`) plus the BUGS #33 CategoryCombo COC-regen workaround (`category_combo_coc_regen.py`).
- **Three v41-only divergence examples** for `oauth2_cid_field`, `apps_display_name`, `grid_rows_wire_shape` (#307).
- **`import_grouped_by_dataset` + `wait_for_coc_generation` examples** across v41/v42/v43 (#308).
- **Split bundled examples** — `validation_and_predictors.{py,sh}` -> `validation_rules.{py,sh}` + `predictors.{py,sh}`; `sharing_and_user_groups.py` -> `user_groups.py` + `user_roles.py`. Six new files; per-concern files instead of coincidence-of-version bundles (#317).
- **`open_client(profile_from_env())` standardised.** 13 client examples that used the lower-level `resolve()` + `build_auth_for_name()` + `Dhis2Client(...)` boilerplate are now on the canonical one-liner (#320). Same alignment applied to non-pinning doc code snippets (#321).
- **Raw `get_raw` replaced with typed `resources.X.list()`** where a typed accessor exists. Five example call sites converted; the audit verified the remaining 18 raw call sites are genuinely escape-hatch use (bulk imports, RFC 6902 patches, version-divergence demos) (#322).
- **Every example's `Usage:` path now version-segmented.** 328 files fixed — `uv run python examples/v42/client/whoami.py` instead of the previously copy-paste-broken unversioned form (#325).

### Documentation

- **5-tab navigation.** Top-of-page tabs (Get started / Architecture / Client / CLI / MCP) replace the previously flat 70+ item left sidebar. Each surface tab carries its own Introduction + Tutorial + Architecture + Reference. The Python API reference is sub-grouped into Core / Plugin accessors / Metadata authoring / Streaming / Utilities (#323).
- **Indigo Material theme.** Switched back to the stock `mkdocs-material` indigo palette; dropped the custom `mkdocs-claude-theme` dependency (#323).
- **Per-surface introductions** at `docs/client/index.md`, `docs/cli/index.md`, `docs/mcp/index.md`, plus a beefed-up `docs/mcp/tutorial.md` covering the full read / mutate / rollback agent workflow with explicit recovery tables.
- **API reference fleshed out.** Worked Python examples added to the 8 previously one-paragraph pages (files, messaging, aggregate, analytics-stream, envelopes, maintenance, uids, generated) and the 6 thin reference pages (auth-schemes, client, data-values, errors, tracker, validation). Every snippet verified against the v42 accessor source.
- **9 new `docs/api/` pages** for previously undocumented public modules (json-patch, categories, category-combos, category-combo-builder, category-option-combos, attribute-values, option-sets, program-rules, tasks).
- **Mermaid dependency diagram** in `docs/architecture/overview.md` + `CLAUDE.md` replaces the ASCII-arrow form.
- **`docs/examples.md`** reframed as the curated v42 catalogue + version-pinned `examples/v{41,42,43}/` trees as source of truth.
- **`docs/architecture/schema-diff-v41-v42-v43.md`** updated with the three split v43 Program setter helpers + the per-concern table (UI labels / audit toggle / alt CC).
- **Learning-path framing** on the 8 primary docs (README, walkthrough, cli-tutorial, client-tutorial, examples, api/index, architecture/overview, BUGS.md) — one-line "step N of 8" banner with prev/next links so a reader landing mid-path sees where they are.

### Workspace packages

All bumped from 0.10.0 to 0.11.0 and published to PyPI via Trusted Publishing:

- `dhis2w-client`
- `dhis2w-core`
- `dhis2w-cli`
- `dhis2w-mcp`
- `dhis2w-browser`

## 0.10.0 — 2026-05-12

Big architectural jump: per-version split of the entire workspace (v41 / v42 / v43), a 39-entry BUGS regression catalogue with 15 live verifiers, and end-to-end example verification across all three DHIS2 majors.

### Architecture

- **Per-version subpackages everywhere.** `dhis2w_client.v{41,42,43}` and `dhis2w_core.v{41,42,43}.plugins.*` are now hermetic — a v43-specific quirk lands in `v43/plugins/...` alone without touching v41/v42. Three trees seeded from the v42 baseline (#253-#272).
- **Per-version `__init__.py` re-export surfaces.** `from dhis2w_client.v41 import X` now works directly, parallel to `from dhis2w_client.v42 import X` and `from dhis2w_client.v43 import X`. The top-level `dhis2w_client` shim still routes to v42 for backwards compat with PyPI consumers (#280-#282).
- **Per-version `dhis2w-core` helpers.** `cli_errors`, `cli_output`, `cli_task_watch`, `client_context`, `oauth2_registration`, `pat_registration`, and `token_store` all have v41 / v42 / v43 copies under `dhis2w_core/v{N}/`. Shared runtime state (`JSON_OUTPUT` ContextVar, `_console` Rich singleton) stays single-source via re-exports — only the type-signature surface diverges per version (#283-#285, #289).
- **Plugin discovery resolves the version from `DHIS2_VERSION` env when `profile.version` is unset.** Lets `make verify-examples DHIS2_VERSION=v41` correctly drive the v41 plugin tree without hand-editing every profile (#292).
- **Plugin retarget — all 47 plugin files per version-tree now import from their matching client subpackage** (`dhis2w_client.v{N}.*` + `dhis2w_core.v{N}.*` helpers + `dhis2w_client.generated.v{N}.*`). One hand-fix per version for genuine wire-shape divergence (#286-#288).
- **Top-level shim dropped from `dhis2w-core`-internal call paths.** Canonical imports go through `v{N}/`; the top-level remains as a PyPI-stable surface only (#271).

### v41 wire-shape adapters

- **`App.model_rebuild()` + eager forward-ref imports.** v41 subclasses `_GeneratedApp` to add the runtime-emitted `displayName` field; the parent's `defer_build=True` required explicit materialisation (#292).
- **`Grid.rows: list[list[Any]]` override.** v41 OAS declares row cells as `dict[str, Any]` but the wire carries scalars/null. Subclass widens the type to match reality (#292).
- **OAuth2 round-trip reads `cid` (BUGS.md #39).** v41 wire shape names the client identifier `cid`; v42/v43 use `clientId`. `dhis2 dev sample oauth2-client` smoke test tolerates both, preferring v41-correct `cid` on the v41 plugin tree (#262, #292).
- **Dropped `oauth2-client-credentials` auth-scheme variant.** v41's OAS and runtime don't ship it; v42/v43 do (#264).
- **`SharingObject` retargeted to `generated.v41`** with a local `Status` stub for the v41-missing enum (#269).

### v43 wire-shape adapters

- **`SharingObject.externalAccess` dropped from v43** (BUGS.md #38). v43's SharingBuilder no longer accepts `external_access` (#261).
- **`CategoryCombo.categorys` legacy alias dropped on v43** — wire writes silently no-op without `categories` (BUGS.md #34) (#260).

### BUGS regression catalogue

- **Paired bug-still-present + workaround-works tests for every BUGS.md entry.** Mocked halves run as part of `make test`; live halves run via `make test-upstream-bugs -m slow` against a docker stack (#273-#275).
- **15 live verifiers shipped** across schema reads + library-relevant writes + scope checks. Each cross-links to its BUGS.md entry and asserts the upstream bug is still observable on the wire (when DHIS2 fixes it, the test fails loudly — the signal to drop the workaround) (#276-#278, #290-#291).
- **`@pytest.mark.upstream_bug` marker + `make test-upstream-bugs` filter.** One-shot view of every workaround the codebase depends on (#273).

### Examples

- **`examples/` split into per-version directories (`examples/v{41,42,43}/{cli,client,mcp}/`).** Each version tree's examples target its matching DHIS2 major. New examples land in the version(s) where they apply (#247-#248, #272).
- **`make verify-examples DHIS2_VERSION=vN`** runs every non-interactive example for major `N` and prints a PASS / FAIL / TIMEOUT / SKIP table. Currently green across all three: v41 153/0/12, v42 153/0/12, v43 158/0/12.

### Infrastructure

- **`dhis2w-codegen` accepts pinned Docker tags + restored v41 codegen tree** (#243).
- **Fresh-install seed flow** auto-disambiguates collision-prone built-in TET/TEA names (`Person (Play)`) and writes seeded PATs + OAuth2 client to `infra/home/credentials/.env.auth` (#244).
- **`make -C infra clean`** wipes volumes for clean version switches (the same Postgres volume can't host v41 then v43 — Flyway rejects unknown applied migrations).

### Coverage + CI

- **Coverage threshold honored after the per-version tripling** — v41 + v43 client / plugin trees omitted from measurement until their `tests/v{41,43}/` folders fill in (Stage 5 follow-up). Coverage on v42 + cross-version code reports 82.67% against the 70% bar (#279).

### Migration notes

- PyPI consumers using `from dhis2w_client import X` are unaffected — the top-level shim still resolves through `dhis2w_client.v42`.
- Code that imported from removed paths (`dhis2w_client.client`, `dhis2w_client.envelopes`, etc. — the pre-split layout) needs to switch to either `dhis2w_client` (top-level shim) or `dhis2w_client.v{N}.X` for version-pinned imports.
- Profiles without a `version` field continue to auto-detect on `connect()`. To pin a profile to a major, add `version = "v41"` (or `"v42"` / `"v43"`) under `[profiles.<name>]` in `profiles.toml`, or set `DHIS2_VERSION` in env when invoking `dhis2`.

## Earlier

See `git log` for releases prior to 0.10.0. Tag `v0.7.0` was the last release before the per-version split landed.
