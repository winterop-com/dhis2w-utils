"""The security plugin's responsible-use contract, encoded as code.

These constants are load-bearing. The guardrail test in
`packages/dhis2w-core/tests/security/test_security_guardrails.py` enforces them against
every public security service function, so a future check cannot silently
widen the plugin's read surface.

The contract:

- Read-only: every check issues ONLY GET requests against `GET_ALLOWLIST`.
  The one exception is the default-credential probe (see below). The plugin
  never reads data values, tracked entities, events, files, or audit logs.
- Credential probe: the probe may make at most one HTTP Basic login attempt,
  for the single well-known default pair `admin`/`district`, against the
  identity endpoint only (`GET /api/me`, in `CREDENTIAL_PROBE_PATHS`). It is
  never retried (`MAX_PROBE_ATTEMPTS == 1`) and is the only place the scanner
  authenticates as anything other than the operator's own profile.
- No-lockout: 401/403 responses are never retried; retries (when enabled at
  all) cover only 429/5xx on idempotent calls, and the default is no retry.
- Egress: the only direct external egress is the public release feed
  (releases.dhis2.org). The App Hub join is proxied by the target instance
  via `GET /api/appHub` (DHIS2 fetches the hub server-side); the client never
  contacts apps.dhis2.org itself, hub URLs are constructed for display only.
- Identifiable traffic: requests carry the d2utils client's default
  User-Agent, so plugin traffic stays identifiable as tooling in
  target-server access logs. The client exposes no per-command User-Agent
  hook today; if one lands, the security plugin should tag its commands.
- Version floor: pre-v41 servers are refused with an explicit "older than
  v41, EOL by definition, unsupported" message, never a raw connect
  traceback.
"""

from __future__ import annotations

# Every path the security plugin is allowed to GET, matched exactly against
# `httpx.URL.path`. Adding an endpoint here is a reviewed decision, not a
# side effect of adding a feature. The list covers the full planned surface
# (settings, authorities, roles, hygiene, guest, apps, access, version) so a
# later check that stays inside it needs no allowlist edit.
GET_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/api/system/info",
        "/api/me",
        "/api/me/authorization",
        "/api/userRoles",
        "/api/users",
        "/api/dataSets",
        "/api/programs",
        "/api/dataElements",
        "/api/indicators",
        "/api/dashboards",
        "/api/visualizations",
        "/api/eventReports",
        "/api/maps",
        "/api/sqlViews",
        "/api/apps",
        "/api/appHub",
        "/api/configuration/selfRegistrationRole",
        "/api/systemSettings",
    }
)

# Paths the client's connect machinery touches before any plugin code runs
# (canonical base-URL probe + version detection). Kept separate so
# `GET_ALLOWLIST` stays exactly the documented plugin read surface.
CONNECT_PATHS: frozenset[str] = frozenset({"/", "/api/system/info"})

# The single default-credential pair the probe tests. admin/district is by far
# the most common live DHIS2 default (DefaultAdminUserPopulator seeds it on a
# fresh install), so no other pairs are seeded.
DEFAULT_PROBE_USERNAME = "admin"
DEFAULT_PROBE_PASSWORD = "district"

# The credential probe's footprint, bounded as tightly as the contract allows:
# at most one authentication attempt, against the identity endpoint only, never
# retried. The guardrail test asserts the probe touches no other path and makes
# no more than this many attempts.
CREDENTIAL_PROBE_PATHS: frozenset[str] = frozenset({"/api/me"})
MAX_PROBE_ATTEMPTS = 1

# One-line statement of the audit's footprint, embedded in every rendered
# report so a reader can see exactly what the scan did and did not touch. Kept
# in lock-step with the contract above and the credential-probe posture.
REPORT_GUARDRAIL_NOTE = (
    "This audit issues only read-only GET requests against a fixed allowlist. The single exception "
    "is the optional default-credential probe, which makes at most one HTTP Basic login attempt for "
    "the well-known admin/district pair against /api/me, never retried. The audit never reads data "
    "values, tracked entities, events, files, or audit logs."
)
