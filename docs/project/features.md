---
title: Feature catalog
---

# Feature catalog

A complete Python toolkit for DHIS2 v41, v42, and v43; async client library,
CLI, MCP servers, browser automation, and codegen, organized as a `uv` workspace
with six publishable packages and one internal generator.

!!! note "Scope of this page"
    This is the user-facing capability inventory across all surfaces. The exact
    command and tool counts are regenerated per release; the auto-built
    [CLI reference](../cli-reference.md) and [MCP tool reference](../mcp-reference.md)
    are the source of truth when a number here drifts. For where the project is
    heading, see the [Roadmap](../roadmap.md).

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
runtime; drop it into any async Python project.

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

- **`/api/schemas`**: pydantic models + `StrEnum`s for every metadata resource
  (DataElement, Indicator, Program, OrgUnit, ...)
- **`/api/openapi.json`**: instance-side shapes (tracker write payloads,
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

- `patch_bulk(operations, concurrency=10)`: JSON Patch with semaphore control
- `apply_sharing_bulk(objects, sharing, concurrency=10)`; bulk sharing updates
- `stream_to(query, file)`: stream large analytics results to disk

### Utilities

- **Period math:** `parse_period()`, `next_period_id()`, `previous_period_id()`, `period_start_end()`
- **UID generation:** `generate_uids(count)`: offline, CSPRNG-based
- **Retry transport:** honors `Retry-After`, retries 429/502/503/504 automatically

---

## Plugin Runtime

**Package:** `dhis2w-core` | **Install:** `uv add dhis2w-core`

Shared runtime that bridges the pure client with user-facing surfaces (CLI, MCP).
Provides profile discovery, plugin registry, auth factory, and token store.

### Profile System

Connection profiles are discovered automatically:

1. `./.dhis2/profiles.toml`: project-local (CWD walk-up)
2. `~/.config/dhis2/profiles.toml`: user-wide
3. Environment variables: `DHIS2_URL`, `DHIS2_USERNAME`/`DHIS2_PASSWORD`/`DHIS2_PAT`
4. `DHIS2_PROFILE` env to pin a named profile

Each profile stores: name, base URL, auth type (basic/pat/oauth2), and DHIS2
version (v41/v42/v43).

### Token Store

SQLite-backed (`aiosqlite`) at `.dhis2/tokens.sqlite`, keyed by profile name.
Handles OAuth2 token caching and automatic refresh on expiry.

### First-Party Plugins

22 built-in plugins, each with a service layer (`service.py`) and CLI
commands (`cli.py`); most also expose MCP tools (`mcp.py`). Every built-in
plugin exists in three version trees (v41, v42, v43). The version-neutral
**fhir** plugin ships as its own `dhis2w-fhir` package and mounts through
the external entry-point mechanism.

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
| **fhir** | FHIR IG generation (package `dhis2w-fhir`): scaffold a dockerized SUSHI project (`fhir init`), generate FSH from DHIS2 metadata (`fhir generate`) - a `foundation` target emitting the DHIS2 identifier aliases and the NamingSystems declaring them, plus the `D2Period` extension and its period-type CodeSystem/ValueSet (all 23 DHIS2 period types, with a matching `parse_period` ISO parser), option sets as CodeSystem/ValueSet pairs carrying both DHIS2 identifiers, organisation units as paired Organization/Location instances with partOf hierarchy and losslessly embedded GeoJSON (one file per level, optional CodeSystem representation) - with DHIS2 `NAME` translations carried through as CodeSystem concept designations and HL7 translation extensions on titles and instance names, filtered by `[generate] locales` - and check an instance's codes for FHIR-safety (`fhir validate`: instance-wide `/api/metadata` sweep plus a deep option-set pass gated on `--code-source`, reports written as Markdown, CSV, and PDF (clickable contents, bookmarked sections, Lao-script font support), exit 1 on errors; the read-only `fhir_validate` is the plugin's only MCP tool - scaffolding/generation are CLI-only). Artifact naming is configurable via `[generate.naming]` in a committed `fhir.toml` discovered by walking up from the working directory, with uid-sourced ids keeping the UID's own case (`d2-os-Qdm5fPK5Ra9-cs`); `fhir init --publisher-url` opts into a `publisher.url` in `sushi-config.yaml`. |
| **messaging** | Message conversations: list, get, send, reply, mark read/unread, ticket-workflow priority/status/assignment. |
| **maintenance** | Background tasks, cache clear, data-integrity checks, soft-delete cleanup, validation runs, predictor runs, analytics-table rebuild. |
| **doctor** | Health probes: ~100+ metadata checks, DHIS2 data-integrity checks, BUGS.md workaround drift detection. |
| **security** | Read-only security posture: version and patch posture (end-of-life version lines, patch and hotfix currency within the supported line, and a curated security-advisory patch floor sourced from the DHIS2 GitHub advisories; a newer release line is an informational note, since a supported non-latest line is a healthy state), transport and security headers (TLS scheme off the resolved base URL plus the Strict-Transport-Security, Content-Security-Policy (and -Report-Only), X-Frame-Options, X-Content-Type-Options, Cross-Origin-Opener/Embedder/Resource-Policy, and Server headers read off one `/api/system/info` response: flags plaintext HTTP, a missing HSTS / CSP / nosniff header, missing anti-framing when neither X-Frame-Options nor a CSP frame-ancestors directive is present, and a Server header that discloses a version token. The grading goes beyond presence: a present-but-weak HSTS header parses `max-age` with a strict digit-only regex and raises ONE WARN when it is missing, invalid, non-positive, below 1 day, or below the recommended 1 year (a `max-age` of 1 year or more is clean); a present-but-weak CSP is parsed into a directive map and aggregated into ONE MEDIUM "Content-Security-Policy is weak" finding listing the failed directives; report-only-only mode, a missing fetch directive on a content-governing policy, a broad source (`*`, `http:`, `https:`, `data:`) or `unsafe-inline`/`unsafe-eval` in script sources, an un-locked-down object-src, an unset or broad base-uri, and a present-but-broad frame-ancestors (`strict-dynamic` is annotated, never warned). DHIS2's stock `frame-ancestors 'self';` is a frame-only policy and is deliberately left ungraded on its content directives so a default instance is never flagged, and a missing frame-ancestors is owned by the anti-framing WARN, never double-flagged in the CSP finding. DHIS2 sets none of COOP/COEP/CORP (it calls Spring Security's `defaultsDisabled()` and re-enables only contentTypeOptions, xssProtection, and HSTS), so the absent cross-origin isolation headers are aggregated into a SINGLE INFO "Cross-origin isolation headers not configured (COOP/COEP/CORP)" rather than three WARNs that would fire on every stock instance; BUGS.md #55. The transport probe also reads the live CORS response headers: because DHIS2's `DhisCorsProcessor` emits Access-Control-Allow-Origin / Access-Control-Allow-Credentials only on a request that carries an Origin, the probe sends a benign foreign Origin (an unresolvable `.invalid` host, never the instance's own origin which DHIS2 always echoes) on its allowlisted `GET /api/system/info` and grades the echoed values: a wildcard `*` or the reflected foreign origin with `Access-Control-Allow-Credentials: true` is HIGH (any origin can make authenticated requests), the same without credentials is WARN, and a specific origin echoed with credentials is a trusted-origin-review WARN. This reads what the server actually grants on the wire, complementing the settings check's read of the declared `/api/configuration/corsWhitelist` config), password policy and registration settings (weak minimum password length, failed-login lockout disabled, passwords never expiring, self-registration captcha disabled, users able to self-grant their own authorities, email verification not enforced (a standalone WARN emitted only when `enforceVerifiedEmail` is explicitly off, never on v41 where the key is absent so a `None` value is left untouched), a permissive `*` CORS origin read from `/api/configuration/corsWhitelist` plus an INFO surfacing a non-empty no-wildcard CORS allowlist for review with its origins enumerated, a static reminder that DHIS2 has no global 2FA enforcement, and account recovery or email verification enabled while SMTP is unconfigured), account authority risk categorisation (dangerous authorities grouped into named categories; superuser/ALL, user-and-role management including F_IMPERSONATE_USER account takeover, app management and custom JS/CSS, SQL views, route management (F_ROUTE_PUBLIC_ADD and its siblings, which can author the very SSRF targets the routes check flags), system configuration including F_SYSTEM_SETTING, metadata import/export, tracker admin, and data administration), instance role audit (ALL-granting and dangerous-authority roles flagged from that taxonomy, a role granting route-management or user-management authorities is HIGH, with member counts), per-user account hygiene (privileged accounts joined to login recency and 2FA posture, including superuser-without-2FA via the v42+ `/api/users/twoFactor` audit endpoint; privileged accounts that never logged in (HIGH) or have gone stale past `--stale-days` (MEDIUM) stay high-signal per-user rows, while active non-privileged accounts that never logged in or have gone stale are rolled up into at most two aggregate WARN findings, "Active accounts that never logged in" and "Stale active accounts", each carrying the offender count plus a username sample capped at 10, so a large instance never emits a row per account and a privileged never-logged-in account is never double-counted in the non-privileged aggregate. Password age is graded the same way but independent of privilege: every active account whose password is older than `--max-password-age` (default 365 days) OR has never been set is rolled up into ONE aggregate WARN "Accounts with stale or unset passwords" carrying the count plus a username sample capped at 10. The `passwordLastUpdated` field is the one genuine wire divergence isolated in `_wire.py`; v41 nests it under `userCredentials`, v42/v43 flatten it onto the User; BUGS.md #56), installed-apps inventory (side-loaded frontend code, App Hub update currency, and custom JS/CSS injection, degrading cleanly when the App Hub is unreachable), an anonymous-access probe (unauthenticated reads of login-required endpoints, self-registration state, and account recovery), a public-metadata sharing check (public-write and externally-accessible objects across the data-bearing and exposure-prone metadata types, decoded from each object's sharing block and built into a single access graph alongside the user/role/group principals, paged and capped by `--max-objects` with loud truncation), an opt-in interactive sharing explorer (`--sharing-graph` / `--visualize` writes a self-contained, offline d3 bundle `sharing-explorer.html` into the run folder: an effective-access reasoning engine that answers "who can concretely read or write this object, and by what path" over the unified access graph, with an object tree, exposure triage, by-principal / by-role pivots, a d3 force-directed graph of the sharing topology, and an access-matrix heatmap of group access per object type), a route-target audit (inventories DHIS2 Route API objects from `/api/routes` and flags each whose destination URL resolves to a private/internal IP (RFC1918, loopback, link-local, unspecified, IPv6 ULA), an internal hostname (`localhost`, `.internal`/`.local`/`.localdomain`), or the cloud instance-metadata endpoint (169.254.169.254 / the IPv6 metadata address / `metadata.google.internal`, flagged as the more specific metadata finding so a single host never raises two HIGHs); a Route is a server-side reverse proxy DHIS2 fetches on the caller's behalf, so a private destination is an SSRF primitive: it also flags `/**` subpath wildcards, routes with no required authorities that fall back to ACL sharing, and notes routes carrying stored upstream credentials (the secret is WRITE_ONLY upstream and never read; only the non-secret identity is shown). The check inspects the configured URL host only and never executes a route. The auth block is the one genuine wire divergence isolated in `_wire.py` (v41's undiscriminated 4-variant union has no OAuth2 client-credentials variant; v42/v43's is the discriminated 5-variant union; BUGS.md #14)), a personal-access-token audit (inventories the PATs readable by the audited account from `/api/apiToken` and flags non-expiring tokens (null/absent `expire` or an epoch already in the past, HIGH) and tokens with no IP allowlist (HIGH), calling out the worst case of a token that both never expires and is usable from anywhere; a MEDIUM inventory summary states the scope verbatim. Scope is a runtime authority distinction, not a version one: `ApiToken` is `defaultPrivate(true)`, so a non-superuser sees only its own tokens and the run adds an INFO caveat that other users' tokens are invisible, while an account with the ALL authority gets the system-wide inventory. The token secret (`key`) is `@JsonIgnore` upstream and never on the wire, so nothing secret is read or carried. The one wire divergence, v41's `ApiToken.type` is a `Literal` with an id-only `createdBy`, v42/v43's is the `ApiTokenType` enum with a `UserDto`, is isolated in each tree's `_wire.tokens_from_raw`, which normalises `type` to a plain str so the version-invariant reducer never imports `ApiTokenType` (BUGS.md #51)), an external login-methods audit (inventories the pre-auth OIDC providers offered on the login page from `/api/loginConfig` (each flagged INFO as a federated trust path; SAML providers are not surfaced here) and the OAuth2 clients DHIS2 acts as an authorization server for from `/api/oAuth2Clients`, flagging a MEDIUM for a broad grant type (client_credentials, implicit, password, or the device-authorization grant URN) or a loose redirect URI (a wildcard, or a non-loopback cleartext `http://` target; loopback `http://localhost` / `127.0.0.1` are not flagged, RFC 8252), with a per-clean-client INFO suppressed when that client also triggers a MEDIUM. The `/api/oAuth2Clients` list requires the F_OAUTH2_CLIENT_MANAGE authority on v42/v43, so a 401/403/404 (never retried) degrades the check with a note while the loginConfig OIDC findings still run. The OAuth2-client wire shape is the one genuine divergence isolated in `_wire.oauth2_clients`: v41 reads the `data` envelope + `cid` + array-typed `grantTypes`/`redirectUris`, v42/v43 read the `oAuth2Clients` envelope + `clientId` + comma-string `authorizationGrantTypes`/`redirectUris`, both projected into one hand-rolled version-invariant `OAuth2ClientView` that omits any secret field so a client secret can never reach a finding; BUGS.md #52, cross-referencing #39), an auditing-posture check (reports the DHIS2 audit configuration: the master `system.audit.enabled` switch, the `audit.logger` file sink, the `audit.database` sink, and the four `audit.metadata` / `audit.aggregate` / `audit.tracker` / `audit.api` scope matrices. This posture lives only in `dhis.conf` and is exposed by no API endpoint, so the API-first result is an INFO that the posture is not API-readable; never a claim that auditing is off. Pass `--dhis-conf <path>` (env `DHIS2_CONF_LOCATION`) pointed at a local COPY of the server's `dhis.conf` to evaluate it: the check then flags auditing disabled instance-wide, both sinks off, every scope matrix blank while auditing is on, and narrow scope coverage that leaves scopes unmonitored or omits CREATE/UPDATE/DELETE/SECURITY (all MEDIUM); a missing/unreadable path degrades with a note. Secret redaction is enforced by construction; the parser retains only the audit keys plus a set/not-set flag for confidential keys (the encryption / connection / analytics / LDAP / Redis / Artemis / OAuth2-keystore / monitoring passwords) and physically cannot hold a secret value, so no password can reach any rendered report. The check needs no per-run API read and runs by default across v41/v42/v43, last in canonical order; BUGS.md #53), and a step-by-step audit runner (`security audit`) that streams a live progress display and writes a report to disk in Markdown, plaintext, CSV, and a self-rendering HTML bundle (open `report.dc.html`; per-scan data lives in `report-data.js` beside a fixed template, runtime, and logo; each HTML section header carries a "See all checks" toggle that lists every control the check evaluated with a live PASS / FLAGGED / SKIPPED outcome, so a reader sees what was inspected and passed, not only the findings that tripped, with SKIPPED reflecting the real conditions that limit a run such as a 403 on the per-user 2FA endpoint, an unreachable App Hub, a non-superuser token scope, or no `--dhis-conf`) (resumable). A `security report` command re-renders an existing run's report files from its JSONL spine without re-scanning. Read-only GET requests against a tested allowlist, with one exception: an optional default-credential probe (the well-known admin/district pair, on by default, `--no-credential-probe` to disable) makes a single HTTP Basic login attempt against `/api/me` and flags a CRITICAL when it succeeds. The full `audit` runner (and its credential probe, guest probe, sharing scan, and per-check subcommands) is CLI-only; the cheap single-request reads are also exposed as read-only MCP tools (`security_settings`, `security_authorities`, `security_version`), each one read-only GET against an already-allowlisted path. `security_version` deliberately skips the external release feed, so it stays a single DHIS2 request with no external egress (the feed-based behind-latest-patch refinement is audit-only). |
| **system** | System info, current user (whoami), calendar, system-settings read/write. |
| **customize** | Brand + theme an instance: login logos, banner, CSS, preset apply. |
| **profile** | Profile CRUD, verification, OAuth2 login/logout, OIDC discovery, PAT + OAuth2-client provisioning. |
| **browser** | Playwright-driven UI automation (PAT creation, login, screenshots). Requires `[browser]` extra. |
| **dev** | Developer tools: UID generation, codegen, sample-data fixtures. |

### External Plugin Discovery

Plugins register via `importlib.metadata.entry_points(group="dhis2.plugins")`
and are discovered automatically at startup. The in-repo `dhis2w-fhir` package
is the first-party example of this mechanism.

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

d2w fhir            FHIR IG generation (SUSHI/FSH, package dhis2w-fhir)
  init                  Scaffold a dockerized SUSHI IG project + fhir.toml
  generate foundation   DHIS2 identifier aliases + the D2Period extension
  generate option-sets  Option sets as CodeSystem/ValueSet pairs
  generate org-units    Org units as Organization/Location instances
  generate all          All three targets in one run
  validate              FHIR-safety of the instance's codes (sweep + md/csv/pdf reports)

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

FastMCP server (`dhis2`) exposing every plugin as typed MCP tools: 319 tools
across 17 plugin groups. The full catalog is auto-generated into
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

- PAT creation requires a session cookie: DHIS2 gates `/api/apiToken` behind it
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

- `discover.py`: fetch `/api/schemas`, normalize to `SchemasManifest`
- `emit.py`: walk manifest, render pydantic models via Jinja templates
- `oas_emit.py`: emit OpenAPI-based shapes with spec patches
- `spec_patches.py`: apply fixes for things DHIS2's OpenAPI spec omits
- `diff.py`: cross-version structural diff (e.g., v42 vs v43)

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

- **`client/`**: 27+ Python examples (whoami, CRUD, analytics, OIDC, bulk
  import, tracker lifecycle, sharing, error handling, ...)
- **`cli/`**: 15+ shell scripts covering every CLI domain
- **`mcp/`**: 14+ Python examples showing MCP tool usage

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

