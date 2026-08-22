---
title: Feature catalog
---

# Feature catalog

A complete Python toolkit for DHIS2 v41, v42, and v43; async client library,
CLI, MCP servers, browser automation, a FHIR IG generator with its own serving
facade, and codegen, organized as a `uv` workspace with ten publishable packages
and two workspace-only ones.

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
- [FHIR IG Toolchain (dhis2w-fhir, dhis2w-fhir-serve)](#fhir-ig-toolchain)
- [FHIR Evaluation Engine (dhis2w-fhir-engine)](#fhir-evaluation-engine)
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
element = await client.resources.data_elements.get(uid)
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

- `patch_bulk(resource_type, patches, concurrency=8)`: RFC 6902 JSON Patch across many UIDs, fanned out through a bounded worker pool
- `apply_sharing_bulk(resource_type, uids, sharing, concurrency=8)`: one sharing block applied to many UIDs through the same pool
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

One row of the table is not a `d2w` plugin. **fhir-engine** is a package with a
console script of its own and no DHIS2 dependency at all, and it is what the
FHIR packages read FHIR through - it owns the R4 resource models `dhis2w-fhir`
and `dhis2w-fhir-serve` both import. It sits beside **fhir** because that is
where a reader looking for the FHIR surface will look, and it is named as a
package rather than a plugin in its own row.

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
| **fhir** | FHIR Implementation Guide generation, serving, capture, and forwarding (packages `dhis2w-fhir` + `dhis2w-fhir-serve`). See [FHIR IG Toolchain](#fhir-ig-toolchain). |
| **fhir-engine** | FHIRPath, CQL, and ELM evaluation over FHIR data, the R4 resource models the FHIR packages read through, and clinical quality measure evaluation (package `dhis2w-fhir-engine`). See [FHIR Evaluation Engine](#fhir-evaluation-engine). |
| **messaging** | Message conversations: list, get, send, reply, mark read/unread, ticket-workflow priority/status/assignment. |
| **maintenance** | Background tasks, cache clear, data-integrity checks, soft-delete cleanup, validation runs, predictor runs, analytics-table rebuild. |
| **doctor** | Health probes: ~100+ metadata checks, DHIS2 data-integrity checks, BUGS.md workaround drift detection. |
| **security** | Read-only security posture: version and patch posture (end-of-life version lines, patch and hotfix currency within the supported line, and a curated security-advisory patch floor sourced from the DHIS2 GitHub advisories; a newer release line is an informational note, since a supported non-latest line is a healthy state), transport and security headers (TLS scheme off the resolved base URL plus the Strict-Transport-Security, Content-Security-Policy (and -Report-Only), X-Frame-Options, X-Content-Type-Options, Cross-Origin-Opener/Embedder/Resource-Policy, and Server headers read off one `/api/system/info` response: flags plaintext HTTP, a missing HSTS / CSP / nosniff header, missing anti-framing when neither X-Frame-Options nor a CSP frame-ancestors directive is present, and a Server header that discloses a version token. The grading goes beyond presence: a present-but-weak HSTS header parses `max-age` with a strict digit-only regex and raises ONE WARN when it is missing, invalid, non-positive, below 1 day, or below the recommended 1 year (a `max-age` of 1 year or more is clean); a present-but-weak CSP is parsed into a directive map and aggregated into ONE MEDIUM "Content-Security-Policy is weak" finding listing the failed directives; report-only-only mode, a missing fetch directive on a content-governing policy, a broad source (`*`, `http:`, `https:`, `data:`) or `unsafe-inline`/`unsafe-eval` in script sources, an un-locked-down object-src, an unset or broad base-uri, and a present-but-broad frame-ancestors (`strict-dynamic` is annotated, never warned). DHIS2's stock `frame-ancestors 'self';` is a frame-only policy and is deliberately left ungraded on its content directives so a default instance is never flagged, and a missing frame-ancestors is owned by the anti-framing WARN, never double-flagged in the CSP finding. DHIS2 sets none of COOP/COEP/CORP (it calls Spring Security's `defaultsDisabled()` and re-enables only contentTypeOptions, xssProtection, and HSTS), so the absent cross-origin isolation headers are aggregated into a SINGLE INFO "Cross-origin isolation headers not configured (COOP/COEP/CORP)" rather than three WARNs that would fire on every stock instance; BUGS.md #55. The transport probe also reads the live CORS response headers: because DHIS2's `DhisCorsProcessor` emits Access-Control-Allow-Origin / Access-Control-Allow-Credentials only on a request that carries an Origin, the probe sends a benign foreign Origin (an unresolvable `.invalid` host, never the instance's own origin which DHIS2 always echoes) on its allowlisted `GET /api/system/info` and grades the echoed values: a wildcard `*` or the reflected foreign origin with `Access-Control-Allow-Credentials: true` is HIGH (any origin can make authenticated requests), the same without credentials is WARN, and a specific origin echoed with credentials is a trusted-origin-review WARN. This reads what the server actually grants on the wire, complementing the settings check's read of the declared `/api/configuration/corsWhitelist` config), password policy and registration settings (weak minimum password length, failed-login lockout disabled, passwords never expiring, self-registration captcha disabled, users able to self-grant their own authorities, email verification not enforced (a standalone WARN emitted only when `enforceVerifiedEmail` is explicitly off, never on v41 where the key is absent so a `None` value is left untouched), a permissive `*` CORS origin read from `/api/configuration/corsWhitelist` plus an INFO surfacing a non-empty no-wildcard CORS allowlist for review with its origins enumerated, a static reminder that DHIS2 has no global 2FA enforcement, and account recovery or email verification enabled while SMTP is unconfigured), account authority risk categorisation (dangerous authorities grouped into named categories; superuser/ALL, user-and-role management including F_IMPERSONATE_USER account takeover, app management and custom JS/CSS, SQL views, route management (F_ROUTE_PUBLIC_ADD and its siblings, which can author the very SSRF targets the routes check flags), system configuration including F_SYSTEM_SETTING, metadata import/export, tracker admin, and data administration), instance role audit (ALL-granting and dangerous-authority roles flagged from that taxonomy, a role granting route-management or user-management authorities is HIGH, with member counts), per-user account hygiene (privileged accounts joined to login recency and 2FA posture, including superuser-without-2FA via the v42+ `/api/users/twoFactor` audit endpoint; privileged accounts that never logged in (HIGH) or have gone stale past `--stale-days` (MEDIUM) stay high-signal per-user rows, while active non-privileged accounts that never logged in or have gone stale are rolled up into at most two aggregate WARN findings, "Active accounts that never logged in" and "Stale active accounts", each carrying the offender count plus a username sample capped at 10, so a large instance never emits a row per account and a privileged never-logged-in account is never double-counted in the non-privileged aggregate. Password age is graded the same way but independent of privilege: every active account whose password is older than `--max-password-age` (default 365 days) OR has never been set is rolled up into ONE aggregate WARN "Accounts with stale or unset passwords" carrying the count plus a username sample capped at 10. The `passwordLastUpdated` field is the one genuine wire divergence isolated in `_wire.py`; v41 nests it under `userCredentials`, v42/v43 flatten it onto the User; BUGS.md #56), installed-apps inventory (side-loaded frontend code, App Hub update currency, and custom JS/CSS injection, degrading cleanly when the App Hub is unreachable), an anonymous-access probe (unauthenticated reads of login-required endpoints, self-registration state, and account recovery), a public-metadata sharing check (public-write and externally-accessible objects across the data-bearing and exposure-prone metadata types, decoded from each object's sharing block and built into a single access graph alongside the user/role/group principals, paged and capped by `--max-objects` with loud truncation), an opt-in interactive sharing explorer (`--sharing-graph` / `--visualize` writes a self-contained, offline d3 bundle `sharing-explorer.html` into the run folder: an effective-access reasoning engine that answers "who can concretely read or write this object, and by what path" over the unified access graph, with an object tree, exposure triage, by-principal / by-role pivots, a d3 force-directed graph of the sharing topology, and an access-matrix heatmap of group access per object type), a route-target audit (inventories DHIS2 Route API objects from `/api/routes` and flags each whose destination URL resolves to a private/internal IP (RFC1918, loopback, link-local, unspecified, IPv6 ULA), an internal hostname (`localhost`, `.internal`/`.local`/`.localdomain`), or the cloud instance-metadata endpoint (169.254.169.254 / the IPv6 metadata address / `metadata.google.internal`, flagged as the more specific metadata finding so a single host never raises two HIGHs); a Route is a server-side reverse proxy DHIS2 fetches on the caller's behalf, so a private destination is an SSRF primitive: it also flags `/**` subpath wildcards, routes with no required authorities that fall back to ACL sharing, and notes routes carrying stored upstream credentials (the secret is WRITE_ONLY upstream and never read; only the non-secret identity is shown). The check inspects the configured URL host only and never executes a route. The auth block is the one genuine wire divergence isolated in `_wire.py` (v41's undiscriminated 4-variant union has no OAuth2 client-credentials variant; v42/v43's is the discriminated 5-variant union; BUGS.md #14)), a personal-access-token audit (inventories the PATs readable by the audited account from `/api/apiToken` and flags non-expiring tokens (null/absent `expire` or an epoch already in the past, HIGH) and tokens with no IP allowlist (HIGH), calling out the worst case of a token that both never expires and is usable from anywhere; a MEDIUM inventory summary states the scope verbatim. Scope is a runtime authority distinction, not a version one: `ApiToken` is `defaultPrivate(true)`, so a non-superuser sees only its own tokens and the run adds an INFO caveat that other users' tokens are invisible, while an account with the ALL authority gets the system-wide inventory. The token secret (`key`) is `@JsonIgnore` upstream and never on the wire, so nothing secret is read or carried. The one wire divergence, v41's `ApiToken.type` is a `Literal` with an id-only `createdBy`, v42/v43's is the `ApiTokenType` enum with a `UserDto`, is isolated in each tree's `_wire.tokens_from_raw`, which normalises `type` to a plain str so the version-invariant reducer never imports `ApiTokenType` (BUGS.md #51)), an external login-methods audit (inventories the pre-auth OIDC providers offered on the login page from `/api/loginConfig` (each flagged INFO as a federated trust path; SAML providers are not surfaced here) and the OAuth2 clients DHIS2 acts as an authorization server for from `/api/oAuth2Clients`, flagging a MEDIUM for a broad grant type (client_credentials, implicit, password, or the device-authorization grant URN) or a loose redirect URI (a wildcard, or a non-loopback cleartext `http://` target; loopback `http://localhost` / `127.0.0.1` are not flagged, RFC 8252), with a per-clean-client INFO suppressed when that client also triggers a MEDIUM. The `/api/oAuth2Clients` list requires the F_OAUTH2_CLIENT_MANAGE authority on v42/v43, so a 401/403/404 (never retried) degrades the check with a note while the loginConfig OIDC findings still run. The OAuth2-client wire shape is the one genuine divergence isolated in `_wire.oauth2_clients`: the `oAuth2Clients` list envelope is the same on every major, but v41 reads `cid` + array-typed `grantTypes`/`redirectUris` while v42/v43 read `clientId` + comma-string `authorizationGrantTypes`/`redirectUris`, both projected into one hand-rolled version-invariant `OAuth2ClientView` that omits any secret field so a client secret can never reach a finding; BUGS.md #52, cross-referencing #39), an auditing-posture check (reports the DHIS2 audit configuration: the master `system.audit.enabled` switch, the `audit.logger` file sink, the `audit.database` sink, and the four `audit.metadata` / `audit.aggregate` / `audit.tracker` / `audit.api` scope matrices. This posture lives only in `dhis.conf` and is exposed by no API endpoint, so the API-first result is an INFO that the posture is not API-readable; never a claim that auditing is off. Pass `--dhis-conf <path>` (env `DHIS2_CONF_LOCATION`) pointed at a local COPY of the server's `dhis.conf` to evaluate it: the check then flags auditing disabled instance-wide, both sinks off, every scope matrix blank while auditing is on, and narrow scope coverage that leaves scopes unmonitored or omits CREATE/UPDATE/DELETE/SECURITY (all MEDIUM); a missing/unreadable path degrades with a note. Secret redaction is enforced by construction; the parser retains only the audit keys plus a set/not-set flag for confidential keys (the encryption / connection / analytics / LDAP / Redis / Artemis / OAuth2-keystore / monitoring passwords) and physically cannot hold a secret value, so no password can reach any rendered report. The check needs no per-run API read and runs by default across v41/v42/v43, last in canonical order; BUGS.md #53), and a step-by-step audit runner (`security audit`) that streams a live progress display and writes a report to disk in Markdown, plaintext, CSV, and a self-rendering HTML bundle (open `report.dc.html`; per-scan data lives in `report-data.js` beside a fixed template, runtime, and logo; each HTML section header carries a "See all checks" toggle that lists every control the check evaluated with a live PASS / FLAGGED / SKIPPED outcome, so a reader sees what was inspected and passed, not only the findings that tripped, with SKIPPED reflecting the real conditions that limit a run such as a 403 on the per-user 2FA endpoint, an unreachable App Hub, a non-superuser token scope, or no `--dhis-conf`) (resumable). A `security report` command re-renders an existing run's report files from its JSONL spine without re-scanning. Read-only GET requests against a tested allowlist, with one exception: an optional default-credential probe (the well-known admin/district pair, on by default, `--no-credential-probe` to disable) makes a single HTTP Basic login attempt against `/api/me` and flags a CRITICAL when it succeeds. The full `audit` runner (and its credential probe, guest probe, sharing scan, and per-check subcommands) is CLI-only; the cheap single-request reads are also exposed as read-only MCP tools (`security_settings`, `security_authorities`, `security_version`), each one read-only GET against an already-allowlisted path. `security_version` deliberately skips the external release feed, so it stays a single DHIS2 request with no external egress (the feed-based behind-latest-patch refinement is audit-only). |
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

d2w fhir            FHIR IG generation (SUSHI/FSH + pre-built JSON, package dhis2w-fhir)
  init                  Scaffold a dockerized SUSHI IG project + fhir.toml
                        (--data-set / --event-program / --tracker-program seed
                        the questionnaire targets; --refresh updates an existing
                        project's scaffold-managed files, rewriting only where no
                        line on disk is lost, and refuses any flag it would ignore)
  generate              All seven targets in one run, off a single pass over the
                        instance (8 requests where the solo targets total 25),
                        reported as one summary row per target; the notes go to
                        reports/fhir-generate-notes.md with one counted hint on
                        the terminal, counting the kinds that only restate a
                        validate finding apart (--details prints them inline)
  generate foundation   DHIS2 identifier aliases + the D2Period / D2FormType /
                        D2AttributeValue / D2OrganisationUnit /
                        D2TrackerEnrollment extensions
  generate option-sets  Option sets as pre-built CodeSystem/ValueSet JSON
  generate categories   Categories as pre-built CodeSystem/ValueSet JSON
                        (category options as the concepts)
  generate questionnaires
                        Data sets + event programs + tracker program stages as
                        Questionnaire instances
  generate examples     Example QuestionnaireResponses (synthetic or real instance data)
  generate org-units    Organisation units as Organization/Location instances
  generate pages        Narrative site pages + per-artifact intros (markdown)
  generate load-set     Synthetic QuestionnaireResponse JSON under load/ for
                        posting at a running facade (--per-target, --output-dir;
                        deliberately not part of a full run - a load set is not
                        IG source)
  validate              FHIR-safety of the instance's codes (sweep + three deep
                        passes + md/csv/pdf reports written into --output-dir),
                        severity graded by build impact on the configured
                        selection (scope: selection/instance), including a
                        code-stem preview of a code-sourced [generate.naming]
                        source (code-stem-fallback warnings, code-stem-refusal
                        errors matching generate's refusal). The terminal is a
                        status view: the summary with the selection split and
                        the code-coverage fraction (objects whose code can
                        serve as an identity stem), a rollup row per (severity,
                        scope, category), every error individually, and one
                        line naming the report file; --details lists every
                        finding, --fail/--no-fail gates the exit code
  serve                 Serve the IG as a FHIR read + capture facade (package
                        dhis2w-fhir-serve, via the dhis2w-cli[serve] extra;
                        --live builds the store off the instance at startup,
                        --strict-codes/--no-strict-codes governs codes outside
                        the served terminology, --ui adds the browser capture
                        UI, --auth none|token|dhis2|jwt with --auth-scope
                        write|all
                        says who is served and how much of the surface the
                        posture covers, and host/port/authentication/strict
                        codes fall back to the [serve]
                        table of fhir.toml - where capture and spool_dir carry
                        no flag, capture=false being the viewer posture and
                        spool_dir naming the receipt tree; ConceptMap
                        $translate is answered over the published maps;
                        Questionnaire/{id}/$generate answers a served form with a
                        synthetic response postable straight back, optionally from a
                        named seed; stored responses are receipts; the profile is
                        the root d2w -p, resolved before the start banner)
  forward               Drain the capture spool back into DHIS2: translate every
                        received QuestionnaireResponse into its /api/dataValueSets
                        envelope or /api/tracker event and post it. DRY RUN IS THE
                        DEFAULT - every payload goes to the real endpoint under its
                        own validate-only mode (dryRun=true / importMode=VALIDATE),
                        so DHIS2's rules decide each answer while nothing is written
                        and no receipt moves; --import commits and then files each
                        receipt by what it became (accepted -> forwarded/, rejected
                        -> rejected/ beside <id>.report.json, refused stays put),
                        and [forward] import = true makes the bare run commit
                        for a project whose drains are routine, the flag still
                        outranking the file. One drain at a time: an exclusive
                        flock on .serve/responses/.drain.lock names its holder.
                        --strict-codes/--no-strict-codes overrides [serve]
                        strict_codes; rejections roll up by cause (error code +
                        the message with its quoted UIDs generalised away) as a
                        reasons table on the terminal and at the head of the
                        report, so 202 rejections read as the 3 rules they
                        broke; a dry run counts a stage event whose enrollment
                        a registration of the same run creates as unverifiable
                        rather than rejected - it writes nothing, so there is
                        no enrollment to check the event against - and gets its
                        own count and section, while a stage event naming an
                        enrollment no registration of the run creates stays a
                        rejection; a DHIS2 rejection exits 1 and a dry run whose
                        only failures are unverifiable exits 0; outcomes go to
                        reports/fhir-forward-report.md with one counted hint
                        (--details prints them inline, with a Why column
                        carrying each response's first reason)
  spool                 What waits in the capture spool and what became of the
                        rest, per state, counting the queued receipts the last
                        committing drain refused to translate (--details lists
                        every receipt with its reason, off the import report or
                        the refusal record beside it); no DHIS2 connection and
                        no profile
  requeue               Move receipts DHIS2 refused back into the queue for the
                        next drain (<id>... or --all-rejected), leaving the
                        import report behind as the record of what DHIS2 last
                        answered; refuses an id that is not there before
                        anything moves
  doctor                Scaffold a throwaway project against the ambient profile
                        and drive the whole chain through it in nine typed
                        phases (connect, scaffold, generate, compile, validate,
                        serve, capture, forward, oracle), each PASS / WARN /
                        FAIL / SKIPPED / BLOCKED with a stated reason; only a
                        FAIL exits 1, and reports/fhir-doctor-report.md is the
                        artifact a handover is read from

  Every command with an instance behind it narrates its steps on stderr - a
  spinner on a terminal, plain [k/N] lines when redirected - and takes
  --progress/--no-progress. Tables, notes, and progress are stderr; stdout
  carries the --json payload alone, so --json implies a silent stderr.

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

FastMCP server (`dhis2`) exposing every plugin as typed MCP tools: 320 tools
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

## FHIR IG Toolchain

**Packages:** `dhis2w-fhir`, `dhis2w-fhir-serve` | **Install:** `uv tool install "dhis2w-cli[serve]"`

Turn a DHIS2 instance into a published FHIR R4 Implementation Guide, serve that
guide as a read-and-capture facade, and drain what was captured back into DHIS2.
The version-neutral `fhir` plugin ships as its own `dhis2w-fhir` package and
mounts through the entry-point mechanism; the facade lives in
`dhis2w-fhir-serve`, pulled in by the `dhis2w-cli[serve]` extra so an install
that only generates stays FastAPI-free.

Four verbs over one project directory - `init`, `generate`, `validate`,
`serve` - plus `forward` to close the loop and `doctor` to drive the whole
chain in one command.

### Scaffold a project

`d2w fhir init` scaffolds a dockerized SUSHI project.

- **A `uv` project.** `pyproject.toml` declares `dhis2w-cli` + `dhis2w-fhir` +
  `dhis2w-fhir-serve`, all sourced from the repository on `main`, so the `d2w`
  binary, the plugin behind `d2w fhir`, and the server behind `d2w fhir serve`
  are one build. The committed `uv.lock` pins the toolchain every make target
  drives through `uv run d2w`; a `.python-version` of `3.13` pins the
  interpreter beside it.
- **The rest of the tree.** `fhir.toml`, `sushi-config.yaml`, the Makefile, the
  Dockerfile, and a `.gitignore` covering `.venv/` and the generated
  `ig/input/resources/` but never the lock nor `ig/input/fsh/`. `load/` and
  `.serve/` are gitignored too.
- **Seeding the selection.** `--data-set` / `--event-program` / `--tracker-program`
  seed the questionnaire targets, with the option sets those targets reference
  unioned into the terminology selection.
- **`--status`** seeds `[ig] status`; **`--publisher-url`** opts into a
  `publisher.url` in `sushi-config.yaml`; **`--profile`** seeds the top-level
  `profile` key so the scaffolded project reads an instance without a flag
  (offline - the name is written as given, never resolved against
  `profiles.toml`); **`--max-level`** seeds the organisation-unit depth cap;
  **`--sushi-timeout`** sets the `[FSH] timeout` of `ig/fsh.ini`, the ceiling
  the IG publisher gives its internal SUSHI run - an IG whose FSH overruns it
  fails the build with exit 143.
- **`--refresh`** brings an existing project's scaffold-managed files up to
  date, recovering the IG identity from the project's own `fhir.toml`,
  `ig/fsh.ini`, and `ig/sushi-config.yaml`, and rewriting a file only when the
  current render reproduces every line already on disk in order. So a refresh
  adds what the scaffold gained (a new `path-resource` glob, a new `.gitignore`
  entry, a new menu entry) and never drops a line the user wrote. Each file is
  reported as created / refreshed / unchanged / with your additions / diverged
  (kept) - the last two both keep the file byte-identical, and `diverged` names
  no author, because a line the user wrote and a scaffold line that has since
  changed read the same to a line-preserving refresh. `fhir.toml` is never
  written; `--force` is rejected; any flag the refresh would ignore is refused.
  The accepted consequence is that a scaffold line deliberately deleted is
  restored, since a deletion leaves the file a subsequence of the render.

### Build and publish

- **The scaffolded Makefile.** `make refresh` chains clean-all, upgrade,
  generate, a non-fatal validate, sushi, and build. `make update` re-runs the
  scaffold refresh. `make serve` / `make serve-live` / `make serve-ui` read the
  `[serve]` table; `make forward` / `make forward-import` drive the drain.
  `make check` is the artifact scan below, and `make build` runs it first.
- **`make build` builds on the container's own disk.** Docker on macOS reaches a
  mounted host directory over a network-style filesystem, and the publisher's
  output phase writes tens of thousands of small files one at a time - 341
  seconds through the mount against 21 on the container's disk, measured on one
  guide. The target streams the project in, builds there, and streams `output/`,
  `fsh-generated/` and `input-cache/` back; `temp/` and `template/` stay behind,
  since nothing reads them and they are the bulk of what a build writes.
  `make build-bind` runs the publisher straight over the mount for anyone who
  wants to watch `output/` fill as it is written.
- **`d2w fhir check-artifacts` refuses a doomed build in seconds.** The
  generate-time gate stands at the emit site, and a build never visits it:
  `make build` publishes whatever `ig/fsh-generated/` and `ig/input/` hold, so
  artifacts written before the gate existed, artifacts from an older toolchain
  pin, and hand-authored FSH all reach the publisher without passing it. The
  command applies the same refusal to those files - `ig/fsh-generated/**/*.json`,
  `ig/input/resources/**/*.json`, and `ig/input/fsh/**/*.fsh` - reading `name`,
  `title`, `display`, `text`, and `identifier[].value` through the shared
  `build_aborting_name` / `build_aborting_code` predicates rather than a second
  copy of the rule. Each finding names the file, the resource, the element, the
  value, and the one line that answers it, which differs for a generated file
  (rename in DHIS2 or narrow the selection, then regenerate) and a hand-authored
  one (edit the file). It opens no connection and reads no profile, exits 1 on
  findings, and takes `--no-fail`, `--json`, and an optional project directory.
  `ig/input/pagecontent/**/*.md` is out of scope on purpose: markdown carries
  HTML by design. An existing project takes the gate up with one
  `d2w fhir init --refresh`.
- **`JAVA_HEAP`** sizes the publisher JVM heap - the knob for an exit-137 OOM
  kill on a small docker VM.
- **Registry scale.** `d2w fhir generate org-units` warns at generate time once
  the registry passes 2,000 instances, because the IG publisher validates and
  renders every resource and the registry therefore sets the wall clock of
  `make build`. The warning names the `[generate.organisation_units]`
  `max_level` / `root` dials.
- **A code or name carrying `<` refuses the run.** `d2w fhir generate` refuses
  a run whose emitted code or byte-true name carries `<`, through the same
  predicates `fhir validate` grades with, naming the resource type, UID, name,
  and code - because the IG publisher writes identifier values and titles into
  pages it strict-parses after writing, and aborts its final pass on the
  malformed page after every resource has been rendered. The whole run is
  refused rather than the object skipped, since skipping leaves every
  Questionnaire binding it pointing at a ValueSet nobody wrote.
- **The name gate covers every kind of object a selection publishes**: option
  sets and their options, categories and their category options, organisation
  units, data sets, event programs, tracker programs and their stages, tracked
  entity types, and the data elements and tracked entity attributes those forms
  ask as questions - a question's name is its label and its data-dictionary
  concept display, both byte-true DHIS2 data. Every target that writes a form's
  name reads the same gate, so `generate pages` and `generate examples` refuse
  exactly what `generate questionnaires` refuses. The parity with
  `fhir validate` runs both ways: a validate error on the build path is a
  generate refusal, and a generate refusal is a validate error on the build
  path. Only codes stay asymmetric, and deliberately - a question object's code
  becomes a concept property the publisher escapes rather than an identifier
  value it does not.
- **Or the guide publishes the name in wording the build survives.** Refusing is
  one answer and often the wrong one: DHIS2 names carry `<` legitimately, and an
  age band called `5 to < 15 years, Female` is not a defect to be renamed in a
  production instance. `--substitute-hostile-names` publishes it as `5 to under
  15 years, Female` (`<=` reads as `at most`); `--refuse-hostile-names` keeps
  today's refusal; `[generate] hostile_names = "refuse" | "substitute"` is the
  project's standing answer; and with none of them a run holding a terminal
  prints the count, up to ten `before -> after` samples, and asks, while a run
  with no terminal names the two flags and rewrites nothing rather than hanging a
  script on a prompt. A flag beats the dial, the dial beats the question. DHIS2 is
  never written to, and names only: no code, UID, or identifier value is
  rewritten, so the ConceptMaps still take a published concept back to its DHIS2
  object, and a code carrying `<` refuses the run under either answer. The rewrite
  lands where DHIS2 metadata enters the emission inputs, before a single identity,
  stem, or decomposition is planned off a name, so every target inherits one
  spelling - which is also how it covers the class no refusal reaches: a DHIS2
  form name and a category option combo name, which become question text and data
  dictionary concept displays (one national selection generated cleanly and handed
  the publisher 738 of them). Every rewrite is a `name-substitution` note, one per
  distinct DHIS2 name.

### Generate the IG source

`d2w fhir generate` runs all seven targets in one go, off a single pass over
the instance - 8 requests where the solo targets total 25 - reported as one
summary row per target. Notes go to `reports/fhir-generate-notes.md` with one
counted hint on the terminal, counting the kinds that only restate a `validate`
finding apart; `--details` prints them inline.

#### Targets and selection

- **Four target tables** select what is published:
  `[generate.data_sets]`, `[generate.event_programs]` (WITHOUT_REGISTRATION),
  `[generate.tracker_programs]` (WITH_REGISTRATION), and
  `[generate.tracked_entity_forms]`.
- **`[generate.tracked_entity_forms]`** names the tracked entity types that
  publish a person-only registration form under `fsh/tracked-entity-types/`
  (`D2TET_<type>`, form kind `tracked-entity`): the attributes the type itself
  collects, every item at the entity level, no enrollment, no organisation-unit
  assignment, answered against `D2TrackedEntityResponse` and forwarded as a
  bare `/api/tracker` `trackedEntities` entry.
- **Absent or empty means all** of that kind for the first three tables, and
  the types the selected tracker programs register for the fourth; a non-empty
  list filters.
- **The whole-instance sweep** routes every program by its live `programType`
  and collects the types neither table maps into one aggregate note. A program
  listed under the table its type does not belong to is a loud failure by name,
  pointing at the table that does select it.

#### Foundation: identifiers and extensions

The `foundation` target emits the DHIS2 identifier aliases and the
NamingSystems declaring them, plus these extensions:

- **`D2Period`** - contexted on QuestionnaireResponse and MeasureReport, with
  its period-type CodeSystem/ValueSet over all 23 DHIS2 period types, matched
  by a `parse_period` ISO parser and its `recent_periods` inverse.
- **`D2PeriodType`** - contexted on Questionnaire and bound to that same
  ValueSet: the reporting frequency an aggregate form's responses have to
  report under, so a client resolves the ISO period format off the form rather
  than off an example.
- **`D2DateLabels`** - contexted on Questionnaire, one `valueString` slice per
  date the instance labels (`enrollmentDate` and `incidentDate` off a tracker
  program, `eventDate` off a program stage or an event program's stage), each
  slice present only where DHIS2 states a label and each carrying its own
  translations.
- **`D2Repeatable`** - contexted on Questionnaire, valued boolean: whether one
  enrollment may capture a tracker program stage more than once, declared
  either way on every stage form.
- **`D2Description`** - contexted on `Questionnaire.item`, valued string: the
  DHIS2 free text about the data element, tracked entity attribute, or section
  a question or group is asked from.
- **`D2FormType`** - contexted on Questionnaire and QuestionnaireResponse
  alike.
- **`D2ProgramRule`** - a repeating complex extension carrying, per rule the
  form does not itself express, the DHIS2 rule UID (`valueId`), its name and
  free text with their translations, the expression the server evaluates
  character for character, and what the rule does, coded from the
  `D2ProgramRuleAction` CodeSystem/ValueSet pair over every
  `programRuleActionType` v41, v42, and v43 declare.
- **`D2OrganisationUnitAssignment`** - contexted on Questionnaire, valued
  `Reference(List)`: the organisation units a form may be captured against.
- **`D2AttributeOptionCombos`** (Questionnaire, `canonical(ValueSet)`) paired
  with **`D2AttributeOptionCombo`** (QuestionnaireResponse, `Coding`) - the
  third key of a DHIS2 data value set, `(orgUnit, period, attributeOptionCombo)`.
- **`D2OrganisationUnitLevel`** - contexted on Location, valued `Coding` and
  bound extensibly to the organisation-unit level ValueSet: the hierarchy level
  a published place sits at, stated on the Location because that is the
  hierarchy-bearing half of the pair, while the Organization already carries
  the same coding as `Organization.type`.
- **`D2AttributeValue`** - contexted on Organization, Location, CodeSystem,
  ValueSet, and Questionnaire.
- **`D2TrackedEntityAttributeValue`** - contexted on Patient.

#### Program rules

- **Two tiers are expressed in core FHIR and carry no extension of their own.**
  A `SHOWERROR` refusing a number outside a range becomes the core `minValue` /
  `maxValue` on the question it tests, narrowing whatever the DHIS2 value type
  already stated. A `HIDEFIELD` on one other question's answer becomes core
  `item.enableWhen` with the operator negated, plus - where DHIS2 would show
  the question before anything is answered - an `exists` arm under
  `enableBehavior = #any`.
- **A deliberately conservative grammar** reads the conditions: one comparison
  between one `#{variable}` and one literal, optionally `d2:hasValue`-guarded
  on that same variable, with the variable resolved through
  `programRuleVariables` to a question the same form asks.
- **Every rule it cannot read whole is published whole instead** on
  `D2ProgramRule`, never half-translated.

#### Organisation-unit assignment

- Published as one R4 `List` of Locations per form under
  `ig/input/resources/assignments/`, and only when the DHIS2 assignment is a
  proper subset of the published registry: assigned everywhere publishes
  nothing, and absence means the whole registry.
- Tracker stages share their program's `List`, because DHIS2 hangs the
  assignment on the program - one `List` across the registration form and every
  stage.
- `List` rather than `Group` because R4 admits no Location as a
  `Group.member.entity`.
- `d2w fhir serve` grades the subject, the tracker organisation-unit extension,
  and every ORGANISATION_UNIT answer against it, on the same lenient/strict
  dial coded answers take, and `$generate` draws its Location from it.

#### Attribute option combos

- One CodeSystem/ValueSet pair per distinct non-default attribute category
  combo under `ig/input/resources/attribute-option-combos/`, on the `AOC`
  naming token - deliberately not the data dictionary's `COC`, which codes a
  question's disaggregation cells rather than the combo the whole response is
  filed under. One pair is shared by every data set on that combo.
- A ConceptMap per pair takes each concept back to
  `<base>/id/category-option-combo` and its `-code` sibling.
- One `Coding`-valued concept property per category the combo splits over,
  declared `category-<stem>` with the category's name as its description and
  valued into that category's own published `d2-cat-<stem>-cs` CodeSystem, in
  the category combo's own order, on the same concept-code assignment the
  category pair builds its concepts from. Carried on the `D2COC_CS`
  disaggregation vocabulary as well as on every `D2AOC` pair, so a reader
  holding "Fixed, <1y" can dig into the Fixed and the <1y it was met from.
- A category outside `[generate.categories]` drops its axis with a
  selection-gap note rather than coding into a CodeSystem nobody wrote.
- Nothing at all for a default-combo data set, because absence means the
  default combo. Publishing the combo is what un-skips a non-default data set
  in `generate load-set` and lets a third party construct a complete aggregate
  capture from the guide alone.

#### DHIS2 attribute values

- **`D2AttributeValue`** is a complex extension of `attributeId` (1..1),
  `attributeCode` (0..1, absent because DHIS2 leaves most attributes uncoded)
  and `value` (1..1, a string whatever the attribute's declared valueType),
  carrying a DHIS2 `attributeValues` entry onto every generated resource that
  can hold one.
- The attribute code is joined from a `/api/attributes` read resolved unpaged
  once per generate run, because DHIS2 pages that endpoint 50 at a time.
- The same read carries `unique`: a value of an attribute DHIS2 declares unique
  names its object rather than annotating it, so those values leave the
  extension and join the resource's `identifier` list, after the UID and code
  slices so the order stays byte-stable, under
  `{base}/attribute/{attributeUid}` - keyed on the UID because a DHIS2
  attribute code may hold spaces and a system URI may not.
- The per-attribute namespaces are declared by convention rather than as
  NamingSystems, since the foundation layer is built from `fhir.toml` alone and
  cannot know which attributes an instance has.
- **`D2TrackedEntityAttributeValue`** carries the same three sub-extensions for
  the other DHIS2 key-value family - a tracked entity attribute being a
  different object from a metadata attribute, and one extension claiming both
  would publish a definition false of half its instances. Same
  unique-becomes-an-identifier rule under
  `{base}/tracked-entity-attribute/{attributeUid}`, with the flag read off the
  `unique` property `D2TEA_CS` already publishes. This is what
  `d2w fhir serve --live` projects a person onto.

#### The capture contract

- **Five response profiles on QuestionnaireResponse**, one per form kind:
  `D2AggregateResponse`, `D2EventResponse`, `D2TrackerRegistrationResponse`,
  `D2TrackerEventResponse`, and `D2TrackedEntityResponse`. Each pins the
  extensions, `questionnaire`, `subject`, and - per kind - the mandatory
  `D2Period` or `authored` a captured response has to carry, with
  `D2FormType.valueCode` fixed to the kind's own code.
- **The aggregate profile** additionally slices `D2AttributeOptionCombo` 0..1
  and states in prose that a response answering a form which declares a
  `D2AttributeOptionCombos` vocabulary has to carry it - requiredness is a fact
  about the form, not the kind, so it cannot be a cardinality.
- **The registration profile** additionally slices `D2SubjectExists` 0..1: the
  boolean stating that the person the response is subject to is already held by
  the instance, so the response enrols them rather than creating them.
  `d2w fhir forward` imports that as a top-level `enrollments` array naming
  that tracked entity under plain `CREATE` rather than a `trackedEntities`
  wrapper whose `CREATE_AND_UPDATE` would rewrite the person's owning
  organisation unit (BUGS.md 73), carries the program's own attributes on the
  enrollment because DHIS2 answers `E1018` when they ride nothing, and refuses
  the whole response with `entity-level-answer-on-existing-subject` where it
  answers a question of the person's own record - an enrollment-only import has
  nowhere to put it, and a silently dropped answer is a captured value that
  reaches no instance.
- **Subject typing.** The aggregate and event profiles restrict
  `subject only Reference(D2Location)`. The three tracked-entity profiles
  (registration, tracker-event, and the person-only one) restrict it to
  `Reference(Patient)` plus every other resource type
  `[generate.tracked_entity_types]` names, so the published union is as tight
  as the project is.
- **The subject is a logical reference**: no `reference` element,
  `subject.identifier` 1..1 with its system fixed to
  `{base}/id/tracked-entity`, because the guide publishes no Patient instances
  and the tracked entity resolves against DHIS2.
- **Two extensions instead** on the tracker-event profile: `D2TrackerEnrollment`
  1..1 carrying the enrollment UID as a valueIdentifier under
  `{base}/id/tracker-enrollment`, and `D2OrganisationUnit` 1..1 carrying the
  capture unit as a valueReference to its published Location.
- **The tracker registration profile** keys the same way and adds the two dates
  a DHIS2 enrollment holds: `D2EnrolledAt` 1..1 and `D2IncidentAt` 0..1, the
  second only because a program states whether it collects an incident date at
  all and the registration Questionnaire publishes that statement on the
  `D2CollectsIncidentDate` extension, so both stores read one declared fact.
- **A registration response mints both identities it names**, as
  client-generated DHIS2 UIDs, since it is the document that creates them -
  which is what lets a client enrol a person and capture the enrollment's first
  stage events in one breath. The registration form ships identifier-keyed,
  deferring roadmap decision 5.2; no Patient, EpisodeOfCare, or CarePlan
  resource is published.
- **`D2CaptureServer` CapabilityStatement** declares one `create` per
  QuestionnaireResponse against all five profiles a server captures.
  `CAPTURED_FORM_KINDS` is the single tuple serve's capture index, the
  conversion gate, the `supportedProfile` declarations, `/metadata`, and the
  load set all key off, so the statement can never claim an interaction the
  facade does not perform. It also declares read and search over the
  Questionnaire, CodeSystem, ValueSet, Location, and Organization resources a
  client resolves a form from.
- **`D2GenerateOperation` OperationDefinition** stands behind `$generate`:
  `kind #operation`, `code #generate`, `resource #Questionnaire`,
  `instance = true` with `system`/`type` false, `affectsState = false` so a GET
  is legal, one optional `integer` `seed` input and a `QuestionnaireResponse`
  `return`, and a `comment` stating outright that it is not SDC's `$populate`.
  It is deliberately absent from the `kind #requirements` capture statement,
  because a server that only receives captures is still conformant.

#### The conversion contract

Published as two FHIR-native artifacts:

- **`D2DataValueSet`** - the `/api/dataValueSets` envelope as a `kind = logical`
  StructureDefinition: the three keys DHIS2 stores a data value under required,
  the attribute option combo and the completeness date optional, one repeating
  data value carrying its data element, its category option combo, and the
  string every DHIS2 value is on the wire.
- **`D2AggregateResponseToDataValueSet`** - the StructureMap from an aggregate
  QuestionnaireResponse onto it in two groups: the envelope, then a recursive
  walk of the item tree splitting `<dataElement>.<categoryOptionCombo>` out of
  each answered link id. Authored as an `Instance:` of StructureMap because
  SUSHI compiles no FHIR Mapping Language.
- **Four rules whose meaning exceeds what a transform states** carry that on
  their own `documentation`: the data set is the form's identifier rather than
  the response's, the organisation unit needs the Location registry resolved,
  the attribute option combo is a ConceptMap translation under code-mode
  naming, and the wire value is the whole serialisation table.
- **Gated in CI** by `test_fhir_conversion_contract.py`, which reads the
  SUSHI-compiled model and holds every data value set the Python forwarder
  produces against its cardinalities and types - the model judging the
  implementation, never the reverse, and never executing the map.

#### Terminology

- **Option sets** become CodeSystem/ValueSet pairs carrying both DHIS2
  identifiers and the set's DHIS2 attribute values on both halves, shipped as
  pre-built R4 JSON under `ig/input/resources/terminology/`, one
  `CodeSystem-<id>.json` and one `ValueSet-<id>.json` per set. They are
  serialised from the `dhis2w_fhir.r4` models and loaded by SUSHI as predefined
  resources into `sushi-local#LOCAL` rather than compiled from FSH, each
  carrying the FSH-style `name` a questionnaire's `Canonical(...)` binding
  fishes them by.
- **Concept codes** are made unique in DHIS2 sort order; an option with no
  unique code left to take is skipped with its own note rather than emitted
  twice.
- **One ConceptMap per set** beside the pair under
  `ig/input/resources/concept-maps/` (`D2OS_<stem>_CM`, id sharing the pair's
  identity stem, `sourceCanonical` the set's own ValueSet), whose two groups
  take every emitted concept code back to the DHIS2 option UID under
  `{base}/id/option` and to the DHIS2 option code under `{base}/id/option-code`,
  `equivalence #equal` on every row because both name the same DHIS2 option.
  Built from the same concept assignment the concepts are, so a mapping can
  only name a concept the pair carries. The code group is emitted only where an
  option has a DHIS2 code that is a valid FHIR `code`, and there is no map at
  all for a set with no concepts.
- **DHIS2 categories** become the same CodeSystem/ValueSet pair built by the
  same concept assignment: one axis of a disaggregation and its category
  options as the concepts, in the category's own `categoryOptions` order, named
  by the `CAT` token (`D2CAT_Sex_CS` / `_VS`), carrying the category's DHIS2
  attribute values on both halves. Shipped as pre-built R4 JSON under
  `ig/input/resources/categories/` - its own directory, because a JSON sync
  deletes every unproduced file in its target and two targets sharing one would
  delete each other's documents - and declared by a third `path-resource` glob
  in the scaffolded `sushi-config.yaml`.
- **One ConceptMap per category** beside the option-set maps in
  `ig/input/resources/concept-maps/` (`D2CAT_<stem>_CM`, id sharing the
  category's identity stem, the category UID under `{base}/id/category` as its
  business identifier, `sourceCanonical` the category's own ValueSet), whose
  two groups take every emitted concept code back to the DHIS2 category-option
  UID under `{base}/id/category-option` and to the DHIS2 category-option code
  under `{base}/id/category-option-code`. Both namespaces are declared as
  NamingSystems and aliased (`$DHIS2-CO`, `$DHIS2-CO-CODE`) by the `foundation`
  target.
- **The one directory two targets share** states ownership by file-name prefix
  (`sync_json_artifacts(owned_prefix=...)`), so each family sweeps only the ids
  its own naming token produces and one `path-resource` glob covers both.
- **Every identifier namespace a map targets is published as a CodeSystem too**,
  at the same URL, with `content: complete` and every identifier the guide's own
  maps name enumerated in it - `{base}/id/option` and `{base}/id/option-code`
  beside the option-set pairs, the two category-option namespaces beside the
  category pairs, the two option-combo namespaces beside the attribute-combo
  pairs. A NamingSystem states what a namespace is and lists nothing, so a
  ConceptMap row validated against one sent the IG publisher to a terminology
  server and came back UNKNOWN_CODESYSTEM: 4,779 requests on one district-scale
  guide, against 5 once the namespaces are enumerated, with the publisher's
  narrative phase down from 438 seconds to 1.5. The namespaces are read off the
  built maps rather than assumed, so a family that grows a mapping group cannot
  leave its new target system un-enumerated, and the scaffolded
  `sushi-config.yaml` declares all six under `special-url` because they sit
  outside the IG's own canonical. Each code is stated once per CodeSystem,
  whichever maps named it: two option sets legitimately share a `Preeclampsia`
  option code, and the publisher anchors a concept row by its code, so the same
  code twice is one anchor id on two rows - which its own QA pass reports as a
  duplicate anchor on the rendered page.
- **`[generate.categories]` `include_ids`** selects, where absent or empty
  meaning every category except DHIS2's built-in `default` placeholder. That
  placeholder exchanges no information, so `include_default = false` skips it
  unless the flag opts it back in or an `include_ids` entry names its UID
  outright; detection is the reserved rename-protected name matched
  case-sensitively, since `/api/categories` carries no `isDefault` flag.
  `d2w fhir validate` resolves its categories scope through the same rule.
- **There is deliberately no `category_option` naming token**, since category
  options are concepts inside their category's CodeSystem exactly as options
  are inside an option set's, and the `CO` name stays reserved for a future
  standalone artifact.

#### Questionnaires

Data sets, event programs, tracker program stages, and a tracker program's own
registration form become `Questionnaire` instances.

- **Structure.** Sections as `#group` items, data elements typed from their
  `valueType`, option-set-bound questions answered from the set's ValueSet,
  non-default category combos as per-option-combo child groups rendered
  `#gtable`.
- **The combo is resolved at one point**, `service._effective_category_combo`:
  the data set element's own `categoryCombo` where DHIS2 states one and the
  data element's where it does not - the disaggregation a data set really holds
  its cells over, and what every downstream reader of a cell follows.
- **Each cell asks the element's own question** - same item type, same
  `answerValueSet`, same `repeats`, same bounds.
- **`required = true`** comes from a data set's `compulsoryDataElementOperands`
  at the grain DHIS2 states them: an operand naming a data element alone marks
  the whole question and every disaggregated cell of it; an operand also naming
  a category option combo marks only that cell.
- **Standard `minValue` / `maxValue` extensions** on the value types that are a
  constraint (`INTEGER_POSITIVE`, `INTEGER_ZERO_OR_POSITIVE`,
  `INTEGER_NEGATIVE`, `PERCENTAGE`, `UNIT_INTERVAL`), typed `valueInteger` or
  `valueDecimal` by the item type and shared by a disaggregated element's
  children.
- **The source data set's, event program's, or program stage's own DHIS2
  attribute values** ride as `D2AttributeValue` extensions, plus data-element,
  tracked-entity-attribute, and category-option-combo support terminology.
- **Four synced directories**: `data-sets/`, `event-programs/`,
  `tracker-programs/` (nested one subdirectory per program,
  `<program stem>/<stage stem>.fsh` plus the program's own `registration.fsh`,
  with the FSH sweep walking subdirectories and pruning one it emptied), and
  `data-dictionary/` for the three shared support pairs.
- **A form that would emit one `linkId` twice** - a DHIS2 section UID reused as
  a data element UID inside one form, which R4's `que-2` forbids and which
  would leave a response naming two questions at once - is skipped whole with
  an aggregate note naming the form and the clashing id, its peers emitted as
  usual.
- **A tracker program is one Questionnaire per program stage**: the stage's
  identity stem as the id, `{prefix}PS_<stage stem>` as the name,
  `$DHIS2-PS` / `$DHIS2-PS-CODE` as its identifiers, the program's own subject
  type on `subjectType`, a title carrying both names ("Child Programme -
  Birth"), and a third `$DHIS2-PROGRAM` identifier slice holding the program
  UID.
- **Plus one registration form for the program itself**,
  `tracker-programs/<program stem>/registration.fsh`, whose questions are the
  program's `programTrackedEntityAttributes` in DHIS2 sort order - typed
  through the very same value-type table, an option-set-bound attribute
  answered from that set's published ValueSet, `mandatory` becoming
  `required = true`. Its identity is the program's own
  (`{prefix}PR_<program stem>`, `$DHIS2-PROGRAM` / `$DHIS2-PROGRAM-CODE`) plus
  a `$DHIS2-TET` slice naming the tracked entity type it enrols an entity as.
- **`Questionnaire?identifier={base}/id/program|<programUid>`** therefore
  selects a program's whole capture surface, registration and stages together,
  on any FHIR server.

#### Subject types

- **`[generate.tracked_entity_types]`** is a UID to FHIR resource type map
  (`Patient`, `Person`, `Practitioner`, `RelatedPerson`, `Group`, `Device`,
  `Location`, `Organization`, `Specimen`; anything else refuses the config)
  that lets a project publish its herds as `Group` and its water points as
  `Location`. It defaults to `Patient`, so a person-tracking project configures
  nothing and every artifact stays byte-identical.
- **The tracked entity type decides the `subjectType`** of the registration
  form and of every stage form of the program alike, and feeds the example
  responses' `subject.type`, `$generate`'s minted subject, and the capture
  server's subject-type check - read off the compiled `subjectType`, warned by
  default and refused under `--strict-codes` - from the same resolution.
- **The guide publishes the map rather than keeping it in `fhir.toml`**: a
  `D2TET_CS` / `_VS` pair over every tracked entity type the run's person-only
  forms register (concept code the DHIS2 UID, display the name the instance
  holds, `dhis2-code` where the instance states one, NAME translations as
  designations under `[generate] locales`) and a `D2TET_CM` ConceptMap beside
  it in `data-dictionary/tracked-entity-types.fsh` stating one `equal` row per
  type onto `http://hl7.org/fhir/resource-types` - every row, not only the
  exceptions, so a consumer resolves a type over `$translate` without holding
  the project's config.
- **`d2w fhir validate` names every type the table does not.** One finding per
  tracked entity type the instance holds that `[generate.tracked_entity_types]`
  never mentions, category `unmapped-tracked-entity-type`, carrying the UID, the
  name the instance holds, and the config line that would type it - a warning on
  a type this build publishes a form for, info on one outside the selection. A
  fifty-type instance gets a fifty-row checklist instead of the silence the
  `Patient` default otherwise applies in.
- **`[generate.tracked_entity_types]` stays exceptions-only and UID-keyed.** A
  run leaving two or more registered types unmapped raises a generate note
  naming each by instance name and UID, which doctor's generate phase reports
  as a warning.

#### The data dictionary

- **`D2TEA_CS` / `_VS`** is the tracked-entity-attribute support pair the
  registration form's item codes point into: `dhis2-code`, `value-type`, a
  `unique` boolean marking the attributes that are business identifiers, and
  searchability with its provenance.
- **Searchability carries its provenance**: a `searchable` roll-up true where
  any context this run publishes declares it, plus one
  `searchable-<contextUid>` boolean per context that asked the attribute -
  because DHIS2 holds the flag on the join, and two programs asking one
  attribute disagree as readily as they agree. Each per-context property is
  declared once with the context named in words, and every flag is read off the
  very `programTrackedEntityAttributes` / `trackedEntityTypeAttributes` join
  the forms already cost.
- **Every dictionary property is declared only where a concept carries it**,
  and `dhis2-code` is written only where DHIS2 states a code rather than
  repeating the UID the concept code already is.
- **`D2EntityLevel`** rides each question, read off
  `trackedEntityType[trackedEntityTypeAttributes]` on the same program fetch:
  true for an attribute the tracked entity type collects, false for one only
  the program asks. That is what makes `d2w fhir forward` write the first onto
  `trackedEntities[].attributes` and the second onto
  `enrollments[].attributes`, the two levels DHIS2 imports a registration at.
  The level rides the item rather than a `D2TEA_CS` property because it is a
  fact about the attribute and the tracked entity type together, and two
  programs on different types can disagree; a question stating no level is
  written on the tracked entity.

#### Examples

- **`Usage: #example` QuestionnaireResponses** declare themselves `InstanceOf`
  the matching response profile, so the publisher validates every example
  against the capture contract on every run, and answer those Questionnaires on
  the same link ids. One file per example under `examples/`, sized and sourced
  by `[generate.examples]` `per_target` / `source`.
- **`source = "synthetic"`** (the default) generates values locally from a
  SHA-256 seed - stable across machines and runs, every option combo filled.
- **`source = "instance"`** reads real data value sets and tracker events off
  the server: an event program by `program`, a tracker stage by `programStage`
  plus its `program`, whose `fields` also carry `enrollment` and
  `trackedEntity`. An event answering neither declares the base
  QuestionnaireResponse and is tallied in one aggregate note rather than
  dropped. Aggregate data walks back through the six newest completed periods
  of the data set's period type via the `recent_periods` inverse of the ISO
  parser, grouping data values by `(orgUnit, period, attributeOptionCombo)`.
- **Answers are typed from the DHIS2 `valueType`**, with option codes resolved
  to codings carrying the very concept code the terminology target assigned
  that option, so a coding never names a concept the CodeSystem lacks. An
  answer selecting an option that received no concept code is left unanswered
  with its own note, and so is an `ORGANISATION_UNIT` answer naming a unit
  outside the organisation-unit selection, which the IG publishes no Location
  for.
- **Numeric answers** are admitted only in the plain lexical forms an R4
  primitive can carry (`NaN`, `1e3`, `+1`, `01.5` stay strings). Temporal
  answers are cleared against the calendar, the clock, and the R4 offset range
  before they are emitted.
- **`authored` and every `DATETIME` answer** get the offset R4 requires and
  DHIS2 omits: the offset the `[generate] timezone` IANA zone stood at on that
  very timestamp, DST included, or `Z` when the project names no zone
  (BUGS.md #62).
- **A target holding no data is one aggregate note, never a failure.**

#### Organisation unit registry

- **Paired Organization/Location instances** with `Organization/<stem>` /
  `Location/<stem>` `partOf` hierarchy, losslessly embedded GeoJSON, and the
  unit's DHIS2 attribute values as `D2AttributeValue` extensions on both
  halves. On the Location the boundary extension is emitted first, the
  attribute values after it, and the `D2OrganisationUnitLevel` extension last,
  so a regenerate of an unchanged unit stays byte-identical.
- **Shipped as pre-built R4 JSON** under `ig/input/resources/registry/`, one
  `Organization-<stem>.json` and one `Location-<stem>.json` per unit,
  serialised from the `dhis2w_fhir.r4` models and loaded by SUSHI as predefined
  resources into `sushi-local#LOCAL` rather than compiled from FSH.
- **`D2Organization` / `D2Location` profiles**, the latter slicing the level
  extension `named level 1..1`, so every published Location states the
  hierarchy level it sits at instead of leaving it to be counted off `partOf`
  hops. The level CodeSystem ships beside them, as does a curated
  `registry-examples.fsh` (`D2OrganizationExample` / `D2LocationExample`,
  `Usage: #example`) drawn from the selection's own root unit so the publisher
  validates both registry profiles against real instance data - kept beside the
  profiles rather than under `examples/`, whose sync deletes every file it did
  not produce.
- **These stay FSH** under `ig/input/fsh/organization/`, along with the
  optional whole-selection CodeSystem representation
  (`[generate.organisation_units] terminology`).

#### Site pages

`d2w fhir generate pages` writes a narrative documentation layer into
`ig/input/pagecontent/`.

- **Six site pages**: Forms (a data-set catalog, an event-program catalog, and
  a "Tracker programs" section grouping each program's stages under its own
  heading), Registry, Terminology, Identifiers, Periods, and Capture.
- **The Capture page** states what a third party sends to capture data: the
  single-response-per-request rule; an aggregate, an event, and a tracker event
  response worked step by step against the selected forms with a real period
  and organisation unit; the logical Patient subject and both tracker
  extensions; where a client obtains the enrollment and tracked entity UIDs
  (`d2w data tracker enrollment list`, outside the guide's scope); the
  `<dataElementId>` / `<dataElementId>.<categoryOptionComboId>` linkId
  grammars; the required rules; the event status map; an answer-typing table
  derived from the same tables the examples answer from; the coded-answer rule;
  and the validate-before-you-send workflow.
- **`<Type>-<id>-intro.md` intros** that the IG publisher injects into the
  matching artifact pages - one per Questionnaire, and one per option set or
  organisation unit carrying a DHIS2 description.
- **Sync-managed by a markdown generated header**, so the hand-authored
  `index.md` survives every regenerate, with every metadata-derived string
  escaped for the publisher's strict HTML parse and for markdown table cells.
- **Escaping is page furniture only**: the FSH `Title:` / `Description:`
  keywords and the generated markdown, never an element of a served resource,
  whose `title`, `description`, `name`, `alias`, `display`, and `text` all
  carry the DHIS2 text byte for byte.

#### Translations

DHIS2 translations are carried through across the whole surface, filtered by
`[generate] locales`.

- **`NAME`** becomes a CodeSystem concept designation on every vocabulary
  (options, category options, organisation units, and the `D2DE_CS` /
  `D2TEA_CS` data dictionary) and an HL7 translation extension on every title
  and instance name (option-set and category CS/VS titles,
  `Questionnaire.title`, `Organization.name`, `Location.name`).
- **A `Questionnaire.item`** takes its `_text` from `FORM_NAME` where DHIS2
  gives the object a form name, and from `NAME` where it does not.
- **A program stage's composed `<program> - <stage>` title** is translated only
  in the locales translating both halves.
- **Tags are normalised to BCP-47** (`pt_BR` becomes `pt-BR`) and locale-sorted,
  so a regenerate of unchanged metadata is byte-identical.
- **`[generate] locales`** narrows which languages travel; absent means every
  language the instance holds.

#### Artifact naming

- **`[generate.naming]`** configures artifact naming, with underscore-delimited
  computational names (`D2OS_Qdm5fPK5Ra9_CS`, `D2OU_Level_VS`,
  `D2DS_BfMAe6Itzgt`, `D2PS_A03MvHHogjR`).
- **`source` picks the identity stem** every artifact of an object derives
  from: the FHIR resource id, the canonical URL, the file name, and the FSH
  name all follow one resolved segment - across option sets (the CS/VS/
  ConceptMap triple shares one stem), categories, organisation units (registry
  file names, ids, `partOf`, `managingOrganization`), questionnaires, examples,
  and pages.
- **`"id"`** (the default) is the DHIS2 id verbatim, keeping its own case:
  `d2-os-Qdm5fPK5Ra9-cs`.
- **`"code-or-id"`** is the object's code when it meets the R4 `id` bar, fits
  the surface's stem budget with no truncation ever, and is unique among the
  selected peers - else the id, with one aggregate note per surface.
- **`"code"`** is the code always: a selected object with a missing, unusable,
  or colliding code refuses the run before a file is written, with a one-liner
  naming the offenders.
- **Stems are assigned once over the whole selection and read by every target**,
  so a question's `answerValueSet` and an example's coding name the artifacts
  that run writes whichever source is set - while the DHIS2 id and code always
  remain as identifier slices.

#### Publication status

- **`[ig] status`** (`draft` / `active`, settable at scaffold time with
  `fhir init --status`) drives the `sushi-config.yaml` status plus the
  publication `status` and the `experimental` flag on every generated
  definitional resource.
- **NamingSystems take the status alone.** The Organization/Location instances
  are data: their `active` / `status` carries the unit's `closedDate`.

#### Generate notes

- **Every note a generate target raises is a `GenerateNote`** carrying its
  kind - `selection-mismatch`, `selection-closure`, `empty-selection`,
  `selection-gap`, `refused-form`, `form-structure`, `skipped-question`,
  `answer-fallback`, `instance-data-gap`, `build-cost`, `code-fallback`,
  `code-collision`, `stem-fallback` - beside its text and an `echoes_validate`
  verdict derived from it.
- **A bare run counts the three kinds that merely restate a `fhir validate`
  finding apart** from what generation itself found
  (`note: 3 note(s) across 2 target(s) (+8 validate echoes); full list in ...`),
  while the notes file still carries every one, echoes under a trailing
  per-target `Restatements of validate findings` heading. A note several
  targets share is counted and filed once, on the first target that raised
  it; `--json` keeps the full per-target lists.
- **A solo target prints all of its notes inline**, and `--json` carries the
  whole model.

#### Load sets

`d2w fhir generate load-set` writes a synthetic load set of QuestionnaireResponse
JSON under `load/` (`--per-target`, default 25; `--salt`; `--output-dir`) for
posting at a running facade.

- **Covers every form kind** and places each response at a unit its target is
  really assigned to.
- **A tracker program's corpus is internally consistent**: its registration
  responses mint the tracked entity and enrollment UIDs from the program UID
  and the ordinal - the program UID being in the seed material is what keeps
  one program's identities out of another's, an event answering the wrong
  program's enrollment being `E1079` - and its stage responses reuse those very
  pairs round-robin rather than inventing enrollments nothing creates, which a
  drain lands whole since it posts registrations before events.
- **A `unique` tracked entity attribute** is answered from the minting
  response's own tracked-entity UID in whatever spelling its value type admits
  (textual types embed it, `EMAIL` / `URL` / `PHONE_NUMBER` in their own shape,
  the integer family as a nine-digit derivation on the admitted side of zero),
  because DHIS2 refuses a second registration claiming one business identifier
  with `E1064` and takes its enrollment and every event on it down too. A value
  type with no room for distinctness (`BOOLEAN`, `LETTER`, a date, an
  option-bound attribute) keeps the ordinary draw and is named in a note rather
  than faked out of range.
- **A corpus mints the identities it names so it imports once**;
  `importStrategy=CREATE` refuses a re-import on `E1002` / `E1080` before any
  value is read, which is what `--salt` answers by moving every drawn value at
  once into a genuinely different corpus that the same salt still reproduces.
- **Deliberately not part of a full `generate` run**, because a load set is
  test data rather than IG source.
### Validate the instance

`d2w fhir validate` checks an instance's codes for FHIR-safety: an
instance-wide `/api/metadata` sweep applying both the R4 code check and the
`template-hostile-name` check to every object in every collection it returns,
graded against the emission scope the run resolves from the same selection
semantics `generate` uses.

- **Every finding carries a `scope`** of `selection` (on the configured build
  path, where severity means build impact) or `instance` (hygiene the build
  never reads, always `info`).
- **The summary** splits the totals into a `selection findings` row and a
  `code coverage` fraction counting the in-scope objects whose code can serve
  as an identity stem (`usable_code_stem`, the R4 `id` bar). The resolved
  `ValidationScope` costs five id-only reads rather than a second sweep.
- **Three deep passes** for what the sweep structurally cannot see: an
  option-set pass gated on `--code-source`; a code-stem pass previewing a
  code-sourced `[generate.naming]` source over the six naming surfaces
  (`code-stem-fallback` warnings under code-or-id semantics,
  `code-stem-refusal` errors under `source = "code"` - the same defect
  predicate generate refuses through, so a validate error equals a generate
  refusal, with collisions graded per id namespace, data sets, event programs
  and tracker stages pooling into the Questionnaire namespace exactly as
  generate resolves them); and an attribute pass naming every attribute the
  instance left uncoded, whose values therefore ride a bare UID on all five
  resource types the `D2AttributeValue` extension is contexted on, counted as
  `attribute_count` in the report beside the option-set, option, resource-type,
  and object counts.
- **`template-hostile-name`** fires in either code mode on any name holding
  `<`, `>`, or `&` - the characters the IG publisher's template injects into
  HTML unescaped. Its sibling **`template-hostile-code`** reads the code for
  the same three on the six collections whose codes become identifier values
  (`optionSets`, `categories`, `organisationUnits`, `dataSets`, `programs`,
  `programStages`).
- **Both are graded the same way**: an error for an in-scope `<`, a warning for
  an in-scope `>` / `&`, and `info` for either out of scope - because a name
  and an identifier value alike land in HTML the publisher writes unescaped and
  then strict-parses, so an aborted build is what a `<` costs on either surface
  and a malformed page is what the other two cost, and the build aborts only
  after every resource has been rendered. Both errors are also generate
  refusals, through the shared `build_aborting_code` / `build_aborting_name`
  predicates.
- **The name grade and the generate refusal hold in both directions.** Every
  name graded a `selection`-scoped `template-hostile-name` error refuses a
  `d2w fhir generate` run, and every name generate refuses is graded that error
  here. The `ValidationScope` therefore carries one surface per kind of object a
  selection can publish - option sets, options, categories, category options,
  organisation units, data sets, programs, program stages, tracked entity types,
  data elements, and tracked entity attributes - rather than only the six whose
  codes become identity stems. Codes stay asymmetric on purpose: a data element's
  code is a concept property the publisher escapes, so neither command gates it.
- **The scope and both restrictions keep the error meaning "this build will
  fail"**: a dashboard is never generated and a data element carries its code
  through an escaped surface, so neither is a finding; `<` is the only
  character seen to abort a build; and an unselected object cannot abort this
  project's build, so only errors gate exit 1.
- **Reports** are written as Markdown, CSV, and PDF (clickable contents,
  bookmarked sections, Lao-script font support) into `--output-dir`, with exit
  1 on errors and `--fail` / `--no-fail` gating the exit code.
- **The terminal is a status view**: the summary table with the selection split
  and the code-coverage fraction, a rollup row per (severity, scope, category)
  with the instance rows dimmed, every error individually because an error
  names the object that gates the build, and one closing line splitting the
  pass into selection warnings, selection infos, and instance findings before
  pointing at the report file. `--details` expands every finding.

### Serve the guide

`d2w fhir serve` is the second verb over the same project: a FastAPI facade
bound to loopback by default that loads the project once at startup.

- **The store** is the compiled `ig/fsh-generated/resources` merged with the
  predefined `ig/input/resources/{registry,terminology,categories}` tree SUSHI
  never re-emits. With `--live` it is the same read set built straight off a
  DHIS2 instance through one client opened during startup and held open for the
  life of the process: no read of the store touches DHIS2 again, but the
  connection stays because `Patient` and the enrollment listing answer from the
  instance per request.
- **Four CodeSystem/ValueSet pairs the foundation FSH declares** are included -
  form type, period type, organisation-unit levels, and the organisation-unit
  code list `[generate.organisation_units] terminology` turns on - each built
  from the very Python vocabulary its FSH template renders and gated dict-equal
  against the SUSHI-compiled pair.
- **The profile is the root `d2w -p`**, resolved before the start banner.
- **Authentication is `[serve] auth`, in four postures.** `none` - the default -
  serves every caller. `token` takes `Authorization: Bearer <token>` and compares
  it against `D2W_FHIR_SERVE_TOKENS` with `hmac.compare_digest`; the tokens come
  from the environment and never from `fhir.toml`, and rotating them is replacing
  the variable and restarting. `dhis2` takes the caller's own DHIS2 credentials -
  HTTP Basic, or a personal access token as `Authorization: ApiToken <token>` -
  and validates them with one `GET /api/me` against the same instance the live
  run reads, in a fresh request carrying the caller's header and never the
  runtime's client, cached about a minute against a hash of that header. The
  validated username becomes the request identity, and under this posture every
  register read is answered under the caller's own DHIS2 authorization. `jwt`
  takes `Authorization: Bearer <token>` from an external OpenID Connect issuer
  and verifies it locally against that issuer's JWKS; the value of
  `[serve.jwt] username_claim` becomes the request identity. `oauth2` is the name
  reserved for an authorization server this facade would run itself and is
  deliberately not accepted: DHIS2 2.43.1's authorization server 500s for any
  client its API creates (BUGS.md 96) - a deployment wanting bearer tokens today
  states `jwt` and names the issuer it already has.
- **The `jwt` posture is `[serve.jwt]`, verified locally against the issuer's
  published keys.** `issuer` names the OpenID Connect issuer identifier and is
  required for the posture; `audience` is checked only when stated;
  `username_claim` defaults to `preferred_username` and names the claim that
  identifies the caller; `forward_bearer` decides whether a register read carries
  the caller's token to DHIS2. While the server starts it reads
  `{issuer}/.well-known/openid-configuration` and the `jwks_uri` it names, and
  every request after that is checked in memory with no round trip: the signature
  against the key the token's `kid` selects, over RS256/RS384/RS512 and
  ES256/ES384/ES512 and no symmetric algorithm (a shared-secret algorithm
  verified against a public key is the algorithm-confusion attack), `iss`, `exp`
  with a minute of clock leeway and no token accepted without one, `nbf` where
  stated, `aud` where configured, and the username claim. The JWKS answer's own
  `Cache-Control: max-age` is honoured with a five-minute floor and no ceiling; a
  `kid` this process does not hold forces one refetch, so a key rotation is not
  an outage, and that refetch is itself floored at a minute so a stream of
  invented `kid`s costs the issuer one read. Revocation is the stated trade: a
  token withdrawn before it expires stays valid here until it expires.
- **Under `jwt`, the register is refused rather than read as the facade.** DHIS2
  resolves a foreign issuer's JWT only when the instance was configured to trust
  the same issuer (`oidc.jwt.token.authentication.enabled`), which this facade
  cannot read and will not guess, so `[serve.jwt] forward_bearer` states it and
  is false by default. False answers every register read 501 with an
  OperationOutcome naming both halves that would make it answerable; true
  forwards the caller's `Bearer` header over exactly the path the `dhis2` posture
  forwards `Basic` over - same opaque header, same credential-free pool. There is
  no silent fallback to the facade's own profile, which under an administrator
  profile would be DHIS2's whole ownership and access-level model skipped with no
  break-the-glass audit entry.
- **`[serve] auth_scope` says how much the posture covers.** `write` - the
  default - guards `POST /QuestionnaireResponse` and nothing else, which is the
  facade's whole state-changing surface: `$generate`, `/evaluate`, and a CDS
  Hooks call are POSTs that write nothing. `all` guards every router but
  `/metadata`, which stays open in every posture so a client can read the posture
  it has to meet; the capture UI's own files stay open too.
- **`GET /whoami` names the caller, and carries the check under every scope.**
  Mounted only where a posture is configured - under `auth = "none"` the path is
  absent and answers 404, because a server that checks nobody has nobody to name.
  It answers `{posture, username, name}`: the DHIS2 username under `dhis2`, the
  `[serve.jwt] username_claim` claim under `jwt`, and no username at all under
  `token`, which names a deployment rather than a person. Wrong credentials meet
  the same 401 and the same OperationOutcome every other refusal carries. It is
  what gives a verdict on a credential without spending one, which under the
  default `write` scope is otherwise only discoverable by making a submission.
- **The `dhis2` posture's 401 challenges with `xBasic`, not `Basic`.** A browser
  meeting `WWW-Authenticate: Basic` on a request a page made opens its own
  credential dialog and leaves the request pending, so the capture UI would hang
  on Submit instead of rendering the refusal. The scheme callers **send** is
  unchanged, and the header reads the same for every caller rather than shifting
  by `Accept` or user agent.
- **`dhis2` forwards the caller's credentials on every register read.** The
  tracked entity read, the identifier search, the register listing and its
  counts, the enrollment listing, and `/evaluate`'s registered context are sent
  to DHIS2 carrying the caller's own `Authorization` header, verbatim and
  unparsed, over a pooled connection the process holds open with no credential
  of its own - so DHIS2's five authorization gates (authority, sharing, the
  data-element bits, the three organisation-unit scopes, ownership with access
  levels) are enforced per caller by DHIS2 itself, and the facade computes no
  permission of its own. DHIS2's verdicts are answered as they stand: a tracked
  entity a caller may not see is the 404 DHIS2 gave, and a 401 or 403 is carried
  rather than turned into a 502. Nothing on the path is cached - the one cache
  is `auth`'s identity cache, keyed by a hash of the header and holding a
  username. Each forwarded read carries one header of the facade's own,
  `X-DHIS2W-Facade`, naming the software and version; never the username, which
  the caller's header already carries. A register read presenting no credential
  is a 401 in either scope, since there is nobody to answer as; one presenting
  credentials is answered in either scope, checked on the spot through the same
  cache.
- **The facade's own profile still answers the work no caller asked for.** The
  startup store build, the instance address `/uiconfig` hands the capture
  screens, and `d2w fhir forward`'s drain read and write as the facade's (or the
  forwarding) profile in every posture, because none of them acts on behalf of a
  request - so least privilege still applies to that profile, and under `none`
  and `token` it is what answers every caller.
- **`rest.security` says so under `dhis2`**: the description states that reads
  of the register are answered under the caller's own DHIS2 authorization, and
  the `write`-scope sentence names the register as needing credentials rather
  than claiming every read is open.
- **Five startup refusals, in `ServeSettings.resolve`** beside the sibling
  preflights, so `d2w fhir serve` and an embedder meet the same ones: binding an
  interface other than loopback while neither the run nor `fhir.toml` has stated
  a posture (the message names the fhir.toml line to write), the `token` posture
  with `D2W_FHIR_SERVE_TOKENS` unset, the `dhis2` posture on a compiled run,
  which has no instance to check anybody against, the `jwt` posture with no
  `[serve.jwt] issuer`, and `[serve.jwt] forward_bearer` on a compiled run, which
  has no instance to forward to. A sixth refusal is a round trip rather than a
  value, so it lands while the server starts: a `jwt` run whose issuer this
  machine cannot reach raises the same `ServeAuthConfigurationError` from
  `open_serve_runtime` before a single request is taken.
- **`/metadata` declares `rest.security` in every posture**, `none` included, so
  a client never infers an absence: the DHIS2 posture names `Basic` by its code
  in R4's `restful-security-service` value set and the personal access token as
  text, the token posture states its scheme as text, the `jwt` posture names
  `OAuth` by its code with `JWT bearer token` as text and carries the issuer in
  an extension on the element (never a key, never the audience, never the claim
  name) while its description states whether the register is forwarded or
  refused, and the `none` posture says in words that every caller is served.
- **The check is one FastAPI dependency**, mounted over the routers
  `ServeRouters.guarded` names. An embedding application reads that set and
  mounts its own dependency in its place, writing a `RequestIdentity` onto
  `request.state` if it wants captures attributed; `register_routes` takes the
  same seam as its `authentication` argument.
- **Attribution.** Under `dhis2`, the validated username lands on the receipt as
  `submitted_by`; `d2w fhir spool --details` shows it as a **Captured by** column
  when any receipt has one, and the forward report carries it through. It is
  facade-side provenance and says nothing about the identity DHIS2 stores: a
  drain posts as the forwarding profile, and `storedBy` is DHIS2's own stamp of
  that profile.
- **Configuration.** `host`, `port`, `auth`, `auth_scope`, `strict_codes`,
  `capture`, `ui`, and
  `spool_dir` fall back to the `[serve]` table of `fhir.toml`, which
  `make serve` / `make serve-live` / `make serve-ui` read too, with flags
  beating the table beating the defaults and `--strict-codes` /
  `--no-strict-codes` reaching all three levels.
  The precedence is `ServeSettings.resolve`, in `dhis2w-fhir-serve`, so an
  embedded facade asks for the posture `d2w fhir serve` has by name rather than
  reproducing it: it applies the flag-over-table precedence, resolves the DHIS2
  profile into the address the screens link out to, and refuses a project with
  nothing compiled.
- **`capture` and `spool_dir` carry no flag**, because each says what the
  server *is* rather than what one run does. `capture = false` is the viewer
  posture: it mounts a 405 that names the key in the create route's place and
  drops `create` from `/metadata`, while every read, `$generate`, and every
  receipt already spooled answers exactly as before. `spool_dir` moves the
  receipt tree - relative to the project unless absolute - through the one
  `resolve_spool_root` the forwarder reads the same key through, so the writer
  and the drainer cannot land on two directories.
- **Content negotiation.** Every FHIR route answers `application/fhir+json`; an
  `Accept` that rules JSON out is a 406 naming the one format served, while
  `/spool`, `/uiconfig`, `/evaluate`, `/terminology/*`, and `/cds-services`
  negotiate nothing. `POST /` is a 405 saying the facade runs no batch and no
  transaction.

#### Evaluating, terminology, and CDS Hooks

- **`POST /evaluate`** runs one FHIRPath expression, CQL library, or compiled
  ELM library over a resource this facade serves - one from the guide by type
  and id, one posted inline, or one tracked entity read from the DHIS2 instance
  a live run holds open. It answers typed results, one row per CQL define, and
  real diagnostics: a parse failure carries the line and column its parser
  stopped on, and a define that refuses carries its message on its own row. A
  bad expression is a 200 with the reason, never a 500. The engine reaches the
  named context and nothing else - no library path is passed and no file is
  opened.
- **`GET /terminology/validate-code`** and **`GET /terminology/lookup`** answer
  about the CodeSystems and ValueSets this project publishes: is this code in
  that set, and what is this code called. It is not a terminology server, and
  says so - a SNOMED CT or LOINC code is answered "this server publishes no
  code system under that url".
- **`GET /cds-services`** and **`POST /cds-services/{id}`** are CDS Hooks, one
  service wide: it evaluates a CQL library the caller sends, or one this guide
  publishes as a Library, over the resources the hook prefetched, and answers a
  card per define that resolves to true or to a message. `fhirServer` is read
  and never followed.
- **The Evaluate screen** in the capture UI is all of the first of those as a
  place to click: a language, a worked example already loaded, a context picker
  offering exactly what the endpoint offers, and a parse error shown against
  the line it names.
- **The source boxes are CodeMirror 6 editors**, not textareas: JSON is read by
  its own grammar with brace matching, and FHIRPath and CQL by stream
  tokenisers this project writes, so keywords, strings, comments, and date
  literals are told apart on both grounds. The colours are CSS tokens declared
  beside every other palette in `index.css`, so a theme change or a switch of
  ground repaints the editor with nothing re-created. The editor is deferred behind `React.lazy`
  into its own chunk, so a client that only fills forms in never downloads it.
  The same read-only renderer paints the JSON results, the receipt page's
  **Raw QuestionnaireResponse**, and the Server page's **Raw
  CapabilityStatement**.
- **A reference panel sits beside the editor**, on two tabs. **Examples** holds
  every runnable example on named shelves - 29 FHIRPath, 18 CQL, 8 ELM, each
  titled by what it answers rather than by the feature it uses, each loading
  into the editor on a click, and every one of them verified to run against the
  shipped context or a stored resource. The language tab states what THIS
  engine answers - the FHIRPath function and operator vocabulary, the CQL
  header, retrieves, query clauses and interval vocabulary, and the ELM library
  shape and expression nodes - drawn from the engine's own registries rather
  than from the published specifications, so nothing on it is a name the server
  would refuse. Each language's shelf of refusals is stated beside what it
  refuses: an unknown function, an unresolved value set, a library with no
  identifier.

#### Read and search

- **`GET /metadata`** answers a `kind #instance` CapabilityStatement
  instantiating the IG's own `D2CaptureServer` and narrowed to the types this
  store actually holds.
- **`GET /{type}/{id}`** answers the resource byte-faithfully as the project
  published it.
- **`GET /{type}?_id&url&identifier&_count`** answers a searchset Bundle whose
  `self` link echoes only the parameters that were applied, so
  `identifier={base}/id/program|<uid>` selects one program's stages, `_count`
  caps the entries rather than paging them and `_count=0` states the total
  alone, and an unrecognised parameter is ignored rather than refused.

#### The tracked entity register

Under `--live` only, `GET /{resourceType}?identifier=` is the output leg: one
read surface per FHIR resource the published `D2TET_CM` takes a registered
tracked entity type onto, so a project tracking people alone serves `Patient`
and one that also registers specimen batches serves `Specimen` beside it, over
exactly the types the map names. The artifact is the contract;
`[generate.tracked_entity_types]` is what produced it, and the server never
reads that table.

- **A token under `{base}/id/tracked-entity`** reads that tracked entity
  directly - a UID is not an attribute, and a value that is not UID-shaped is
  never spent on a read DHIS2 answers 400 to.
- **A token under `{base}/tracked-entity-attribute/<uid>`** filters
  `GET /api/tracker/trackedEntities?trackedEntityType=<published TET>&filter=<uid>:eq:<value>&ouMode=ACCESSIBLE`.
  `ACCESSIBLE` always, because a unique attribute gets no organisation-unit
  scope exemption on the tracker endpoint (BUGS.md 74), so a capture-unit scope
  would miss exactly the people identifier search exists to find.
- **A bare value** tries every key at once and folds the results deduplicated
  by tracked entity UID.
- **One FHIR resource type is one register serving the UNION of its tracked
  entity types.** Two DHIS2 types mapped to `Device` - a cold-chain fridge and a
  delivery vehicle - are one `GET /Device` answering about both: no collision,
  no refusal, no last-writer-wins. The read, the search, the listing, and the
  `_count=0` count are all parameterized by the list of types the resource is
  served over, `/metadata` names every type in that register's documentation,
  and each served resource still states its own type as a `meta.tag`.
- **`_tag` asks that union about one of its types.** R4's own token search over
  `meta.tag`, which is the very element the type is stated in:
  `_tag={base}/id/tracked-entity-type|<uid>`, or `_tag=<uid>` for the code
  alone. Values widen the way `identifier` values do. It narrows the listing
  walk, the identifier search, and the count alike; it rides every `next` and
  `previous` link so a walk stays inside the type it started in; under
  `[serve.search] backend = "projection"` it narrows the store's own query
  rather than thinning its pages; and a tag naming a type that resource is not
  served over is an empty searchset rather than a refusal. Declared as a
  `searchParam` on every register entry of `/metadata`.
- **Every search runs through a `NameSearchIndex`**, which answers with tracked
  entity identifiers and never with records; each match is then read back by UID
  under the credentials the request runs as, so DHIS2 authorizes every record
  this server hands out whatever found it. `[serve.search] backend` names the
  index and has two values. `"dhis2"` - the default - is the instance itself, one
  `filter=<uid>:eq:<value>` query per key, which is the search a live run has
  always run. `"projection"` is the synced copy `d2w fhir sync` fills: one
  indexed query however many keys and types are in scope, plus `_content` for a
  search across every value a person holds. `"index"` arrives with the OpenSearch
  backend and is refused until then, naming `serve.search.backend`. The seam is
  `ProjectionStore` and `NameSearchIndex`, both exported, both documented in
  [the materialized projection](../fhir/design/projection.md).
- **The identifier set** is the attributes `D2TEA_CS` publishes `unique` - not
  `searchable`, which a superuser is not held to. The tracked entity types come
  from the registration forms the store publishes, and an unmatched identifier
  or an unpublished system is an empty searchset rather than a 404. Every
  parameter the register cannot apply is refused with a 400 naming `identifier`
  as the one it answers on, rather than answered with the register dressed as a
  match set.
- **A search naming no parameter at all is the listing** rather than an empty
  search: the register paged, for a client with no identifier to type. It takes
  `_count` (clamped to `[serve.tracked_entities] page_size_limit` rather than
  refused, defaulting to `page_size`, and `_count=0` answering how large the
  register is without building a page) and `page`, an opaque token because one
  page can sit part-way through a DHIS2 cursor per tracked entity type at once,
  with `self` / `next` / `previous` links a client follows rather than
  constructs - no `previous` on the first page, no `next` on the last, so the
  end is a missing link rather than an empty page.
- **`total` is the whole searchset counted.** DHIS2 counts one tracked entity
  type at a time, so a listing over several asks each type for its count: one
  count-only request per type, spent on the first page of a walk and carried
  through the rest on the page token, and states the sum - absent only where
  the instance stated no count for one of those types, rather than guessed or
  walked.
- **The whole people surface is `[serve.tracked_entities]`' to give.**
  `enabled` false answers none of it even under `--live`; `listing` false keeps
  the identifier search and drops the browse; `page_size` / `page_size_limit`
  size a page and cap what may be asked for; `tracked_entity_types` narrows
  search and listing to named types (the laboratory instance that registers
  specimens beside patients); and `search_attributes` names the search keys in
  place of the default set, which is every attribute DHIS2 declares unique or
  searchable - uniqueness names a subject, searchability is DHIS2's own
  statement that people are looked up by it, and keying on uniqueness alone
  would refuse the clinic finding a woman by her searchable first name. Several
  matches is a normal answer the listing already renders. Each refusal names
  the setting and the line to change.
- **The projection is identity and nothing else**: `id` and an `identifier`
  under `{base}/id/tracked-entity`, one `identifier` per unique attribute value
  under `{base}/tracked-entity-attribute/<uid>`, the tracked entity type as a
  `meta.tag`, and every other attribute value - entity-level and
  enrollment-level alike, so a person found by a program attribute comes back
  holding it - on the `D2TrackedEntityAttributeValue` foundation extension.
  There is no `name`, `gender`, or `birthDate`, because DHIS2 states no mapping
  for them and a wrong one is worse than none.
- **`GET /{resourceType}/{uid}`** reads one tracked entity, which is what each
  Bundle entry's `fullUrl` points at. The projection is identity-only whatever
  the resource: the tracked entity uid, the values of the attributes DHIS2
  declares unique, the type as `meta.tag`, the rest as extensions, and nothing
  the target resource otherwise defines - a served `Specimen` states no
  `Specimen.type`, exactly as a served `Patient` states no name, gender, or
  birth date.
- **`GET /tracked-entities/{uid}/enrollments`** is the picker's feed: typed
  JSON rather than a FHIR resource, because EpisodeOfCare-versus-CarePlan is
  still an open decision. It lists enrollment uid, program uid and the name the
  guide publishes it under, status, `active`, `enrolledAt`, and the
  organisation unit uid and registry name - read entity-scoped and never by
  program (BUGS.md 72: a program the person is not enrolled in answers 404
  claiming the person does not exist), with a COMPLETED enrollment listed and
  marked rather than hidden (BUGS.md 70: DHIS2 takes events into one without a
  word).
- **A compiled run holds no client**, so both answer a `not-supported`
  OperationOutcome naming `--live`, and `/metadata` declares no register
  resource at all.

#### `$translate`

- **R4's type-level `GET /ConceptMap/$translate?system&code[&targetsystem]`**
  over the published ConceptMaps, answering a `Parameters` resource carrying
  `result` plus one `match` per mapping (`equivalence`, the target `concept` as
  a Coding, the `source` map), or `result` false with a `message`.
- **Declared in `/metadata`** on the `ConceptMap` resource entry - the entry
  whose URL answers it - and only when the store holds a ConceptMap. Served in
  `--live` mode from the same builders.
- **The maps themselves are read and searched like every other type**
  (`GET /ConceptMap`, `GET /ConceptMap/{id}`), so the mapping tables are
  browsable, not only translatable.

#### `$generate`

The custom instance-level `GET|POST /Questionnaire/{id}/$generate` answers one
served form with a profile-declared synthetic `QuestionnaireResponse` - and is
deliberately not SDC's `$populate`, which means fill-from-real-context.

- **Built from the very `CaptureIndex` the capture path validates against**:
  the same `value[x]` element, the same `minValue` / `maxValue` bounds on both
  their numeric and their `valueDate` spellings (a drawn day is clamped into
  the calendar range the form pins rather than redrawn, so a range the
  generation window does not overlap still terminates), the same `enableWhen`,
  and the same `repeats`.
- **`enableWhen` is evaluated over the whole draw to a fixed point**, so a
  generated response never answers a question its own answers closed: draw
  everything in document order keeping the seed reproducible, then drop what
  the conditions turned out to hide, and repeat until the set stops shrinking.
- **Coded answers are drawn as real concepts** of the served CodeSystem in the
  exact concept-code spelling; a question bound to terminology the project
  never published is left unanswered.
- **Every value is drawn on the axis DHIS2 grades it on** - the DHIS2 value
  type rather than the FHIR item type - so the five types R4 asks as a `string`
  and DHIS2 still parses are spelled the way it parses them (a
  `[longitude,latitude]` `COORDINATE`, an `EMAIL` address, a `PHONE_NUMBER`, a
  one-letter `LETTER`, a `USERNAME`) instead of landing on the free-text
  wording DHIS2 refuses with `E1302`. The types holding a document or a
  reference to a DHIS2 object the guide publishes nothing for
  (`FILE_RESOURCE`, `IMAGE`, `GEOJSON`, `REFERENCE`, `TRACKER_ASSOCIATE`) are
  left unanswered. Both through `seeded_format_constrained_value`, the one rule
  the guide's own example corpus draws from.
- **Wrapped in the context its form kind's response profile requires**: a
  `D2Period` and a `Location` subject for aggregate, plus one
  `D2AttributeOptionCombo` drawn out of the vocabulary the form declares where
  it declares one (which is what holds the 201 invariant for a data set on a
  non-default category combo, `--strict-codes` included); an `authored` instant
  for event; and for tracker-event an `authored` instant plus the
  tracked-entity and enrollment pair a registration receipt in this project's
  spool minted.
- **That join is made server-side** on the program the two forms share, with
  forwarded receipts preferred over received ones and the newest of either,
  rejected ones never - so a generated stage event names an enrollment DHIS2
  can resolve rather than one it refuses with `E1079` and `E1313`. It mints a
  shaped pair of its own only where the spool holds no registration of that
  program, which the contract admits either way because it checks the shape of
  those identifiers rather than their existence.
- **The invariant that generated output POSTed back to this server's own
  `/QuestionnaireResponse` answers 201** is held as a test per form kind, in
  both store modes, and under `--strict-codes`.
- **An optional `seed`** (query for GET, a `Parameters` body for POST, an R4
  `integer` so `0..2147483647`) makes a call byte-reproducible and rides back
  on `QuestionnaireResponse.identifier` under `{canonical}/id/generate-seed`,
  so a seedless call is reproducible too and a corpus can be regenerated from
  the seeds off it.
- **Two facts a compiled Questionnaire cannot carry take documented rules**:
  the data set's period type is read off a served example response answering
  the same form and falls back to `Monthly` (which is every `--live` store,
  since a live build serves no examples), and `TRUE_ONLY` is indistinguishable
  from `BOOLEAN` so both generate either value. The incident date, by contrast,
  is a published fact rather than an inferred one, so a registration always
  generates `D2EnrolledAt` and generates `D2IncidentAt` exactly where the
  form's `D2CollectsIncidentDate` says true, compiled store and `--live` store
  alike.
- **Declared in `/metadata`** on the `Questionnaire` resource entry - the entry
  whose URL answers it - naming the `D2GenerateOperation` OperationDefinition
  the project's own `foundation` target publishes.

#### Capture

The one write is `POST /QuestionnaireResponse`, validated against the served IG
in phases that stop at the first level to find an error.

- **Phase order**: body and R4 shape (400), then the `D2FormType` kind and the
  invariants that kind's profile pins, the questionnaire canonical and its
  index, the ISO period, and finally every answer against that index (422).
- **A tracker registration's envelope** is among those invariants: a subject
  and an enrollment identifier that are DHIS2-UID-shaped, since a client mints
  both and a facade holding no instance data can honestly check nothing else
  about them; an enrolment date that parses; and an incident date graded only
  on its primitive, because the compiled form publishes no
  `displayIncidentDate`. A `unique` tracked entity attribute is deliberately
  not checked for uniqueness, which is global instance state DHIS2 enforces at
  import.
- **The answer** is an OperationOutcome naming each issue by FHIRPath
  expression, or 201 with a `Location` header and an OperationOutcome carrying
  the warnings the server had to record.
- **Coded answers are lenient by default**: a code that names the right option
  in the wrong spelling resolves through the option-UID and DHIS2-code tiers
  and records a warning; a code the served terminology does not hold at all is
  warned about and stored; `--strict-codes` turns both into refusals; two
  options matching one code is an ambiguity refused under either setting.
- **The same dial grades the attribute option combo.** A form declaring
  `D2AttributeOptionCombos` whose response names no `D2AttributeOptionCombo` -
  or names a concept the served vocabulary does not hold - warns with `E8023`
  in the diagnostics and refuses under `--strict-codes`. The mirror case of a
  combo named against a form declaring none grades the same way, because it
  would be stored and silently not written. A coding from another system or
  with no code is refused under either setting.

#### Receipts and the spool

- **An accepted response is stored as a receipt**: the submission as it
  arrived, stamped with the id it is served under, written atomically to
  `.serve/responses/received/<id>.json`. So reading one back through
  `GET /QuestionnaireResponse/{id}` or `?questionnaire=` says what was
  submitted and never what DHIS2 now holds, and `ls` on that directory is the
  pending count the forwarding phase will drain.
- **The spool is a directory rather than an index**: reads re-read `received/`,
  `forwarded/`, `rejected/`, and `withdrawn/` on every request, because
  `fhir forward` renames receipts between them from another process while the
  server is up, and a receipt keeps reading back after a drain rather than
  expiring the id its sender was handed. `[serve] spool_dir` is where that
  tree lives.
- **The served lifecycle names the spool's fourth state**: a receipt
  `d2w fhir withdraw` retracted is read out of `withdrawn/`, counted by
  `GET /spool`, and carries the record of the delete on its row - the event
  UID, the instant, and what the instance keeps - which is the one sidecar
  that is not an import report. The receipt still reads back at
  `GET /QuestionnaireResponse/{id}`, because retracting data from an instance
  does not unsay the submission.
- **A correction or a withdrawal is refused at capture where the project's
  dial is off**: `status = "amended"` is read against `[forward] corrections`
  and `status = "entered-in-error"` against `[forward] withdrawals`, both off
  unless a project says otherwise, and an unreceived one is answered 422 with
  an OperationOutcome naming the key and the value that would accept it. The
  check runs before the profile invariants, so a client that sent a correction
  is told the one thing that decided the request. With a dial on the
  submission is stored like any other receipt, status preserved - what a drain
  then does with the marker is the corrections design's later slices.
- **A translator-refused receipt says so in the listing**: a committing drain
  writes `<id>.refusal.json` beside a receipt it refused and left queued - the
  drain's instant, an attempt count, and the reasons - and `/spool` rows and
  the Responses page state it, so a receipt every drain refuses reads
  differently from one no drain has touched. The move that finally drains the
  receipt deletes the marker.
- **A capture is durable before it is acknowledged**: the temporary file is
  `fsync`ed, renamed, and the directory entry `fsync`ed too, so the 201
  promises a receipt that survives power loss rather than one that reached the
  page cache.
- **A file that no longer reads as a receipt is moved to a fourth directory**,
  `malformed/`, with a `<file>.reason.json` beside it naming what stopped it,
  so one unreadable byte costs one row rather than 500-ing the whole listing -
  a directory the process cannot read at all still does. Temporary files an
  interrupted write abandoned are swept at startup under an hour's mtime guard,
  so a concurrent in-flight write is never deleted.
- **Both spool reads run off the event loop and are paged** behind the register
  listing's own idiom: `_count` for the page size (50 by default, 500 at most)
  and an opaque `page` cursor a client only ever gets from a `next` or
  `previous` link, with `total` the whole listing on every page of a walk and
  `/spool`'s per-state counts the whole spool rather than the page. So a facade
  holding ten thousand receipts answers a page of them and pays the per-row
  projection for that page alone.
- **`GET /spool` is the one endpoint that is deliberately not FHIR**: it
  answers typed JSON carrying the receipt envelopes - the instant each
  submission was accepted, its form kind, its warnings, its lifecycle state,
  and the DHIS2 import report stored beside a rejection - none of which are
  QuestionnaireResponse elements.

### Sync a copy of the register

`d2w fhir sync` fills a **materialized projection**: a durable copy of the mapped
scope of a DHIS2 instance, held as the FHIR resources this project's map
publishes, on one SQLite file under the project. `[serve.search] backend =
"projection"` is what searches it. Both are opt-in, and a facade that configures
neither behaves exactly as it always has - reading the instance per request needs
no operator, no second command, and no schedule, and that stays the product.

- **The first run reads the whole mapped scope**, bulk-paged, projecting each page
  through the same `registered_entity_for` a live register read answers with -
  so a synced answer and a live one are the same bytes from the same code, and
  the only difference between them is the instant they are true as of. Measured
  on the seeded 2.43.1 stack: 502 people in about five seconds over ten pages.
- **Every run after it reads what moved**, on a `lastUpdated` cursor, and applies
  creates, updates, and tombstones. `--rebuild` drops the copy and fills it from
  zero, which is routine rather than a recovery step: it is how a change to
  `[serve.tracked_entities]` or to the published map reaches what is already
  stored. `--dry-run` reads the instance exactly as a committing run does, counts
  what would change, and writes neither a row nor a cursor.
- **`includeDeleted=true` rides every poll and is not a flag**, because its
  absence is silent - a sync without it never learns that anybody left and does
  not error. A tombstone removes the row rather than archiving a last state,
  because DHIS2 answers 404 to a read of a deleted entity, so there is no final
  state to archive.
- **The watermark is the instance's own clock and is per collection.** Tracked
  entities and enrollments carry one each - a person's `lastUpdated` does not move
  when one of their enrollments does, and an enrollment carries programme-level
  attribute values the projected resource does carry, so the enrollment poll says
  whose copy went stale and each one is re-read through the single tracked entity
  path. Events are not polled: the projected resource carries no data value, so an
  event that moved is not a change to anything held. The enrollment poll is scoped
  by programme because `/api/tracker/enrollments` accepts no other scope
  (BUGS.md 102).
- **A watermark never runs ahead of its rows.** The store writes a batch and its
  cursor in one transaction, and a walk advances its watermark only once every row
  it read is durable - so a walk that failed halfway advances nothing and the next
  run re-reads it, which the idempotent write makes free. An incremental run polls
  from the watermark less `[serve.projection] overlap_seconds`, because a poll from
  exactly the watermark drops the rows written in the instant it was reading.
- **`SyncReport` is typed and `--json` prints it whole**: the mode, created /
  updated / removed per FHIR resource type, the pages read, where each collection's
  cursor stood before and after, and the instant every answer served from the
  projection now states. The counts are read out of the projection rather than
  assumed, so a row the overlap window re-read is honestly an update.
- **DHIS2 stays the record.** No route writes the projection, no operator writes
  it, and a row that disagrees with the instance is a defect of this command whose
  fix is `--rebuild` rather than an edit. Deleting the file is supported. A capture
  still travels spool, `d2w fhir forward`, DHIS2, then the next sync, so a captured
  value appears in a synced server one sync interval after DHIS2 accepted it -
  stated rather than hidden behind a write-through.

### Serve from the synced copy

`[serve.search] backend = "projection"` moves the *finding* half of a register
search into the copy and leaves the *disclosing* half exactly where it is.

- **`_content` is the search that arrives with it** - R4's own parameter for a
  text search over a resource's whole content, matching a case-insensitive
  substring of any value a person holds. It is spelled `_content` and not `name`
  or `family` because this server does not know which of somebody's DHIS2
  attribute values is their name and will not guess; `"dhis2"` refuses the
  parameter, because an exact-match filter cannot answer it. `/metadata` declares
  it only where it is answered.
- **One indexed query replaces one tracker query per key per tracked entity
  type.** The identifier search matches exactly over the token index; the listing
  pages the copy with the same `_count` and opaque `page` pair the live listing
  uses, so a client cannot tell the backends apart by the shape of a link.
- **Every projection-served answer states the instant it is as of** - an
  `outcome` entry in the searchset, which is R4's own way for a server to say
  something about a search inside the search's answer, plus an
  `X-DHIS2W-Projection-As-Of` header beside it. A live answer states neither,
  because it is as of the moment the instance answered.
- **Who may see whom does not change.** The copy says who is on the page; each
  record is read from the instance under the credentials of whoever asked, so
  DHIS2 applies its sharing, organisation-unit scopes, and ownership rules per
  person per request. A person the copy holds and the instance will not disclose
  to this caller is on nobody's page, and `GET /{resourceType}/{id}` is a
  person-level read answered from the instance whatever the backend says.
- **A projection-served searchset states no `total`.** The copy counted its rows
  under the identity the sync ran as, and how many of them a given caller may see
  is the instance's to say one read at a time - so a count taken for somebody else
  is not offered. The Bundle keeps the same silence it already keeps when the
  instance states no count, and `_count=0` - which asks for that number alone -
  comes back with the cursor and no walk to follow.
- **What it still cannot do is cross scripts.** Finding `ສົມສັກ` from `Somsack`
  needs transliteration applied when the index is built, which arrives with a
  search-engine backend; a one-character typo finds nothing here either. The
  measurement and what closes each gap are in
  [the materialized projection](../fhir/design/projection.md).

### Embed the facade

`dhis2w-fhir-serve` publishes what `d2w fhir serve` assembles, so an application
that already runs FastAPI serves the real FHIR surface rather than a second
implementation of it.

- **The settings.** `ServeSettings.resolve(project, ...)` returns a
  `ServeInvocation`: the frozen settings, the address the process binds, and the
  profile it resolved - the credentials stay on the invocation and never reach
  the settings the app is handed.
- **The runtime.** `open_serve_runtime(settings)` is an async context manager
  over everything one facade holds - project, store, spool, register surface,
  and the CapabilityStatement `/metadata` answers with - as a `ServeRuntime`,
  with the DHIS2 client a live run reads through open for as long as it is
  entered and closed when it is left. A caller already holding an authenticated
  `Dhis2Client` hands it in and keeps owning it. `attach_serve_runtime(app,
  runtime)` writes the two names every handler reads.
- **The routers.** `serve_routers(capture=..., serve_ui=...)` answers a
  `ServeRouters` with the mount requirements as data: the FHIR routers that must
  carry `require_json_is_acceptable`, the three that answer plain JSON about the
  facade and must not, and the read catch-alls that mount after every fixed path.
  `accept_head_wherever_get_is_served` is the HEAD parity a liveness probe needs.
  `d2w fhir serve` is the first caller of all of it.
- **The UI is not on this surface.** The capture bundle and `/uiconfig` exist so
  the browser can work and are reached by running the server with `[serve] ui`;
  `create_app` is the only thing that mounts them, and `UiBundleMissingError` is
  the one name of theirs the package publishes, because `create_app` raises it.

### Capture in the browser

`d2w fhir serve --ui` (or `[serve] ui`, or `make serve-ui`) adds a browser
capture UI at `/`, same-origin with the FHIR routes so it reads the very
endpoint it is served from with no URL to configure. It is a React 19 +
TypeScript + Tailwind v4 + shadcn/ui app under
`packages/dhis2w-fhir-serve/frontend/`, built into the Python package and
shipped inside the wheel.

#### Signing in

- **The shell reads the posture off `/metadata` before it draws a page**, because
  that is the one document open under every posture. A `none` posture renders
  nothing new; a `token` posture asks for one field and a `dhis2` posture for a
  DHIS2 username and password, in place of the page rather than over it - so the
  app never sends a request this server would answer 401 to, and a browser never
  gets the chance to open a credential dialog of its own over ours.
- **Submitting the panel asks `GET /whoami` with what was typed, and stores
  nothing until the server names the caller.** A wrong password is refused at the
  prompt - "DHIS2 did not accept this username and password." under the DHIS2
  posture, "This server did not accept this token." under the other two - with
  the fields still there to try again with. A server that could not be reached
  says so in its own sentence, because credentials that were never checked are
  not credentials that were rejected. Without the check the default `write` scope
  leaves every read open, so the first thing that would refuse a wrong password
  is a submission somebody spent minutes filling in.
- **The name that is kept is the server's, never what was typed.** `/whoami`
  answers the DHIS2 instance's own spelling of the username under `dhis2` and the
  claim the server read out of the token under `jwt`; the token posture names
  nobody, and the header names nobody for it.
- **The credential is the whole `Authorization` value, in `sessionStorage`**, per
  tab: closing the tab ends the session and a second tab signs in on its own. The
  one function in the app that reaches the network attaches it and records any
  401 that comes back, so a credential that goes stale after signing in - a
  password changed, an account disabled - is refused at the next read, listing, or
  submission, dropped rather than signed with again, and the prompt returns with
  the same sentence. The header names whoever is signed in and offers **Sign
  out**, which forgets the credential and the name and asks again.
- **The Server page states the posture and its scope**, off `/uiconfig`'s `auth`,
  beside the `rest.security` description the conformance document carries.

#### Overview

- **Four spool counts as stat tiles**, with `Received` (the queue
  `fhir forward` drains) set at hero size and every tile linking into the
  Responses table with that lifecycle already selected via
  `#/responses?lifecycle=`.
- **A withdrawn receipt states what the instance keeps**, in the withdrawal
  record's own words - "This DHIS2 instance keeps a hidden copy of the event;
  it no longer appears in reports" - beside the instant and the event UID, and
  never the bare word "deleted". The answers stay on the page.
- **The rejected tile names the DHIS2 error code most of its receipts share**,
  counted per receipt rather than per issue, because DHIS2 states a rule once
  and then names every object that broke it.
- **The served forms beneath as quick-entry cards**, and a server-identity
  strip carrying the guide, its version, the store mode, the resource-type
  count and the declared operations.
- **Each of the three sections reads its own endpoint behind its own
  loading/error state**, so one dead read cannot blank the others.

#### Forms

- **`/forms` shelves every served Questionnaire by the DHIS2 capture model its
  `D2FormType` states**: **Data sets** (periodic reports for an organisation
  unit), **Event programs** (single events, no person registered), **Tracker
  programs** as one group per program with the registration form leading its
  stages and the enrols-a-person / records-a-visit dependency stated per group,
  and **People** - the `tracked-entity` kind, registering a person in the
  instance without enrolling them in a program.
- **People is a shelf of its own** because it is generated from a tracked
  entity type, names no program to group under and no period to report for, and
  is reportable at every published organisation unit since DHIS2 hangs no
  assignment on a type.
- **A form declaring no kind gets its own stated section**, since the facade
  refuses to capture against it. The same `catalogueForms` fold in
  `lib/catalogue.ts` shelves the organisation-units rail.
- **Every row keeps its title, question count, and id.**

#### The form view

`/forms/{id}` renders any served Questionnaire as fillable controls: the item
tree flattened into an ordered spec, one reducer over every answer, and a
control per R4 item type.

- **A three-state Switch for `boolean`** - Yes, No, or not answered - which
  becomes a two-state tick for a question the served dictionary types
  `TRUE_ONLY`, since DHIS2 stores `"true"` or nothing for one and an offered No
  would be discarded at import.
- **Numeric inputs bounded** by the `minValue` / `maxValue` extensions; native
  `date` / `dateTime` / `time` inputs whose values are completed into R4
  primitives on submit; Textarea for `text`; a Select for `choice` whose
  options are expanded by reading the bound ValueSet and the CodeSystem it
  composes; and a cmdk-backed searchable combobox for a `reference` question -
  the item type the emitter writes for a DHIS2 `ORGANISATION_UNIT` data element
  - writing `valueReference` through an answer slot of its own rather than
  through the text a keyboard writes.
- **Repeating questions** with add and remove rows.
- **`enableWhen` evaluated with full R4 semantics**: the six comparison
  operators plus `exists`, `any` / `all` behaviour, a group's conditions
  cascading to everything beneath it, and a condition on an unanswered question
  holding only for `exists=false`. A disabled item is hidden, uncounted in the
  required sweep, and has its answer cleared rather than held out of sight - a
  stale answer under a question the form stopped asking is the value DHIS2's
  own program rules exist to prevent, and forwarded it becomes a real data
  value.
- **Bounds are honoured client-side** on both the numeric and the `valueDate`
  spellings of `minValue` / `maxValue`: the control wears the range, the hint
  states it, and Submit refuses an answer outside it with the fact and nothing
  else (*137 is above the highest value this form accepts, 100*).
- **A repeating `D2ProgramRule` declaration** is read off the form and stated
  where the form describes itself - *This DHIS2 instance enforces N more rules
  when the submission is imported* - each rule's name and DHIS2 description
  listed behind a `details` fold with its uid and machine condition kept mono
  inside it, since a program rule is an instance-side expression this server
  can name but never evaluate.
- **Every question is labelled with the DHIS2 uid it is known by**, and a
  **Fill with test data** button reads `$generate` and pours its answers into
  the form to be edited rather than posting them blind; the drawn seed is
  shown, so the same answers can be asked for again.
- **A submission keeps the `$generate` skeleton's envelope** - the `D2Period`,
  the tracked entity and enrollment - rather than deriving DHIS2 period
  arithmetic client-side, so what the page posts carries capture-valid context
  by construction. The facts written over that envelope are the person's rather
  than the server's:
- **A Reporting from organisation-unit picker** beside the combo, whose choice
  is kept for the browser tab (session-scoped, so a fresh tab starts fresh) and
  adopted by the next form that admits it, with the mismatch stated when the
  next form does not. It offers the published registry intersected with the
  form's own `D2OrganisationUnitAssignment` List, so the control cannot produce
  the capture DHIS2 refuses with `E1029`; an empty intersection says so instead
  of offering the registry. Searchable by name, uid, or DHIS2 code through the
  same rule the Organisation units tree filters by, and browsable as the
  hierarchy itself through a **Browse** mode beside the search box (units the
  assignment does not name kept as disabled context, branches it admits nothing
  in pruned away, opened on the held unit's ancestors, walked with the arrow
  keys). Pre-selected from whatever unit `$generate` drew, and rewriting
  `subject` for an aggregate or event form and the `D2OrganisationUnit`
  extension for a tracker one. The same one read of `GET /Location` feeds every
  `ORGANISATION_UNIT` question in the form below it.
- **An attribute option combo control** for a data set on a non-default
  category combo: the combo the whole submission is filed under, expanded from
  the `D2AttributeOptionCombos` ValueSet the form declares and rendered
  UNANSWERED however the draft was drawn. `$generate` files its skeleton under
  a combo so the skeleton is postable, and adopting that pick would make every
  unread submission claim a project a random draw chose - so the page disables
  Submit with a stated reason until somebody picks one, mirroring DHIS2's own
  refusal to render a form until the combo is chosen. **Fill with test data**
  still adopts the fresh draw, because that is the server proposing a whole
  submission.
- **A Person control on both registration kinds**, naming who the submission is
  about. **New person** by default - the minted identity, and the only option a
  compiled run offers, which says so rather than offering a search it cannot
  answer. **Find in this DHIS2 instance** is offered exactly when `/metadata`
  declares the form's own register - its `subjectType`, `Patient` only by
  default - with a `search-type` interaction on `identifier`, searching
  `GET /{RegisterType}?identifier=` in its bare-value form once the typing
  stops and listing each match as what the projection carries: the value of a
  unique attribute leading, the other attribute values beside it, the tracked
  entity uid last, and never an invented name, since DHIS2 states no attribute
  that means one.
- **Choosing a person** rewrites the subject to their real tracked-entity uid,
  names that person through the served `D2TEA_CS` displays on the picker cards
  rather than repeating their uid twice, writes the `D2SubjectExists` marker
  (pinned as one exported constant in `lib/patients.ts` and derived off the
  form's own canonical like every other extension url this UI writes), and
  makes every `D2EntityLevel` question read-only and cleared with the reason
  stated. That is load-bearing rather than tidy, because `fhir forward` refuses
  a submission that states its subject exists and carries an optional
  entity-level answer anyway, while a program-mandatory one rides the
  enrollment instead - DHIS2 answers `E1018` to a mandatory program attribute
  arriving on nothing, and an enrollment attribute writes the same store the
  person already carries the value in.
- **The person's existing enrollments** are listed beneath from
  `GET /tracked-entities/{uid}/enrollments`: program name where the guide
  publishes one, the status in one human spelling with `active` stated in words
  beside it, the enrolment date, the organisation unit - and a completed one
  carrying the warning that DHIS2 takes new events into it without complaint.
- **The stage form's Answering for picker** gains the same instance source
  beside its spool receipts, offering the found person's enrollments in that
  stage's own program alone, since DHIS2 refuses an event filed against another
  program's.
- **A tracker registration form gains an Enrollment block** stating what the
  submission will file: the enrollment date, the incident date where the
  program declares `D2CollectsIncidentDate`, and the client-minted enrollment
  UID.
- **The dates are drafted by the server and editable**, because a visit typed
  up on Thursday is not a visit that happened on Thursday, and an edit rides
  the envelope in the exact slot `$generate` put it. An event or stage form
  dates itself the same way through a **Visit date** control over `authored`,
  and an aggregate form through a **Reporting period** control over the
  `D2Period` `iso` sub-extension - required and period-type-aware off the
  form's own `D2PeriodType`, so it opens with the shape of its data set's
  period as the placeholder and the worked example beneath, and refuses an
  empty box and an identifier of the wrong shape before the round trip
  (`Daily`, `Weekly`, `BiWeekly`, `Monthly`, `BiMonthly`, `Quarterly`,
  `SixMonthly` and `Yearly` are checked; the offset weeks and the financial
  years spell their offset into the identifier and are accepted as typed rather
  than half-checked, with the server naming both types in its refusal). It
  keeps the drafted `type` and drops the optional range sub-extension rather
  than claim a range no client-side period arithmetic resolved.
- **The form is the authority on what it asks, and this UI states what it
  states.** The enrollment, incident and visit date controls take their labels
  from the form's own `D2DateLabels` where the instance renamed them - the
  receipt page labels the same facts from the same function, so one programme's
  "Date first seen" reads that way on both surfaces. A stage form declaring
  `D2Repeatable` says so where the form describes itself and on its row in the
  forms listing. An item's `D2Description` renders as the question's help text
  under its label and as a section's under its heading. A group of
  disaggregated cells names the DHIS2 categories it is cut by, joined from the
  served combo vocabulary's own property declarations in DHIS2's declared
  order - nothing in this UI sorts a decomposition or a combo expansion.
- **A question the form marks `readOnly`** over an attribute the dictionary
  declares `generated` renders disabled with what will arrive stated ("DHIS2
  fills this in when the submission is imported, shaped `ANC-#######`"), is
  never counted among the required questions the form is waiting on, and is
  left unanswered by `$generate`. One rule held on both sides of the wire: the
  capture index carries `readOnly`, the synthesizer declines to draw for it,
  and the validator admits its absence even where the form marks it required.
- **The form screens gate their Submit on the `capture` flag `/uiconfig`
  carries.** False, and a form still opens, fills, and reads, with *This server
  does not accept submissions* where the button was. Silence is read as
  receiving, so an unanswered settings read never withholds the one control the
  screens exist for.
- **A refusal is rendered issue by issue** with the severity, code, and
  FHIRPath expression the capture validator names the offending question with.

#### Responses and receipts

- **`/responses`** lists every stored receipt with the lifecycle state its file
  is in (received, forwarded, rejected), tinted by shared theme tokens,
  filterable by state or form, the state chips carrying the counts so the queue
  depth is on screen.
- **`/responses/{id}`** is a deep-linkable receipt page opened by clicking a
  row: the answers joined to the questions the served Questionnaire asks, in
  that form's order, each with its enclosing groups (what turns a disaggregated
  cell from `Fixed, <1y` into `Immunization / BCG doses given - Fixed, <1y`),
  its link id, and its value rendered as what it is - a coding keeping both
  display and the code DHIS2 stores, a boolean as Yes or No, a repeating
  question showing every answer, an organisation-unit answer named off the
  served `Location` when the stored reference carries no display, which is what
  turns a bare `Location/<uid>` into the place it names. The receipt's own
  capture-context organisation unit is resolved the same way.
- **A capture-context grid** merges what the spool derived with what the stored
  resource carries, so a fact reaching it from both sources is stated once -
  which is how a registration receipt states its enrolled-at and incident
  dates, the two the spool has no column for, beside the tracked entity and
  enrollment it minted. It degrades to link ids and values with a stated reason
  when the form has been recompiled away.
- **Beside it**: the DHIS2 context the receipt carries, the `$generate` seed it
  was drawn from, the capture warnings, and the import report's rollup of what
  DHIS2 said about a rejection - with an `E1300` row's program rule read back
  as the rule's own name, joined client-side from the `D2ProgramRule` list on
  the served form (the uid taken off DHIS2's own *Generated by ProgramRule
  (`uid`)* sentence, never off the row's `subject`, which on an `E1300` is the
  data element the rule read; a rule the served form does not list stays
  unnamed rather than guessed at).
- **A collapsible raw view** of the stored QuestionnaireResponse, reloaded on
  demand, on window focus, and on every in-app arrival at the listing, because
  the forwarder moves files under an open page. Nothing polls, so a window left
  open and unfocused shows what it last read until it regains focus.

#### Terminology browser

- **A listing per type** over all three terminology types, carrying each
  artifact's id, the DHIS2 identifiers it was generated from, and its concept
  or mapping count, with one filter narrowing all three at once.
- **`/terminology/{resourceType}/{id}`** shows, for a CodeSystem, every concept
  with one column per declared property, headed by the property code as words
  with the declared description as the header's tooltip - the DHIS2 option code
  beside the concept code standing for it, the category a combo splits over
  beside the combo itself.
- **Any property valued as a `Coding` into a published CodeSystem** renders as
  a link to that CodeSystem's own page with the concept filter preset to the
  coded concept. Generic to every coding-valued property, which is how a
  category option combo digs down into the category options it was met from.
- **The concept filter lives in the address bar** so the one row is
  deep-linkable, filtered client-side and paged at 200 rows for the systems
  that run to thousands.
- **A ValueSet expands through the CodeSystems it composes**, because the
  facade publishes no `$expand`; a ConceptMap shows every mapping one table per
  group with its target code and equivalence.
- **Both detail pages carry a `$translate` tester** that asks the running
  server about a typed or clicked concept code, optionally against one target
  system, and renders the `Parameters` as match rows or the not-found message.

#### Organisation units

`/organisation-units` folds `GET /Location` into the reporting hierarchy.

- **A lazily expanded tree over `partOf`**: children rendered only when a node
  is open, a filter that keeps the ancestors of every match so a matched
  facility is never shown detached, and a unit whose parent the project never
  published shown as a flagged root rather than dropped.
- **Three resizable panes on wide viewports**, in a GIS tool's shape: the tree,
  the map as the always-visible centre canvas, and a collapsible inspector rail
  that opens on selection. Narrower viewports fall back to two columns with the
  selection's sections behind tabs, Map the default.
- **The rail opens with the selected unit's own identity**: its level off the
  `D2OrganisationUnitLevel` coding rather than a count of `partOf` hops, its
  DHIS2 uid and organisation-unit-code identifiers, and its parent chain as
  clickable breadcrumbs.
- **Which forms may be captured there**, shelved by DHIS2 kind as **Data sets**
  and **Programs** (a tracker program's registration and stages grouped under
  the program), with the assignment join in DHIS2's own vocabulary: the forms
  assigned to this organisation unit badged and the ones assigned everywhere
  listed plainly, because a form carrying no `D2OrganisationUnitAssignment` is
  assigned everywhere and badging all of them at every unit would bury the one
  that is not.
- **Captured here**: the spool receipts naming the unit - lifecycle counts, the
  five most recent linked to their pages, a descendant rollup, and the stated
  scope, captures this server received rather than what DHIS2 holds.
- **Children**: the subtree as a mini tree that re-roots on selection.
- **A MapLibre GL JS map** renders every decoded boundary and point over raster
  basemap tiles.
- **`[serve.basemaps]`** is an ordered list of named `{z}/{x}/{y}` layers,
  defaulting to one OpenStreetMap entry, with `basemaps = []` for the
  self-contained boundary-only canvas and repeatable `--basemap Name=url` /
  `--basemap none` overriding per run. The UI reads it from a typed
  `GET /uiconfig` endpoint carrying only what the browser may know.
- **A layers control** in the corner stack lists each configured layer plus
  **None** and swaps the raster source in place on a choice, so the camera, the
  selection, and the popup survive a switch and the boundaries restyle for the
  ground they land on. Tiles are muted per ground through `raster-brightness-max`
  / `-contrast` / `-saturation` / `-opacity` so they read as ground rather than
  glare, with MapLibre's own attribution control fed the OpenStreetMap credit
  the tile policy requires - and no credit invented for a source the server
  cannot know the terms of.
- **The GeoJSON is decoded out of the base64 `location-boundary-geojson`
  attachments**, which are DHIS2's own `geometry` field and therefore hold a
  Polygon for a district and a Point for a facility. Both are drawn, with
  `Location.position` winning the dedupe when a unit states its coordinates
  twice, leaving the unreadable count for payloads that are genuinely neither.
- **The selection is lit in amber**: a two-hue encoding, the `--map-selection`
  pair against the identity-coloured subtree wash over a neutral context tier,
  with the colours read from the live CSS custom properties so the map is the
  same product in every theme and on both grounds, and a surface-coloured
  casing under each stroke so
  the ramp keeps its validated contrast over a busy basemap.
- **A zoom-aware click model**: a left-click on a shape opens a popup naming
  the unit, its level, its parent, and what sits below, with an Open action
  selecting it - or eases a step in toward the pointer while the map is still
  too far out for the click to have meant one shape. A right-click drills
  straight to the selection whatever the zoom, the point outranking the
  boundaries under it where shapes stack.
- **Corner controls** for fullscreen, a globe projection toggle that hangs the
  sphere in a deterministic starfield, and a recenter button back to the
  selection's extent or the whole registry's. The map grows into whatever
  height the page has left with a floor rather than sitting in a fixed box, and
  the whole route is lazy-loaded so the ~930 kB renderer is fetched only when
  the browser is opened.
- **The selected unit rides the query string**
  (`#/organisation-units?unit=<uid>`) so a unit is a link that can be sent. A
  unit with no geometry of its own is framed by a stated priority - the union
  of its subtree's shapes, else the nearest located ancestor, else the whole
  registry - with a caption naming which. A registry with no coordinates at all
  hides the map panel behind one sentence, and tiles that fail to load leave
  the painted ground behind them.
- **One organisation unit published as two Locations** - the registry instance
  and the curated profile exemplar a generated IG ships beside it, both
  claiming the same uid - is deduplicated by that identifier in favour of the
  instance the hierarchy hangs off, so a root is never listed twice.

#### Tracked entities

On a live run that serves them, `/tracked-entities` is a page over the register
the instance holds, headed by the register's own name where one type is served:
an identifier search and a paged listing on one page, with a detail route at
`/tracked-entities/{resourceType}/{uid}`.

- **What is being searched for rides the query string** (`?q=<value>`), the way
  the selected organisation unit does - so a search is a link that can be sent,
  reloaded, and arrived at from elsewhere. The command palette is the first
  thing to arrive from elsewhere: it hands the value over rather than running a
  search of its own. Typing into the box replaces the entry rather than pushing
  one, so Back leaves the page instead of unwinding the keystrokes.

- **Gated into the navigation** by the `tracked_entities` block `GET /uiconfig`
  carries beside the `capture` flag - `enabled`, `listing`, and `registers` -
  all three effective rather than as written, so a compiled run reports false
  and no page is drawn.
- **`registers`** is the published `D2TET_CM` read for a screen: one entry per
  served FHIR resource with the tracked entity types riding it under the
  instance's own names, so the navigation entry and the page heading alike read
  the instance's own name for the one type a run serves - *Person*,
  *Fridge*, *Specimen batch*, singular and unpluralised because the
  string is DHIS2's - and **Tracked entities** once more than one type rides,
  never the FHIR resource this project projects a person onto. A section is
  titled *Specimen batch* rather than `Specimen` on the same rule.
- **Each row carries what the projection states and no name column**, since
  DHIS2 states no attribute that means one. The attribute-values column prefers
  the attributes the published `D2TEA_CS` marks `display-in-list` - DHIS2's own
  answer to which values let a clerk recognise somebody - and falls back to the
  first few when an instance marks none.
- **The detail keeps showing everything**, heads itself with the tracked entity
  uid only once, and drops the badge beneath when no unique value names the
  record. A total is shown only where DHIS2 stated one. The detail view carries
  the person's identifiers, attribute values, and enrollments, with a completed
  one warned (BUGS.md 70).
- **Only the matched entries of a searchset become rows.** R4 lets a server
  append entries beside its results, and the projection backend appends an
  `outcome` one; an entry stating `search.mode` of anything but `match` is
  never a row and never counted, while an entry stating no mode at all is a
  match by omission, which is what R4 says it is.
- **The searchset's own outcome becomes the page's as-of line.** A projection-
  served answer carries `X-DHIS2W-Projection-As-Of` beside an OperationOutcome
  saying the same thing in prose, so the instant is taken from the header and
  said once, in the wall clock every other instant on every other page is read
  in - *Answered from the synced copy of this DHIS2 instance, as of ...* The
  outcome's own sentence is what answers for a copy nothing has filled yet, and
  a facade that asks DHIS2 itself states no line at all, because there is
  nothing to say about an answer read a moment ago.
- **The search box sends the parameter `/metadata` declared for that register.**
  `identifier` is what every live facade publishes and what the box has always
  sent. A run keeping a synced copy of the instance declares `_content` beside
  it, and the box then searches that instead - any part of any value a record
  holds, upper and lower case alike - with its own label and its own sentence
  about what it searches, so a blank result never means something the copy on
  screen did not describe. Neither wording calls anything a name: DHIS2 states
  no attribute that means one, which is why the server spells the parameter
  `_content` rather than `name`.

#### Server page and links out

- **`/server`** renders `/metadata` in full: declared operations including
  `$translate` and `$generate`, per-type interactions and search parameters,
  and the store mode - with the conformance document itself behind a **Raw
  CapabilityStatement** toggle, since this document is the facade's whole
  contract and the tables above it show the parts a browser needed.
- **Links out to the DHIS2 instance the guide was generated from**: a new-tab
  external-link mark beside the selected organisation unit's name, on every
  data set / program / program-stage row of the rail's form shelves, and on
  every concept row of the data-element dictionary. Each opens that object's
  own page in the instance's Maintenance app
  (`{base}/dhis-web-maintenance/index.html#/edit/{section}/{type}/{uid}`,
  verified against a running 2.43.1), with `rel="noreferrer noopener"` and an
  accessible name stating which object and where it goes.
- **The address is the base url of the profile the serve run resolved**, served
  on `/uiconfig` with any userinfo stripped - so a run that resolved no profile
  carries no links at all, rather than a link that goes nowhere.

#### Command palette

- **Cmd+K on macOS, Ctrl+K everywhere else**, plus a magnifying-glass button in
  the header for anyone who was never told about the chord. Every chord this app
  binds sits on a letter, because one over the bracket, brace, pipe or backslash
  keys is one a Nordic keyboard cannot press without Alt - and no row in the
  palette carries a chord of its own.
- **Pages, forms, receipts, the register, appearance, the view, help, and the
  session**, on shelves in that order. The pages are the shell's own navigation table mapped
  onto the palette, so what the rail offers and what the palette reaches cannot
  drift; the forms are every published Questionnaire by title with its served id
  beneath; the receipts are the newest few at rest and the ones a typed id
  **prefix** names, capped, because an id is what a forward run prints and what
  somebody has in hand.
- **A register lookup hands its value to the register page in the URL**
  (`#/tracked-entities?q=...`) rather than running a search of its own, under
  the register's own threshold - so which parameter this server answers and how
  long to wait for the typing to stop stay decided in one place, and the result
  is a link that can be sent. The register page reads the value out of the query
  string, and writes what is typed into it back with `replace`.
- **Each row is one line**: a leading icon by kind, the name, the line about it
  beside rather than beneath, and the kind itself - *Page*, *Form*, *Receipt*,
  *Theme* - at the far edge. A footer bar states what the key under the reader's
  finger would do to the highlighted row (*Open*, *Switch*, *Run*) and spells the
  chord, which is where somebody who opened it by button first learns there is
  one.
- **Nothing in it changes what the server holds.** Every action navigates,
  repaints, lays the screen out, or ends the session; submitting, forwarding, and
  withdrawing all stay on their own screens.
- **It reads nothing until it is opened.** The Questionnaire search runs once
  per tab (a served guide cannot change under a running server) and the spool is
  re-read on each open, over whatever the last read produced - so the rows are
  there instantly and no page load carries the cost.
- **The action list is a pure function** (`lib/palette.ts`) of what this run
  offers, so the claim that the palette reaches every page is asserted rather
  than believed.

#### Settings, and the keys

- **One gear at the foot of the sidebar** holds both appearance controls - the
  five themes under **Theme**, the light or dark ground under **Mode** - and a
  way into the list of shortcuts. The header keeps the collapse control, the
  page's name, who is signed in, and the server light, and carries neither
  appearance control. Collapsed to icons the gear stays where it is, with the
  tooltip every rail entry has.
- **`?` puts every key this app answers on screen**, matched on the character
  rather than on a physical key plus Shift, because a `?` is Shift and the slash
  on one layout and Shift and the plus on another. It never fires while an input,
  a textarea, a select, a rich-text region, or a CodeMirror editor has focus.
- **Cmd+B on macOS, Ctrl+B everywhere else, collapses the sidebar** and puts it
  back - the platform's own modifier rather than either, because Ctrl+B on macOS
  is the "back one character" that text fields and CodeMirror both answer. It
  fires while a box or an editor has focus, since clearing the screen is worth
  most mid-form, and stands aside only for a rich-text region.
- **The list is `lib/shortcuts.ts` and the rules are pure functions** over a
  described key press, so "not while somebody is typing" and "which modifier on
  which platform" are asserted rather than buried in an effect. Both chords are
  palette rows as well.

#### Themes

- **Five designed themes, each complete on both grounds**: **Clinical** (the
  default - near-achromatic surfaces and one clinical blue), **Indigo** (deep
  blue surfaces under a violet identity), **Paper** (warm surfaces and an ink
  blue), **Contrast** (the widest separation between text and its surface), and
  **Terminal** (phosphor green, and a ground to match).
- **Theme and mode are two axes and stay two controls.** next-themes owns light
  or dark as a `dark` class; `lib/theme.ts` owns the theme as `data-theme` on the
  same element. The settings gear carries the two under their own headings, and
  the palette carries both on its Appearance shelf.
- **Applied before the first paint** by an inline script in `index.html` reading
  the same `localStorage` key the module writes, so a reload never flashes one
  theme under another. The two copies of the theme-name list are kept in step by
  a test that reads `index.html`.
- **Every theme states the whole palette** - surfaces, identity, the spool's
  lifecycle colours, and the `.tok-*` source colours the CodeMirror editors are
  painted from - hung off `html[data-theme]` for the light ground and
  `html.dark[data-theme]` for the dark one, so the dark block outranks its light
  sibling by specificity rather than by source order. A unit test reads
  `index.css` and fails a theme that leaves a token behind; a Playwright case
  paints every token pair into a canvas and puts it through the WCAG contrast
  formula, on all five themes and both grounds.
- **Geometry is not a theme axis**: no theme redeclares `--radius`, so the whole
  surface still rescales from one number.
- **Terminal moves one status colour and says so**: its identity is the phosphor
  green, so `forwarded` and `completed` become a cyan rather than share the
  identity's hue with `received`. Every other theme keeps the lifecycle colours
  unchanged, and `--map-selection` stays an amber pair in all five so a selected
  organisation unit is never a stronger shade of the wash beneath it.
- **The organisation-unit map follows both axes.** It watches `<html>` for the
  class and the attribute, and rebuilds its layers from the tokens on either -
  a theme change repaints the boundaries with nothing reloaded.

#### Mounting and coverage

- **The bundle mounts in two pieces around the router table**: its asset tree
  ahead of the read catch-alls that would otherwise claim `/assets/<file>`, its
  shell after everything - so no FHIR path is shadowed and an unserved resource
  type is still an OperationOutcome rather than a page.
- **Routing is hash-based**, so a reload needs no SPA fallback.
- **`--ui` without a built bundle refuses in one line** naming
  `make build-frontend` rather than serving a blank page.
- **Covered by vitest unit tests** over its wire layer and by a Playwright
  suite (`make e2e-frontend`) that boots a real `d2w fhir serve --ui` on its
  own port over a fixture IG project and drives the capture loop end to end
  twice: at the API level (`$generate`, post, the receipt appearing on the
  Responses page) and through the renderer (open the form, fill with test data,
  submit, land on the listing).
### Forward captures into DHIS2

`d2w fhir forward` is the third verb, and it closes the loop
IG -> form -> QuestionnaireResponse -> DHIS2. It reads the receipts out of
`.serve/responses/received/` and drains them.

#### Translation context

- **Assembled from the very artifacts the facade serves**: the compiled
  `ig/fsh-generated/resources` merged with the predefined `ig/input/resources`
  tree.
- **Or, for a project holding no compiled guide**, the same documents built off
  the instance through `fetch_live_artifacts` - the forward-side twin of
  `serve --live`, reading one metadata pass through the same builders - so a
  receipt captured with no build step drains with none. The absence of the
  compiled tree is the whole trigger, and `[forward] live = false` restores the
  refusal naming `d2w fhir generate` and `make sushi`.
- **Plus one id-only `fields=id,valueType` read** against `/api/dataElements`
  and another against `/api/trackedEntityAttributes`, for the one fact the
  compiled IG cannot carry: R4 spells `BOOLEAN` and `TRUE_ONLY` as the same
  `#boolean` item type.

#### Translation

Each response goes through `dhis2w_fhir.conversion` all-or-nothing.

- **An aggregate envelope** carries all three DHIS2 keys, with its
  `attributeOptionCombo` resolved off the response's `D2AttributeOptionCombo`
  coding against the vocabulary the form declares, on the same concept-code /
  `dhis2-id` / ConceptMap tiers a coded answer resolves through and under the
  same lenient/strict dial. A form that declares one and a response that names
  none is refused as `missing-attribute-option-combo` rather than posted,
  because DHIS2 refuses that write with `E8023`; a combo the vocabulary does
  not hold is `unresolvable-attribute-option-combo`; a combo named against a
  form that declares none is noted and left off, since its data set rides the
  default category combo.
- **A tracker registration** becomes the `/api/tracker` `trackedEntities` entry
  it creates, carrying the client-minted tracked entity UID, the tracked entity
  type the form's `$DHIS2-TET` identifier names (absent, it is refused as
  `missing-tracked-entity-type`, since a program without one cannot register
  anybody), one `TrackerAttribute` per answered tracked entity attribute
  through the same value-type serialisation and the same coded-answer dial a
  data element's answer goes through, and the single `ACTIVE` enrollment it
  mints - `enrolledAt` required (`missing-enrollment-date`) and `occurredAt`
  written only where the response states an incident date, both read back to
  the zone-less wall clock DHIS2 stores.
- **An event of either kind** carries the DHIS2 UID derived from the receipt's
  own logical id (SHA-256 over `<response id>:event:0`, shaped by the drawer
  the synthesis path mints tracked entity and enrollment UIDs with), so one
  receipt always names one event: a dry run and the import behind it report the
  same object, and a receipt forwarded twice is refused as an object the
  instance already holds rather than filed as a second copy of one visit.

#### Posting

- **One payload per response**: an aggregate envelope to `/api/dataValueSets`,
  everything else to `/api/tracker` under
  `importStrategy=CREATE&async=false`, through one client opened for the whole
  run.
- **People before the payloads that create an enrollment, and those before
  everything that answers into one**, so the person a registration of the same
  drain enrols and the enrollment a stage response answers against both exist
  by the time DHIS2 reads them (`E1313` otherwise). No dependency tracking sits
  behind the ordering, and the report still reads back in spool order.

#### Dry run is the default

- **Every payload still reaches the real endpoint** under that endpoint's own
  validate-only mode (`dryRun=true` on `/api/dataValueSets`,
  `importMode=VALIDATE` on `/api/tracker`, the v42 spellings taken from the
  generated OpenAPI), so DHIS2's own rules decide each outcome while nothing is
  written and no receipt moves.
- **The terminal opens and closes with a DRY RUN banner** naming `--import` as
  the way to commit.
- **`[forward] import = true`** makes the bare run of a project whose drains
  are routine commit instead, with `--import` / `--dry-run` still outranking it
  either way - flag, then table, then default, resolved in `forward_responses`
  so the CLI and the MCP tool cannot resolve it differently.
- **A dry run counts a stage event whose enrollment a registration of the same
  run creates as unverifiable** rather than rejected - it writes nothing, so
  there is no enrollment to check the event against - and gives it its own
  count and section, while a stage event naming an enrollment no registration
  of the run creates stays a rejection.
- **A DHIS2 rejection exits 1; a dry run whose only failures are unverifiable
  exits 0.**

#### What DHIS2 said

- **A DHIS2 refusal arrives as a 409** and is recorded as one response's
  outcome rather than raised as the run's, with every word DHIS2 said kept.
- **The two endpoints disagree on the shape**: `/api/dataValueSets` answers a
  `WebMessage` wrapping the `ImportSummary`, `/api/tracker` answers the
  `TrackerImportReport` bare with no envelope at all - so each family
  recognises its own report by the fields only that report carries.
- **Every row lands as a typed `ForwardImportIssue`** (`error_code`, `subject`,
  `message`) whether it came from `response.conflicts[]` or
  `validationReport.errorReports[]`, with the generated `ImportSummary` /
  `TrackerImportReport` riding alongside untouched.
- **Rejections roll up by cause** - error code plus the message with its quoted
  identifiers generalised away, except a UID naming a program rule the guide
  published, which is read back as that rule's own name so an `E1300` refusal
  says which rule refused rather than which twelve characters did (the raw UID
  stays untouched on the response's own `.report.json`). Each response is
  counted once per distinct cause, so `202 rejected` reads as the three rules
  it broke, rendered as a `Responses | Code | What DHIS2 said` table on the
  terminal and at the head of the written report.

#### The spool as ledger

- **With `--import`**, an accepted receipt is renamed into
  `.serve/responses/forwarded/` and a rejected one into `rejected/`, each
  beside an atomically written `<id>.report.json` holding its import outcome -
  a rejection needs one to say why it was refused, and an acceptance needs one
  because the import counts are what say how much of it landed, which
  `GET /spool` then carries on the row as `imported`.
- **A conversion-refused receipt stays in `received/` untouched**, because the
  fix for it is in the guide or in the data and the next run is the retry -
  except the one refusal no fix could ever reach.
- **A response reporting itself `entered-in-error`** asks for a withdrawal this
  toolchain does not build, and is therefore filed to `rejected/` with a
  sidecar naming the doctrine (`TERMINAL_REFUSAL_CATEGORIES`, one explicit set
  rather than a flag on a whim; see
  [Corrections and withdrawals](../fhir/design/data-lifecycle.md)) rather than translated
  again by every drain for ever. `d2w fhir requeue` is the way back for an
  operator who disagrees.
- **Each receipt is filed the instant DHIS2 answers about it** - the sidecar
  written, then the rename - inside the posting loop rather than in a pass at
  the end. So a drain that is killed halfway leaves everything it posted in
  `forwarded/` or `rejected/` with its report, and everything it had not
  reached untouched in the queue; a rename that finds the file already gone is
  graded onto the report as a lost race rather than throwing the drain and
  DHIS2's answer away.
- **One drain at a time.** A run holds an exclusive `flock` on
  `.serve/responses/.drain.lock` for its whole length with its own process id
  written inside, so a second drain of the same project fails at once naming
  the holder rather than posting every payload twice and racing its renames,
  and the kernel releases it however the run ended. `fhir serve` never takes
  it.
- **A file in `received/` that will not read as a receipt is quarantined** to
  `malformed/` with its reason and named on the report while the drain proceeds
  with the rest, and abandoned temporary files older than an hour are swept as
  the drain starts.
- **An instance that fails mid-drain** - a 5xx, or a connection that never
  completes - stops the run rather than being read as a verdict on the payload
  that met it: whatever was already posted stays filed, that receipt and
  everything behind it stay in `received/` as `not-posted`, and the report
  names what stopped it and how many were never sent.
- **The terminal states the distinction in its own closing line**: a DHIS2
  rejection points at the import summary, a translator refusal points at the
  guide.

#### Data set completeness

- **An aggregate response whose `status` is `completed` also registers data-set
  completeness**: a second write to `/api/completeDataSetRegistrations` naming
  the very `(dataSet, period, organisationUnit, attributeOptionCombo)` tuple
  the values landed under, claiming the day the response records itself
  `authored`, and made only after DHIS2 has taken the values - since a
  completeness claim about data the instance refused would be a lie.
- **`in-progress` imports its values and registers nothing.**
- **`--register-completeness` / `--no-register-completeness`** (default on,
  `[forward] register_completeness` stating it once for the project, and
  `register_completeness` on the MCP tool) turns the whole run's second write
  off. A dry run posts nothing and states the tuple it would register instead.
- **A refused registration is reported as such without un-importing the
  values**, which stay imported and are re-claimed by forwarding the same tuple
  again - DHIS2 answers a registration it already holds with `updated`, not a
  conflict.
- **Each outcome is typed on `ForwardCompletenessOutcome`** (`registered` /
  `would-register` / `not-claimed` / `not-registered` / `refused`) and rendered
  as its own terminal table, summary row, and written-report section carrying
  the four keys, because a registration has no UID to look it up by.
- **The envelope's own `completeDate` is deliberately never written**, since on
  2.42 it registers completeness even when every value was refused and even
  under `dryRun=true` (BUGS.md 76, 77).

#### Values a previous submission already sent

- **A drain names every aggregate value it sends that a forwarded receipt
  already sent**, with the receipt that sent it and when that receipt arrived.
  DHIS2 replaces such a value in place and counts the write exactly as it
  counts a first entry (BUGS.md 85), so no import summary can separate a
  correction from a first entry - the spool answers what the wire cannot.
- **The record is the sidecar.** A forwarded receipt's `<id>.report.json`
  carries the identity of every value its payload landed on - data element,
  category option combo, period, organisation unit, attribute option combo -
  and the day the receipt arrived. Identity only, never the numbers.
- **Only `forwarded/` counts**: a receipt DHIS2 refused never landed its
  values, and one still in the queue has not been sent. Receipts filed earlier
  in the same drain do count, so a drain holding two captures of one report
  says that the second replaced the first.
- **A dry run states it too**, as the prediction it is - the moment there is
  still something to be done about it.
- **`[forward] overwrites` decides what the drain does about it**, with
  `--overwrites allow|refuse` outranking it for one run - flag, then table, then
  default, resolved in `forward_responses` like the sibling dials. `allow` - the
  default - posts the value and names it, which is DHIS2's own last-write-wins
  semantics taken as a posture rather than inherited by omission.
- **`refuse` sends no payload holding such a value at all**, and refuses the
  **whole response** rather than part of it - a payload posted in part would
  tear one submission across two postures. The refusal is non-terminal: the
  receipt stays in `received/` with an `<id>.refusal.json` under category
  `overwrite-refused` naming every covered value, the receipt that sent it, and
  when that receipt arrived, so `d2w fhir spool` shows it as refused-but-queued
  with the reason and a later drain under `allow` posts it. A dry run under
  `refuse` states what it would refuse and files nothing. A refused response
  claims no data-set completeness, since its values were never sent.
- **The refused responses are counted under the run's own refused number**, and
  read apart from a translator refusal wherever the reason matters:
  `ForwardOutcome.overwrite_refused`, a `Refused as an overwrite` section of the
  written report, and a terminal note naming `--overwrites allow` as the way to
  post them.
- **The dial never reaches a tracker payload.** An event's DHIS2 identity is
  derived from the receipt's own id, so it collides rather than overwriting -
  see [Corrections and withdrawals](../fhir/design/data-lifecycle.md), which
  carries the decision (D8) in full.
- **The reading is built once per drain and only when the drain carries an
  aggregate payload**, so a tracker-only run reads nothing at all. It opens
  each forwarded receipt's import report once and nothing else, and it never
  truncates or samples - a reading that quietly stopped part-way would answer
  "no earlier submission" about a value that has one.
- **Typed as `AggregateCell` / `OverwrittenValue` / `ForwardOverwrite`** on
  `ForwardOutcome.overwritten_values`, and rendered as a terminal note, a
  `--details` table, its own written-report section, and the `--json` payload.
  A receipt in `forwarded/` whose report records no values is counted on
  `forwarded_without_values` and named, rather than passed over in silence.

#### Corrections and withdrawals

The posture today, in one place, because "is this supported?" is the question
this section exists to close. The full argument and the design the remaining
slices follow are in
[Corrections and withdrawals](../fhir/design/data-lifecycle.md).

- **A second capture of an aggregate report overwrites the first in place.**
  The envelope names no `importStrategy`, so DHIS2 applies its own
  `CREATE_AND_UPDATE`; the values are replaced and the report says which ones
  (above). `[forward] overwrites = "refuse"` is the deployment posture that
  leaves such a response in the queue instead of sending it.
- **A second capture of a tracker visit creates a duplicate**, because an
  event's UID is derived from the receipt's own id and every capture mints a
  fresh receipt. Re-forwarding the *same* receipt is the case DHIS2 refuses,
  with `E1030` - one receipt names one event, and that is the guarantee that
  holds.
- **`[forward] corrections` and `[forward] withdrawals` are the deployment's
  posture towards a marked submission**, where `overwrites` is its posture
  towards an unmarked one. `corrections` takes `"off"` (the default) or
  `"amend"`; `withdrawals` takes `"off"` (the default) or `"retract"`. Both
  resolve in `service.forward_responses` alongside every sibling dial - the
  flag, then `fhir.toml`, then the default - with `--corrections` and
  `--withdrawals` on `d2w fhir forward` overriding either for one run, and both
  are named in `--details` and `--json` wherever a project has turned one on.
  A drain acts on neither: it imports.
- **A project publishing forms is not thereby a project that reaches back into
  DHIS2**, which is why both default to off. Turning one on is a sentence
  somebody wrote rather than a default nobody read.
- **`d2w data tracker delete` is the raw escape hatch** for the kinds the FHIR
  path does not retract, outside it and behind a confirmation prompt, with
  `d2w data aggregate delete` beside it.

### Withdraw an event you forwarded

`d2w fhir withdraw <receipt id>...` deletes from DHIS2 the event a forwarded
receipt landed, and files the receipt under the spool's fourth state.

- **`[forward] withdrawals = "retract"` gates the whole command**, with
  `--withdrawals retract` stating it for one run. Off, the command posts
  nothing at all and the refusal names the key.
- **The identity is recomputed, never looked up.** The object deleted is
  `receipt_event_uid(<the receipt's id>)`, so a withdrawal needs no compiled
  guide, no metadata read, and no translation - which makes it answerable about
  a project captured through `d2w fhir serve --live`.
- **A dry run is the default**, exactly as it is for a drain: the delete goes
  to `/api/tracker` under `importMode=VALIDATE`, so DHIS2 answers whether it
  would take it while nothing is deleted and no receipt moves. `--import`
  commits.
- **`withdrawn/` is the spool's fourth state**, and the only one a receipt
  reaches without being posted again. The receipt file is never rewritten; a
  `<id>.report.json` holding what DHIS2 answered the delete lands beside it
  first, and the import report that recorded what it landed **stays in
  `forwarded/`** - two answers to two questions, neither rewritten.
- **Withdrawal is terminal, and the copy says what remains rather than
  "deleted".** DHIS2 burns the UID it deletes and refuses it under every import
  strategy afterwards, so a withdrawn receipt can never be forwarded again;
  what stays in the instance is a hidden copy of the event carrying its values,
  which no ordinary read returns.
- **Only a forwarded receipt that landed one event can be withdrawn**, and
  every id is checked before anything is posted. An aggregate report and a
  registration are refused by name with the kind they are - each needs a guard
  the event leg does not.
- **A delete DHIS2 refuses leaves the receipt in `forwarded/`** with the import
  report that says what it landed, names it `refused` in the run, and exits 1.
- **Typed as `WithdrawReport` / `WithdrawnReceipt` / `WithdrawalRecord` /
  `WithdrawalKind`**, with `--json` carrying the whole report, and
  `WithdrawalNotEnabledError` / `WithdrawalUnsupportedError` for the two
  refusals that are about the project rather than about DHIS2.
- **`d2w fhir spool` counts the fourth state** and reads the record of the
  delete back for the reason column.

#### Output

- **`[serve] strict_codes` is the default coded-answer dial**, so a project
  that captures strictly forwards strictly, and `--strict-codes` /
  `--no-strict-codes` overrides it.
- **The condensed terminal writes every response's outcome** to
  `reports/fhir-forward-report.md` with one counted hint, while `--details`
  prints the per-response table with a Why column carrying each response's
  first reason, and `--json` carries the whole `ForwardReport`. The written
  report's header states what the run replaced as well as what it counted.
- **The scaffolded Makefile gains `make forward` / `make forward-import`.**

### Inspect and requeue the spool

Two operator verbs sit beside the drain and touch no instance at all.

- **`d2w fhir spool`** states how many receipts wait in each state and how many
  files are in the holding pen. `--details` adds a row per receipt with the
  short reason read off the sidecar, and `--json` carries the whole
  `SpoolStateReport`.
- **`d2w fhir requeue <id>... | --all-rejected`** renames refused receipts back
  into `received/` for the next drain, leaving the import report behind in
  `rejected/` as the record of what DHIS2 last answered about that payload, and
  refusing an id that is not there before anything moves - so a run of five
  never leaves an operator working out which three it reached.
- **`d2w fhir spool` states four states**, `withdrawn/` beside the three the
  drain files into.
- **Neither opens a client nor needs a profile**, because every fact either
  states is in the project directory, which is what makes them answerable while
  the instance is down.

### Check an instance

`d2w fhir doctor` is the conformance runner: it scaffolds a throwaway project
against the ambient profile and drives the entire chain through it in nine
typed phases.

- **connect** - version detected, plugin tree named.
- **scaffold** - a coherent probe: the first data set, the first
  WITHOUT_REGISTRATION program, and the first WITH_REGISTRATION program by
  name, plus the organisation-unit subtree those forms are actually assigned
  inside, since DHIS2 refuses a response naming a unit a form is not assigned
  to. `--all-targets` takes the lot instead.
- **generate** - the full pipeline, every note kept as a finding.
- **compile** - real SUSHI when the machine offers one (`sushi` on PATH or the
  `fhir-ig` docker image the scaffold builds), and SKIPPED with that reason
  otherwise, because a compile is evidence rather than a gate every machine can
  meet.
- **validate** - the scope-aware code report folded in.
- **serve** - the store built in process, no port bound and no subprocess
  started, from the compiled guide or from the live builders written where a
  compiler would have written them.
- **capture** - `$generate` over every published form, posted straight back
  through an in-process `httpx.AsyncClient` over the ASGI app, holding the
  endpoint to its 201 invariant, registrations before their stages.
- **forward** - the corpus drained at the real instance in validate-only mode,
  rejections rolled up by cause.
- **oracle** (`--live`) - the instance judges the served output: every served
  UID resolved back against the DHIS2 collection it names, plus a seeded sample
  per family deep-compared field by field, with the field path stated on every
  mismatch and the DHIS2 object always the authority.

Each phase reports PASS / WARN / FAIL / SKIPPED / BLOCKED with a stated reason,
a failure never stops a phase that does not depend on it, and only a FAIL exits
1. The run renders a phase table, a findings table, and a verdict line on
stderr, carries the typed `DoctorReport` under `--json`, and writes
`reports/fhir-doctor-report.md` as the artifact a handover is read from.

CLI-only by design: a write-heavy orchestration with no read-only shape an MCP
tool could honestly advertise.

### Configuration

A committed `fhir.toml`, discovered by walking up from the working directory,
carries the whole project's settings. Every table of that document declares its
full key set and refuses anything else.

| Table | What it sets |
| --- | --- |
| top level | `profile` - the connection profile the project reads |
| `[ig]` | `id`, `canonical`, `name`, `title`, `publisher`, `status` |
| `[generate]` | `identifier_system_base`, `concept_code_source`, `timezone`, `locales` |
| `[generate.naming]` | `source` plus `prefix` and the eight artifact tokens |
| `[generate.option_sets]` | Terminology selection |
| `[generate.categories]` | Category selection, `include_default` |
| `[generate.organisation_units]` | `root`, `max_level`, `terminology` |
| `[generate.data_sets]` | Aggregate form selection |
| `[generate.event_programs]` | Event program selection (WITHOUT_REGISTRATION) |
| `[generate.tracker_programs]` | Tracker program selection (WITH_REGISTRATION) |
| `[generate.tracked_entity_forms]` | Person-only registration form selection |
| `[generate.tracked_entity_types]` | UID to FHIR resource type map |
| `[generate.examples]` | `per_target`, `source` |
| `[serve]` | `host`, `port`, `strict_codes`, `capture`, `ui`, `spool_dir`, `basemaps`, `tracked_entities`, `search` |
| `[serve.tracked_entities]` | `enabled`, `listing`, `page_size`, `page_size_limit`, `tracked_entity_types`, `search_attributes` |
| `[serve.search]` | `backend` (`dhis2`, `projection`) |
| `[serve.projection]` | `store` (`none`, `sqlite`), `path`, `overlap_seconds` |
| `[forward]` | `live`, `import`, `register_completeness`, `overwrites`, `corrections`, `withdrawals` |

- **An unknown key stops the command.** A misspelled `max_lvl = 4` produces
  `error: fhir.toml: unknown key 'max_lvl' in [generate.organisation_units]`
  with a `did you mean 'max_level'?` beneath it - one such line per unknown
  key, `difflib`-matched against the very names that table accepts, and no
  suggestion where nothing is close, instead of setting nothing and saying
  nothing.
- **Two values unset silently**: `root = ""` and `max_level = 0`.
- **Flags beat the table beats the defaults** on `[serve]` and `[forward]`
  alike, and `--strict-codes` / `--no-strict-codes` reaches all three levels.
  `[serve] capture` and `[serve] spool_dir` have no flag at all, and neither do
  `[serve.tracked_entities]`, `[serve.search]`, and `[serve.projection]`, because
  each states what the server is rather than what one run does.
- **The `[forward] import` key is spelled `import` in the file** (the field is
  `import_responses` in Python, because `import` is a keyword), and the file
  accepts no other spelling of it.
- **`fhir.toml.example`** carries a one-line comment per option pointing at its
  section in the guide, and the scaffolded `fhir.toml` header names both the
  example file and the series.

### Progress and output

Every `d2w fhir` command with an instance behind it narrates its steps on
stderr - a spinner on a terminal, plain `[k/N]` lines when redirected - and
takes `--progress` / `--no-progress`. Tables, notes, and progress are stderr;
stdout carries the `--json` payload alone, so `--json` implies a silent stderr.

### The library surface

Every capability behind a `d2w fhir` command is importable from `dhis2w_fhir`
itself, so an embedding application calls what the command calls. Names below are
`from dhis2w_fhir import ...`; [the API reference](../fhir/api-dhis2w-fhir.md)
renders each module.

| Capability | Names |
| --- | --- |
| Generation, whole guide or one target | `generate_full`, `generate_foundation`, `generate_option_sets`, `generate_categories`, `generate_questionnaires`, `generate_examples`, `generate_organisation_units`, `generate_pages`, plus `GenerateReport` / `GenerateFullReport` |
| The build refusals | `BuildAbortingCodeError`, `BuildAbortingNameError`, and the two predicates behind them, `build_aborting_code` and `build_aborting_name` |
| The same refusal read off disk | `check_publishable_artifacts`, `ArtifactCheckReport`, `ArtifactFinding` |
| Scaffolding | `init_project`, `refresh_project`, `read_project_scaffold_state`, `ProjectScaffoldState`, `normalize_project_name`, `preserves_every_line` |
| Validation, producing a report rather than rendering one | `validate_codes`, `resolve_validation_context`, `resolve_validation_scope`, `resolve_code_source`, `ValidationContext`, `display_code` |
| The conformance runner | `run_doctor`, `DoctorOptions`, `DoctorReport`, `DoctorPhase`, `DoctorOutcome`, `DoctorPhaseResult`, `DoctorFinding`, `PhaseOutcome`, `CaptureOutcome`, `FamilyOutcome`, `resolve_doctor_profile`, `render_doctor_markdown`, `phase_evidence`, `generate_findings`, and the graders `grade`, `grade_capture`, `grade_forward`, `grade_oracle` |
| Refusal records on the spool | `record_refusal`, `read_refusal_record`, `ForwardRefusalRecord`, `RefusalReason`, `SPOOL_RELATIVE_PATH`, `REFUSAL_RECORD_SUFFIX`, `QUARANTINE_REASON_SUFFIX`, `DRAIN_LOCK_FILE_NAME`, `ORPHAN_TEMPORARY_FILE_AGE_SECONDS` |
| The profile a run resolves | `GenerationProfile`, `resolve_generation_profile` |

- **Every capability that reads DHIS2 takes the connection as an argument.**
  `client=` on `validate_codes`, `run_doctor`, `forward_responses`, and each
  generate target, with the `Profile` form kept as the convenience wrapper the
  commands use. A handed-in client is used as it stands and left open - its
  lifetime belongs to whoever entered it - so an application already holding an
  authenticated connection makes one connection rather than one per call.
  `fetch_live_ig_inputs` and `fetch_live_artifacts` have always taken one.
- **`run_doctor` states what it does to the machine** in its own docstring: it
  mints a workspace, shells out to `sushi` or `docker run`, writes compiled
  resources, runs an ASGI application in process, and posts a synthetic corpus
  under validate-only mode. The graders are pure and callable without any of it.
- **A test asserts the surface.** `test_fhir_package_surface.py` parses the
  `:::` directives out of `docs/fhir/api-dhis2w-fhir.md` and fails when a module
  the API reference renders exports a name the package does not, so the docs and
  the imports cannot drift apart quietly.

### No MCP tools

The surface is CLI-only, and the plugin registers nothing on the MCP server.
Most of it could be nothing else - scaffolding, every generate target, and
`doctor` write a file tree onto whatever machine the server runs on, and
`serve` binds a port and stays up. `validate` and `forward` broke neither rule
and are still not tools: each mirrored its command closely enough to earn
nothing. What an agent drives instead is the served facade, which answers FHIR
over HTTP.

### Documentation

The graded `d2w fhir` series lives under `docs/fhir/`, routed from
[the series index](../fhir/index.md) - the "I am a..." router
(implementer / M&E configurer / integration developer / operator) and the full
101/201/301/401 page map, which is also the FHIR top-level tab's Overview page.

**101 - Understand**

- [Glossary](../fhir/glossary.md) - every DHIS2 and FHIR term the series
  uses, and what the toolchain does with it.
- [What `d2w fhir` is and why](../fhir/101-what-and-why.md) - why a
  ministry publishes an IG, what each verb produces, what adopting the
  toolchain costs. No commands.
- [FHIR for DHIS2 people](../fhir/101-fhir-concepts.md) - every FHIR
  term the series uses, explained in DHIS2 terms.
- [Quickstart: from nothing to a served IG](../fhir/101-quickstart.md) -
  scaffold, sync, profile, validate, generate, and compile, each command with
  captured real output.

**201 - Operate a project**

- [Check an instance with doctor](../fhir/201-doctor.md) - the whole
  chain against one instance, phase by phase.
- [Set up an IG project](../fhir/201-set-up-a-project.md) -
  `d2w fhir init` and its flags, the pinned `uv` toolchain, profile resolution
  order, `init --refresh` and `make update`.
- [Validate the instance](../fhir/201-validate.md) - the FHIR-safety
  check: severity as build impact, the scope column, the `--code-source` dial,
  report files, the CI exit-1 gate.
- [Generate the IG source](../fhir/201-generate.md) - the generate
  targets, directory ownership and sync, selection narrowing, notes and
  validate echoes, site pages.
- [Build and publish the guide](../fhir/201-build-and-publish.md) - the
  scaffolded Makefile, the three build knobs, registry scale, the two caches,
  publishing `ig/output/`.
- [Serve the guide](../fhir/201-serve.md) - `d2w fhir serve` in both
  modes, `[serve]` in practice with the flag-beats-table-beats-default rule,
  receipts as the storage model, the strict/lenient dial across all four things
  it grades, the viewer posture, the spool on disk, and load sets.
- [Capture in the browser](../fhir/201-capture-ui.md) - the capture UI
  page by page, with screenshots produced by a committed, skipped-by-default
  Playwright spec against the fixture suite server
  (`frontend/e2e/docs-screenshots.spec.ts`), including how to re-shoot them.
- [Forward captures into DHIS2](../fhir/201-forward.md) - the
  dry-run-first workflow on DHIS2's own validate-only modes, the six steps of a
  run, the four receipt states, refusal versus rejection, the drain lock,
  reading the queue with `fhir spool` and putting a refused receipt back with
  `fhir requeue`, taking back a forwarded event with `fhir withdraw`, the
  translated-payload field tables, and a worked run with the rejection rollup.
- [Troubleshooting](../fhir/201-troubleshooting.md) - every literal
  `d2w fhir` refusal plus the SUSHI / IG publisher failure modes, as symptom,
  cause, fix.

**301 - Configure `fhir.toml`**

Every option gets the same per-option treatment: plain words, a concrete change
scenario, an example, the default and leave-it-out behaviour, and the exact
refusal text a mistake produces, captured from real misconfigured runs.

- [The settings file: fhir.toml](../fhir/301-fhir-toml.md) - what the
  file is, how commands discover it, the `fhir.toml` / `fhir.toml.example`
  split, TOML editing rules, the unknown-key refusal and its `did you mean`
  suggestion, the two silent-unset values, and the three
  read-before-you-decide options.
- [Who the guide is](../fhir/301-identity.md) - `profile` and the
  `[ig]` table.
- [How things are generated](../fhir/301-generation.md) - the
  `[generate]` options, the `[generate.naming]` pieces and their shared token
  rule, and the `naming.source` re-identification warning.
- [What goes in](../fhir/301-what-goes-in.md) - the selection tables,
  `include_default`, `[generate.tracked_entity_types]`, `[generate.examples]`,
  and the organisation-unit scope with the `max_level` cost warning.
- [Serving it](../fhir/301-serving.md) - the `[serve]` options with the
  `host` exposure warning, the `capture` viewer posture, the `spool_dir`
  receipt tree and the `basemaps` outbound-call note; the
  `[serve.tracked_entities]` register block; and the `[forward]` section -
  `live`, `import`, `register_completeness`, `overwrites`, `corrections`, and
  `withdrawals`.

**401 - Integrate and extend**

- [The capture contract](../fhir/401-capture-contract.md) - the five
  response profiles, the requirements CapabilityStatement, the logical
  tracked-entity subject, minted identifiers and what a server can honestly
  check about them, and the required-question and numeric-bound rules.
- [Consume the FHIR API](../fhir/401-consume-the-fhir-api.md) - the
  served read set and searches, `$translate` and `$generate` with real requests
  and responses, the capture POST with its validation phases, and the two
  non-FHIR endpoints `/spool` and `/uiconfig`.
- [Identifiers and the D2 extensions](../fhir/401-identifiers-and-extensions.md) -
  the `D2Period` and `D2AttributeValue` extensions, the identifier families,
  NamingSystems, and the UID fall-back rules.
- [Terminology and ConceptMaps](../fhir/401-terminology-and-conceptmaps.md) -
  the option-set and category CodeSystem/ValueSet pairs, the per-object
  ConceptMaps, the two-group shape, and UID-versus-code target guidance.
- [Custom subject types](../fhir/401-custom-subject-types.md) -
  `[generate.tracked_entity_types]` end to end: the admitted resource types,
  everything one mapping feeds, and the union rule the two tracker response
  profiles publish under.
- [Regeneration and hand-authoring](../fhir/401-regeneration-and-hand-authoring.md) -
  the generated-header contract, the directories generation owns outright, what
  is scaffolded as yours, what to commit, and the duplicate-definition
  recovery.

---

## FHIR Evaluation Engine

**Package:** `dhis2w-fhir-engine` | **Install:** `uv add dhis2w-fhir-engine`

Evaluate FHIRPath expressions, CQL libraries, and ELM against FHIR-shaped data,
and score CQL quality measures into a FHIR R4 `MeasureReport`.

The grammar, parser, AST, and evaluator layers are FHIR-version-neutral - FHIRPath
is normative and CQL is 1.5, and neither names a FHIR release. Everything that does
bind to a release reaches those layers as a `FhirVersionBinding` value out of
`dhis2w_fhir_engine.r4`, so R5 lands as a sibling subpackage rather than a fork of
the evaluator.

The package runs the official HL7 CQL and FHIRPath R4 compliance suites as part of
its own test run.

It ships the console script `d2w-fhir-engine` with `fhirpath`, `cql`, and `elm`
sub-apps over the same engine.

It owns the R4 resource models at `dhis2w_fhir_engine.r4.resources`: `Patient`,
`Bundle`, `QuestionnaireResponse`, `Composition`, `Extension`, and the rest.
Every model is closed, frozen, and alias-aware, so
`model_dump_json(exclude_none=True, by_alias=True)` reproduces the wire document
key for key. `dhis2w_fhir.r4` is the capture-facing facade re-exporting that
family, so a name is defined once and imported from whichever package a caller
already works in.

Every entry point that ingests a resource - the evaluation contexts, the
FHIRPath, CQL, and ELM evaluators, the data sources, the measure evaluator -
accepts either the wire dict or a pydantic model of it. A model is dumped once
on entry and evaluation reads dicts from there on, so nothing the engine does
reaches back into the caller's model.

It has no DHIS2 dependency and no web-framework dependency: it evaluates
expressions over FHIR-shaped JSON and returns values. It is the FHIR foundation
of the workspace rather than a leaf of it - `dhis2w-fhir` and `dhis2w-fhir-serve`
both depend on it.

- [`dhis2w_fhir_engine` API reference](../fhir/api-dhis2w-fhir-engine.md) - the
  importable surface, module by module.
- [FHIRPath](../fhir/501-fhirpath.md), [CQL](../fhir/501-cql.md),
  [Quality measures](../fhir/501-measures.md), and
  [The FHIR version binding](../fhir/501-version-binding.md) - the 501 guide series.
- [`examples/fhir/engine/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/fhir/engine) -
  nine runnable examples, one feature apiece.

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

One example tree, version-neutral: each example is a single copy that runs
against DHIS2 v41, v42, and v43.

- **`examples/fhir/`**: the `d2w fhir` surface in its own group - 5 CLI scripts
  (init/generate/validate, serve, forward, doctor, spool) and 25 Python library
  examples grouped as build a response, read a form, convert to DHIS2, send and
  verify, and drive the toolchain. Every one runs in `make verify-examples`
  against a shared `_fixture.py` that scaffolds a project, builds a translation
  context off the instance, and starts a live facade on a port the operating
  system picks. There are no MCP examples because there are no MCP tools: what
  an agent drives is the served facade, over HTTP.
- **`examples/fhir/igs/`**: eight complete `d2w fhir init` project trees, one
  per feature story - minimal aggregate, disaggregated aggregate, event program,
  tracker registration, strict terminology, district registry, mixed facility,
  and the `refused-names` exhibit whose generate is refused by design. Each is
  committed as its inputs alone (`fhir.toml`, the SUSHI skeleton, the Makefile,
  the Dockerfile); nothing `d2w fhir generate` or SUSHI writes is. `make
  verify-igs` refreshes, validates, generates, and dockerized-SUSHI-compiles all
  eight - an on-demand target, because it needs a reachable DHIS2 instance and
  docker.
- **`examples/client/`**: 80+ Python examples (whoami, CRUD, analytics, OIDC,
  bulk import, tracker lifecycle, sharing, error handling, ...)
- **`examples/cli/`**: 60+ shell scripts covering every CLI domain
- **`examples/mcp/`**: 40+ Python examples showing MCP tool usage

Examples that exist for one major only live under that major's subdirectory -
`examples/client/v41/` (3 v41 wire quirks) and `examples/client/v43/`
(10 v43 schema divergences). Every example is small, shows one feature, and is
executed by `make verify-examples`.

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

dhis2w-cli --------> dhis2w-fhir -----> dhis2w-core
dhis2w-mcp --------> dhis2w-fhir            |
dhis2w-fhir-serve -> dhis2w-fhir            |
       |               |                     |
       +---------------+---> dhis2w-fhir-engine
                       |
              (optional [serve] extra)

dhis2w-codegen        workspace-only generator
```

No dependency cycles. `dhis2w-client` is standalone, and so is
`dhis2w-fhir-engine`: it depends on nothing else in this workspace, and both
`dhis2w-fhir` and `dhis2w-fhir-serve` depend on it for the R4 resource models
and for FHIRPath and CQL evaluation. Browser automation and the FHIR serving
facade are always optional.

