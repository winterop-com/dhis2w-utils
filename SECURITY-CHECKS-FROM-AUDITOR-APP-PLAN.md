# Security checks from the auditor app: gap plan

Author: Morten Svanaes
Date: 2026-06-25
Status: PRs A-F IMPLEMENTED on `feat/security-audit-scanner` (2026-06-25) -- A `13adeb36` (settings top-ups), B `5e4a4291` (transport header grading: HSTS max-age / CSP directives / cross-origin isolation), C `9446ef0c` (runtime CORS response headers), D `e6c28d40` (all-account hygiene aggregates), E `f4962051` (password-age with the v41-vs-v42/v43 _wire split), F `9ae0b38f` (route-management dangerous-authority category). Each was adversarially reviewed and gated. PR G (js-x-ray static app-bundle analysis, section 4) is the one remaining item, deferred as an opt-in post-release sub-project. Source-grounding corrected an app bug en route: the app's `F_PUBLIC_ROUTE_ADD` authority does not exist; the real constant is `F_ROUTE_PUBLIC_ADD` (BUGS.md #57). The sections below are the as-built design for A-F and the design for G.

## 1. Method and scope

This is a one-directional `app -> ours` gap analysis. The input is the
security-auditor-app's extracted signal inventory (three clusters:
`authorities-users-settings`, `connection-headers-appsources`, and
`apps-static-analysis`) diffed against OUR scanner's shipped inventory
(`security_core/*.py`, 14 implemented checks, verified against the code on
`feat/security-audit-scanner`). It asks ONE question: which app signals does our
scanner NOT already cover, and how do we add them. It deliberately does NOT do
the reverse (what we have that the app lacks) except for the short section 6
note, so the reader does not re-add things we are already ahead on.

How the diff was produced:

- Each app signal was mapped to the OUR-check whose domain it falls in
  (`transport`, `settings`, `hygiene`, `apps`, `auth-methods`, `routes`, etc.).
- Each was then marked HAVE (ours is equivalent), HAVE-BUT-WEAKER (ours covers
  the domain but the app inspects more / more precisely -- the delta is noted),
  GAP (we lack it entirely), or OUT-OF-SCOPE (with reason).
- Severity translation: the app's `fail`/`warning`/`pass` enum is coarser than
  ours (CRITICAL/HIGH/MEDIUM/WARN/INFO, no LOW). App `fail` maps to HIGH or
  CRITICAL by blast-radius judgement; app `warning` maps to MEDIUM or WARN; app
  `pass`/`info` carries no finding in our model (absence of a finding IS our
  success signal -- we emit no per-check pass rows).

Version scope mismatch (load-bearing):

- The app targets DHIS2 **v39-v42**. We target **v41-v43**. So any app behaviour
  that only matters on v39/v40 is OUT-OF-SCOPE for us (e.g. the app's
  `coreApp:true` legacy bundled-app flag for "older instances", and the nested
  `userCredentials.passwordLastUpdated` field which the app uses only for `<v42`).
- Conversely, an app signal gated to v42+ (`enforceVerifiedEmail`,
  `lockMultipleFailedLogins` via systemSettings, flattened `passwordLastUpdated`)
  is fully in our window and worth porting.
- Any app setting-key must be re-checked against v43 during build for
  rename/removal. The DHIS2 source at
  `/Users/netromsb/develop/dhis2/GARAGE/SLOT3/dhis-2` is ground truth; build
  steps below flag exactly which keys to verify there.

## 2. Diff table (every app signal, grouped by the OUR-check it maps to)

Status legend: HAVE = ours equivalent; WEAKER = ours covers domain, app more
thorough (delta noted); GAP = we lack it; OOS = out of scope (reason).

### 2.1 -> OUR `settings` check

| app signal | status | delta / reason |
|---|---|---|
| password-policy (minPasswordLength < 8) | HAVE | ours: `settings_audit.py:60`, identical threshold. |
| account-lockout (lockMultipleFailedLogins false) | HAVE | ours: `keyLockMultipleFailedLogins is False` (`:71`). App also warns when the key is ABSENT (older version) -- minor WEAKER, see 3.1. |
| password-expiry-policy (credentialsExpires == 0) | HAVE | ours: `credentialsExpires in (None, 0)` (`:81`). |
| email-verification (enforceVerifiedEmail) | WEAKER | ours reads `enforceVerifiedEmail` only inside the SMTP-coupling verdict (`:139`); we do NOT emit a standalone "email verification not enforced" finding. App warns whenever it is not `'true'`. GAP-ish verdict, see 3.2. |
| password-policy / lockout / expiry "setting unavailable -> warning" | OOS | ours degrades the whole check with a note when systemSettings is unreachable; we do not emit per-setting "unable to check" warnings. Design choice (DEGRADED note, not a finding). Keep as-is. |

### 2.2 -> OUR `settings` check (CORS)

| app signal | status | delta / reason |
|---|---|---|
| cors-whitelist wildcard (`*`) | HAVE | ours: `CorsWhitelist.has_wildcard` (`settings_audit.py:114`), MEDIUM. |
| cors-whitelist non-empty (N origins) -> warning | GAP | app surfaces ANY non-empty whitelist as a warning for review; we only flag the wildcard. Low-value, see 3.3. |
| cors-headers (runtime ACAO/ACAC response headers) | GAP | app reads `Access-Control-Allow-Origin` + `Access-Control-Allow-Credentials` off the live response (wildcard+credentials = fail). We only read the server-config whitelist, never the runtime CORS response headers. See 3.4. |

### 2.3 -> OUR `transport` check (response headers)

| app signal | status | delta / reason |
|---|---|---|
| https-connection (scheme not https) | HAVE | ours: `transport` base-URL scheme check, HIGH. |
| hsts missing | HAVE | ours: no-HSTS MEDIUM. |
| hsts max-age invalid / too-short / below-1-year | GAP | app PARSES the `max-age` directive and grades it (invalid, <1 day, <1 year, >=1 year). We only check presence/absence. See 3.5. |
| server-header version exposed | HAVE | ours: Server-header digit-run check, WARN. |
| csp missing | HAVE | ours: no-CSP MEDIUM. |
| csp report-only / broad-source / unsafe-inline / unsafe-eval / object-src / base-uri / frame-ancestors / strict-dynamic | GAP | app PARSES the CSP directive map and grades each directive (aggregated to one warning). We only check CSP presence/absence + a frame-ancestors substring for anti-framing. See 3.6 (biggest transport gap). |
| coop-header (Cross-Origin-Opener-Policy) | GAP | not inspected by us at all. See 3.7. |
| coep-header (Cross-Origin-Embedder-Policy) | GAP | not inspected by us. See 3.7. |
| corp-header (Cross-Origin-Resource-Policy) | GAP | not inspected by us. See 3.7. |
| header "unavailable -> warning" (responseHeaders null) | OOS | ours degrades the check with a note when the response is unreachable; we do not emit per-header "unavailable" warnings. Keep DEGRADED-note design. |
| anti-framing (X-Frame-Options / CSP frame-ancestors) | HAVE | ours: combined anti-framing WARN, suppressed when CSP frame-ancestors present. |
| X-Content-Type-Options nosniff | HAVE | ours: nosniff WARN. (App does NOT check this -- we are ahead here.) |

### 2.4 -> OUR `hygiene` check (users)

| app signal | status | delta / reason |
|---|---|---|
| users-never-logged-in (ALL active users) | WEAKER | ours flags never-logged-in ONLY for PRIVILEGED accounts (`hygiene.py:99`). App flags EVERY active account that never logged in. Real coverage gap on non-privileged accounts. See 3.8. |
| users-inactive-3-months (ALL active users) | WEAKER | ours flags stale ONLY for privileged accounts (`hygiene.py:110`, configurable `stale_days`). App flags every active account inactive > N months via the server `inactiveMonths` param. See 3.8. |
| password-age (older than 365d OR never set, ALL active users) | GAP | we have NO password-age check at any privilege level. App unions `passwordLastUpdated:lt:<iso>` and `passwordLastUpdated:null`. See 3.9. |
| default-admin-credentials-active (admin/district live probe) | HAVE | ours: `credential-probe` check, CRITICAL, MAX_PROBE_ATTEMPTS=1. We are equal-or-stronger (we bound retries explicitly). |
| user-roles ALL-authority holder count > max | HAVE | ours: `roles` (Role grants ALL -> CRITICAL/HIGH) + `hygiene` privileged-account findings. App counts holders against a max-superusers threshold; ours flags the role itself plus each privileged account's hygiene. Equivalent coverage, different framing. See note in 3.10. |
| route-manager-authority (F_PUBLIC_ROUTE_ADD) holder count | WEAKER | ours `roles` flags dangerous-authority categories per role, but F_PUBLIC_ROUTE_ADD is not currently in a dangerous category and we do not COUNT holders against a threshold. See 3.10. |
| impersonate-user-authority (F_IMPERSONATE_USER) holder count | WEAKER | same as above: not in our dangerous-authority taxonomy; no holder-count threshold. See 3.10. |
| system-setting-authority (F_SYSTEM_SETTING) holder count | WEAKER | same: F_SYSTEM_SETTING maps to our `system_settings` category for the AUDITED account only; we do not count instance-wide holders against a threshold. See 3.10. |

### 2.5 -> OUR `apps` check (install source)

| app signal | status | delta / reason |
|---|---|---|
| untrusted-app-sources manual/sideloaded present | HAVE | ours: `apps` side-loaded -> HIGH (`apps.py`). |
| untrusted-app-sources bundled/coreApp/appHubId classification | HAVE | ours classifies bundled / core_app / app_hub_id identically. (coreApp is the v39/v40 legacy flag -- partially OOS but we already read it.) |
| untrusted-app-sources fetch error | OOS | ours degrades with a note rather than an `error` finding row. Keep. |

### 2.6 -> OUR `apps-static-analysis` (js-x-ray) -- NEW capability

| app signal | status | delta / reason |
|---|---|---|
| obfuscated-code / unsafe-import / unsafe-stmt (fail) | GAP | no bundle static analysis at all. |
| encoded-literal / weak-crypto / suspicious-literal / parsing-error (warning) | GAP | same. |
| short-identifiers / unknown-kind / noisy-kinds / file-fetch / size-skip / no-scripts | GAP | same. |

This entire cluster is a strategic decision treated separately in section 4.

## 3. Per-gap plans (GAP and WEAKER-worth-closing)

Severity is the ceiling; the runtime enum has no LOW (LOW -> WARN). Every new
check follows the proven anatomy (section 2 of `SECURITY-POSTURE-EXTRAS-PLAN.md`):
a version-invariant reducer in `security_core/<check>.py`, per-tree wiring in
`v{41,42,43}/plugins/security/audit.py`, one parametrised test, and a registry
+ allowlist edit where a new endpoint is touched.

---

### 3.1 settings: lockout / expiry "setting absent on older version" (WEAKER, low value)

- Lands in: extend `settings_audit.evaluate_settings`.
- Setting-keys: `keyLockMultipleFailedLogins`, `credentialsExpires` (already read).
- Delta: app emits a distinct warning when the key is absent (unsupported
  version). On our v41-v43 window all three keys exist, so the "absent ->
  unsupported version" branch is largely moot. RECOMMENDATION: SKIP. Our
  `None` -> existing verdicts (e.g. `credentialsExpires in (None, 0)`) already
  cover absence as the unsafe case. No work.
- Build check: confirm `keyLockMultipleFailedLogins` exists on v43 in
  `dhis-2/.../SettingKey.java` (it does on v42; verify no rename to a `login.*`
  namespace on v43).
- Effort: none (decision to skip).

---

### 3.2 settings: standalone "email verification not enforced" (WEAKER -> close)

- Lands in: extend `settings_audit.evaluate_settings` (one new verdict).
- Setting-key: `enforceVerifiedEmail` (already on `SettingsLike` and the per-tree
  `SecuritySettings` projection -- NO model change).
- Today we only read it inside the SMTP-coupling verdict. Add a standalone
  verdict: `enforceVerifiedEmail is False` (or None) -> WARN "Email verification
  is not enforced". Keep it WARN not MEDIUM: it is a hardening gap, not an active
  hole, and we already MEDIUM-flag the SMTP coupling.
- Version applicability: `enforceVerifiedEmail` introduced in v42. On v41 the key
  is absent -> `None`; do NOT emit the v41 warning (avoid a guaranteed false
  positive on a version that cannot support it). Gate: only emit when the value
  is explicitly `False`, not when `None`.
- Models: reuse `SettingsLike` / `SecuritySettings` (no change). Reuse
  `AuditFinding` / `Severity`.
- GET_ALLOWLIST: none (systemSettings already allowlisted).
- Build check: confirm in `dhis-2` that `enforceVerifiedEmail` is absent (not
  defaulted to a value) on v41 systemSettings, so the `None` gate is correct.
- Effort: XS (one verdict + one reducer test).

---

### 3.3 settings: non-empty CORS whitelist surfaced for review (GAP, low value)

- Lands in: extend `settings_audit.evaluate_settings` (the `cors` branch).
- Endpoint: `/api/configuration/corsWhitelist` (already allowlisted, already
  wrapped as `CorsWhitelist`).
- Add: when `cors.origins` is non-empty AND has no wildcard -> INFO (not WARN; an
  origin allowlist is the CORRECT mechanism, listing it as a warning would
  inflate the warning count on correctly-configured instances). Enumerate the
  origins in `evidence`. This diverges from the app (which warns) on purpose --
  our INFO tier is the right home for "review this".
- Models: reuse `CorsWhitelist`. No new model.
- Effort: XS.

---

### 3.4 settings/transport: runtime CORS response headers (GAP, medium value)

- Lands in: extend `transport` (it already reads response headers off
  `/api/system/info`). Do NOT spawn a new check.
- Endpoint/fields: `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`
  response headers on the existing `client.get_response("/api/system/info")`.
- Findings (proposed severity in OUR enum):
  - ACAO == `*` AND ACAC == `true` -> **HIGH** ("wildcard origin with credentials;
    any origin can make authenticated requests"). App calls this fail/critical.
  - ACAO == `*` (no credentials) -> **WARN**.
  - ACAO specific + ACAC == `true` -> **WARN** ("trusted-origin review").
  - else -> no finding.
- CAVEAT: ACAO is only emitted on a response that carries an `Origin` request
  header (CORS is request-conditioned). A plain server-side GET sends no Origin,
  so DHIS2 may not emit ACAO at all -> our read frequently sees nothing. Mitigate
  by sending a benign `Origin: https://<base-host>` on the system/info probe and
  reading the echoed ACAO. This is still a read-only GET against an allowlisted
  path; document the synthetic Origin header in the guardrail note.
- GET_ALLOWLIST: none (system/info already allowlisted; only adds a request
  header).
- Version: uniform; the CorsFilter behaviour is version-invariant. Verify in
  `dhis-2/.../CorsFilter.java` that the Origin-echo + credentials behaviour is
  unchanged across v41-v43.
- Models: extend `TransportHeaders` with `access_control_allow_origin: str | None`
  and `access_control_allow_credentials: str | None`. Reuse otherwise.
- Effort: S (two fields + two findings + the synthetic-Origin wrinkle + tests).

---

### 3.5 transport: HSTS max-age grading (GAP, low-medium value)

- Lands in: extend `transport`.
- Field: the existing `strict-transport-security` header value (no new endpoint).
- Parse `max-age=(\d+)` with a strict digit-only regex (mirror the app: reject
  `max-age=31536000abc`). Findings:
  - present but max-age missing/invalid/<=0 -> WARN.
  - 0 < max-age < 86400 (1 day) -> WARN.
  - 86400 <= max-age < 31536000 (1 year) -> WARN ("below recommended 1 year").
  - >= 1 year -> no finding (we already have the "missing HSTS" MEDIUM for the
    absent case).
- Collapse the three sub-cases into ONE WARN finding with the parsed value in
  detail to avoid finding spam.
- Models: no change (value already on `TransportHeaders`).
- Effort: XS-S (pure-Python parse + reducer tests).

---

### 3.6 transport: CSP directive parsing (GAP, medium value -- biggest transport gap)

- Lands in: extend `transport` (or a focused `csp.py` helper imported by
  `transport.py` to keep the reducer readable).
- Field: the existing `content-security-policy` (and `-report-only`) header value.
- Parse into a directive map (lowercase directive names and source values, mirror
  the app). Grade and AGGREGATE into ONE finding (the app does exactly this):
  - report-only mode (only `-report-only` present) -> contributes WARN.
  - no `script-src` and no `default-src` -> WARN.
  - `script-src`/`default-src` contains a BROAD source (`*`,`http:`,`https:`,
    `data:`) -> WARN.
  - `unsafe-inline` / `unsafe-eval` in script sources -> WARN.
  - `object-src` not `'none'` (and no locked default-src) -> WARN.
  - `base-uri` unset or broad -> WARN.
  - `frame-ancestors` unset or broad -> WARN (NOTE: our existing anti-framing
    WARN already covers the "frame-ancestors entirely missing" case -- de-dup so
    we do not double-flag; the CSP parse should only ADD the "present but broad"
    sub-case).
  - `strict-dynamic` -> informational annotation only, NEVER a warning.
  - Aggregate: any sub-warning -> ONE MEDIUM "Content-Security-Policy is weak"
    finding listing the failed directives in detail.
- Severity: the aggregate is MEDIUM (matches the weight of our existing no-CSP
  MEDIUM). App uses warning.
- Models: no new endpoint; add nothing to `TransportHeaders` (value already read).
  A small frozen `CspDirectives` view-model inside `transport.py`/`csp.py` for the
  parsed map (NO dict across boundaries -- typed accessor).
- Version: uniform. DHIS2's `CspFilter` is version-invariant; the policy STRING
  is what we grade, so no per-tree wire split. Verify against `CspFilter.java`
  that the default policy on v43 has not tightened in a way that would make our
  grading noisy.
- Effort: M (the parser is the bulk; reuse the app's directive logic verbatim as
  the spec).

---

### 3.7 transport: COOP / COEP / CORP headers (GAP, low value)

- Lands in: extend `transport`.
- Fields: `cross-origin-opener-policy`, `cross-origin-embedder-policy`,
  `cross-origin-resource-policy` response headers (no new endpoint).
- Findings (one each, all WARN -- these are defence-in-depth, not active holes):
  - COOP: missing or `unsafe-none` or unrecognized -> WARN; `same-origin` /
    `same-origin-allow-popups` -> no finding.
  - COEP: missing or `unsafe-none` or unrecognized -> WARN; `require-corp` /
    `credentialless` -> no finding.
  - CORP: missing or `cross-origin` or unrecognized -> WARN; `same-origin` /
    `same-site` -> no finding.
- IMPORTANT caveat: DHIS2 does not set COOP/COEP/CORP by default (these are not
  in `setHttpHeaders`). So on a stock instance ALL THREE will fire WARN on every
  audit. That is noise. RECOMMENDATION: ship these as a SINGLE aggregated WARN
  ("cross-origin isolation headers not configured: COOP/COEP/CORP") rather than
  three findings, OR make them opt-in. Confirm the default in
  `dhis-2/.../DhisWebApiWebSecurityConfig.java` before shipping; if DHIS2 sets
  none of them, lower to INFO or gate behind a flag so we do not flag every
  instance.
- Models: extend `TransportHeaders` with three optional str fields.
- Effort: S (trivial logic; the judgement call on default-noise is the real work).

---

### 3.8 hygiene: never-logged-in / stale for ALL active accounts (WEAKER -> close, high value)

- Lands in: extend `hygiene.evaluate_hygiene` (or add sibling verdicts). Today the
  never-logged-in (`:99`) and stale (`:110`) branches are guarded by
  `if not user.is_privileged: continue` (`:85`). The app applies these to every
  active account.
- Endpoints/fields: `/api/users` (already allowlisted) -- we already fetch
  `disabled`, `lastLogin` for the hygiene join. To match the app efficiently,
  optionally use the server `inactiveMonths` param and `filter=lastLogin:null`,
  but our existing full-user fetch already carries `lastLogin`, so we can grade
  client-side without new requests.
- Findings (proposed severity):
  - active (non-disabled) NON-privileged account, lastLogin null -> **WARN**
    "Active account never logged in" (privileged stays HIGH as today).
  - active non-privileged account stale > `stale_days` -> **WARN** "Stale active
    account" (privileged stays MEDIUM as today).
  - Fold per-account findings under a `group_key` so a 5000-user instance does
    not emit 5000 rows -- emit a COUNT + a capped sample (mirror app's
    SAMPLE_LIMIT=10) in one finding. This is important: the privileged path
    emits per-user because privileged sets are small; the all-users path MUST
    aggregate.
- Version: uniform (lastLogin/disabled on `/api/users` all three). No `_wire`
  change.
- Models: reuse `UserHygiene`; the join already builds one per user. Add an
  aggregation helper.
- GET_ALLOWLIST: none.
- Effort: S-M (the aggregation + not regressing the privileged per-user rows).

---

### 3.9 hygiene: password-age check (GAP, high value)

- Lands in: extend `hygiene` (new verdict + a per-tree field read), or a small
  `password_age.py` reducer. We have NO equivalent today.
- Endpoint/field: `/api/users` (allowlisted). Field is VERSION-DIVERGENT:
  - v42/v43: flattened `passwordLastUpdated`.
  - v41: nested `userCredentials.passwordLastUpdated`.
  This is the ONE genuine `_wire.py` divergence in this gap set. Add a
  `password_last_updated(user_raw) -> str | None` extractor to each tree's
  `_wire.py` (v41 reads the nested path; v42/v43 read the flat field), exactly
  mirroring the existing 2FA `_wire` split. Cite the field-name divergence in
  BUGS.md.
- Finding: active account whose `passwordLastUpdated` is older than
  `max_password_age_days` (default 365) OR is null/never-set -> WARN. Union the
  two (mirror the app: `:lt:` excludes nulls). Aggregate to a count + sample like
  3.8.
- Severity: WARN (stale password is a hardening gap; reserve MEDIUM/HIGH for
  active holes). Privileged accounts with never-set passwords could be bumped to
  MEDIUM -- decide at build.
- Version: divergent field name (v41 vs v42/v43) -> `_wire.py` member required.
  The app's `<v42` nested path is partially OOS (we only support v41 as the floor,
  and v41 IS pre-v42, so we DO need the nested path for v41).
- Build check: confirm in `dhis-2` that v41 `/api/users` returns
  `userCredentials.passwordLastUpdated` and v42/v43 returns the flattened
  `passwordLastUpdated` (the systemSettings/user flattening landed around v42 --
  verify the exact major).
- Models: reuse `UserHygiene` (add a `password_last_updated: str | None` field)
  or a sibling model. Reuse `Severity`/`AuditFinding`.
- GET_ALLOWLIST: none.
- Effort: M (the `_wire` split + the union logic + three-tree tests).

---

### 3.10 roles/hygiene: privileged-authority holder counts vs threshold (WEAKER, medium value)

- App signals: ALL, F_PUBLIC_ROUTE_ADD, F_IMPERSONATE_USER, F_SYSTEM_SETTING
  holder counts vs `maxSuperUserRoles` (default 5).
- We already cover ALL strongly (the `roles` check flags any role granting ALL as
  CRITICAL/HIGH, and `hygiene` flags each privileged account). The DELTA is:
  - We do not COUNT instance-wide holders of a specific authority against a
    configurable threshold.
  - F_PUBLIC_ROUTE_ADD and F_IMPERSONATE_USER are NOT in our dangerous-authority
    taxonomy (`AUTHORITY_CATEGORIES`).
- Lands in: extend `authorities.py` taxonomy + the `roles` reducer.
  - Add `F_PUBLIC_ROUTE_ADD` to a new/`tracker_admin`-adjacent category (it pairs
    naturally with our `routes` SSRF check -- a user who can add public routes can
    create the SSRF targets that check flags), and `F_IMPERSONATE_USER` to a
    `user_management`-adjacent or new `impersonation` category. F_SYSTEM_SETTING
    already maps to our `system_settings` category.
  - Decide whether to ADD a holder-count-vs-threshold finding. RECOMMENDATION:
    do NOT replicate the app's `maxSuperUserRoles` threshold model wholesale --
    our `roles` check already flags the role; adding a separate "N users hold X"
    count is incremental. Instead, ensure F_PUBLIC_ROUTE_ADD / F_IMPERSONATE_USER
    are in the dangerous taxonomy so any ROLE granting them is flagged (which
    transitively flags the holders via hygiene). That closes the security gap
    without a new threshold concept.
- Endpoints: `/api/userRoles`, `/api/users` (both allowlisted). No new endpoint.
- Version: `F_IMPERSONATE_USER` / `F_PUBLIC_ROUTE_ADD` authority constants --
  verify they exist as named authorities on v41-v43 in
  `dhis-2/.../Authorities.java`. v41 `/api/authorities` returns 500 (BUGS.md #45),
  but we key the taxonomy on constant names, not the live endpoint, so that does
  not block us.
- Models: reuse the `authorities` taxonomy + `roles` reducer. No new model.
- Effort: S (taxonomy additions + reducer test; the threshold-count is
  explicitly descoped).

---

## 4. js-x-ray installed-app static analysis (MAJOR strategic section)

This is the single largest gap and the one the app's `apps-static-analysis`
cluster is built around. It is NOT a posture read -- it FETCHES every installed
app's bundles and statically analyzes the JavaScript for malware/obfuscation
signals (eval/new Function, remote dynamic import, obfuscation fingerprints,
encoded literals, weak crypto). Our `apps` check today does ONLY install-source
classification + App Hub update currency + custom JS/CSS settings. Zero bundle
analysis. Honest assessment: this is a sub-project, not a check.

### 4.1 Why it is hard

- No drop-in js-x-ray in Python. js-x-ray is a Node/meriyah-AST malware heuristic
  engine; its specific kinds (obfuscated-code via curated obfuscator fingerprints,
  encoded-literal, suspicious-literal, short-identifiers, unsafe-import/stmt) have
  no Python port.
- The heaviest signal -- `obfuscated-code` -- relies on curated
  javascript-obfuscator fingerprints that are non-trivial to reproduce.
- It is heavier than ANY current check: it fetches `index.html` per app, parses
  `<script src>`, fetches each same-origin bundle (up to 5 MB each), and runs an
  AST pass. That violates the spirit of our GET-only, fixed-tiny-payload posture
  reads.

### 4.2 Options

(a) **Port the high-signal heuristics in pure Python via tree-sitter.**
`tree-sitter-javascript` (mature Python bindings, fast, tolerant) parses each
bundle to an AST; then hand-implement: `eval`/`new Function(string)` ->
unsafe-stmt; dynamic `import()`/`require()` with URL/non-literal args ->
unsafe-import; Shannon-entropy + length on string literals -> encoded-literal /
suspicious-literal; mean identifier length -> short-identifiers; MD5/SHA1
references -> weak-crypto. Port the FAIL/WARNING/INFO mapping and the
NOISY_KINDS exclusions (`unsafe-assign`, `unsafe-regex`) verbatim. The
`obfuscated-code` fingerprint detector is the hard part -- ship it as a stretch
goal.

(b) **Shell out to js-x-ray via a Node subprocess.** Exact parity, but adds a
Node runtime dependency to a pure-Python CLI -- contradicts the repo ethos
(CLAUDE.md, `uv` for everything Python). Reject as the default; acceptable only
as an optional `obfuscated-code` fallback if a user has Node.

(c) **Defer entirely.** Document the gap; recommend operators run the
auditor-app's Apps Audit for malware analysis.

### 4.3 Recommendation

**Defer to its OWN future PR (post-release), and when built, take option (a) with
tree-sitter, opt-in.** Rationale:

- It is opt-in like `--sharing-graph`: fetching and parsing app bundles is far
  heavier than our posture reads, makes many extra requests, and downloads code.
  It must NOT run in the default audit. Gate behind an explicit
  `--scan-app-bundles` (or a separate `apps-static-analysis` check key that is in
  CANONICAL_CHECKS but NOT in the default `IMPLEMENTED`/run set, requiring `--only
  apps-static-analysis`).
- Guardrail implications: this needs a NEW allowlist concept. Today GET_ALLOWLIST
  is `/api/*` paths; app bundles live under `<app.baseUrl>/index.html` and
  `<contextPath>/api/apps/<key>/index.html` and arbitrary same-origin `/assets/*`
  script URLs. The guardrail must be widened to "same-origin under the instance
  base, GET-only, <=5 MB, same-origin scripts only (never cross-origin fetch)".
  That is a deliberate, reviewed widening of the read surface and belongs in the
  guardrail doc + test, not a silent addition.
- A first cut ships unsafe-stmt / unsafe-import / encoded-literal / weak-crypto /
  short-identifiers cheaply; `obfuscated-code` is a documented stretch goal
  (option (b) subprocess as an optional enhancement).
- Effort: L (a full sub-plugin: bundle fetcher with `asyncio.Semaphore` bounded
  concurrency mirroring `maxAppAuditConcurrency`, HTML `<script src>` parse via
  selectolax/lxml, `urljoin` same-origin resolution, tree-sitter analyzer,
  severity mapping, new guardrail surface, three-tree wiring, a substantial test
  corpus of benign vs malicious bundles). Realistically 1-2 dedicated PRs on its
  own, separate from the section-3 gaps. Do NOT pretend it is trivial.

## 5. Proposed PR grouping (cheapest, highest-signal first)

Mirrors the 8a/8b/8c sizing (small/medium, ~<=15 files). Ordered so each PR is
independently shippable and reviewable.

- **PR A -- settings verdict top-ups (XS-S).** 3.2 (standalone email-verification
  WARN), 3.3 (non-empty CORS INFO). Pure `settings_audit.py` reducer edits + one
  reducer test. No allowlist, no `_wire`, no model change. Highest signal-per-line.
  Files: `settings_audit.py`, `test_security_settings*.py`, `FEATURES.md`.
- **PR B -- transport header grading (S-M).** 3.5 (HSTS max-age), 3.6 (CSP
  directive parse), 3.7 (COOP/COEP/CORP, shipped as a single aggregated WARN/INFO
  after confirming DHIS2 defaults). Extends `transport.py` (+ optional `csp.py`),
  `TransportHeaders` fields. One reducer test file. No new endpoint.
  Files: `transport.py`, `csp.py`(new), `__init__.py`, `test_security_transport.py`,
  `BUGS.md`, `FEATURES.md`.
- **PR C -- runtime CORS response headers (S).** 3.4. Extends `transport` with the
  synthetic-Origin probe + ACAO/ACAC findings. Carries the guardrail-note update
  for the synthetic Origin header.
  Files: `transport.py`, `guardrails.py` (note only), `test_security_transport.py`,
  `test_security_guardrails.py`, `FEATURES.md`.
- **PR D -- all-account hygiene (S-M).** 3.8 (never-logged-in / stale for all
  active accounts, AGGREGATED). Extends `hygiene.py`. No `_wire`.
  Files: `hygiene.py`, `audit.py` x3 (only if the user fetch needs widening),
  `test_security_hygiene.py`, `FEATURES.md`.
- **PR E -- password-age (M).** 3.9. The one PR with a real `_wire.py` split
  (v41 nested vs v42/v43 flat `passwordLastUpdated`). BUGS.md entry for the field
  divergence.
  Files: `hygiene.py` (or `password_age.py`), `_wire.py` x3, `audit.py` x3,
  `test_security_*`, `BUGS.md`, `FEATURES.md`.
- **PR F -- privileged-authority taxonomy (S).** 3.10. Add F_PUBLIC_ROUTE_ADD /
  F_IMPERSONATE_USER to the dangerous-authority taxonomy; descope the
  holder-count threshold.
  Files: `authorities.py`, `roles.py`, `test_security_roles.py`, `FEATURES.md`.
- **PR G+ -- js-x-ray static analysis (L, post-release, opt-in).** Section 4. Its
  own 1-2 PRs with the new same-origin bundle-fetch guardrail surface and the
  tree-sitter analyzer. Explicitly NOT in the default run set.

Ordering rationale: A/B/C are pure reducer/header work with no version divergence
(cheap, high signal). D/E close the real user-coverage gaps (D cheap, E carries
the only `_wire` split). F is a taxonomy tweak. G is the strategic stretch.

## 6. Where we are already ahead (do not regress / re-add)

The gap is one-directional. Our scanner has whole checks the app lacks; the gap
analysis above must not be read as "the app is more complete". We are ahead on:

- **Version / EOL / advisory floor**: parsed version -> EOL (< line 41),
  newer-line-available, and a GHSA-mapped advisory patch-floor table (41/42/43).
  The app only reads `version` for field-gating; it has no advisory awareness.
- **Default-credential probe**: we bound it (MAX_PROBE_ATTEMPTS=1, no retry,
  inconclusive-status handling). Equal-or-stronger than the app's probe.
- **Guest anonymous reads**: unauthenticated GET of `/api/users` (CRITICAL),
  `/api/userRoles`/`/api/me` (HIGH), self-registration role, account recovery.
  The app has none of this.
- **Routes SSRF**: literal-host private/loopback/link-local/internal detection
  with numeric-IP-encoding bypass normalization (decimal/hex/octal/short-form),
  cloud-metadata detection, subpath-wildcard, no-required-authorities. The app
  has no route analysis.
- **Tokens (PAT)**: inventory + non-expiring + no-IP-allowlist + account-scope
  caveat. The app has none.
- **Audit-config**: dhis.conf parsing for audit posture with
  redaction-by-construction (no API equivalent). The app has none.
- **OAuth2 clients**: broad-grant / loose-redirect analysis. The app does not
  inspect oAuth2Clients.
- **Sharing explorer**: external-access, public-write/read on data/metadata
  objects, SQL-view exposure. The app has none.
- **X-Content-Type-Options nosniff** transport check: the app does NOT check it;
  we do.
- **2FA enrolment gaps** (per-account, v41 user-field vs v42/v43 endpoint): the
  app does not check 2FA at all.

Net: every section-3 item is additive hardening over an already-broader scanner.
The js-x-ray bundle analysis (section 4) is the only capability the app has that
represents a genuinely new CLASS of capability for us, and it is correctly scoped
as a post-release opt-in sub-project.
