# Decisions log

Running list of architectural choices and the reasoning behind them. Each entry is a terse "we decided X because Y, alternatives were Z". This file is a first stop when you're wondering "why is it done that way?".

## 2026-08-15 — The spool stays files on disk: the state is the directory, the last error is the sidecar

**Decision:** the revisit trigger recorded on the 2026-08-08 spool entry has fired — a receipt now has a state that moves (`received → forwarded | rejected`), a last-error, and a reverse move (`d2w fhir requeue`) — and the answer is still **files**, hardened rather than replaced. What hardening means, concretely: every write is `fsync`ed and its directory entry `fsync`ed before the caller acknowledges anything; a file that will not parse is moved to `.serve/responses/malformed/` with its reason beside it instead of failing the read that met it; one drain at a time, via an exclusive `flock` on `.serve/responses/.drain.lock` carrying the holding process id; each receipt is filed the instant DHIS2 answers about it rather than in a pass at the end; abandoned temporary files older than an hour are swept at process start and at drain start; and both spool reads are paged behind an opaque cursor and run off the event loop.

**Why files, given the trigger:** the mutable state rule 10 is about is state a schema has to hold. This state has nowhere to be held, because it is already expressed by something the filesystem enforces for free. **Which directory the file is in is the status**, and a rename is atomic — there is no window in which a receipt is in two states, and no bookkeeping to disagree with the files. **The last error is the `<id>.report.json` sidecar**, which is DHIS2's own answer written down whole rather than a column projecting a summary of it. A SQLite table would have to mirror both facts and then keep the mirror true against a second process moving files underneath it, which is a consistency problem the directory does not have. The attempt count nobody has asked for is the one thing genuinely absent, and it is absent because no behaviour depends on it: a drain retries what is in `received/`, and an operator who wants a receipt tried again says so with `requeue`.

**What files cost, stated plainly:** no transaction across two receipts, so a drain killed between two posts leaves the first filed and the second queued — which is the correct outcome and is why filing moved inside the posting loop. No index, so ordering a listing reads every envelope; paging keeps the *projection* cost proportional to the page, and a facade serving one project is nowhere near where that stops being a rounding error. Concurrency is by lock rather than by row, which suits exactly one writer of `received/` (the facade) and exactly one drain (the lock).

**Revisit trigger:** a fact about a receipt that the directory cannot express and the sidecar cannot carry — a retry schedule the forwarder itself acts on, a per-receipt lease across several drains, or a query that has to be answered without reading the files. Any of those is a table, and this entry is what it argues against.

**Alternatives rejected:** SQLite now (a schema mirroring two facts the filesystem already states, plus a migration story, plus the mirror-drift problem against a second process); a status field written inside each receipt file (two statements of one fact, and the file's own copy is the one that goes stale); a lock-free drain relying on `os.replace` alone (atomic per file, but two drains still translate and post the same receipts).

## 2026-08-08 — `d2w fhir serve` ships as `dhis2w-fhir-serve`, a member, not an extra of `dhis2w-fhir`

**Decision:** the FHIR facade is its own workspace member (`packages/dhis2w-fhir-serve`, tenth publishable), depending on `dhis2w-fhir` + FastAPI + uvicorn. `dhis2w-cli` declares it as the optional `serve` extra, and `d2w fhir serve` — the command itself, which stays in `dhis2w-fhir/cli.py` — guards the import and raises a `LookupError` naming both install routes when the package is absent.

**Why:** the workspace convention is "each shippable unit is a member; new surfaces land as new folders", and this is the first HTTP surface that convention has had to absorb. `dhis2w-fhir` generates a file tree — httpx, pydantic, jinja2, nothing that listens — and it is a dependency of both `dhis2w-cli` and `dhis2w-mcp`, so an optional-dependency group inside it would still put FastAPI + uvicorn in the resolver's path for every install that only ever writes FSH, including CI and the MCP server. A separate member makes the dependency arrow explicit (`fhir-serve → fhir`, never the reverse) and lets the server version and publish on its own.

**Alternatives rejected:** an optional dependency group on `dhis2w-fhir` (fails the "API-only installs stay FastAPI-free" goal and hides the arrow); putting the server in `dhis2w-core` (it is FHIR-shaped, not DHIS2-domain-shaped, and core is imported by everything); a standalone repo (the store, the capture path, and the JSON builders share the parity tests with the generator).

## 2026-08-08 — The received-response spool is files on disk, not SQLite

**Decision:** `d2w fhir serve` writes each received `QuestionnaireResponse` to `.serve/responses/received/<id>.json` and holds nothing: every read re-scans the directory, because `d2w fhir forward` renames these files from another process while the server runs. The write is atomic and durable — `mkstemp` in the same directory, `fsync`, `os.replace`, then an `fsync` of the directory. No database.

**Why:** CLAUDE.md rule 10 says persistent *state* defaults to SQLAlchemy + SQLite, and this is not state — it is artifact persistence. Each receipt is one immutable FHIR document, written once and never updated, and the useful operations on the set are "count what is pending" and "hand the next one to the forwarder". A directory does both with `ls`, keeps every receipt readable by any tool without a schema, and makes an interrupted write a leftover temp file instead of a partially-committed row. The spool assumes a single writing process, which is exactly what one server process is.

**Revisit trigger — recorded deliberately:** the moment a receipt gains mutable state (a forwarding attempt count, a last-error, a status that moves `received → sent → failed`), rule 10 applies and this becomes a SQLite table. The forwarding phase ([FHIR conversion layer](project/fhir-conversion.md)) is where that judgment gets made; until then, adding a database would be a schema with one immutable column. **That judgment is the 2026-08-15 entry at the top of this file**: the trigger fired, and the resolution is files — the status lives in the directory name and the last error in the sidecar.

**Alternatives rejected:** SQLite from the start (a schema and a migration story for write-once documents); in-memory only (a restart loses submissions a client was told were stored).

## 2026-08-08 — A stored QuestionnaireResponse reads back as a receipt, not as DHIS2 data

**Decision:** `GET /QuestionnaireResponse/{id}` returns the submission exactly as it arrived, stamped with the id it is served under. It is never a projection of what DHIS2 currently holds. The accepted-capture OperationOutcome says so in words, `/metadata` says so in `implementation.description`, and the CapabilityStatement's QuestionnaireResponse entry says so in its `documentation`.

**Why:** the facade accepts submissions and does not yet forward them, so the only honest answer to "what is this resource" is "what a client sent us". Serving it as though it were current data would make the endpoint quietly wrong the moment anyone edits the same values in DHIS2 — and would stay wrong after forwarding lands, since DHIS2 remains the system of record either way. Saying it three times, in three places a client actually reads, is cheaper than a support conversation about why a receipt disagrees with a data value set. Querying current data through FHIR is a read proxy, tracked separately in the FHIR roadmap.

**Alternatives rejected:** refusing reads on QuestionnaireResponse entirely (a client that just posted one has a `Location` header pointing at it — 404 on your own `Location` is worse); rewriting a stored response from DHIS2 on read (that is the read proxy, and it is not built).

## 2026-08-08 — The store and the spool hold resources verbatim, not as validated models

**Decision:** `StoreEntry.body` and `StoredResponseEnvelope.response` are `dict[str, Any]`, holding the parsed document as written. The store parses just enough to index a resource (`resourceType`, `id`, `url`, `identifier[]`) and passes the rest through untouched; the spool keeps the received body byte-faithfully. Both fields carry a docstring saying why, and the dict leaves either object only as an HTTP response body.

**Why:** the rule-7 escape hatch is "the HTTP/JSON boundary", and this is one — with the direction reversed from the usual case. An IG holds resource types this repo has no models for (StructureDefinition, ImplementationGuide, whatever a project hand-writes into `input/resources`), and a captured response carries extensions and answer types the R4 subset here does not cover. Validating through a model would mean silently dropping everything outside it, which for a served IG reads as a resource the project never published, and for a receipt means the stored copy is no longer what the client sent. Byte-faithful passthrough is the contract; a model would be a lossy filter wearing a type.

**What is still typed:** everything that carries meaning to another layer — `StoreEntry`'s index fields, `StoredResponseEnvelope`'s receipt metadata, `SearchQuery`, `CaptureIssue`, `ValidatedCapture`, every OperationOutcome and Bundle the facade emits (built from `dhis2w_fhir.r4` models and serialised at the edge). Validation of a received response *does* go through `QuestionnaireResponse`; what gets stored is the original bytes, not the round trip.

**Alternatives rejected:** a `JsonResource`-style permissive model everywhere (adds a validation pass and a re-serialisation that can reorder keys, for no checking); modelling only the served subset (drops the rest of the IG).

## 2026-06-17 — Name the new MCP surface `dhis2w-mcp-router`, not `dhis2w-router`

**Decision:** the search+dispatch router (front many upstream MCP servers behind two meta-tools — `search_tools` + `call_tool`) ships as `dhis2w-mcp-router`, the third MCP surface alongside `dhis2w-mcp` (full server) and `dhis2w-mcp-bridge` (single-tool bridge). Its benchmark lane (`dhis2w_bench.router`, `make bench-router`) lives in `dhis2w-bench` with the other lanes, not in the router package.

**Why:** the decisive factor is a **name collision** — this repo already has a DHIS2 **route plugin** (`d2w route create`, `route_*` MCP tools, reverse-proxy/API routes; see `architecture/route-plugin.md`). A package called `dhis2w-router` reads like "the thing that manages DHIS2 routes," which is exactly what the route plugin does, and would confuse docs, search, and conversation. The `mcp` qualifier disambiguates: it routes among **MCP servers/tools**, not DHIS2 routes. Secondary reasons: it *is* an MCP router (accurate even though the core is domain-neutral); it keeps the three MCP surfaces a readable family (`mcp` / `mcp-bridge` / `mcp-router`); and if it ever extracts to a standalone repo the natural name is `mcp-router` (drop the `dhis2w-` brand) — `dhis2w-router` serves neither the present nor that future. The bench lane stays in `dhis2w-bench` for consistency with every other lane and to keep the router package's core FastMCP-only and domain-neutral (the bench needs the LM-Studio backend). **Alternative considered:** `dhis2w-router` (shorter, top-level framing) — rejected on the route collision; the surfaces doc (`architecture/mcp-surfaces.md`) gives the router equal billing without a top-level name.

## 2026-06-04 — Single metadata listing surface: drop typed per-resource `list`

**Decision:** Listing metadata goes through ONE surface — the generic `d2w metadata list <type>` CLI command and the `metadata_list` MCP tool (plus `metadata list <type> --count` / the `metadata_count` tool for totals). The 34 typed per-resource list commands (`metadata data-elements list`, `metadata indicators list`, …), their 34 MCP counterparts (`metadata_data_element_list`, …), and the ~33 now-dead `service.list_<resource>` functions are removed. Kept: `metadata type list` (the resource-type catalog), every typed sub-app's authoring verbs (`create` / `rename` / `delete` / `add-*` / …), and the special reads (`members`, `tree`, `list-for-combo`, `vars-for`).

**Why:** both list paths hit the same endpoint — `GET /api/<resource>` (e.g. `/api/dataElements`) — so the typed `list` duplicated the generic one with a different, inconsistent flag set. That confused humans and LLM clients alike (a model reaches for `metadata data-elements list --all` and hits "No such option", because `--all`/`--fields`/`--count` live only on the generic command). `/api/metadata` is a separate bundle-export endpoint, not involved in listing. Pre-1.0, no deployed users, so the removal is clean — no shims, no aliases.

**Cost / follow-up:** the typed lists carried resource-specific convenience filters (`--domain-type`, `--program-type`, `--period-type`, viz `--type`, `--program`, `--data-set`) and curated table columns the generic command lacks. For now those are expressed via the generic `--filter <prop>:<op>:<value>` DSL (e.g. `--filter domainType:eq:AGGREGATE`). Re-exposing type-specific filters/columns ergonomically on the canonical surface is tracked in `docs/roadmap.md` (Gaps → Metadata listing consolidation) — that design should land BEFORE the example scripts are rewritten to `--filter`, to avoid churning them twice.

**Pending (split-PR checklist):** docs + examples still reference the removed typed lists — ~42 example scripts (`examples/cli/*.sh`, gated by `make verify-examples`) and ~19 doc pages (incl. the MCP tutorial worked example and `architecture/conventions.md` naming examples). Migrate those as their own slice once the filter-exposure design is settled.

## 2026-05-13 — Lift `Profile` + PAT/Basic `open_client` into `dhis2w-client`

**Decision:** the `Profile` Pydantic model, `profile_from_env_raw()`, and a lightweight `open_client(profile)` that handles `auth in ("pat", "basic")` now live in `dhis2w-client`. `dhis2w-core` becomes a strict superset — TOML loading + multi-profile `resolve()` chain + OAuth2 `_build_oauth2` + token-store wiring stay there, and its `open_client` delegates PAT/Basic to the new helpers in `dhis2w-client`. Every `from dhis2w_core.profile import Profile` / `from dhis2w_core.client_context import build_auth, open_client` import keeps working via re-export.

**Why:** the original split (see 2026-04-17 entry) was correct for "ship `dhis2w-client` lean on PyPI", but the cut was placed slightly too high: a library user embedding `dhis2w-client` for PAT or Basic still had to pull in `dhis2w-core` (and its Typer / FastMCP / SQLAlchemy / bcrypt / questionary deps) to get the `Profile + open_client` ergonomic. Lifting just the model + the two trivial auth dispatches keeps `dhis2w-client` lean (no new deps; `tomllib` is stdlib in 3.11+) and lets PAT/Basic users do `uv add dhis2w-client` alone. OAuth2 still requires `dhis2w-core` because OAuth2 token refresh genuinely needs concurrent-writer safety on the token store. Calling `dhis2w_client.open_client(oauth2_profile)` raises `NotImplementedError` with the install hint pointing at `dhis2w_core.open_client`.

**Also dropped in the same PR:** `alembic>=1.18` from `dhis2w-core` dependencies. It was a declared dep but unused — no `alembic.ini`, no migrations directory; the OAuth2 token store schema is created via `Base.metadata.create_all()`. Pure dead weight.

## 2026-04-19 — Two codegen paths: `/api/schemas` + `/api/openapi.json`

**Decision:** `dhis2w-codegen` emits from both sources into the same per-version directory. `/api/schemas` drives `generated/v{N}/schemas/` + `resources.py` + `enums.py` (the metadata resources). `/api/openapi.json` drives `generated/v{N}/oas/` (the instance-side shapes `/api/schemas` can't describe — `WebMessage` envelopes, tracker read/write, `DataValue` / `DataValueSet`, auth-scheme leaves, data-integrity checks, `SystemInfo`).

Top-level domain modules (`dhis2w_client.v42.envelopes`, `.aggregate`, `.system`, `.maintenance`, `.auth_schemes`, `.generated.v42.tracker`) shim over the OAS output. They add caller-friendly helpers (`WebMessageResponse.created_uid()` / `task_ref()` / `conflicts()` etc., the `AuthScheme` discriminated union, `TrackerBundle`) that OpenAPI doesn't express on its own.

Hand-written hold-outs: `Me` (not in OpenAPI), `PeriodType` (Java class hierarchy upstream, not an enum), `analytics.py` (OpenAPI's `Grid` shape differs from our current accessors — a behaviour-changing migration left for a future touch), `Notification` (OpenAPI ships typed `category` / `dataType` / `level` enums; caller churn to thread them through).

**Why:** hand-writing the ~15 models was tractable for the initial landing; once the surface broadened, the drift risk (DHIS2 ships new fields every minor, the hand-written classes lag silently) justified the emitter infrastructure. The OAS emitter is ~600 LOC + four Jinja templates + `openapi_manifest.json` for reviewable rebuild diffs.

**Three emitter deltas that matter for OAS output:**

- Every field optional (DHIS2 over-marks `required` relative to real response contents — `WebMessage.errorCode` is flagged required but no 200-OK response includes it).
- Enums with > 64 members demote to `str` aliases (`ErrorCode` ships 488 members and grows every minor; a strict StrEnum would reject unknown codes between regen passes).
- Builtin shadows rename to `DHIS2<Name>` (only `Warning` → `DHIS2Warning` in v42). Pydantic resolves `list[Warning]` to the builtin class at FieldInfo construction regardless of `defer_build`, so emit-time renaming is the only reliable fix.

**Alternatives rejected:** leave everything as `dict[str, Any]` (fast but no static checking); keep everything hand-written indefinitely (drift + onboarding cost scale with the number of endpoints we care about).

## 2026-04-18 — Generated pydantic wrappers live in `schemas/`

**Decision:** `dhis2w_client/generated/v{N}/schemas/` holds the per-resource pydantic classes.

**Why:** two reasons. One, "model" widely means a SQLAlchemy/Django ORM row, and we already have those in `dhis2w-core/token_store.py` — same name for two different things would confuse. Two, DHIS2's own REST API calls these `/api/schemas`; using the server's term anchors the generated code to the source it derives from.

**Alternatives rejected:** `models/` (accepted common-in-pydantic-ecosystem naming but breaks our internal consistency); `types/` (overlaps with `typing` + collides with `metadata type list` CLI sub-command).

## 2026-04-18 — `Dhis2` StrEnum + `Dhis2Client(version=...)` kwarg

**Decision:** `dhis2w_client.Dhis2` is a `StrEnum` listing the supported DHIS2 majors (`V42`, `V43`). `Dhis2Client(..., version=Dhis2.V42)` skips auto-detection via `/api/system/info` and binds the specified generated module. Omit to let the client auto-detect.

**Why:** users targeting a known DHIS2 line shouldn't have to eat a roundtrip to `/api/system/info` and shouldn't have to guess whether auto-fallback will land them on a close-but-wrong version. The enum makes valid values discoverable in IDE autocomplete; the kwarg makes intent explicit.

**Alternatives rejected:** `version: str` (no tab-completion, typo-prone); a `version: str | Dhis2` union (adds a string-parsing branch, awkward for zero API gain).

## 2026-04-18 — OAuth2 redirect receiver stays a loopback socket, and `redirect_capturer` is the seam

**Decision:** the redirect receiver invoked during `d2w profile login` is the bare `asyncio.start_server` loopback in `dhis2w-client/v{41,42,43}/auth/oauth2.py`. `OAuth2Auth` takes a pluggable `redirect_capturer`, which is the seam a caller substitutes — `dhis2w-core`'s profile service passes one that refuses rather than opening a browser, so `d2w profile verify` never starts a login flow by accident. There is no `oauth2_redirect.py` and no FastAPI app in the auth path.

**Why:** the FastAPI rule in CLAUDE.md governs *services* — something that stays up, routes requests, and has a contract. This is a one-shot socket that reads a single redirect and closes, and it lives in `dhis2w-client`, which has to stay FastAPI-free for PyPI. The 2026-04-17 entry below ("OAuth2 loopback via `asyncio.start_server`") is the decision that holds; the capturer protocol is what keeps the mechanism swappable without dragging a web framework into the published client.

**Where the FastAPI rule does bind:** a real HTTP surface lands as its own workspace member — see the 2026-08-08 `dhis2w-fhir-serve` entry.

## 2026-04-18 — Preflight-check DHIS2 before running the OAuth2 flow

**Decision:** both `d2w profile verify` (for oauth2 profiles) and `d2w profile login` probe `GET /.well-known/openid-configuration` before doing anything else. On 404 / 500 / connection error, we emit an actionable message (`"set oauth2.server.enabled = on in dhis.conf and restart"`) and bail out.

**Why:** DHIS2 ships Spring Authorization Server switched off. Without the preflight, users would see a cryptic mid-flow failure (404 after the browser opens, or a token-exchange HTTP error). The one extra roundtrip catches the common misconfig and produces a message the user can act on.

**Alternatives rejected:** rely on the main OAuth2 call to fail — poor UX, fails too deep in the flow to suggest a config fix.

## 2026-04-18 — OAuth2 client registration with BCrypt-hashed secret, Jackson-serialized settings, `scopes = "ALL"`

**Decision:** `infra/scripts/_seed_auth_oauth2.py` POSTs to `/api/oAuth2Clients` with `clientSecret` pre-hashed by BCrypt, with `clientSettings` / `tokenSettings` populated with the exact Jackson-serialized Spring AS JSON that the DHIS2 settings UI writes, and with `scopes = "ALL"` only. The seed additionally PATCHes the admin user's `openId` to match the username so JWTs with `sub=admin` map to a real DHIS2 user.

**Why:** each of these were real failure modes uncovered during OAuth2 bring-up against DHIS2 v2.42:

- Plaintext `clientSecret` → 401 `invalid_client` at `/oauth2/token` (DHIS2 uses `BCryptPasswordEncoder`).
- Empty `clientSettings` / `tokenSettings` → 500 `IllegalArgumentException: settings cannot be empty` at `/oauth2/authorize`.
- `scopes = "openid email ALL"` (space-separated) → Spring AS's `validateScopes` rejects whitespace inside a scope, and DHIS2 has no fine-grained scopes anyway.
- Empty `openId` on admin → 401 `Found no matching DHIS2 user for the mapping claim` when using a valid JWT.

**Alternatives rejected:** creating clients via the DHIS2 settings UI — the UI omits `scopes` and `clientAuthenticationMethods`, so UI-created clients can't complete the end-to-end flow.

## 2026-04-18 — DHIS2's own AS is registered as a generic OIDC provider to its own API

**Decision:** `dhis.conf` carries a full `oidc.provider.dhis2.*` block (client_id, client_secret, issuer_uri, authorization_uri, token_uri, jwk_uri, user_info_uri, redirect_url, scopes, mapping_claim). This tells DHIS2's API-side JWT validator that its own Spring AS is a trusted issuer — without it, even tokens minted by DHIS2 itself are rejected as "Invalid issuer" on `/api/*`.

**Why:** DHIS2 v2.42 doesn't auto-wire the AS as an internal OIDC provider when `oauth2.server.enabled=on`. The JWT validator's registry (`DhisOidcProviderRepository`) only contains what `oidc.provider.<id>.*` populates. The generic OIDC parser does NOT fall back to OIDC discovery for missing URIs — every endpoint has to be listed explicitly (observed at startup: `missing a required property: 'user_info_uri'`, `missing a required property: 'authorization_uri'`, etc.).

**Alternatives rejected:** relying on issuer-URI auto-discovery (not implemented in v2.42); documenting it as a post-seed manual step (invisible bootstrap — wrong default).

## 2026-04-18 — Default profile scope is global; `--global/--local` flag pair

**Decision:** `d2w profile add` with no scope flag writes to `~/.config/dhis2/profiles.toml`. `--local` opts into `.dhis2/profiles.toml` in the current directory. `--global` is an explicit no-op alias. `--scope global|project` is removed from docs (still works internally).

**Why:** users typically have 1-3 DHIS2 instances they return to; global is the correct default. Scoping to the current directory by default would silently create `.dhis2/` in whatever directory you happened to run the command — surprising. The `--global/--local` flag pair matches git (`git config --global`), npm (`npm install -g`), and `aws configure --profile`, all of which treat global as the baseline and local as the override.

## 2026-04-18 — Profile names restricted to `^[A-Za-z][A-Za-z0-9_]*$`

**Decision:** `validate_profile_name()` enforces a strict identifier-like grammar — must start with a letter, then letters/digits/underscores only, max 64 characters. Checked at every mutation (`add`, `rename`, `default`). Names like `"he llo"`, `prod-eu`, `1stthing` are rejected with a clean error pointing at the rules.

**Why:** names become env var suffixes (`DHIS2_PROFILE=prod_eu`), TOML keys, and unquoted shell arguments. Allowing spaces/hyphens/dots means every call site needs quoting discipline; the failure mode is subtle and platform-dependent. A narrow grammar avoids the whole class. Typical user names (`local`, `prod`, `laohis42`) fit trivially.

## 2026-04-18 — `d2w profile rename` preserves scope + default

**Decision:** `rename_profile(old, new)` mutates whichever file the old name lives in (project or global), preserves key ordering, and updates the `default` key if the renamed profile was the default. Refuses to clobber an existing name.

**Why:** renames are a common "I picked the wrong name" recovery action. Preserving scope keeps a project-local profile local (no surprise scope jump); preserving default keeps workflows working after the rename without a separate `profile default` step.

## 2026-04-18 — Profiles live in directories, not loose TOML files

**Decision:** `.dhis2/profiles.toml` (project) and `~/.config/dhis2/profiles.toml` (global). The `.dhis2/` and `~/.config/dhis2/` are directories, not bare files.

**Why:** the directory holds every scope-local artefact, not just profiles — OAuth2 token DB, metadata cache, per-scope preferences all land under the same prefix. Costs nothing over a loose file and scales cleanly as new artefacts land.

## 2026-04-18 — Name-as-ID for profiles, no UUIDs

**Decision:** profile identifier is the user-chosen name (`local`, `prod`, `staging`). No separate opaque ID.

**Why:** profiles are low-cardinality (2–10 per user over a lifetime), human-picked, rarely moved. UUIDs would be clutter. The name *is* the API.

## 2026-04-18 — MCP profile tools are read-only; mutations are CLI-only

**Decision:** `profile_list`, `profile_verify`, `verify_all_profiles`, `profile_show` are exposed as MCP tools. `add_profile`, `remove_profile`, `set_default_profile` are **not** — they're CLI-only.

**Why:** an autonomous agent rewriting the user's credential files is the wrong default. Reading (and probing with existing creds) is safe. Writing requires a human at the keyboard.

## 2026-04-18 — Every MCP tool takes an optional `profile: str | None`

**Decision:** instead of making the MCP server stateful (`use_profile` setter + shared state), every tool accepts a per-call `profile` kwarg that overrides the default.

**Why:** stateless is simpler, matches MCP's function-call model, and avoids surprises when multiple agents share a server. The call-site precedence is then: tool arg → `DHIS2_PROFILE` env → raw `DHIS2_URL/PAT` env → project TOML default → global TOML default → `NoProfileError`. All five layers exist and are individually useful.

## 2026-04-17 — uv workspace instead of single package

**Decision:** repo is a virtual `uv` workspace with multiple members under `packages/`.

**Why:** `dhis2w-client` must ship to PyPI without dragging Typer/FastMCP/Playwright deps. MCP servers deployed in Docker don't need the CLI. New surfaces (FastAPI, TUI) should land as new folders, not conditional imports.

**Alternatives rejected:**

- Single package with optional-dependency extras — doesn't reduce import-time surface, and extras don't help when users install from PyPI.
- Monorepo with separate PyPI projects per top-level folder — same thing, more ceremony.

## 2026-04-17 — Chapkit's linter config copied verbatim

**Decision:** ruff + mypy + pyright configs in the workspace root match chapkit exactly.

**Why:** chapkit is the house standard. Matching conventions across personal projects means less mental overhead. Divergence requires justification.

## 2026-04-17 — `dhis2-claude-theme` for docs with left-side nav only

**Decision:** mkdocs with the custom claude theme, `navigation.sections` + `navigation.expand` + `navigation.indexes` features, no `navigation.tabs`.

**Why:** user finds top-tab nav distracting. The sidebar carries everything, auto-expanded.

## 2026-04-17 — Plugin runtime in `dhis2w-core`, both CLI and MCP mount it

**Decision:** plugins live in `dhis2w-core/v42/plugins/<name>/` with `service.py` + `cli.py` + `mcp.py`. `dhis2w-cli` and `dhis2w-mcp` discover them at startup via module walk + entry points.

**Why:** MCP tool calls should never subprocess the CLI (latency, lost typing, text parsing). Sharing `service.py` across both surfaces gives parity for free and lets tests cover both through one code path.

**Alternatives rejected:**

- MCP shelling out to `d2w` CLI — slow, brittle, loses pydantic in/out.
- MCP importing Typer commands programmatically — fights Typer's CLI ergonomics; you end up wanting the underlying function anyway.

## 2026-04-17 — Pluggable auth via Protocol

**Decision:** `dhis2w-client` defines `AuthProvider` Protocol; ships Basic/PAT/OAuth2 providers; accepts any conforming class.

**Why:** DHIS2 has at least three auth mechanisms in common use (Basic, PAT, OAuth2/OIDC) and future providers will appear (service-account JWT, OIDC federation, proxied auth). Hardcoding auth into the client means forking it whenever a new mechanism is needed.

## 2026-04-17 — OAuth2 loopback via `asyncio.start_server`

**Decision:** OAuth2 provider uses `asyncio.start_server` for the loopback redirect, not `http.server.HTTPServer` on a thread.

**Why:** native async cleanup, no thread-pool juggling, no concurrent-request surprise, clearer lifecycle. Matches the async-first stance of the rest of the client.

**Alternative rejected:** running `http.server.HTTPServer.handle_request` in `run_in_executor`. Works, but requires custom subclass for silent logging and doesn't integrate with async task cancellation.

## 2026-04-17 — Version-aware committed generated clients

**Decision:** `dhis2w_client.generated.v{40,41,42,43}/` are separate modules, populated by `d2w codegen`, committed to git. `Dhis2Client.connect()` picks the right one via `/api/system/info`.

**Why:** user's explicit direction. DHIS2 schemas evolve per version; a single hand-curated client either lags or grows shims. Committed generated code means PyPI users don't need to run the generator, and diffs are reviewable in PRs.

**Alternatives rejected:**

- Runtime dynamic models (`pydantic.create_model`) — kills static analysis, no autocomplete, pyright-strict incompatible.
- Single hand-written model set covering v41 + v42 + v43 — combinatorial explosion of optional fields, or worse, silent accuracy drift.
- Code-generated output gitignored and regenerated at CI — PyPI install wouldn't have the types.

## 2026-04-17 — Strict version dispatch by default, opt-in soft fallback

**Decision:** `Dhis2Client` raises `UnsupportedVersionError` when the reported DHIS2 version has no generated module. `allow_version_fallback=True` enables nearest-lower fallback with a warning (never nearest-higher).

**Why:** strict by default protects library users from silently losing typed fields. Agents and CLIs that want to keep running against unknown versions opt in explicitly; library code that cares about correctness gets the default.

## 2026-04-17 — Async-only, no sync façade

**Decision:** all public APIs in `dhis2w-client` are `async`. No sync wrapper generated via `unasync` or similar.

**Why:** FastMCP and FastAPI are async, httpx is async, and notebook users who actually need sync can do `asyncio.run(...)`. A sync wrapper would double the test surface for negligible ergonomic gain.

## 2026-04-17 — camelCase fields in generated pydantic models

**Decision:** generated pydantic models use DHIS2's camelCase field names directly (e.g. `displayName`), not snake_case with aliases.

**Why:** eliminates alias translation at parse/serialise time; the wire format and the Python field names are identical. Codegen output is explicitly not PEP 8 pure — it mirrors the source API.

## 2026-04-17 — SQLAlchemy + SQLite for persisted state

**Decision:** any persistent storage in this workspace (OAuth2 tokens, metadata cache, run history) uses SQLAlchemy async + aiosqlite with Alembic migrations. No Postgres, no raw SQL, no pickled files.

**Why:** SQLite is the correct scale for personal/project-scoped tooling. SQLAlchemy gives us typed `Mapped[...]` columns for free. Alembic means schema changes are reviewable.

## 2026-04-17 — Filesystem-scan version discovery, not a hardcoded list

**Decision:** `dhis2w_client.generated.available_versions()` walks the `generated/` folder and imports each `v\d+` subpackage, returning only those whose `__init__.py` sets `GENERATED = True`. No hardcoded `_KNOWN` tuple.

**Why:** originally the list was hardcoded. Filesystem scan means adding a new version is literally just running codegen — no Python edit required. The supported set today is v41 + v42 + v43; the discovery path doesn't care.

## 2026-04-17 — Codegen templates use relative imports

**Decision:** generated `__init__.py` does `from .resources import Resources`, and `resources.py` does `from .schemas.<name> import <Name>`. Not absolute `from dhis2w_client.generated.v43.resources ...`.

**Why:** absolute imports tie the generated code to exactly one install location, breaking when the module is imported from tmp_path during tests, or if a downstream project vendors the generated code elsewhere. Relative imports resolve wherever the package sits.

(Originally written with `.models.<name>` — directory was renamed to `schemas/` on 2026-04-18 to match DHIS2's own `/api/schemas` endpoint and free up "model" for SQLAlchemy-style DB models.)

## 2026-04-17 — Codegen derives resource class names from `schema.klass`, not `schema.name`

**Decision:** the Java-class tail (`klass.rsplit(".", 1)[-1]`) is the primary identifier for a generated resource. `schema.singular` and `schema.name` are fallbacks.

**Why:** `schema.name` is not unique across DHIS2's `/api/schemas` response — six schemas (JobConfiguration, Route, etc.) all report `name="identifiableObject"`. `klass` is fully qualified and always distinct. The emitter also dedupes by final class name + plural attr-name to catch any remaining collisions.

## 2026-04-17 — Generated resources return raw dicts for create/update/delete

**Decision:** `create`, `update`, and `delete` return `dict[str, Any]` — the raw DHIS2 import-summary response — not parsed pydantic models.

**Why:** DHIS2's response shape for write operations (`{status, stats, response: {uid, errorReports, ...}}`) is not the resource shape. Parsing into the resource model would discard detail. Typed GET/LIST keep pydantic; write responses stay raw.

## 2026-04-17 — System module endpoints use dedicated models

**Decision:** `/api/system/info` and `/api/me` get pydantic models in `dhis2w_client/system.py`. `client.system.info()` and `client.system.me()` are accessors on the client.

**Why:** these aren't metadata types, so `/api/schemas` doesn't describe them. `SystemInfo` was hand-written initially; it now re-exports from the OAS codegen output at `generated/v42/oas/system_info.py` (46 fields where we'd hand-maintained 9). `Me` stays hand-written because `/api/me` isn't a component schema in the OpenAPI spec.

## 2026-04-17 — Integration tests use string fixtures, not shared dataclass

**Decision:** `conftest.py` in each member exposes `play_url`, `play_username`, `play_password` as separate session-scoped string fixtures. Test files accept them as individual parameters rather than a single `PlayCredentials` object.

**Why:** pytest's conftest auto-discovery doesn't make fixtures importable as module attributes — `from tests.conftest import PlayCredentials` fails in mypy and at runtime (`tests/` is not a real package). Flat string fixtures sidestep that entirely and let each member have its own conftest.

## 2026-04-17 — COMPLEX schema properties become `Any`, not `dict[str, Any]`

**Decision:** codegen maps DHIS2 schema property type `COMPLEX` to `Any` in generated pydantic fields.

**Why:** empirically, DHIS2's COMPLEX fields return dicts, lists, empty lists, or nested arrays of dicts across different metadata types. `dict[str, Any]` forces pydantic to reject anything non-dict, which breaks real server responses (observed with `Constant.attributeValues = []`). `Any` plus `extra="allow"` preserves the payload without validation failures.

## 2026-04-17 — Generated CRUD dumps with `mode="json"`

**Decision:** `create` and `update` in the generated resources template use `model.model_dump(by_alias=True, exclude_none=True, mode="json")`.

**Why:** default pydantic dumps leave `datetime` objects raw, which `httpx.Request(json=...)` cannot serialise. `mode="json"` converts datetime → ISO 8601 strings and handles other JSON-unfriendly types transparently. No cost on models that don't have such fields.

## 2026-04-17 — `DHIS2_HEADFUL=1` env var flips Playwright to visible mode

**Decision:** `dhis2w_browser.session.resolve_headless()` is the single source of truth for headed-vs-headless. Explicit `headless=bool` kwargs override. Otherwise, `DHIS2_HEADFUL=1` (or `true`/`yes`/`on`) shows the browser; anything else keeps it headless.

**Why:** tests and automation want headless for speed; humans debugging a flow want to see what's happening. A single env var applied across every Playwright entry point (CLI, test fixtures, programmatic callers) means one switch controls all of them.

## 2026-04-17 — Dep floors bumped to installed latest

**Decision:** every `>=` floor across member and workspace `pyproject.toml` files was raised to match the currently-installed version. Major-version gaps (e.g. `fastmcp>=2.0` while we run 3.x, `pytest>=8.4` while we run 9.x, `mkdocstrings>=0.26` while we run 1.x) were closed.

**Why:** the lockfile always pinned latest — but the floors in pyproject.toml were stale reading "we support 2.x" when we actively require 3.x features. Tightening the floors keeps documentation and constraints honest, without changing actual installed versions. Future `uv lock --upgrade` runs (`make deps-upgrade`) continue to pick up latest.

## 2026-04-17 — Playwright PAT helper uses Playwright for login, API for creation

**Decision:** `dhis2w_browser.create_pat` navigates to the DHIS2 login UI with Playwright (driven form fill + submit), then uses the authenticated browser context's `page.request.post` to hit `/api/apiToken`. It does not automate the PAT-creation UI.

**Why:** mixing UI flow (for auth cookie) with API flow (for PAT creation) is robust to future UI changes — the login selectors are stable across DHIS2 versions; the PAT UI isn't. Using the authenticated context's request client preserves cookies without us having to marshal them manually.

## 2026-04-17 — In-process FastMCP Client for MCP testing

**Decision:** MCP integration tests construct a `FastMCP` server via `build_server()`, hand it to `fastmcp.Client(server)`, and call tools inside the same Python process. No subprocess, no stdio framing.

**Why:** FastMCP's `Client` accepts a `FastMCP` instance directly when you pass the server object. This gives real tool invocation through FastMCP's dispatch machinery without the cost or flakiness of spawning a subprocess. ~50ms per test instead of multi-second. The code path exercised is the same one an external agent would hit; we only skip transport serialization.

## 2026-04-17 — CLI tested via `typer.testing.CliRunner`, not subprocess

**Decision:** `dhis2w-cli` integration tests use `CliRunner().invoke(build_app(), [...])` rather than `subprocess.run(["uv", "run", "d2w", ...])`.

**Why:** subprocess invocation is ~2s per test (venv resolution overhead). CliRunner runs Typer dispatch in-process in ~5ms and covers everything that can actually break — command wiring, Typer argument parsing, async-run bridging, printed output. The console-script entry point itself is a one-liner we trust.

## 2026-04-17 — Shared `profile_from_env()` for CLI and MCP

**Decision:** every plugin service call reads the DHIS2 profile from environment variables via `dhis2w_core.profile.profile_from_env()`. CLI commands and MCP tools both call this at invocation time; no profile threading through arguments.

**Why:** keeps the two surfaces perfectly symmetric. The CLI user exports env vars in their shell; the MCP client configures `env` in its server spec. Neither surface has to invent its own profile flag. A future `.dhis2/profiles.toml` layer will be added inside `profile_from_env()` without either surface changing.

## 2026-04-17 — Tests auto-source seeded `.env.auth`

**Decision:** conftest files in `dhis2w-client`, `dhis2w-cli`, and `dhis2w-mcp` walk up from the test file to find `infra/home/credentials/.env.auth` and `os.environ.setdefault(...)` every line. Explicit env overrides win; the seeded file is a fallback.

**Why:** when the user runs `make dhis2-run`, we write the PATs into that file. The test suite picks them up automatically on the next `make test-slow` run — no manual `source` step. The `setdefault` means CI or an explicit env override still takes precedence.

## 2026-04-17 — mypy excludes `conftest.py` to allow per-member conftests

**Decision:** root `pyproject.toml` sets `[tool.mypy] exclude = "^packages/[^/]+/tests/conftest\\.py$"`.

**Why:** two `conftest.py` files at sibling `tests/` dirs both resolve to the module name `conftest`, which mypy rejects as duplicate. Excluding them from mypy is pragmatic — they're fixture-only, pytest still discovers them normally, and actual test functions stay fully typechecked.
