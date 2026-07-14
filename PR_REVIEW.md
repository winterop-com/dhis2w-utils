# Review: PR #452 — read-only DHIS2 security audit scanner

## Overview

Adds a `d2w security audit` CLI plugin plus a matching read-only MCP surface: 14
posture checks over a live DHIS2 instance, emitting JSON / terminal / interactive
HTML. A shared `security_core` engine holds the reducers, control catalog, and
report renderer; the per-version `audit.py` runners are triplicated across
v41/v42/v43. 132 files, ~26k additions, 30 test files.

This is a large, well-engineered PR. The read-only guarantee is encoded as an
enforced contract (not a comment), the SSRF host classification is thorough, the
error-isolation model is sound, and the test suite mostly proves the
security-relevant properties rather than asserting trivia. The concerns below are
a handful of correctness bugs in the verdict logic, one build-provenance blocker,
and some hygiene/convention cleanups.

## What's strong

- **The guardrail is architecture, not aspiration.** `guardrails.py` defines a
  GET-only path allowlist enforced by an httpx request hook (`GuardrailViolation`,
  deliberately not a `Dhis2ClientError`/`httpx.HTTPError` subclass so a check's
  degrade-catch cannot swallow it). A guardrail test drives a full real-client run
  across all three trees and asserts every recorded request is GET/HEAD, same-host,
  and allowlisted. The credential probe's "one attempt, never retried" claim is
  actually tested (decodes the Basic header to confirm `admin:district`, asserts
  `call_count == 1`).
- **`net.py` SSRF classification** normalizes the decimal/hex/octal-packed/
  octal-dotted IP encodings the JVM `InetAddress` accepts before classifying — a
  real bypass class handled correctly and exception-guarded.
- **The `event_hooks` client change is minimal and correct.** Stored, passed to
  `AsyncClient` only when non-`None`, applies at the client level so retries cannot
  bypass it; `CONNECT_PATHS` correctly allowlists the connect-time probes.
- **Report XSS surface is contained**: data is emitted as an external
  `report-data.js` JSON assignment (no inline `</script>` breakout) and flows
  through a virtual-DOM text path; XSS-containment is unit-tested by parsing the
  emitted payload.

## Findings

### Correctness bugs in verdict logic (a false PASS in a security tool is the worst failure mode)

1. **Report-only CSP falsely satisfies the anti-framing control** —
   `transport.py:103-114`. `csp_value` falls back to
   `Content-Security-Policy-Report-Only`, and `has_frame_ancestors` is derived from
   it. A response with only `Content-Security-Policy-Report-Only: frame-ancestors
   'self'` and no `X-Frame-Options` is reported PASS / protected, but report-only
   enforces nothing — the instance is clickjackable. The CSP-grade path already
   threads `report_only=enforced_csp is None`; the frame-ancestors check needs the
   same awareness. No test covers this exact combo.

2. **Expired-but-not-deleted PAT reported as HIGH "non-expiring permanent
   credential"** — `tokens.py:107-111`. `_is_non_expiring` returns `True` both for
   no-expiry tokens and for tokens whose expiry is already in the past. A token that
   expired two years ago (inert — DHIS2 rejects it server-side) is reported HIGH
   with detail "A token with no expiry is a permanent credential… grants standing
   API access until revoked." A stale-token-cleanup finding at low severity would be
   right; HIGH "permanent credential" is a mischaracterization.

3. **Token inventory roll-up is always MEDIUM** — `tokens.py:124` /
   `evaluate_tokens`. The purely-informational inventory finding is rated MEDIUM and
   recorded whenever any PAT exists, so a perfectly-configured token set (all
   expiring, all IP-restricted) still emits a MEDIUM. The equivalent roll-ups in
   `routes.py` and `hygiene.py` are INFO — this looks like a mis-rating that adds
   MEDIUM noise to every instance with tokens.

4. **`max-age=0` HSTS graded WARN, but missing HSTS is MEDIUM** —
   `transport.py:168-197`. The two states provide identical (zero) protection;
   `max-age=0` (which actively deletes cached HSTS state) is arguably worse, yet
   scored lower. Inconsistent.

5. **Naive timezone drop in hygiene date math** — `hygiene.py:380-382,400-401`.
   `_is_stale`/`_has_stale_password` do `.replace(tzinfo=None)`, which drops an
   offset rather than converting it; if DHIS2 returns an offset-bearing
   `lastLogin`/`passwordLastUpdated` against a UTC `now`, the day-boundary
   comparison is off by the offset. Small impact, real imprecision.

The rest of the check logic (version parsing/comparison and advisory floors, CSP
grading, roles/authorities dominance, apps tuple-versioning, settings three-valued
logic, dhisconf parsing, auth-methods redirect logic) was reviewed and is correct.

### Version-tree parity — sed-sweep corrupted cross-version facts

The three trees are behaviorally in parity, but a `s/v42/vNN/` sweep substituted
the tree's own version into strings that state a cross-version fact and should read
identically everywhere:

- `cli.py:154` — the `--two-factor-detail` help says "On v41+" (v41) / "On v43+"
  (v43) instead of "On v42+". Worse, per BUGS.md #58 the `/api/users/twoFactor`
  endpoint does not exist on v41, so the flag is silently inert there — the v41 help
  text tells the user it works. Fix the string in all three, and have v41 note the
  flag is a no-op.
- `audit.py:608` — docstring reads `F_OAUTH2_CLIENT_MANAGE on v43/v43` (nonsense)
  and `on v41/v43` in the other trees; should be `v42/v43`.

The genuine `_wire.py` v41-vs-v42/v43 divergence (per-user 2FA read, nested
`passwordLastUpdated`, route auth union, token/OAuth2 shapes) is intentional and
each piece cites a real BUGS.md entry — that part is done right.

### Orchestration

6. **Progress reporter leaked on the exception path** — `orchestrator.py`.
   `reporter.finish()` sits after the `finally`, which only calls `writer.close()`.
   Any exception from `writer.write_result`/`finalize` skips `reporter.finish()`,
   leaving the Rich `Live` display (and its refresh thread) running and the terminal
   corrupted. Stop the reporter in the `finally` (or make it a context manager). Not
   triggered by a check failure (those are isolated), only by writer/reporter errors.

### Build provenance — should block for a security tool

7. **The report runtime cannot be audited or rebuilt from source.**
   `report/assets/support.js` (1513 lines) is a generated bundle whose header says
   `GENERATED from dc-runtime/src/*.ts … Rebuild with bun run build`, and
   `dc-runtime` exists in no git ref. The PR's own `report/assets/README.md`
   documents this as a provenance gap headed "ACTION REQUIRED" with a three-step
   remediation. For a security tool, the code that renders server-supplied strings
   into a browser and holds the HTML-escaping logic is exactly what a reviewer must
   read in source form — the XSS-safety read above was of the opaque bundle, not
   auditable source. Land `dc-runtime` sources + a reproducible `make` target in
   this PR, or replace the bundle with the hand-maintained vanilla-JS approach
   already used by the sibling `sharing-runtime.js`.

### Repo hygiene

8. **Personal machine path in shared CLAUDE.md** — the new "DHIS2 backend source
   available locally" section hardcodes `/Users/netromsb/develop/dhis2/GARAGE/SLOT3/dhis-2`
   (not even this checkout's user). Instructions to "read the source there" silently
   fail for everyone else. Belongs in the developer's private `~/.claude/CLAUDE.md`.
9. **CLAUDE.md now mandates syncing `FEATURES.md`, which does not exist** on either
   branch — the real catalog is `docs/project/features.md`. Name the real path or
   create the root file.
10. **Root plan-file clutter** — 5 `*_PLAN.md` at repo root; only one is wired into
    the docs nav, the other four are orphaned, with inconsistent naming
    (`DHIS2_Security_Report_Redesign_PLAN.md` vs SCREAMING-KEBAB). Either give each a
    `docs/project/planning/` page or move them there.
11. **CHANGELOG references uncommitted local state** — the top entry points readers
    at a `.pc/` scaffold and a `pc` tool that are not in the branch (and are not
    gitignored). Fails the "reader coming in cold" standard.
12. Minor: `sharing/assets/` has d3 + logo but no README/ISC-license text
    (attribution sits in the sibling `report/assets/README.md`); the DHIS2 logo is
    committed twice byte-identically and shipping it in a PyPI package is a small
    trademark note worth adding; the `.gitignore` PNG carve-out covers `report/assets`
    but not the `sharing/assets` twin; theme-toggle glyphs (sun/moon) in
    `sharing-runtime.js` and status glyphs in `report.dc.html` are a judgment call
    against "NO EMOJIS EVER."

### Conventions (mostly clean; rule 7 is where it matters here)

- Architecture is sound: zero `@dataclass`, services return typed models, MCP dumps
  at the tool edge, generated OAS models reused (`ApiToken`, `Dhis2OAuth2Client`,
  `LoginConfigResponse`, `Route`).
- **`dict[str, Any]` crossing into `_wire.py`** —
  `two_factor_enabled`/`last_login`/`password_last_updated(user: dict[str, Any])`
  (v42 `_wire.py:46,51,57`) and `oauth2_clients(raw: dict[str, Any])`.
  `tokens_from_raw` in the same file already validates raw records through the
  generated `ApiToken`; the User-shaped ones should do the same through the generated
  `User` schema, which eliminates the dict params. The author may argue `_wire.py`
  is the parse seam, but these hit rule 7's stated code-review trigger.
- **Tuple-as-struct returns** (banned in new code) — several, clearest at
  `audit.py:749` returning a 4-tuple whose docstring names the fields; make it a
  frozen `BaseModel`.
- `obj` parameter naming (abbreviation) across `sharing/*` — use
  `object_node`/`fetched_object`. A few nested-closure docstrings missing; one
  unparameterized `list` annotation in `client_context.py`.

### Test coverage

Strong overall — all 14 checks have dedicated tests, guardrail enforcement and the
credential-probe contract are genuinely proven, XSS-containment is parsed and
asserted. Two gaps: the full-run guardrail test asserts only on recorded calls (a
false-positive guardrail block that turns a check into `ERROR` stays green — add a
"no result is ERROR" assertion) and never exercises data-driven URL construction
(the sharing scan's `f"/api/{focus.plural}"` from `/api/schemas`);
`MAX_PROBE_ATTEMPTS` is a spec-only constant, enforced structurally rather than
referenced.

## Verdict

Solid, careful work with an unusually rigorous safety model — but not mergeable
as-is. Before merge: the report-runtime source + reproducible build (#7), the two
verdict-logic false-signal bugs (#1 report-only CSP, #2 expired-PAT), the sed-drift
string fixes (cli.py:154 / audit.py:608), and the reporter-leak (#6). The personal
path (#8) and phantom `FEATURES.md` (#9) are quick fixes worth doing in-branch. The
severity re-ratings (#3, #4), tuple/dict convention cleanups, plan-file placement,
and license/provenance notes are follow-up-able but should at least be acknowledged
in the PR description.
