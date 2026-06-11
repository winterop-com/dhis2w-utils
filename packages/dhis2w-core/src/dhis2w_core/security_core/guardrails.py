"""The security plugin's responsible-use contract, encoded as code.

These constants are load-bearing. The guardrail test in
`packages/dhis2w-core/tests/test_security_guardrails.py` enforces them against
every public security service function, so a future check cannot silently
widen the plugin's read surface.

The contract:

- Read-only: the plugin issues ONLY GET requests, and only against
  `GET_ALLOWLIST`. It never reads data values, tracked entities, events,
  files, or audit logs.
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
