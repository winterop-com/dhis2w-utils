"""Per-control outcome catalog: every rule a check evaluates, with a live PASS/FLAGGED/SKIPPED result.

A check's findings are only the controls that tripped. To let the report list everything a check
looked at, each check declares its controls once in `CONTROL_CATALOG` and its reducer records, via a
`ControlLog`, whether each control passed, flagged (produced findings), or was skipped (could not run
this run). The reducer returns a `CheckOutcome` carrying both the findings and the resolved controls.
"""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity, severity_rank


class ControlStatus(StrEnum):
    """Outcome of one control this run."""

    PASSED = "PASS"
    FLAGGED = "FLAGGED"
    SKIPPED = "SKIPPED"


class ControlSpec(BaseModel):
    """One catalog entry: a stable control id and the human label the report shows."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str


class ControlOutcome(BaseModel):
    """One control's resolved result: its status plus, when flagged, the severity and finding titles."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    status: ControlStatus
    severity: Severity | None = None
    finding_titles: list[str] = []
    note: str | None = None


class CheckOutcome(BaseModel):
    """What a reducer returns: the findings it produced plus every control it evaluated."""

    model_config = ConfigDict(frozen=True)

    findings: list[AuditFinding] = []
    controls: list[ControlOutcome] = []


# Every control each check can evaluate, in the display order the report renders them. Control ids are
# stable identifiers findings reference via AuditFinding.control; labels are the report copy. This is
# the single source of truth: a finding carrying a control id absent here is a bug the tests catch.
CONTROL_CATALOG: dict[str, tuple[ControlSpec, ...]] = {
    "version": (
        ControlSpec(id="version-unparseable", label="Version string is exposed"),
        ControlSpec(id="version-eol-below-min-line", label="Running a supported version line"),
        ControlSpec(id="version-eol-feed-unsupported", label="Version line supported per release feed"),
        ControlSpec(id="version-newer-line-available", label="Version line currency"),
        ControlSpec(id="version-below-advisory-floor", label="Patch above the security-advisory floor"),
        ControlSpec(id="version-patch-currency", label="Latest patch or hotfix within the line"),
    ),
    "transport": (
        ControlSpec(id="transport-no-tls", label="Base URL uses HTTPS"),
        ControlSpec(id="transport-no-hsts", label="Strict-Transport-Security header present"),
        ControlSpec(id="transport-weak-hsts", label="HSTS max-age is strong"),
        ControlSpec(id="transport-no-csp", label="Content-Security-Policy header present"),
        ControlSpec(id="transport-weak-csp", label="Content-Security-Policy is strict"),
        ControlSpec(id="transport-no-anti-framing", label="Anti-framing header present"),
        ControlSpec(id="transport-no-nosniff", label="X-Content-Type-Options: nosniff set"),
        ControlSpec(id="transport-cross-origin-isolation", label="Cross-origin isolation headers (COOP/COEP/CORP)"),
        ControlSpec(id="transport-cors-credentialed-any-origin", label="CORS blocks credentialed any-origin"),
        ControlSpec(id="transport-cors-any-origin", label="CORS blocks any-origin requests"),
        ControlSpec(id="transport-cors-credentialed-specific-origin", label="CORS specific-origin credentials"),
        ControlSpec(id="transport-server-version-disclosure", label="Server header hides version"),
    ),
    "settings": (
        ControlSpec(id="settings-weak-min-password-length", label="Minimum password length"),
        ControlSpec(id="settings-lockout-disabled", label="Failed-login lockout"),
        ControlSpec(id="settings-passwords-never-expire", label="Password expiry"),
        ControlSpec(id="settings-self-registration-captcha-off", label="Self-registration captcha"),
        ControlSpec(id="settings-can-grant-own-authorities", label="Self-grant of authorities"),
        ControlSpec(id="settings-email-verification-not-enforced", label="Email verification enforced"),
        ControlSpec(id="settings-cors-wildcard", label="CORS wildcard origin"),
        ControlSpec(id="settings-cors-allowlist", label="CORS origin allowlist"),
        ControlSpec(id="settings-2fa-not-global", label="Global 2FA enforcement (DHIS2 baseline)"),
        ControlSpec(id="settings-email-feature-without-smtp", label="Email features versus SMTP configuration"),
    ),
    "authorities": (
        ControlSpec(id="authorities-audited-superuser", label="Audited account superuser status"),
        ControlSpec(id="authorities-audited-category", label="Audited account dangerous-category authorities"),
    ),
    "roles": (
        ControlSpec(id="roles-grants-all-in-use", label="Roles granting ALL that are in use"),
        ControlSpec(id="roles-grants-all-unused", label="Unused roles granting ALL"),
        ControlSpec(id="roles-dangerous-authorities", label="Roles holding dangerous authorities"),
    ),
    "hygiene": (
        ControlSpec(id="hygiene-priv-disabled-holds-roles", label="Disabled accounts holding privileged roles"),
        ControlSpec(id="hygiene-priv-never-logged-in", label="Privileged accounts that never logged in"),
        ControlSpec(id="hygiene-priv-stale", label="Stale privileged accounts"),
        ControlSpec(id="hygiene-priv-no-email", label="Privileged accounts without an email"),
        ControlSpec(id="hygiene-agg-never-logged-in", label="Active accounts that never logged in"),
        ControlSpec(id="hygiene-agg-stale", label="Stale active accounts"),
        ControlSpec(id="hygiene-agg-stale-password", label="Accounts with stale or unset passwords"),
        ControlSpec(id="hygiene-seed-admin-enabled", label="Default seed 'admin' account"),
        ControlSpec(id="hygiene-2fa-superuser", label="Superusers with two-factor authentication"),
        ControlSpec(id="hygiene-inventory", label="User account inventory"),
    ),
    "credential-probe": (ControlSpec(id="credential-probe-default", label="Default admin/district credentials"),),
    "guest": (
        ControlSpec(id="guest-anonymous-readable-endpoint", label="Login-required endpoints require auth"),
        ControlSpec(id="guest-self-registration-enabled", label="Self-registration"),
        ControlSpec(id="guest-account-recovery-enabled", label="Account recovery"),
    ),
    "apps": (
        ControlSpec(id="apps-side-loaded", label="No side-loaded apps"),
        ControlSpec(id="apps-update-available", label="Installed apps up to date"),
        ControlSpec(id="apps-custom-js", label="No custom JavaScript injected"),
        ControlSpec(id="apps-custom-css", label="No custom CSS injected"),
    ),
    "sharing": (
        ControlSpec(id="sharing-external", label="No objects accessible without authentication"),
        ControlSpec(id="sharing-public-write-data", label="No public write to data-bearing objects"),
        ControlSpec(id="sharing-public-write-metadata", label="No public write to metadata objects"),
        ControlSpec(id="sharing-public-sql-view", label="No SQL views readable by all users"),
        ControlSpec(id="sharing-public-read-data", label="No public read of data-bearing objects"),
    ),
    "auth-methods": (
        ControlSpec(id="auth-methods-oidc-provider", label="External OIDC login providers"),
        ControlSpec(id="auth-methods-oauth2-broad-grant", label="OAuth2 clients avoid broad grant types"),
        ControlSpec(id="auth-methods-oauth2-loose-redirect", label="OAuth2 clients avoid loose redirect URIs"),
        ControlSpec(id="auth-methods-oauth2-clean-client", label="Registered OAuth2 clients"),
    ),
    "tokens": (
        ControlSpec(id="tokens-inventory", label="Personal access token inventory"),
        ControlSpec(id="tokens-non-expiring", label="No non-expiring tokens"),
        ControlSpec(id="tokens-no-ip-allowlist", label="Tokens restricted by IP allowlist"),
    ),
    "routes": (
        ControlSpec(id="routes-metadata-endpoint", label="No routes targeting cloud metadata"),
        ControlSpec(id="routes-private-address", label="No routes to private or internal hosts"),
        ControlSpec(id="routes-allows-subpaths", label="Routes restrict subpaths"),
        ControlSpec(id="routes-carries-auth", label="Routes carrying upstream credentials"),
        ControlSpec(id="routes-no-required-authorities", label="Routes require authorities"),
        ControlSpec(id="routes-inventory", label="Route inventory"),
    ),
    "audit-config": (
        ControlSpec(id="audit-config-system-disabled", label="Auditing enabled instance-wide"),
        ControlSpec(id="audit-config-both-sinks-off", label="At least one audit sink enabled"),
        ControlSpec(id="audit-config-narrow-scope", label="Audit scope coverage"),
    ),
}


class ControlLog:
    """Records per-control outcomes as a reducer runs, then folds them into a CheckOutcome.

    Every catalog control starts SKIPPED ("not evaluated this run"), so a control the reducer never
    touches is never falsely reported as passed. `mark_passed` promotes an evaluated-clean control,
    `record` appends a finding and flags its control, and `mark_skipped` sets an explicit skip reason.
    """

    def __init__(self, check: str) -> None:
        """Start a log for one check, seeding every catalog control as not-yet-evaluated."""
        self._check = check
        self._specs = CONTROL_CATALOG[check]
        self._status: dict[str, ControlStatus] = {spec.id: ControlStatus.SKIPPED for spec in self._specs}
        self._severity: dict[str, Severity] = {}
        self._titles: dict[str, list[str]] = defaultdict(list)
        self._notes: dict[str, str | None] = {spec.id: "not evaluated this run" for spec in self._specs}
        self._findings: list[AuditFinding] = []

    def mark_passed(self, *control_ids: str) -> None:
        """Promote each still-untouched control to PASS; leave already-flagged controls flagged."""
        for control_id in control_ids:
            self._require(control_id)
            if self._status[control_id] is ControlStatus.SKIPPED:
                self._status[control_id] = ControlStatus.PASSED
                self._notes[control_id] = None

    def record(self, finding: AuditFinding) -> None:
        """Append a finding; when it carries a control id, flag that control at the finding's severity."""
        self._findings.append(finding)
        control_id = finding.control
        if control_id is None:
            return
        self._require(control_id)
        self._status[control_id] = ControlStatus.FLAGGED
        self._severity[control_id] = self._more_severe(self._severity.get(control_id), finding.severity)
        self._titles[control_id].append(finding.title)
        self._notes[control_id] = None

    def mark_skipped(self, control_id: str, note: str) -> None:
        """Mark a control SKIPPED with the reason it could not run this run."""
        self._require(control_id)
        self._status[control_id] = ControlStatus.SKIPPED
        self._notes[control_id] = note

    def result(self) -> CheckOutcome:
        """Fold the recorded findings and per-control outcomes into a CheckOutcome (controls in catalog order)."""
        controls = [
            ControlOutcome(
                id=spec.id,
                label=spec.label,
                status=self._status[spec.id],
                severity=self._severity.get(spec.id),
                finding_titles=self._titles[spec.id],
                note=self._notes[spec.id],
            )
            for spec in self._specs
        ]
        return CheckOutcome(findings=self._findings, controls=controls)

    def _require(self, control_id: str) -> None:
        """Guard that a control id belongs to this check's catalog, so typos fail loudly."""
        if control_id not in self._status:
            raise KeyError(f"control id {control_id!r} is not in the {self._check!r} catalog")

    @staticmethod
    def _more_severe(current: Severity | None, candidate: Severity) -> Severity:
        """Return the more urgent of two severities so a flagged control shows its worst finding."""
        if current is None or severity_rank(candidate) < severity_rank(current):
            return candidate
        return current
