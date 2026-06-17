# Security scanner: plan

Author: Morten (Morty)
Date: 2026-06-13
Status: PLANNED. Decisions locked 2026-06-13 (see Decisions locked). Branch: `feat/security-audit-scanner`. Greenfield feature plan; supersedes the scrapped migration docs.

This is a fresh plan for a first-party DHIS2 security scanner in the `security` plugin. It reuses ideas and concepts from the old standalone `dhis2-security-scanner`, not its code. It builds on the foundation already shipped in this repo and adds the headline experience: a single `d2w security audit` command that runs every check step by step, shows live progress, and streams a readable report to disk as it goes so nothing is lost if the connection drops, and so an interrupted run can resume.

## What already exists (build on this, do not redo)

Shipped in PR #369 (merged 2026-06-12) and the releases around it:

- `dhis2w_core/security_core/`: the shared, version-agnostic core. Holds the 8-category dangerous-authority taxonomy (`authorities.py`), the guardrail contract as code (`guardrails.py` with `GET_ALLOWLIST` and `CONNECT_PATHS`), the base result models (`models.py`), and the findings scaffolding (`findings.py`).
- `d2w security settings`: read-only security slice of `/api/systemSettings` (`SecuritySettings`, a typed projection per BUGS.md #42).
- `d2w security authorities`: the caller's own effective authorities, categorised, with a superuser flag.
- Per-version plugin trees `dhis2w_core.v{41,42,43}.plugins.security` with thin `service.py` + `cli.py`.
- The guardrail test (`tests/security/test_security_guardrails.py`) and the live taxonomy-contract test (`tests/security/test_security_taxonomy_contract.py`).
- Render primitives in `dhis2w_core.v{N}.cli_output` (`render_detail`, `render_list`, `ColumnSpec`, `DetailRow`, `format_bool`, `is_json_output`). `rich>=15` and `typer>=0.26` are already dependencies.

The new work extends `security_core` and the plugin trees. It does not touch the shipped `settings` / `authorities` commands except to register them as steps in the audit.

## What we are building

1. `d2w security audit`: the centerpiece. Runs all checks in a fixed order, renders a live `Step k of N` progress display with a spinner per step, and streams the report to disk incrementally (crash-safe), resumable after an interruption.
2. Granular subcommands, one per check group, each reusable by the audit and runnable standalone (`roles`, `hygiene`, `version`, `apps`, `guest`, `sharing`, `transport`, `auth-methods`, `tokens`, `routes`, `audit-config`, plus a credential probe).
3. An active default-credential login probe (admin/district), on by default. This is a required capability and it changes the guardrail posture (see below).
4. An auditing-settings check, API-first, with an optional `dhis.conf` read for the server-side parts the API does not expose.
5. A typed report model rendered to four human formats (Markdown, plaintext, CSV, HTML) plus a JSON/JSONL machine spine, written as the scan progresses, with an interrupted run resumable from disk.

## Decisions locked (2026-06-13)

1. Credential probe tests exactly one pair out of the box: `admin/district`. It is by far the most common live default, so no other pairs are seeded. On by default; `--no-credential-probe` disables it.
2. Report formats: Markdown, plaintext, and CSV, and HTML, all first-class. JSON/JSONL is the machine spine underneath them. `--format` selects a subset; default writes all of them.
3. Resumability: yes. An interrupted run can resume from the on-disk JSONL spine and skip the checks already completed.
4. Output location: the current working directory by default, overridable with a `--output-dir` parameter.
5. `audit-config` is API-first. An optional `--dhis-conf PATH` (env `DHIS2_CONF_LOCATION`, same canon as the rest of the CLI) lets it also read the server config file for the audit settings the API does not expose. Secrets in that file are never written to the report.
6. Scope of v1: land the whole catalog, not a spine-only first release.
7. Branch `feat/security-audit-scanner` (created).

## Implementation progress

- **PR 1 (audit framework): implemented and verified on `feat/security-audit-scanner` (2026-06-13).** Shipped the version-invariant core in `security_core` (the `Finding`/`CheckResult`/`RunManifest`/`AuditSummary`/`AuditReport` models, the ordered check registry with `resolve_check_keys` validation, the four renderers md/txt/csv/html, the crash-safe streaming `ReportWriter` with JSONL spine + fsync + atomic finalize + resume + no-clobber, the `run_audit` orchestrator, and the single-source guardrail note), plus the per-tree `audit.py` orchestration and the `d2w security audit` / `d2w security report` commands wired across v41/v42/v43. The two already-shipped checks (`settings`, `authorities`) run as the first steps. Examples (3 trees), `features.md`, and the regenerated `cli-reference.md` are in sync. Gate: ruff + mypy + pyright clean; 66 security tests and the full 522-test dhis2w-core suite green; an adversarial review pass was run and its must-fix findings (guardrail-note honesty, finalize handle-leak, resume-of-completed-run corruption) plus the cheap safety items (selection/format validation, resume profile/target guard, folder-collision precision) were all addressed. The credential probe is intentionally NOT in this PR; it lands in PR 2 and flips the single guardrail-note constant.

## Guardrail posture change (the important one)

The shipped contract is "GET only, against `GET_ALLOWLIST`, never retry 401/403." Adding the default-credential probe deliberately relaxes the GET-only rule. The revised contract:

- Read-only GETs against `GET_ALLOWLIST` for everything except the credential probe.
- The credential probe may make at most one authentication attempt for the single default pair `admin/district`, against the identity endpoint only (`GET /api/me` with HTTP Basic), never retried.
- Everything else stands: never retry 401/403, no data values / tracked entities / events / files / audit logs are ever read, the only direct external egress is the release feed, traffic stays identifiable via the client User-Agent, pre-v41 is refused with the explicit EOL message.
- An optional `--dhis-conf PATH` reads a local server config file. It parses only the security-relevant keys and reports posture, never the secret values it contains (db password, encryption password, SMTP/SMS credentials are redacted to "set / not set").

This is encoded, not just documented. `guardrails.py` grows a `CREDENTIAL_PROBE_PATHS` constant and `MAX_PROBE_ATTEMPTS = 1`. The guardrail test asserts the probe never retries and never touches a non-probe path with anything but GET.

### Lockout handling for the credential probe

A wrong attempt counts toward the failed-login lockout counter when `keyLockMultipleFailedLogins` is enabled, so the probe is careful:

- It reads `keyLockMultipleFailedLogins` first and prints a prominent warning before probing when lockout is active: a wrong guess contributes to locking the real admin account.
- It tries exactly one attempt, no retry, no backoff loop.
- When lockout is enabled it warns and continues. A single attempt is below the typical multi-failure lockout threshold, so warn-and-continue is the default rather than abort. (If you would rather abort on an active lockout setting, that is a one-line policy flip.)
- On a resumed run, an already-completed probe is not repeated.
- A 200 is a CRITICAL finding ("default credentials accepted"). A 401 passes. Anything else is reported inconclusive.

Mechanism: build a throwaway `BasicAuth(username="admin", password="district")` (`dhis2w_client.v{N}.auth.basic`), open a short-lived `Dhis2Client` against the already-resolved base URL, one `GET /api/me`, capture the status, close. This is the only place the scanner authenticates as anything other than the operator's own profile.

## Architecture

```
packages/dhis2w-core/src/dhis2w_core/
  security_core/                      # shared, version-agnostic
    authorities.py                    # (shipped) taxonomy + categorise
    guardrails.py                     # (shipped, extended) allowlist + probe contract
    models.py                         # (shipped, extended) result models
    findings.py                       # (shipped, extended) Finding + Severity + shaping
    versions.py                       # version/EOL classification + advisory patch floor
    releases.py                       # live releases.dhis2.org feed, TTL cache
    hygiene.py                        # per-user predicates over typed User/Me
    sharing.py                        # public/external sharing predicates
    transport.py                      # TLS/header verdicts from response headers
    credentials.py                    # the admin/district probe verdict shaping
    dhisconf.py                       # optional dhis.conf parse (audit keys), secret redaction
    registry.py                       # ordered Check registry (drives Step k of N)
    report/                           # AuditReport model + renderers
      model.py                        # AuditReport, RunManifest, AuditSummary
      markdown.py  text.py  csv.py  html.py
    streaming.py                      # ReportWriter: JSONL spine, fsync, atomic finalize, resume
  v42/plugins/security/
    service.py                        # thin: open_client + orchestrate + call core
    audit.py                          # the orchestrator: iterate registry, stream, progress
    cli.py                            # audit + granular subcommands
    mcp.py                            # cheap reads only (later)
    _wire.py                          # per-tree extractors (lastLogin, 2FA field, appType)
  v41/plugins/security/               # same shims; _wire.py differs where it must
  v43/plugins/security/
```

Core security opinion (taxonomy, EOL/advisory judgement, hygiene predicates, severity shaping, report rendering) lives once in `security_core`. Only genuinely version-divergent wire extraction is triplicated in `_wire.py`. Tests live once under `packages/dhis2w-core/tests/security/`, parametrised over the three trees.

### Check model and registry

Every check is a small object with a stable key, a human label, a severity ceiling, and an async `run(context) -> CheckResult`. The registry is an ordered tuple, so the audit knows `N` up front and emits `Step k of N: <label>`.

```python
class Severity(StrEnum):
    critical = "critical"; high = "high"; medium = "medium"; low = "low"; info = "info"

class Finding(BaseModel):
    check: str
    severity: Severity
    title: str
    detail: str
    evidence: dict[str, str] | None = None   # render-only bag inside the model, never crossed as a bare dict

class CheckResult(BaseModel):
    check: str
    label: str
    status: Literal["ok", "skipped", "degraded", "error"]
    findings: list[Finding] = []
    note: str | None = None                  # degradation reason, e.g. hub unreachable

class RunManifest(BaseModel):
    target: str
    profile: str
    scanner_version: str
    dhis2_version: str | None
    started_at: str                          # stamped by the CLI, not in the core, to keep the core deterministic
    check_order: list[str]                   # the selected steps, in order; resume validates against this

class AuditReport(BaseModel):
    manifest: RunManifest
    results: list[CheckResult] = []
    summary: AuditSummary
```

All result types are pydantic (rule 7). The one `dict[str, str]` on `Finding.evidence` is a render-only bag inside a model, never passed across a module boundary as a bare dict.

### Streaming, crash-safety, and resume

The requirement is: stream to disk so a dropped connection never loses finished work, and let an interrupted run resume. Design around a single per-run folder and a JSONL spine.

- A run writes to a folder, default `./dhis2-security-<profile>-<timestamp>/` in the current working directory, redirected by `--output-dir`. The folder holds `manifest.json`, `report.jsonl`, and the rendered `report.md` / `report.txt` / `report.csv` / `report.html`.
- At start, write `manifest.json` (target, profile, scanner + DHIS2 version, the ordered check list) and fsync. This is what `--resume` validates against.
- `report.jsonl` is the crash-safe spine: after each check completes, append its `CheckResult` as one line, `flush()` + `os.fsync()`. The spine always reflects every finished step.
- `report.md` is also streamed live (header up front, a section appended and fsynced per step) so the human file is readable mid-run. `report.txt`, `report.csv`, and `report.html` are rendered from the accumulated results at finalize, and can be re-rendered from `report.jsonl` at any time, including after a crash.
- On full completion, append the summary, render the remaining formats, and write a `COMPLETE` marker into the manifest.
- `--resume <folder>`: read `manifest.json` and `report.jsonl`, confirm the target/profile/version and check order match, skip every check already present in the spine, and continue from the next step. An already-completed credential probe is not re-run.
- `--format md,txt,csv,html,json` selects which human formats to render (default: all). The JSONL spine is always written because resume depends on it.
- `d2w security report <folder> --format html` re-renders any format from an existing run's spine without re-scanning, which also covers "I lost the connection, give me the HTML from what completed."

### Progress UI

The orchestrator drives a `rich` progress display: a step counter `Step k of N`, the current check label, and a spinner, marking each step done / degraded / failed as its `CheckResult` arrives. When stdout is not a TTY, or `--json` / `--quiet` is set, it falls back to plain one-line-per-step logs (`[3/14] roles: ok (2 findings)`), so logs and redirected output stay clean. Progress goes to stderr; the report goes to the folder; `--json` to stdout stays pure.

## The checks

Grouped by subcommand. Severity is the ceiling; the actual finding severity depends on what is observed.

### audit (orchestrator)

Runs the steps below in this order, which is the `Step k of N` sequence. Cheap and high-signal first, broad/expensive last:

1. version  2. transport  3. settings  4. authorities  5. roles  6. hygiene  7. credential-probe  8. guest  9. apps  10. sharing  11. auth-methods  12. tokens  13. routes  14. audit-config

`--checks a,b,c` runs a subset; `--skip x` drops steps; `--no-credential-probe` disables step 7. `N` adjusts to the selected set.

### version

- EOL version (below v41 refused with the explicit message).
- Outdated minor (`upgrade available: 2.N`).
- Known-advisory patch floor: a curated table mapping each minor to the lowest patch that clears published DHIS2 security advisories; below it is HIGH with the advisory reference. This is "running versions with unfixed security issues" and needs a maintained table sourced from DHIS2 advisories.
- Version string stripped (INFO; weakens the advisory check).

### transport

- HTTP base URL (HIGH: credentials in clear text).
- No HSTS header on HTTPS (MEDIUM).
- Missing CSP / X-Frame-Options / X-Content-Type-Options, cross-checked against `keyCspEnabled` (LOW to MEDIUM).
- Server version disclosure in the `Server:` header (LOW).

Reads response headers already on the wire; no new allowlist entry.

### settings (extend the shipped command)

- Weak password policy: `minPasswordLength` < 8 or no `credentialsExpires` (MEDIUM). Password rotation lives here.
- No failed-login lockout: `keyLockMultipleFailedLogins=false` (MEDIUM).
- 2FA not enforced globally (MEDIUM): verify the exact key per version; report "per-user only" when there is no global key.
- Users can grant their own authorities: `keyCanGrantOwnUserAuthorityGroups=true` (HIGH, direct privilege escalation).
- Permissive CORS: wildcard in `keyCorsWhitelist` (MEDIUM).
- Email not configured while recovery / email-2FA on (LOW).
- Unique-email enforcement (verify key exists; else lean on the hygiene missing-email flag).

### authorities (shipped)

No change beyond registering it as a step.

### roles

- Roles granting ALL, with member fetch; CRITICAL when active members exist.
- Roles in any dangerous category (HIGH).
- Distinct ALL-holder count for the summary scorecard.

### hygiene

Per-user, joined to dangerous-role membership. One row per flagged user.

- Superuser without 2FA (CRITICAL). The 2FA field name varies across versions (`twoFactorType` vs `twoFA`); resolved in `_wire.py`, BUGS.md if a tree diverges. Highest-value hygiene signal.
- Never logged in / stale admin (90d, `--stale-days`) / missing email / suspicious username / disabled-but-privileged / account-expiry-in-past-but-enabled.
- Full last-login inventory with active vs disabled counts (INFO): the "old unused accounts" and "deactivated vs active" tables.
- Seed-account presence: the well-known `admin` account exists and is enabled (read-only signal that complements the active credential probe).

### credential-probe (on by default)

The active default-credential test of `admin/district`, per the guardrail and lockout design above. CRITICAL when it authenticates.

### guest

Uses a named anonymous-GET boundary on `dhis2w-client` (a small client-side addition, may ship as its own client PR before this check).

- Anonymous data leak on `/api/me`, `/api/users`, `/api/systemSettings`, `/api/userRoles` (CRITICAL for users/settings).
- Self-registration enabled (`/api/configuration/selfRegistrationRole`) and self-registration without captcha (`keySelfRegistrationNoRecaptcha`) (HIGH).
- Account recovery enabled (INFO, MEDIUM combined with weak email uniqueness).

### apps

- Side-loaded app (no `app_hub_id`): untrusted frontend code (HIGH).
- Update available vs App Hub latest (MEDIUM).
- Custom JS/CSS configured (HIGH, verify read path).
- Preserve the `hub_unreachable` vs `not_in_hub` degradation so an App Hub outage never reads as "all untrusted".

### sharing

- Public-write metadata on dataSets, programs, sqlViews, dashboards, documents (HIGH for data-bearing types).
- Public-read sensitive metadata (MEDIUM).
- `externalAccess=true` objects, reachable with no login (HIGH).
- SQL views inventory and broadly-readable QUERY/VIEW views (MEDIUM).
- Defer: overlapping / boundary-crossing sharing-tree analysis (graph work, follow-up).

Paged, GET-only, capped by `--max-objects` with a logged truncation note (silent truncation reads as "all clear").

### auth-methods

- Configured login providers via `/api/loginConfig` (OIDC, SAML offered on the login page) (INFO).
- OAuth2 clients via `/api/oAuth2Clients`: flag broad grants or wildcard redirect URIs (MEDIUM).
- LDAP / SAML / OIDC enablement is largely dhis.conf and not API-readable; report only what the API proves (the `--dhis-conf` option can fill some of this in).

### tokens

- PAT inventory via `/api/apiToken`: count, type, expiry, IP allowlist, scoped authorities (MEDIUM). Confirm whether the endpoint enumerates system-wide or only the calling account; scope the claim to what it actually returns.
- Non-expiring or over-scoped PAT (HIGH, within readable scope).

### routes

- `/api/routes` inventory (2.41+): destinations and auth headers; HIGH when a route targets a private or cloud-metadata address (SSRF). Adding `/api/routes` to the allowlist is a reviewed change.

### audit-config

Report DHIS2 auditing posture. API-first, with an optional config-file read.

- API surface: report whatever audit-related system settings are readable and what they say. When nothing is API-readable, state that plainly ("audit config is server-side; not verifiable via the API") rather than implying auditing is off.
- Optional `--dhis-conf PATH` (env `DHIS2_CONF_LOCATION`): parse the server config for the audit keys the API does not expose (`audit.logger`, `audit.database`, `audit.metadata`, `audit.tracker`, `audit.aggregate`) and report whether each audit channel is on. Flag audit being off or narrowly scoped (MEDIUM).
- Secret redaction is mandatory: the parser reads only the audit keys and reports posture; any credential-bearing key it happens to see (db password, encryption password, SMTP/SMS secrets) is reported as "set / not set", never echoed. Encoded and tested.

## Report format (the easy files)

A run produces a folder of reports sharing one base. The human formats:

- Markdown (`report.md`): the easy file, readable in any editor and on GitHub. Header (target, timestamp, scanner + DHIS2 version, support status), a scorecard of counts by severity, one section per check in run order with findings sorted by severity, degraded/skipped checks listed honestly, and a footer guardrail statement of what was and was not touched.
- Plaintext (`report.txt`): the same content, no markup, for terminals and pipes.
- CSV (`report.csv`): one row per finding (check, severity, title, detail, key evidence) for spreadsheets and diffing.
- HTML (`report.html`): a self-contained styled report (inline CSS, no external assets) for sharing and printing.
- JSON spine: `manifest.json` plus `report.jsonl` (one `CheckResult` per line); the assembled `AuditReport` is available via `--format json`. This is the machine record and the resume source.

Timestamps are passed in by the CLI, not generated inside the core, so the core stays deterministic and testable.

## Phasing

Land the whole catalog (decision 6), on `feat/security-audit-scanner`, split into reviewable PRs that each ship their tests (parametrised over the three trees), examples under `examples/v{41,42,43}/`, `FEATURES.md` rows, `docs/` updates, and `BUGS.md` entries where a divergence surfaces. Commit signing is required (GPG key C64F35A7CC42BF6B, committer `msvanaes@dhis2.org`).

- PR 1, audit framework: the `Finding` / `CheckResult` / `RunManifest` / `AuditReport` models, the `registry`, the streaming `ReportWriter` (JSONL spine + live Markdown + fsync + atomic finalize + resume), the four renderers (md/txt/csv/html), the `report` re-render subcommand, and the progress UI. The `audit` command wires the already-shipped `settings` and `authorities` as its first steps to prove the end-to-end skeleton before any new check logic. Extends the guardrail test for the streaming/report code.
- PR 2, credential probe + revised guardrail contract: the active `admin/district` probe, the `guardrails.py` extension, the lockout warning, and the updated guardrail test.
- PR 3, roles + hygiene: instance role audit, member fetch, per-user hygiene flags including superuser-without-2FA and seed-account presence; `_wire.py` for lastLogin and the 2FA field.
- PR 4, version: `versions.py` + `releases.py` + the advisory patch-floor table and the pre-v41 EOL degradation.
- PR 5, apps: installed-apps + App Hub join, side-loaded and update-available signals, hub-unreachable degradation.
- PR 6, guest: the anonymous-GET boundary on `dhis2w-client` (its own small client PR if needed) plus the guest probe and self-registration state.
- PR 7, sharing: public / external metadata sharing and the SQL-view inventory, capped and paged.
- PR 8, posture extras: `transport`, `auth-methods`, `tokens`, `routes`, `audit-config` (including the `--dhis-conf` parse with secret redaction), plus the `settings` verdict extensions. Splittable if it gets large; each carries its allowlist additions as reviewed changes.
- PR 9, MCP surface: cheap single-request reads (`security_settings`, `security_authorities`, `security_version`) mirroring the CLI. The long-running `audit` stays CLI-only.

PR 1 and PR 2 are the spine. PRs 3 to 8 fan out and only depend on the PR 1 framework. PR 9 is last. The feature is released only once the full catalog has landed.

## Still to confirm during build (you said we can find out)

- The exact 2FA field name per version (`twoFactorType` vs `twoFA`) on `/api/users`.
- Whether a global enforce-2FA key, a unique-email key, and session-timeout keys are API-readable on each supported version, or dhis.conf only.
- Whether `/api/apiToken` enumerates system-wide or only the calling account.
- The advisory patch-floor table contents and a maintenance source.
- The custom JS/CSS read path for the apps check.
- The exact set of audit-related keys readable via the API vs only via `--dhis-conf`.
