# Security posture extras (PR 8): plan

Author: Morten Svanaes
Date: 2026-06-24
Status: IMPLEMENTED on `feat/security-audit-scanner` (2026-06-25) -- 8a `1a7da685`, 8b `f8c19125` / `e9b22859` / `649f4655`, 8c `52ac0f1f`. All five checks (transport, settings extensions, auth-methods, tokens, routes, audit-config) landed adversarially reviewed and gated; the 14-check catalog is complete. Only PR 9 (the cheap MCP read surface) remains before the scanner is release-complete. The sections below are the as-built design.

## 1. Overview

PR 8 closes out the security scanner catalog. Seven PRs have landed: the audit
framework (PR 1), the credential probe (PR 2), roles + hygiene (PR 3), version
(PR 4), apps (PR 5), guest (PR 6), and sharing (PR 7). PR 8 implements the last
five catalog checks that are pre-declared in `registry.py` but not yet flipped
into the implemented set, plus the verdict extensions to the already-shipped
`settings` check:

1. `transport` -- TLS posture and HTTP security headers read off the wire.
2. `auth-methods` -- OIDC providers on the login page plus registered OAuth2 clients.
3. `tokens` -- Personal Access Token inventory and weak-token posture.
4. `routes` -- the 2.41+ Route API as an SSRF surface.
5. `audit-config` -- DHIS2 auditing posture, API-first with an optional `--dhis-conf` parse.
6. `settings-extensions` -- new privilege-escalation and account-policy verdicts on the existing `settings` check.

After PR 8, the only remaining work before release is PR 9 (the MCP surface:
cheap single-request reads mirroring the CLI). The long-running `audit` stays
CLI-only. The feature is released once PR 8 and PR 9 have both landed.

This is greenfield. Every check below is the first working version of the thing;
nothing here fixes, migrates, or deprecates prior behaviour. The `settings`
extension adds verdicts to a reducer that already ships -- it does not rewrite
the four verdicts already there.

## 2. Architecture pattern recap

Every new check follows the same anatomy proven by `apps`, `guest`, `hygiene`,
and the shipped `settings` reducer. The work splits cleanly into version-invariant
opinion (`security_core`) and version-divergent wire extraction (`_wire.py`).

### 2.1 The version-invariant check module

A new check is a single file at
`packages/dhis2w-core/src/dhis2w_core/security_core/<check>.py`, no I/O, no client,
holding exactly four things (model after `apps.py:1-140`, `guest.py:1-119`):

1. A module docstring stating the signals, and a `_CHECK = "<key>"` constant
   matching the registry key (`apps.py:17`, `guest.py:18`, `settings_audit.py:12`).
2. Frozen input pydantic models (`model_config = ConfigDict(frozen=True)`, NO
   dataclass, NO dict across boundaries). Example precedent: `apps.InstalledApp`
   (`apps.py:20-29`), `guest.AnonymousResult` (`guest.py:30-37`). Typed
   probe-target / constant tuples live next to the model (`guest.ANONYMOUS_PROBE_TARGETS`
   at `guest.py:42-46`).
3. A pure reducer `evaluate_<check>(*, ...) -> list[AuditFinding]` taking
   ALREADY-TYPED inputs and fanning out to private `_*_findings` helpers
   (`apps.evaluate_apps:41-58`, `guest.evaluate_guest:49-62`). The
   `None`-means-degraded convention rides the signature (e.g. `apps.py:55-56`
   passes `hub: list[HubApp] | None` where `None` skips the update findings).
   The shipped `settings_audit.evaluate_settings:28-74` reads through a
   `SettingsLike` Protocol (`settings_audit.py:15-26`) so the reducer never
   imports a per-tree model -- the settings extension follows that same Protocol path.
4. Finding shaping via `AuditFinding` (`security_core/findings.py:43-54`: fields
   `check`, `severity`, `title`, `detail`, `subject?`, `evidence: dict[str,str]|None`,
   `group_key?`). `Severity` is the StrEnum CRITICAL/HIGH/MEDIUM/WARN/INFO
   (`findings.py:11-19`) -- there is NO LOW tier, so any "LOW" signal maps to WARN.
   `evidence` values are ALWAYS str. `group_key` folds repeated findings of one
   kind in the renderer; `subject` names the offending object. Reuse the
   severity helpers in `findings.py:57-74` where a role-reach signal is involved.

Each new check exports its public symbols (models + `evaluate_*`) through
`security_core/__init__.py` imports AND `__all__` (precedent `apps` at
`__init__.py:12`, `guest` at `:44-49`, `settings` at `:96`).

### 2.2 Per-tree audit.py wiring

The orchestrator lives per tree at
`dhis2w_core/v{41,42,43}/plugins/security/audit.py`. The three files are
mechanical copies differing ONLY in the docstring line and the `dhis2w_client.v{N}`
/ `dhis2w_core.v{N}` import paths (confirmed by diff: v42 `audit.py:1,12-13`
vs v41 `audit.py:1,12-13`; v43 `_RUNNERS` identical at `:395-402`). For a plain
check:

1. Write `async def _run_<key>(client: Dhis2Client) -> CheckResult` (model after
   `_run_apps:311-344`, `_run_guest:378-392`): get `label = label_for("<key>")`;
   fetch via the client `get_raw(path, params=...)` escape hatch inside a
   `try/except Dhis2ApiError` that returns `CheckResult(..., status=CheckStatus.DEGRADED,
   note=f"HTTP error: {exc}")`; IMMEDIATELY wrap the raw payload into the
   security_core input models (`get_raw` returns a parsed body, which is wrapped
   into named view-models inside `_run_*` and never leaves the function as a bare
   dict, per CLAUDE.md rule 7); call `evaluate_<key>(...)`; return
   `CheckResult(..., status=CheckStatus.OK, findings=..., note=...)`. Degrade-with-note
   (not fail) when an OPTIONAL signal is unreachable (`_run_apps` hub note `:330-334`).
2. Import the new symbols from `dhis2w_core.security_core` in the big import block
   (`audit.py:17-77`).
3. Register a no-arg runner in `_RUNNERS: dict[str, Callable[[Dhis2Client],
   Awaitable[CheckResult]]]` (`audit.py:395-402`): add `"<key>": _run_<key>`.
   `_bind` (`audit.py:713-721`) wraps it into the zero-arg coroutine `BoundCheck.run`
   expects; the `else` branch of `_bound_checks` (`audit.py:755-779`, `:777`) handles
   plain runners automatically. A check that needs an extra tunable (audit-config's
   `--dhis-conf`) gets a dedicated `_bind_<key>(...)` closure factory (model after
   `_bind_hygiene:733-741`, `_bind_sharing:744-752`) and a branch in `_bound_checks`.

The same edit lands in all three trees (the three-tree rule). `run_security_audit`
(`audit.py:826-880`) resolves keys, opens ONE client, builds the manifest, and
calls `_bound_checks`.

### 2.3 Registry edit

`registry.py` needs ONE edit per newly-implemented check: add the key string to
`IMPLEMENTED_CHECK_KEYS: frozenset[str]` (`registry.py:43-45`, today
`{"version","settings","authorities","credential-probe","roles","hygiene","apps","guest","sharing"}`).
The `CheckSpec` rows for `"transport"` (`:27`), `"settings"` (`:28`),
`"auth-methods"` (`:36`), `"tokens"` (`:37`), `"routes"` (`:38`), and
`"audit-config"` (`:39`) ALREADY exist in `CANONICAL_CHECKS` in canonical running
order, so PR 8 adds NO `CANONICAL_CHECKS` rows -- it only flips the implemented
set. `"settings"` is already implemented (shipped PR 1), so the settings-verdict
EXTENSION needs NO registry edit.

CRITICAL: the guard test `test_security_audit_guards.py:41-52` hard-codes the
expected default-run order from `resolve_check_keys()`. Adding to
`IMPLEMENTED_CHECK_KEYS` REQUIRES updating that assertion list in the same PR.
`resolve_check_keys()` returns implemented keys in CANONICAL_CHECKS order, and
`transport` is declared 2nd in CANONICAL_CHECKS (`registry.py:27`, right after
`version`). So flipping `transport` into the implemented set inserts it at
position 2 and shifts every later index by one -- it is NOT appended. The shipped
assertion is `version, settings, authorities, roles, hygiene, credential-probe,
guest, apps, sharing`. After PR 8a adds `transport`, the new assertion list is
exactly: `version, transport, settings, authorities, roles, hygiene,
credential-probe, guest, apps, sharing`. Each later sub-PR inserts its keys at
their canonical positions too (auth-methods, tokens, routes, audit-config land
after sharing).

### 2.4 _wire.py only where versions diverge

`dhis2w_core/v{41,42,43}/plugins/security/_wire.py` is the ONLY per-tree file
that legitimately diverges by content (audit.py/cli.py/service.py differ only in
import paths). It exports module-level constants and tiny pure extractors, NOT
classes -- the 2FA case is the worked example (v41 `_wire.py:10-22` reads the
inline `twoFactorEnabled`; v42/v43 `_wire.py:14-26` return None and cite
BUGS.md #58). The reducer in `security_core` stays version-blind; only the
extraction lives per tree. For PR 8, `_wire.py` gains members ONLY for
`auth-methods` (the OAuth2 client wire split) and `tokens` (the v41 ApiToken
shape split) and `routes` (the auth-union split). `transport`, `audit-config`,
and `settings-extensions` need NO `_wire.py` change.

### 2.5 One parametrised test per check

Tests live ONCE at `packages/dhis2w-core/tests/security/`, parametrised over the
three trees -- never per-tree copies. File naming `test_security_<check>.py`.
Each file has two sections: version-invariant reducer tests (call
`evaluate_<check>` directly with hand-built typed inputs, no client/respx/parametrize),
and per-tree wiring tests (`TREES = ("v41","v42","v43")`, a `_audit_module(tree)`
helper, `@pytest.mark.parametrize("tree", TREES)`, mocking via a typed-client
MagicMock or `@respx.mock`). Model after `test_security_apps.py` and
`test_security_guest.py`.

## 3. Per-check sections

Severity is the ceiling. The runtime `Severity` enum is CRITICAL/HIGH/MEDIUM/WARN/INFO
with NO LOW member, so every "LOW" signal below maps to `Severity.WARN`.

---

### 3.1 transport

The transport check inspects TLS posture and HTTP security headers DHIS2 (or its
reverse proxy) returns on the wire, because credential confidentiality and
clickjacking/MIME-sniffing defences are decided at the transport edge, not in
metadata. It reads the base-URL scheme from `client.base_url` and the response
headers from a single GET against `/api/system/info` -- already in `GET_ALLOWLIST`
(`guardrails.py:48`) and `CONNECT_PATHS` (`guardrails.py:88`). It adds NO new
endpoint and NO new allowlist path. The check reads the response headers via
`client.get_response("/api/system/info")` (`client.py:444`), the no-raise GET
escape hatch that returns the raw `httpx.Response` -- headers, status, and body
all inspectable -- while still applying the audited auth header and base-URL
machinery. The docstring already names "you need the raw `Content-Type` (SSO /
proxy-page detection)" as a sanctioned use, so reading security headers off the
same response is the idiomatic path.

**Endpoints + wire fields.** GET `/api/system/info`. Response headers only:
`strict-transport-security`, `content-security-policy`, `x-frame-options`,
`x-content-type-options`, `server`; plus the URL scheme from `client.base_url`.
No response body fields are read.

**Models.** No generated model fits (grep of `generated/v{41,42,43}/oas` and
`/schemas` found only `api_headers_auth_scheme.py` and `grid_header.py`, both
unrelated). NEW plugin-internal frozen view-model in `security_core/transport.py`:

- `TransportHeaders` -- frozen BaseModel, fields `scheme: str`,
  `strict_transport_security: str | None`, `content_security_policy: str | None`,
  `x_frame_options: str | None`, `x_content_type_options: str | None`,
  `server: str | None`. Mirrors `guest.AnonymousResult`. Exported from
  `security_core/__init__.py` + `__all__`.
- `TransportProbe` (optional) -- frozen BaseModel `reachable: bool`,
  `status_code: int | None`, `headers: TransportHeaders | None`, `error: str | None`,
  to keep the transport-error degraded path typed like `AnonymousResult.status_code=None`.
  Fold into `_run_transport` if it does not earn its keep.

The `httpx.Response.headers` returned by `client.get_response` are wrapped into
`TransportHeaders` inside `_run_transport` and never leave it as a dict (rule 7).

**Findings.**

| signal | severity | condition | detail |
|--------|----------|-----------|--------|
| Base URL uses http:// (non-TLS) | HIGH | resolved canonical base URL scheme != https | Plaintext HTTP at `{base_url}`; every request carries the operator's credentials and all metadata in clear text. Terminate TLS in front of DHIS2 and serve only https. |
| HTTPS but no HSTS | MEDIUM | scheme is https AND no `strict-transport-security` header | HTTPS endpoint returns no Strict-Transport-Security header, leaving an SSL-strip / downgrade window. DHIS2 emits HSTS via Spring Security only when the request reaches the app as secure; a TLS-terminating proxy that forwards plain HTTP commonly suppresses it. Set HSTS at the proxy or forward the secure flag. |
| No Content-Security-Policy | MEDIUM | no `content-security-policy` header | On a default DHIS2 (csp.enabled=on) the CspFilter always emits at least `frame-ancestors 'self';`. Absence means CSP was disabled in dhis.conf (csp.enabled=off) or stripped upstream. The header on the wire is the SOLE evidence -- there is no `keyCspEnabled` system setting. |
| No anti-framing (no X-Frame-Options and no CSP frame-ancestors) | WARN | neither `x-frame-options` NOR a `content-security-policy` containing `frame-ancestors` | DHIS2 supplies one or the other (CSP frame-ancestors when csp.enabled=on, X-Frame-Options SAMEORIGIN when off); both missing points at upstream stripping. Suppressed when CSP frame-ancestors is present, to avoid a guaranteed false positive on default instances. |
| No X-Content-Type-Options: nosniff | WARN | no `x-content-type-options` header, or value not `nosniff` (case-insensitive) | Browsers may MIME-sniff. DHIS2 sets this unconditionally via Spring Security, so absence indicates upstream stripping. |
| Server header version disclosure | WARN | `server` header value contains a version token (digit run, or Apache/nginx/Jetty/Tomcat with a version) | The Server header reveals server software and version (`{server_value}`), a free fingerprint for CVE matching. Emitted by the container or proxy, not DHIS2 code; genericize it at the proxy. A bare token (just `nginx`) is INFO-or-suppressed. |

**GET_ALLOWLIST additions.** None. `/api/system/info` is already allowlisted.

**Version divergence + _wire.py.** No wire divergence. The DHIS2 header-setting
code is version-uniform (`DhisWebApiWebSecurityConfig.setHttpHeaders` enables
contentTypeOptions + xssProtection + httpStrictTransportSecurity identically;
`CspFilter` emits CSP frame-ancestors or X-Frame-Options identically in all three).
NO `_wire.py` needed. The only per-tree footprint is the mechanical `_run_transport`
runner + `_RUNNERS` entry in each of v41/v42/v43 audit.py (three identical edits).

**Ground-truth notes (confirmed from the DHIS2 source).**

- `CspFilter.java`: when CSP enabled (default) adds `Content-Security-Policy:
  frame-ancestors 'self';` on every response; when DISABLED adds
  `X-Frame-Options: SAMEORIGIN` instead.
- CSP is governed by `ConfigurationKey.CSP_ENABLED('csp.enabled', Constants.ON,
  confidential=true)` -- a dhis.conf key, default ON, confidential. There is NO
  `keyCspEnabled` system setting anywhere (grep returned nothing).
  `DefaultDhisConfigurationProvider.getConfigurationsAsMap` masks every confidential
  key to `""`, so csp.enabled is never observable via any exposed config -- the
  only evidence of CSP state is the response header.
- `DhisWebApiWebSecurityConfig.setHttpHeaders` (lines 274-282) sets
  X-Content-Type-Options (nosniff) and X-XSS-Protection unconditionally and HSTS
  via Spring (emits only on secure requests by default); X-Frame-Options is NOT
  set there (only by CspFilter when CSP is off).
- `/api/system/info` is already in `GET_ALLOWLIST` (line 48) and `CONNECT_PATHS`
  (line 88); no allowlist change. The transport check reads the response headers
  via `client.get_response` (`client.py:444`), the no-raise GET escape hatch that
  returns the raw `httpx.Response`, so no separate httpx client is needed.

**Files to add / edit.**

- ADD `packages/dhis2w-core/src/dhis2w_core/security_core/transport.py`
- EDIT `security_core/__init__.py` (export `TransportHeaders` + `evaluate_transport`)
- EDIT `security_core/registry.py` (add `"transport"` to `IMPLEMENTED_CHECK_KEYS`)
- EDIT `v{41,42,43}/plugins/security/audit.py` (the `_run_transport` runner + `_RUNNERS` entry)
- ADD `packages/dhis2w-core/tests/security/test_security_transport.py`
- EDIT `FEATURES.md`, `BUGS.md` (optional entry recording the keyCspEnabled-vs-csp.enabled
  surprise and the HSTS-behind-proxy suppression)

---

### 3.2 auth-methods

The auth-methods check inventories the external login surface: OIDC providers on
the pre-auth login page (GET `/api/loginConfig`) and registered OAuth2 clients
DHIS2 acts as authorization server for (GET `/api/oAuth2Clients`). Each provider
is a federated trust path; an OAuth2 client with a broad grant type or a loose
redirect URI is a token-theft vector. It is read-only: two GETs, never a login
attempt, never reading secrets.

**Endpoints + wire fields.**

- GET `/api/loginConfig` -- `oidcProviders[]` (each: `id`, `loginText`, `url`,
  `icon`, `iconPadding`), `selfRegistrationEnabled`, `allowAccountRecovery`,
  `emailConfigured`. PermitAll / pre-auth on all majors. SAML providers are NOT
  surfaced here -- describe the signal as OIDC providers, not OIDC/SAML.
- GET `/api/oAuth2Clients` -- DIVERGENT (see below). v41: `data[].{cid,
  grantTypes:list[str], redirectUris:list[str], secret, displayName}`;
  v42/v43: `oAuth2Clients[].{clientId, authorizationGrantTypes:comma-string,
  redirectUris:comma-string, clientSecret, scopes:comma-string, displayName}`.

**Models to reuse vs new.** PR 8 reads each endpoint via the client `get_raw`
escape hatch and IMMEDIATELY wraps into a NAMED Pydantic view-model in
`security_core` (rule 7); there is NO typed client accessor for these endpoints.

REUSE (verified generated classes):

- `LoginConfigResponse` -- `dhis2w_client.generated.v{41,42,43}.oas.login_config_response.LoginConfigResponse`.
  Exact wire model for `/api/loginConfig`, has `oidcProviders: list[LoginOidcProvider]`.
  `extra=allow`. v42/v43 byte-identical; v41 omits min/maxPasswordLength (not read here).
- `LoginOidcProvider` -- `dhis2w_client.generated.v{41,42,43}.oas.login_oidc_provider.LoginOidcProvider`.
  Uniform across all three trees.
- `OAuth2Client` -- `dhis2w_client.generated.v41.oas.o_auth2_client.OAuth2Client`,
  reuse ONLY in the v41 tree (list-typed `grantTypes`/`redirectUris`, `secret`, `cid`).

NEW (the three-tree gap -- BUGS.md REQUIRED): the generated `Dhis2OAuth2Client`
(`dhis2w_client.generated.v{42,43}.oas.dhis2_o_auth2_client.Dhis2OAuth2Client`,
string-typed `authorizationGrantTypes`/`redirectUris`/`scopes`, `clientSecret`,
`clientId`) exists ONLY for v42/v43, and the array-typed `OAuth2Client` exists
ONLY for v41. There is no version-invariant generated OAuth2-client model.
So auth-methods reads `/api/oAuth2Clients` via `get_raw` and each per-tree
`_wire.py` projects its own generated class into ONE hand-rolled version-invariant
view-model in `security_core/auth_methods.py`, with a REQUIRED BUGS.md entry
(cross-referencing #39) explaining the absent v42/v43 array schema / the absent
v41 string schema:

- `OAuth2ClientView` -- frozen BaseModel: `identifier: str` (clientId on v42/v43,
  cid on v41), `display_name: str | None`, `grant_types: frozenset[str]`
  (normalized lowercase), `redirect_uris: tuple[str, ...]`. Deliberately omits
  `secret`/`clientSecret` so the audit can NEVER carry a secret into a finding.
- `LoginProviderView` (optional) -- frozen BaseModel `provider_id: str`,
  `login_text: str | None`. Skip if the evaluator can accept `list[LoginOidcProvider]`
  directly (it is uniform and already a BaseModel); decide at implementation time.

**Findings.**

| signal | severity | condition | detail |
|--------|----------|-----------|--------|
| configured-oidc-provider | INFO | `/api/loginConfig` returns one or more `oidcProviders[]` | Per provider: external login provider configured (`loginText`/`id`); the login page trusts this OIDC IdP. Verify it is intentional. subject=provider id. |
| registered-oauth2-client | INFO | `/api/oAuth2Clients` returns one or more clients | Per clean client: DHIS2 acts as authorization server for it. subject=client id, evidence={client, grant_types, redirect_uris}. Suppressed when the same client triggers a MEDIUM below. |
| oauth2-client-broad-grant | MEDIUM | normalized grant set includes any of `client_credentials`, `implicit`, `password`, `urn:ietf:params:oauth:grant-type:device_code` | High-risk grant on client `<id>`. On v42/v43 the server rejects these on create, so a client carrying one was imported/seeded around REST validation. group_key=oauth2-broad-grant. |
| oauth2-client-wildcard-redirect | MEDIUM | a redirect URI contains `*`, or a non-loopback cleartext `http://` scheme (loopback http://localhost / 127.0.0.1 not flagged, RFC 8252) | Loose redirect target on client `<id>` enables authorization-code interception via open redirect. group_key=oauth2-wildcard-redirect. |
| oauth2-clients-unreadable | INFO (note) | `/api/oAuth2Clients` returns 401/403 (lacks F_OAUTH2_CLIENT_MANAGE) or transport error | Not a finding row; the check returns `CheckStatus.DEGRADED` with a note. The loginConfig half still runs and produces its INFO findings. 401/403 never retried. |

**GET_ALLOWLIST additions (reviewed changes).** `/api/loginConfig`,
`/api/oAuth2Clients`. Each gets an inline justifying comment in `guardrails.py`
modelled on the 2FA-endpoint comment style at `guardrails.py:53`.

**Version divergence + _wire.py.** Two divergences. (1) `LoginConfigResponse`:
v42/v43 byte-identical; v41 omits fields not read here, and oidcProviders is
uniform -- NO per-tree branch for loginConfig. (2) OAuth2 client list: STRONGLY
divergent and the reason this check needs `_wire.py` members. Add
`OAUTH2_CLIENT_FIELDS` + `oauth2_clients(raw) -> list[OAuth2ClientView]`,
`grant_types(client) -> set[str]`, `redirect_uris(client) -> list[str]` to each
`_wire.py`: v41 reads list fields + `cid` + `data` envelope; v42/v43 read
comma-string fields + `clientId` + `oAuth2Clients` envelope. The
`security_core/auth_methods.py` reducer stays version-agnostic and consumes
`OAuth2ClientView`. NEVER include the secret value in any finding or evidence.

**Ground-truth notes.**

- `LoginConfigController` `@RequestMapping(/api/loginConfig)`; oidcProviders built
  from registrations filtered by `isVisibleOnLoginPage()`. SAML not included.
- `DhisWebApiWebSecurityConfig`: `/api/loginConfig` is `permitAll` (pre-auth, by
  design for the login page).
- `OAuth2ClientController` `@RequestMapping(/api/oAuth2Clients)`
  `@RequiresAuthority(F_OAUTH2_CLIENT_MANAGE)`; list hides the SYSTEM_REGISTRAR
  DCR client. `OAuth2ClientSchemaDescriptor` READ authority = F_OAUTH2_CLIENT_MANAGE,
  so list requires that authority on v42/v43.
- `Dhis2OAuth2ClientServiceImpl.validateGrantTypes`: only authorization_code +
  refresh_token allowed on create; client_credentials rejected 409 E4000;
  custom-scheme redirect URIs must be on `deviceEnrollmentRedirectAllowlist`.
- BUGS.md #39 documents the v41 (cid + arrays) vs v42+ (clientId + comma-strings)
  wire divergence. Generated trees confirm: v41 has only `OAuth2Client`; v42/v43
  have only `Dhis2OAuth2Client`.

**Files to add / edit.**

- ADD `security_core/auth_methods.py`
- EDIT `security_core/__init__.py`, `security_core/guardrails.py`,
  `security_core/registry.py` (add `"auth-methods"`)
- EDIT `v{41,42,43}/plugins/security/_wire.py` (the OAuth2 client extractors)
- EDIT `v{41,42,43}/plugins/security/audit.py` (`_run_auth_methods` + `_RUNNERS`)
- ADD `packages/dhis2w-core/tests/security/test_auth_methods.py`
- EDIT `packages/dhis2w-core/tests/security/test_security_guardrails.py`
- EDIT `FEATURES.md`, `BUGS.md` (REQUIRED: the absent v42/v43 array schema /
  absent v41 string schema, cross-referencing #39)

---

### 3.3 tokens

The tokens check inventories Personal Access Tokens via GET `/api/apiToken` and
flags weak posture: non-expiring tokens, missing IP allowlists, and PATs
constrained only by referer/method allowlists. A leaked long-lived PAT is a
standing credential that bypasses interactive login and 2FA.

RESOLVED scope (not an open question): `ApiTokenController` extends
`AbstractCrudController` and the list goes through the ACL-aware
`HibernateIdentifiableObjectStore`, filtered by `createdBy` ownership
(`ApiToken` is `defaultPrivate(true)`). The test
`ApiTokenControllerTest.testListApiTokensNotYours` proves a non-superuser sees
ONLY their own tokens; only an account with ALL (superuser, which bypasses ACL)
gets the system-wide inventory. EVERY token finding is therefore scoped to
"tokens readable by the audited account", and a non-superuser run emits an INFO
caveat that it cannot prove the absence of dangerous PATs. This resolution CLOSES
the open "still to confirm" item in the parent `SECURITY-SCANNER-PLAN.md`
(line ~305: "Whether /api/apiToken enumerates system-wide or only the calling
account") -- caller-only unless superuser -- so the two documents agree.

**Endpoints + wire fields.** GET `/api/apiToken` (alias `/api/apiTokens`),
all three majors. Read `id,name,type,expire,created,lastUpdated,createdBy[id],
attributes[type,allowedIps,allowedMethods,allowedReferrers]`. The runner should
pass an explicit `fields=` param to guarantee `attributes`/`expire` are projected.
The token secret (`key`) is `@JsonIgnore` and never returned over the wire.

**Models to reuse vs new.** No typed client accessor exists; PR 8 reads via
`get_raw` and IMMEDIATELY wraps into named view-models. REUSE generated wire
models inside the per-tree `_wire.py`: `ApiToken`, `IpAllowedList`,
`MethodAllowedList`, `RefererAllowedList` (all in `dhis2w_client.generated.v{41,42,43}.oas`),
and `ApiTokenType` (v42/v43 only -- v41's generated `ApiToken.type` is a
`Literal`, not the enum). The per-tree `_wire.py` absorbs the v41-vs-v42/43 shape
difference and normalizes `type` to a plain str so `security_core` never imports
`ApiTokenType`.

NEW version-invariant view-models in `security_core/tokens.py`:

- `TokenAllowlists` -- frozen, `ips: tuple[str,...]=()`, `methods: tuple[str,...]=()`,
  `referrers: tuple[str,...]=()`. Flattens the polymorphic `attributes` list.
- `TokenView` -- frozen, `id: str`, `name: str | None`, `token_type: str`
  (normalized str), `expire_epoch_millis: int | None`, `created: str | None`,
  `owner_id: str | None`, `allowlists: TokenAllowlists`.
- `TokensInventory` -- frozen, `tokens: tuple[TokenView,...]=()`,
  `account_is_superuser: bool = False`. The ALL flag comes from the
  `/api/me/authorization` data the audit already fetches for the authorities check.

**Findings.**

| signal | severity | condition | detail |
|--------|----------|-----------|--------|
| tokens-inventory | MEDIUM | 200 with at least one readable token | Summary of PATs visible to the audited account: count, per-token type, expiry (or never), IP-allowlist presence, method/referer constraints. The detail MUST state scope: "account-scoped: a non-superuser sees only its own tokens; a full system inventory requires an account with ALL authority." |
| tokens-non-expiring | HIGH | `expire` null/absent, OR an epoch-millis value already in the past (expired-but-not-deleted), within readable scope | A token with no expiry is a permanent credential; if it leaks it grants standing API access until manually revoked. Names the token + type + "expires: never" or the past date. |
| tokens-no-ip-allowlist | HIGH | no `IpAllowedList` attribute, or empty `allowedIps`, within readable scope | Without an IP allowlist the token is usable from anywhere. Pair with non-expiring: a token that never expires AND has no IP allowlist is the worst case -- call that out. |
| tokens-degraded-account-scoped | INFO | 200 but the audited account is NOT a superuser | An INFO caveat (not a vulnerability) that the inventory is account-scoped, so tokens owned by other users are invisible to this scan. |
| tokens-endpoint-unavailable | INFO (note) | `Dhis2ApiError` (401/403/404) -- never retried | Returns `CheckStatus.DEGRADED` with `note="HTTP error: <exc>"`; no synthesised findings. |

**GET_ALLOWLIST additions (reviewed change).** `/api/apiToken`, with an inline
justifying comment.

**Version divergence + _wire.py.** Route and check logic uniform; only the wire
shape diverges. v42/v43 generated `ApiToken` byte-identical (`type` is the enum,
`createdBy`/`lastUpdatedBy` are `UserDto`). v41 differs: `type` is a `Literal`,
`createdBy`/`lastUpdatedBy` are id-only inline classes, plus an extra `user`
ref, and `ApiTokenType` is absent. The `attributes` list and `expire` are
identical across all three. Add `tokens_from_raw(raw) -> list[TokenView]` to each
`_wire.py` (normalizing `type` to str), so `security_core/tokens.py` consumes a
version-neutral `TokenView` and never imports `ApiTokenType`. A `_wire.py` member
IS needed for v41 vs v42/v43. The account-scoped-vs-system-wide distinction is a
RUNTIME authority distinction, not a version one, so it does not drive `_wire`.

**Ground-truth notes.**

- `ApiTokenController` `@RequestMapping({"/api/apiToken","/api/apiTokens"})`
  extends `AbstractCrudController`; the GET list is the inherited standard CRUD
  list, ACL/sharing-filtered by `createdBy`. `testListApiTokensNotYours` returns
  exactly the caller's own tokens.
- `ApiToken`: `key` is `@JsonIgnore` (secret never serialised); `expire` is a
  nullable `Long` (epoch millis); `DEFAULT_TOKEN_EXPIRE = 30 days` is set
  server-side at create if null, so a "never expires" token cannot be made via
  the normal POST path -- but `expire` is still nullable on the model and
  imported/DB-inserted tokens may lack it, so the non-expiring check is valid.
- `ApiTokenAttribute` is a polymorphic base keyed by `type` with three subtypes:
  `IpAllowedList`, `MethodAllowedList`, `RefererAllowedList`. There is NO
  per-token authority subset -- a PAT inherits the full authority set of its
  owning user; the only per-token scoping is the IP/method/referer allowlists.

**Files to add / edit.**

- ADD `security_core/tokens.py`
- EDIT `security_core/__init__.py`, `security_core/guardrails.py`,
  `security_core/registry.py` (add `"tokens"`)
- EDIT `v{41,42,43}/plugins/security/_wire.py` (`tokens_from_raw`)
- EDIT `v{41,42,43}/plugins/security/audit.py` (`_run_tokens` + `_RUNNERS`)
- ADD `packages/dhis2w-core/tests/security/test_security_tokens.py`
- EDIT `packages/dhis2w-core/tests/security/test_security_guardrails.py`
- EDIT `FEATURES.md`, `BUGS.md` (note that `expire` is nullable on the model
  despite the controller default)

---

### 3.4 routes

The routes check inventories DHIS2 Route API objects (GET `/api/routes`, 2.41+)
and flags each route whose destination URL resolves to a private, loopback,
link-local, or cloud-metadata address. A Route is a server-side reverse proxy:
DHIS2 fetches the configured `url` on behalf of the caller and attaches the
configured `auth` block, so an authenticated operator can pivot a route into an
SSRF primitive against the internal network or a cloud metadata endpoint. The
check NEVER executes a route (never `/api/routes/{id}/run`).

This check is fully grounded: `RouteController` at `/api/routes`, the `Route`
model (`url`/`auth`/`headers`) present in all three trees, 2.41+ correct (v41 is
the floor; the scanner already refuses pre-v41).

**Endpoints + wire fields.** GET `/api/routes` (the `AbstractCrudController`
collection, `{pager, routes:[Route]}` envelope). Request
`fields=id,code,name,url,disabled,authorities,auth,headers,responseTimeoutSeconds`,
`paging=false`. Key fields: `url` (required), `auth` (AuthScheme oneOf with
discriminator `type`; secrets WRITE_ONLY, not returned), `headers`, `authorities`,
`disabled`, `code`, `name`, `responseTimeoutSeconds`.

**Models to reuse vs new.** No typed client accessor on the security plugin; PR 8
reads `/api/routes` via `get_raw`. REUSE the generated `Route`
(`dhis2w_client.generated.v{41,42,43}.oas.route.Route`) and the auth-scheme leaves
(`HttpBasicAuthScheme`, `ApiTokenAuthScheme`, `ApiHeadersAuthScheme`,
`ApiQueryParamsAuthScheme`, `OAuth2ClientCredentialsAuthScheme`, re-exported via
`dhis2w_client.v{N}.auth_schemes` as `AuthScheme` + `AuthSchemeAdapter` +
`auth_scheme_from_route`). The security check uses `oas.Route` because its `auth`
field is the typed discriminated `AuthScheme` union, which is what the
auth-extraction relies on. The existing `route` plugin's `_RoutesEnvelope`
(`v{41,42,43}/plugins/route/service.py:43`) is NOT reusable here: it is built on
`generated.v{N}.schemas.Route` (`service.py:23`), whose `auth` is typed `Any`
(`schemas/route.py:30`), so reusing it would throw away the very typing this check
needs. PR 8 therefore declares its OWN transient envelope over `oas.Route` in the
per-tree `_wire.py`/`audit.py`. The raw payload is wrapped immediately into typed
`oas.Route` objects, never crossing a boundary as a dict.

NEW version-invariant view-model in `security_core/routes.py`:

- `RouteTarget` -- frozen, `uid: str | None`, `code: str | None`, `name: str`,
  `url: str`, `host: str | None` (literal host parsed from url; None when
  unparseable), `disabled: bool`, `allows_subpaths: bool`, `auth_type: str | None`
  (the discriminator tag, None when no auth), `auth_identity: str | None`
  (non-secret identity: username / clientId / tokenUri; NEVER a secret),
  `required_authorities: tuple[str,...]`. Carries NO secret field by construction,
  enforcing the redaction contract in the type.
- `_RoutesEnvelope` -- per-tree transient declared by this check (`pager`,
  `routes: list[oas.Route]`). It is NOT the existing `route` plugin's envelope:
  that one types `routes` as `schemas.Route` (`auth: Any`), so PR 8 declares its
  own over `oas.Route` to keep the typed `auth` union.

**Findings.**

| signal | severity | condition | detail |
|--------|----------|-----------|--------|
| route-destination-private-address | HIGH | `url` host is a literal private/internal IP: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16, ::1, fc00::/7, fe80::/10, 0.0.0.0; OR host is `localhost`, ends in `.internal`/`.local`/`.localdomain`, OR is `metadata.google.internal` | Route `{name}` ({code}) proxies to {url}, a private/internal or cloud-metadata host. Any operator authorized to run it makes DHIS2 issue the request from inside the network -- an SSRF primitive. Detection inspects the configured URL host only; the audit never executes the route. |
| route-metadata-endpoint | HIGH | host is specifically 169.254.169.254, the IPv6 metadata address, or `metadata.google.internal` | Route `{name}` targets the cloud instance metadata endpoint; on a misconfigured IMDSv1 host this exposes temporary IAM/role credentials. The highest-value SSRF target. |
| route-allows-subpaths | MEDIUM | `url` ends with `/**` (Route.PATH_WILDCARD_SUFFIX) | Callers can append arbitrary paths, widening the upstream URLs DHIS2 can be made to fetch; combined with a private base host this increases SSRF reach. |
| route-carries-auth | INFO | `auth` block non-null (any scheme) | Route stores upstream credentials server-side (auth type `{auth_type}`) that DHIS2 attaches when proxying. The secret is WRITE_ONLY and not exposed; identity shown for context. |
| route-no-required-authorities | MEDIUM | `authorities` empty/absent AND not disabled | Run access falls back to ACL canRead (sharing); if broadly shared, a wide set of users can drive a possibly-SSRF-capable destination. Pair with the sharing check. |
| route-inventory | INFO | always on successful read | N routes registered (active vs disabled). Each route is a server-side reverse proxy DHIS2 can be made to call. |

**GET_ALLOWLIST additions (reviewed change).** `/api/routes`, with an inline
justifying comment.

**Version divergence + _wire.py.** All three trees implement it. The endpoint
path and the fields the check reads (`url`, `disabled`, `headers`, `authorities`,
`code`, `name`) are identical, so the private-address detection and the other
findings live ONCE in `security_core/routes.py` over `RouteTarget`. The ONE
genuine wire divergence is the auth union: generated v41 `oas.Route.auth` is an
UNDISCRIMINATED 4-variant union (no oauth2-client-credentials, no
`Field(discriminator)`); v42/v43 is the 5-variant discriminated union. A `_wire.py`
extractor isolates this: each tree turns the raw route's auth into `auth_type` +
non-secret identity using that tree's `auth_scheme_from_route`/`AuthSchemeAdapter`,
so v41 never references the OAuth2 variant. `_wire.py` IS needed (extends the
existing per-tree `_wire.py`). Cite BUGS.md #14 in the v41 `_wire` docstring
rather than opening a new entry (#14 already documents the divergence).

**Ground-truth notes.**

- `Route.java`: fields `disabled` (required), `url` (required), `headers`
  (required, default empty), `auth` (optional), `authorities` (optional, default
  empty), `responseTimeoutSeconds` (default 5). `PATH_WILDCARD_SUFFIX="/**"`;
  `allowsSubpaths()` = `url.endsWith("/**")`.
- `RouteController` `@RequestMapping("/api/routes")` extends
  `AbstractCrudController`; GET is the standard collection listing. Run
  authorization: `aclService.canRead(user, route)` OR
  `currentUser.hasAnyAuthority(route.getAuthorities())`.
- SECRET REDACTION CONFIRMED: every secret-bearing auth field is
  `@JsonProperty(access = WRITE_ONLY)` so it is NEVER serialized in GET responses
  (`HttpBasicAuthScheme.password`, `ApiTokenAuthScheme.token`, the api-headers /
  api-query-params maps, `OAuth2ClientCredentialsAuthScheme.clientSecret`).
  Non-secret returned fields: `type`, `username`, `clientId`/`tokenUri`/`scopes`.
  Secrets are also PBE-encrypted at rest. The check cannot and must not read them.
- `/api/routes` is NOT currently in `GET_ALLOWLIST` -- it must be added.

**Files to add / edit.**

- ADD `security_core/routes.py`
- EDIT `security_core/__init__.py`, `security_core/guardrails.py`,
  `security_core/registry.py` (add `"routes"`)
- EDIT `v{41,42,43}/plugins/security/_wire.py` (the auth-union extractor)
- EDIT `v{41,42,43}/plugins/security/audit.py` (`_run_routes` + `_RUNNERS`)
- ADD `packages/dhis2w-core/tests/security/test_security_routes.py`
- EDIT `packages/dhis2w-core/tests/security/test_security_guardrails.py`
- EDIT `FEATURES.md`, `BUGS.md`

---

### 3.5 audit-config

The audit-config check reports the DHIS2 auditing posture. Ground truth: the
entire audit configuration (logger, database sink, the four scope matrices, the
system-wide enable flag) lives ONLY in dhis.conf via `ConfigurationKey.java`;
none of it is a system setting, none is exposed on `/api/configuration` or
`/api/system/info`. There is nothing audit-related to read over the API. The
check therefore reports "audit posture is not exposed via the DHIS2 API" as its
API-first result (NEVER "auditing is off"), and an optional `--dhis-conf PATH`
parses ONLY the audit.* keys to report each channel on/off, with mandatory
secret redaction enforced by construction.

**Endpoints + wire fields.** GET `/api/system/info` (optional reachability /
report header version only; carries NO audit data). The check needs no per-check
API read because audit posture is not API-exposed.

**Models to reuse vs new.** No generated OAS model covers dhis.conf (it is not an
API resource). The dhis.conf is parsed into Pydantic models in
`security_core/dhisconf.py` whose ONLY fields are the audit keys plus a set/not-set
enum for credential keys -- the models CANNOT physically hold a secret value:

- `AuditChannel` -- frozen, `name: str` (the audit.* key), `enabled: bool`,
  `raw_value: str | None` (on/off/matrix string for NON-secret audit keys ONLY).
- `AuditScopeMatrix` -- frozen, `scope: str` (METADATA/AGGREGATE/TRACKER/API),
  `configured: bool`, `audit_types: tuple[str,...]` (subset of
  CREATE/READ/UPDATE/DELETE/SEARCH/SECURITY).
- `RedactedSecret` -- frozen, `key: str`, `is_set: bool`. NO value field by
  construction; a secret value is unrepresentable through this model.
- `AuditPosture` -- frozen, `system_enabled: bool | None`, `logger_enabled: bool`,
  `database_enabled: bool`, `in_memory_queue_enabled: bool`,
  `changelog_aggregate_enabled: bool`, `scopes: tuple[AuditScopeMatrix,...]`,
  `secrets: tuple[RedactedSecret,...]`, `source_path: str | None`, `parsed: bool`.
  `parsed=False` is the API-first / unreadable case driving the INFO note.

The audit key set is: `audit.logger`, `audit.database`, `audit.metadata`,
`audit.tracker`, `audit.aggregate`, PLUS `audit.api` (AUDIT_API_MATRIX) and the
master switch `system.audit.enabled` (AUDIT_ENABLED).

**Findings.**

| signal | severity | condition | detail |
|--------|----------|-----------|--------|
| audit-system-disabled | MEDIUM | `system.audit.enabled` equals `off` (case-insensitive; default is ON) | Auditing is disabled instance-wide regardless of the per-scope matrices. No CREATE/UPDATE/DELETE/READ/SECURITY events are recorded; no forensic trail. |
| audit-logger-and-database-both-off | MEDIUM | `audit.logger=off` (default ON) AND `audit.database=off` (default OFF) | Both sinks off; audit events have nowhere to land. Enable at least the file logger or the database sink. |
| audit-scope-matrix-empty | MEDIUM | every matrix (`audit.metadata`/`audit.aggregate`/`audit.tracker`/`audit.api`) blank while `system.audit.enabled` is on | No AuditScope x AuditType pairs are captured even though auditing is enabled. Auditing is a no-op until a matrix is set. |
| audit-scope-narrowly-scoped | MEDIUM | auditing enabled but only a subset of scopes has a matrix, or a matrix omits CREATE/UPDATE/DELETE/SECURITY | Report which scopes are unmonitored. Narrow scoping leaves changes in unaudited scopes without a trail. |
| audit-config-api-only | INFO | `--dhis-conf` NOT supplied (the API-first path) | DHIS2 does not expose its audit configuration over the API; the audit.* keys live only in dhis.conf. Re-run with `--dhis-conf <path>` on the server host. Stated as "not API-readable", NOT "auditing is off". |
| dhis-conf-unreadable | INFO (note) | `--dhis-conf` supplied but path missing/unreadable/unparseable | A degraded note on the check, not a finding about the instance. |

**GET_ALLOWLIST additions.** None. API-readable settings stay inside
`/api/systemSettings` (already allowlisted) and `/api/system/info` is already
allowlisted; the dhis.conf read is a local-file read, not an HTTP path.

**audit-config dhis.conf secret-redaction contract.** Redaction is enforced by
CONSTRUCTION, not discipline. `dhisconf.py` parses the Java `.properties` file
into the Pydantic models above whose only fields are the audit keys plus
`RedactedSecret(key, is_set)` for credential keys -- so the model physically
cannot hold a secret value. Non-audit, non-credential keys are not represented at
all. The confidential keys reported as set/not-set (never echoed):
`encryption.password`, `connection.password`, `analytics.connection.password`,
`ldap.manager.password`, `redis.password`, `artemis.password`,
`oauth2.server.jwt.keystore.password`, `oauth2.server.jwt.keystore.key-password`,
`system.monitoring.password`. The contract is tested with a NEGATIVE test: feed a
dhis.conf containing a known password and assert that string never appears in any
rendered format (md/txt/csv/html/json). The scanner does NOT read the server's
filesystem; `--dhis-conf` takes an explicit local path the operator points at a
copy of dhis.conf.

**Version divergence + _wire.py.** None. The AUDIT_* `ConfigurationKey` entries,
their dhis.conf key strings, and their defaults are identical across v41/v42/v43
(the source enum is shared). Because the audit posture is not API-readable in ANY
version, there is no per-version wire extraction -- NO `_wire.py` change. The
dhis.conf parser and key set are version-invariant in `security_core/dhisconf.py`.
The per-tree audit.py edit is a mechanical three-way copy (add `_run_audit_config`
to `_RUNNERS`, thread the optional `dhis_conf_path` through `run_security_audit`
and a `_bind_audit_config` closure, and add the CLI `--dhis-conf` flag). The CLI
edit lands in all three `cli.py` (identical except import paths).

**Ground-truth notes.**

- `ConfigurationKey.java` (dhis.conf-only): AUDIT_LOGGER `audit.logger` default
  ON; AUDIT_DATABASE `audit.database` default OFF; AUDIT_METADATA_MATRIX
  `audit.metadata` default ''; AUDIT_AGGREGATE_MATRIX `audit.aggregate` default
  ''; AUDIT_TRACKER_MATRIX `audit.tracker` default ''; AUDIT_API_MATRIX
  `audit.api` default ''; AUDIT_ENABLED `system.audit.enabled` default ON;
  AUDIT_USE_IN_MEMORY_QUEUE_ENABLED default OFF; CHANGELOG_AGGREGATE
  `changelog.aggregate` default ON.
- Enums: `AuditScope` = {METADATA, AGGREGATE, TRACKER, API}; `AuditType` =
  {CREATE, READ, UPDATE, DELETE, SEARCH, SECURITY}.
- `/api/configuration` exposes only systemId / feedbackRecipients / etc -- NO
  audit.* keys. `/api/systemSettings` filters @Confidential keys server-side.
  `/api/system/info` has no audit field. The audit posture is genuinely not
  API-readable.
- The generated OAS `AuditOperationType` / `DataValueAuditDto` are about reading
  audit DATA VALUES, which the guardrail forbids; they are NOT the config posture
  and are NOT reused.
- `registry.py` `CANONICAL_CHECKS` already contains the `audit-config` row; it
  must be added to `IMPLEMENTED_CHECK_KEYS`.

**Files to add / edit.**

- ADD `security_core/dhisconf.py`, `security_core/audit_config.py`
- EDIT `security_core/__init__.py`, `security_core/registry.py` (add `"audit-config"`)
- EDIT `v{41,42,43}/plugins/security/audit.py` (`_run_audit_config`, `_bind_audit_config`,
  thread `dhis_conf_path`)
- EDIT `v{41,42,43}/plugins/security/cli.py` (the `--dhis-conf` Typer Option)
- ADD `packages/dhis2w-core/tests/security/test_security_audit_config.py`
- ADD `packages/dhis2w-core/tests/security/test_security_dhisconf_redaction.py` (the negative test)
- EDIT `FEATURES.md`, `BUGS.md`

---

### 3.6 settings-extensions

PR 8 extends the existing `settings` check (the `evaluate_settings` reducer in
`security_core/settings_audit.py`, fed by the per-tree `SecuritySettings`
projection of `/api/systemSettings` through the `SettingsLike` Protocol). The
reducer today emits four verdicts: weak `minPasswordLength` (MEDIUM, `:33`),
failed-login lockout disabled (MEDIUM, `:44`), passwords-never-expire (WARN,
`:54`), and self-registration captcha disabled (MEDIUM, `:64`). PR 8 adds
privilege-escalation and account-policy verdicts. `"settings"` is already in
`IMPLEMENTED_CHECK_KEYS`, so this needs NO registry edit.

The hard constraint from the DHIS2 source: two proposed verdicts are NOT backed
by system settings, and one has no source at all.

**Endpoints + wire fields.**

- GET `/api/systemSettings` (already allowlisted) -- `minPasswordLength`,
  `credentialsExpires`, `keyLockMultipleFailedLogins`,
  `keyCanGrantOwnUserAuthorityGroups`, `keyAccountRecovery`, `enforceVerifiedEmail`,
  `keyEmailHostName`, `keyEmailUsername`. v41 has no generated SystemSettings OAS
  but all three keep the hand-rolled `SecuritySettings` projection, so this does
  not affect the plan.
- GET `/api/configuration/corsWhitelist` -- the ONLY source for the permissive-CORS
  verdict. Returns a bare JSON array of origin strings. The `keyCorsWhitelist`
  system setting was removed in v2.31, so the settings endpoint cannot answer this.
  GET has no `@RequiresAuthority` (readable by any authenticated user).

**Models to reuse vs new.** REUSE `AuditFinding` and `Severity`
(`security_core.findings`) and the per-tree `SecuritySettings`
(`dhis2w_core.v{41,42,43}.plugins.security.models`). The `SettingsLike` Protocol
(`settings_audit.py:15-26`) today declares only FOUR fields -- `minPasswordLength`,
`credentialsExpires`, `keyLockMultipleFailedLogins`, `keySelfRegistrationNoRecaptcha`.
The email and self-grant verdicts read fields the Protocol does not yet expose, so
PR 8 WIDENS `SettingsLike` with five fields:
`keyCanGrantOwnUserAuthorityGroups`, `keyAccountRecovery`, `enforceVerifiedEmail`,
`keyEmailHostName`, `keyEmailUsername`. Two of these (`keyAccountRecovery`,
`enforceVerifiedEmail`) already exist on the per-tree `SecuritySettings` model
(v42 `models.py:29,32`), so the model only gains the remaining three
(`keyCanGrantOwnUserAuthorityGroups`, `keyEmailHostName`, `keyEmailUsername`)
across all three trees; the Protocol gains all five, because the Protocol is the
version-agnostic surface `evaluate_settings` reads through.

CORS is read separately. No typed client accessor exists; PR 8 reads
`/api/configuration/corsWhitelist` via `get_raw` and IMMEDIATELY wraps into a
NAMED view-model in `security_core` (the client wraps non-dict bodies under a
`data` key, same as `/api/me/authorization`, so the fetch unwraps `raw["data"]`
-> `list[str]`):

- `CorsWhitelist` -- frozen, `origins: tuple[str,...]`, with a `has_wildcard`
  property checking for `"*"`. Lives in `security_core` (shared; the wire shape is
  uniform across v41/v42/v43).

**Findings (NET-NEW only; the four shipped verdicts are unchanged).**

| signal | severity | condition | detail |
|--------|----------|-----------|--------|
| keyCanGrantOwnUserAuthorityGroups | HIGH | `settings.keyCanGrantOwnUserAuthorityGroups is True` | Users can grant themselves authorities they already hold -- a direct privilege-escalation path. NOT @Confidential, API-readable on all three. Add the field to the projection + Protocol. Version-uniform; verdict in `evaluate_settings`. |
| corsWhitelist contains wildcard | MEDIUM | `"*"` present in the `/api/configuration/corsWhitelist` array | A `*` origin lets any site make credentialed cross-origin API calls. Config-sourced (NOT settings-sourced); requires the new allowlist entry and the `CorsWhitelist` wrapper. |
| global 2FA enforcement | INFO | always (no global enforcement key exists) | 2FA is per-user/per-role only (via the TWO_FACTOR_AUTH_REQUIRED restriction); no global enforce-2FA system setting exists in any version. Emitted at INFO, not MEDIUM: it is an always-true fact about DHIS2 rather than a per-instance misconfiguration, so a MEDIUM here would floor every audit's worst-severity at MEDIUM and inflate the MEDIUM count on clean instances (the same INFO tier `versions.py` uses for "version not exposed"). Cross-references the hygiene check for actual per-account enrolment gaps. Must NOT read a non-existent key. |
| email not configured while recovery / verification on | WARN (the LOW tier) | (`keyAccountRecovery` True OR `enforceVerifiedEmail` True) AND `keyEmailHostName`/`keyEmailUsername` blank | When recovery or email-verification is on but SMTP is unconfigured, recovery/verification silently fails. `isEmailConfigured()` = host non-blank AND username non-blank. Add `keyEmailHostName`/`keyEmailUsername` to the projection + Protocol. The task says LOW; the enum has no LOW, so emit WARN. |

DROP from PR 8: the unique-email verdict. There is NO system-setting key and NO
dhis.conf key for email uniqueness in any version. It is not implementable from
any read surface. Either drop it entirely or downgrade to a one-line INFO note
that DHIS2 does not enforce email uniqueness. Recommend dropping.

**GET_ALLOWLIST additions (reviewed change).** `/api/configuration/corsWhitelist`,
with an inline justifying comment. The `/api/systemSettings` base read adds none.

**Version divergence + _wire.py.** The system-setting-backed verdicts
(keyCanGrantOwnUserAuthorityGroups, email) are uniform across v41/v42/v43: the
`/api/systemSettings` wire shape, keys, and defaults match, and the verdicts read
through the version-agnostic `SettingsLike` Protocol, so the verdict logic stays
in shared `security_core` with NO `_wire.py` -- only the three `SecuritySettings`
models gain the new fields identically. The CORS verdict reads a different
endpoint returning a uniform bare array, so it also needs NO `_wire.py` -- a
single shared `CorsWhitelist` wrapper plus identical per-tree fetch wiring. The
only genuine version split is the 2FA enrolment-summary enrichment:
`/api/users/twoFactor/summary` is v42/v43 (master-pending-backport for v41) and
superuser-only, so the 2FA verdict degrades to the static per-user/per-role
message on v41 or on 403, isolated as a try/except in each per-tree audit.py
rather than a `_wire.py`. NO `_wire.py` is required for the settings extension.

**Ground-truth notes.**

- `SystemSettings.java` confirmed keys/defaults: `minPasswordLength=8`,
  `credentialsExpires=0`, `keyLockMultipleFailedLogins=false`,
  `keyCanGrantOwnUserAuthorityGroups=false` (getter `getCanGrantOwnUserRoles`,
  NOT @Confidential -> API-readable), `keyAccountRecovery=false`,
  `enforceVerifiedEmail=false`, `keyEmailHostName=""`, `keyEmailUsername=""`.
  `isEmailConfigured()` = host non-blank AND username non-blank.
- CORS: `keyCorsWhitelist` was DELETED from systemsetting in migration V2_31_1;
  CORS lives in `Configuration.corsWhitelist`, served by `ConfigurationController`
  `@RequestMapping("/api/configuration")` GET `{"/corsWhitelist","/corsAllowlist"}`
  returning `Set<String>`; GET has no `@RequiresAuthority`.
- 2FA enforcement: no system-setting key;
  `TwoFactorAuthenticationProvider.checkTwoFactorEnrolment` uses a per-user-role
  restriction. `/api/users/twoFactor/summary` is `@RequiresAuthority(ALL)`
  (superuser only).
- No `uniqueEmail`/`requireUniqueEmail` key exists in `SystemSettings.java` or
  `ConfigurationKey.java`.

**Files to add / edit.**

- EDIT `security_core/settings_audit.py` (new verdict branches + Protocol fields),
  `security_core/guardrails.py` (add `/api/configuration/corsWhitelist`),
  `security_core/__init__.py` (export `CorsWhitelist`)
- ADD `CorsWhitelist` (in `settings_audit.py` or a small `security_core` module)
- EDIT `v{41,42,43}/plugins/security/models.py` (new `SecuritySettings` fields),
  `v{41,42,43}/plugins/security/audit.py` (CORS fetch + 2FA-summary enrichment)
- ADD `packages/dhis2w-core/tests/security/test_security_settings.py` (the MISSING
  version-invariant `evaluate_settings` coverage -- today only the CLI render
  test exists)
- EDIT `packages/dhis2w-core/tests/security/test_security_guardrails.py`
- EDIT `FEATURES.md`, `BUGS.md`

## 4. Guardrail + allowlist changes

This is the reviewed-change summary for the PR description. Every `GET_ALLOWLIST`
addition in `security_core/guardrails.py` is a reviewed decision and gets an
inline justifying comment, modelled on the 2FA-endpoint comment at
`guardrails.py:53`. The complete set PR 8 adds:

| path | added by check | justification |
|------|----------------|---------------|
| `/api/loginConfig` | auth-methods | Pre-auth OIDC provider list; read-only inventory of federated trust paths offered on the login page. |
| `/api/oAuth2Clients` | auth-methods | Registered OAuth2 clients; read-only, to flag broad grants / wildcard redirects. Secrets are not returned. |
| `/api/apiToken` | tokens | PAT inventory; ACL-filtered to the audited account's own tokens unless superuser. The secret `key` is never serialized. |
| `/api/routes` | routes | Route inventory for SSRF triage; GET only, the run executor `/api/routes/{id}/run` is never called. Secrets are WRITE_ONLY. |
| `/api/configuration/corsWhitelist` | settings-extensions | The only source for the permissive-CORS verdict (`keyCorsWhitelist` was removed in v2.31). Bare array, GET readable by any authenticated user. |

`transport` and the `settings` base read add NO allowlist paths.

audit-config dhis.conf secret-redaction contract (repeated here as a guardrail):
the `--dhis-conf` parser reads a local file (not an HTTP path, so no allowlist
entry) and parses ONLY into models that physically cannot hold a secret value
(`AuditChannel`/`AuditScopeMatrix` for audit.* keys; `RedactedSecret(key, is_set)`
for credential keys). A negative test asserts a known password fed into the parser
never appears in any rendered format. This redaction-by-construction is the same
posture as the existing `REPORT_GUARDRAIL_NOTE` discipline, encoded in the type system.

## 5. Sub-PR split

PR 8 spans five checks plus the settings extension. At roughly 10-12 files per
check (security_core module, `__init__`, registry/guardrails, three audit.py,
optional three `_wire.py`, one test, FEATURES/BUGS), the whole thing is 50-60
files -- 3-4x the ~15-file target. It MUST be split. THE split, in landing order:

### PR 8a -- transport + settings-extensions

Cheapest, highest-signal, and NO new HTTP allowlist paths beyond
`/api/configuration/corsWhitelist`. Transport reads response headers already on
the wire; settings-extensions read `/api/systemSettings` (already allowlisted)
plus the one CORS endpoint. No `_wire.py` changes in either. Lands first because
it is the lowest-risk and proves the registry/guard-test flip with the smallest
blast radius. Also fills the long-standing gap that `evaluate_settings` has no
version-invariant test (adds `test_security_settings.py`).

### PR 8b -- auth-methods + tokens + routes

The new-endpoint checks. Groups the three reads that add the bulk of the
`GET_ALLOWLIST` surface (`/api/loginConfig`, `/api/oAuth2Clients`, `/api/apiToken`,
`/api/routes`) and ALL three `_wire.py` divergences (the OAuth2 v41-vs-v42/43
client split with its REQUIRED BUGS.md entry, the v41 ApiToken shape split, and
the v41 route auth-union split citing BUGS.md #14). Grouping the wire-divergent
checks together keeps the `_wire.py` edits and their BUGS.md entries in one
reviewable PR.

SIZE: this is the large sub-PR -- roughly 28-34 files (three
`security_core` modules + `__init__` exports, registry + guardrails, three
`audit.py`, three `_wire.py`, three tests, the guard/guardrail test edits, plus
nine example files and the docs/FEATURES sweep), about 2x the ~15-file target this
plan sets. That is a deliberate, informed choice, not an oversight: all three
checks here are the wire-divergent ones, each carrying a v41-vs-v42/43 `_wire.py`
split and a BUGS.md entry, and a reviewer evaluating the three-tree divergence
contract benefits from seeing the OAuth2, ApiToken, and route-auth splits side by
side rather than across three separate reviews. Routes alone is the cleanest
single-divergence story and is the natural carve-out if a reviewer asks 8b to
shrink, but the default is to keep the three wire-divergent checks in one review.

### PR 8c -- audit-config

The `--dhis-conf` parser, the redaction-by-construction models, and the negative
redaction test. Isolated because it is the only check touching `cli.py` (the
`--dhis-conf` flag), the only one with a local-file read instead of an HTTP path,
and the only one whose value is a security-critical redaction contract that
deserves its own focused review. No allowlist changes.

Each sub-PR ships its tests (parametrised over the three trees), its
`examples/v{41,42,43}/cli/security.sh` lines, its `FEATURES.md` row, its `docs/`
sweep, and its `BUGS.md` entries where divergence surfaces.

## 6. Testing

Tests live ONCE under `packages/dhis2w-core/tests/security/`, parametrised over
`TREES = ("v41","v42","v43")`, never per-tree copies. Each check gets two sections.

- **transport** (`test_security_transport.py`): version-invariant
  `evaluate_transport(scheme, headers)` covering each finding (non-TLS HIGH, no
  HSTS, no CSP, the anti-framing dedup where CSP frame-ancestors suppresses the
  X-Frame-Options finding, no nosniff, Server version disclosure) and the clean
  case; per-tree `_run_transport` wiring with `@respx.mock` capturing headers from
  the `client.get_response` call (mirroring `test_security_guest.py`), plus the
  transport-error degrade-to-note.
- **auth-methods** (`test_auth_methods.py`): version-invariant
  `evaluate_auth_methods` over hand-built `OAuth2ClientView` + provider lists
  (INFO provider, INFO clean client, MEDIUM broad-grant, MEDIUM wildcard/cleartext
  redirect, loopback-http NOT flagged, INFO-suppression when a client is also
  MEDIUM); per-tree wiring asserting the v41 array envelope vs v42/v43 comma-string
  envelope both normalize to the same `OAuth2ClientView`, and the
  oauth2-clients-unreadable 403 degrade with loginConfig still producing INFO.
- **tokens** (`test_security_tokens.py`): version-invariant `evaluate_tokens` over
  `TokensInventory` (inventory MEDIUM with scope text, non-expiring HIGH for null
  and past-epoch, no-IP-allowlist HIGH, the worst-case pairing, the
  account-scoped INFO caveat when not superuser); per-tree `tokens_from_raw`
  mapping asserting v41 Literal-type and v42/v43 enum-type both yield the same
  `TokenView`, plus the endpoint-unavailable degrade.
- **routes** (`test_security_routes.py`): version-invariant route evaluation over
  `RouteTarget` (private CIDRs incl. IPv4-mapped IPv6 and integer-encoded IPs via
  `ipaddress`, the metadata-endpoint sub-case, `/**` subpaths, carries-auth INFO,
  no-required-authorities MEDIUM, inventory INFO, and external hostnames NOT
  flagged); per-tree wiring asserting v41's undiscriminated auth union and
  v42/v43's discriminated union both project to the same `auth_type`/identity
  without v41 referencing the OAuth2 variant.
- **audit-config** (`test_security_audit_config.py`): the API-only INFO path
  (no `--dhis-conf`), the dhis.conf-unreadable note, and the four
  dhis.conf-parsed verdicts (system-disabled, both-sinks-off, empty-matrix,
  narrow-scope) over hand-built `AuditPosture`. Plus the MANDATORY negative test
  (`test_security_dhisconf_redaction.py`): feed a dhis.conf with a known password,
  render the report in every format (md/txt/csv/html/json), and assert that string
  never appears in any output.
- **settings-extensions** (`test_security_settings.py`, NEW): the FOUR shipped
  verdicts (today untested at the reducer level -- only the CLI render test exists)
  PLUS the new ones (keyCanGrantOwnUserAuthorityGroups HIGH, CORS wildcard MEDIUM
  via `CorsWhitelist.has_wildcard`, the static 2FA MEDIUM, the email-not-configured
  WARN, and the dropped/INFO unique-email decision).
- **guardrail test** (`test_security_guardrails.py`): each PR that adds a public
  service.py function registers it in `SERVICE_CALLS` and mocks its endpoint in
  `_mock_read_surface`; the completeness test asserts the public-coroutine set
  equals `SERVICE_CALLS`. The no-lockout tests (401/403 not retried,
  `open_client` defaults `retry_policy=None`) must stay green.
- **guard test** (`test_security_audit_guards.py:41-52`): update the hard-coded
  default-run order assertion in the SAME PR that flips each key into
  `IMPLEMENTED_CHECK_KEYS`.

## 7. Docs / examples / FEATURES

Every behaviour-changing sub-PR touches docs + examples + FEATURES in the SAME PR.

- **Examples**: `examples/v{41,42,43}/cli/security.sh` (three files per tree). Each
  new check adds a commented `d2w security audit --checks <key>` block to all three
  files (model after the apps/guest/sharing blocks in `examples/v42/cli/security.sh`).
  The audit-config `--dhis-conf` flag gets its own example line.
- **FEATURES**: the actual file is `docs/project/features.md` (the root
  `FEATURES.md` name in CLAUDE.md is the convention name). Extend the single big
  security table row (`features.md:151`) to enumerate the new checks (transport
  headers, auth-methods, tokens, routes, audit-config) and the settings-verdict
  additions. The command-tree snippet (`features.md:253-256`) lists `d2w security`
  subcommands.
- **docs/**: `docs/cli-reference.md` and `docs/mcp-reference.md` are GENERATED --
  NEVER hand-edit. After adding the `--dhis-conf` flag (audit-config), regenerate
  with `make docs-cli` (pinned to v42 via DOCS_PIN) so the new flag/help appears.
  Run `make docs-build` (`mkdocs build --strict`) after doc edits so broken links
  fail. Hand-edited prose to sweep per CLAUDE.md: `docs/project/features.md`,
  `docs/walkthrough.md`, `docs/roadmap.md`, `docs/decisions.md`, and the planning
  page `docs/planning/security-scanner.md`. Grep `docs/` + `examples/` for any
  renamed symbol/flag and update each hit in the same PR.

## 8. Open questions to confirm during build

Pulled from each check's research, deduplicated, recommended answers in brackets.

1. **auth-methods, v41 envelope**: confirm the v41 `/api/oAuth2Clients` list
   envelope key (`data[]` vs `oAuth2Clients[]`) against a real v41 dump; until
   then read tolerantly (try `oAuth2Clients[]` then `data[]`).
2. **auth-methods, redirect scope**: include non-loopback cleartext `http://`
   redirect URIs in the MEDIUM, not only literal `*`? [Recommend yes -- same
   code-interception class; confirm with the PR owner so the finding set matches
   the brief.]
3. **routes, no DNS**: private-address detection does NO DNS resolution (the
   no-egress guardrail forbids it), so a hostname resolving to 10.x is NOT flagged.
   Confirm the accepted trade-off (flag literal private IPs + known-internal
   suffixes, accept DNS-cloaked false negatives, document the limitation in the
   finding detail). [Recommend yes -- the only design consistent with the guardrail.]
4. **tokens, default fields**: confirm GET `/api/apiToken` default projection
   includes `attributes`/`expire`/`type`/`createdBy` without an explicit `?fields=`;
   the runner should always pass an explicit `fields=` to be safe.
5. **audit-config, flag placement**: surface `--dhis-conf` as a per-check Typer
   Option on the single `audit` command (mirroring `--stale-days`/`--max-objects`),
   threaded through `run_security_audit` -> `_bind_audit_config`, default None
   (API-first). It binds the env var `DHIS2_CONF_LOCATION` (the same canon as the
   rest of the CLI, per `SECURITY-SCANNER-PLAN.md` line ~270). Confirm the team
   wants it on the audit command, not a standalone subcommand.
6. **settings, severities**: confirm the email-not-configured verdict uses WARN
   (the enum has no LOW); decide whether `credentialsExpires` stays WARN (current)
   or bumps to MEDIUM (a tuning decision, not new logic); confirm dropping the
   unique-email verdict.
7. **transport, severity home**: confirm WARN is the intended home for the
   brief's LOW findings (X-Frame-Options, X-Content-Type-Options, Server), MEDIUM
   for HSTS/CSP, HIGH for non-TLS; and that CSP presence is inferred solely from
   the observed header (no `keyCspEnabled` read, which does not exist).

Top 3 to resolve before coding: (1) the routes no-DNS trade-off, (2) the
auth-methods v41 envelope key, (3) the settings email/credentialsExpires severity
and the unique-email drop.

## 9. Gate

Each sub-PR ships only when:

- `make lint` is clean (ruff + mypy + pyright, strict).
- `make test` is green (the full dhis2w-core suite, including the new
  parametrised security tests and the updated guard / guardrail tests).
- The guard test `test_security_audit_guards.py` default-run order is updated in
  the same PR as each `IMPLEMENTED_CHECK_KEYS` flip.
- The negative redaction test passes (PR 8c): a known password never appears in
  any rendered format.
- `make docs-cli` is re-run when a CLI flag is added (PR 8c's `--dhis-conf`), and
  `make docs-build` passes (`mkdocs build --strict`).
- Examples (three trees), `docs/project/features.md`, and the regenerated
  `docs/cli-reference.md` are in sync.
- An adversarial review pass is run and its must-fix findings addressed before merge.

Commits are signed (GPG key C64F35A7CC42BF6B, committer `msvanaes@dhis2.org`).
NO emojis, NO AI attribution in commits, PR titles, or descriptions. Greenfield
voice throughout: state what the code does now, not what it used to do.
