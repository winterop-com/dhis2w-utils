"""Verdicts over the DHIS2 auditing posture parsed from a `dhis.conf` copy.

The audit posture (the instance-wide enable flag, the file logger, the database sink, and the four
per-scope matrices) is not exposed over any DHIS2 API; it lives only in `dhis.conf`. The reducer therefore
has two modes driven by `AuditPosture.parsed`: when `parsed` is False (no `--dhis-conf` supplied) it emits a
single INFO stating the posture is not API-readable -- never "auditing is off". When a `dhis.conf` copy was
parsed it reports each weak channel: the master switch off, both sinks off, and an explicitly-configured
matrix that is narrower than the DHIS2 default {CREATE, UPDATE, DELETE, SECURITY}.

The DHIS2 default (absent or empty matrix key) gives every scope {CREATE, UPDATE, DELETE, SECURITY}, so a
freshly-deployed instance with NO audit.* config is already audited on all change types. Only an EXPLICIT
matrix that omits one or more forensic types relative to the default is flagged as narrowly scoped. A scope
whose matrix is set to DISABLED (empty type set) is also flagged because it explicitly turns off a scope that
would otherwise be audited by default. See BUGS.md #54 for the upstream behaviour reference.
"""

from __future__ import annotations

from dhis2w_core.security_core.dhisconf import _FORENSIC_AUDIT_TYPES, AuditPosture
from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "audit-config"


def evaluate_audit_config(posture: AuditPosture) -> list[AuditFinding]:
    """Turn an audit posture into findings: the API-only INFO, or the parsed-posture weak-channel verdicts."""
    if not posture.parsed:
        return [_api_only_finding()]
    findings: list[AuditFinding] = []
    if posture.system_enabled is False:
        findings.append(_system_disabled_finding())
        return findings
    if not posture.logger_enabled and not posture.database_enabled:
        findings.append(_both_sinks_off_finding())
    findings.extend(_scope_findings(posture))
    return findings


def _scope_findings(posture: AuditPosture) -> list[AuditFinding]:
    """Scope-coverage findings: only explicit matrices that are narrower than the DHIS2 forensic default are flagged.

    An absent or blank matrix key receives the DHIS2 default {CREATE, UPDATE, DELETE, SECURITY} and is
    healthy. Only scopes where the operator supplied an EXPLICIT matrix (explicit=True) that omits one or
    more of the forensic types are reported -- including a DISABLED scope (empty type set).
    """
    narrow = _narrowly_scoped(posture)
    if narrow:
        return [_narrowly_scoped_finding(narrow=narrow)]
    return []


def _narrowly_scoped(posture: AuditPosture) -> dict[str, tuple[str, ...]]:
    """Map each EXPLICITLY-configured scope to the forensic audit types it omits vs. the DHIS2 default.

    Scopes without an explicit matrix (explicit=False) receive the DHIS2 default and are not reported.
    An explicitly-DISABLED scope omits all four forensic types.
    """
    narrow: dict[str, tuple[str, ...]] = {}
    for scope in posture.scopes:
        if not scope.explicit:
            # No explicit matrix: DHIS2 applies its default -- not a narrowing.
            continue
        missing = tuple(audit_type for audit_type in _FORENSIC_AUDIT_TYPES if audit_type not in scope.audit_types)
        if missing:
            narrow[scope.scope] = missing
    return narrow


def _api_only_finding() -> AuditFinding:
    """INFO: the audit posture is not API-readable; re-run with `--dhis-conf` on the server host."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Audit configuration is not API-readable",
        detail=(
            "DHIS2 does not expose its audit configuration over the API; the audit.* keys live only in "
            "dhis.conf. This check could not read the audit posture remotely -- this is a property of DHIS2, "
            "not a statement that auditing is off. Re-run with --dhis-conf <path> pointed at a copy of the "
            "server's dhis.conf to evaluate the file logger, the database sink, and the per-scope matrices."
        ),
        group_key="audit-config-api-only",
        evidence={"api_readable": "false"},
    )


def _system_disabled_finding() -> AuditFinding:
    """MEDIUM: system.audit.enabled is off, so no audit events are recorded regardless of the matrices."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="Auditing is disabled instance-wide",
        detail=(
            "system.audit.enabled is off, so auditing is disabled instance-wide regardless of the per-scope "
            "matrices. No CREATE/UPDATE/DELETE/READ/SECURITY events are recorded; there is no forensic trail."
        ),
        group_key="audit-system-disabled",
        evidence={"system.audit.enabled": "off"},
    )


def _both_sinks_off_finding() -> AuditFinding:
    """MEDIUM: both the file logger and the database sink are off, so audit events have nowhere to land."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="Both audit sinks are off",
        detail=(
            "audit.logger is off and audit.database is off, so audit events have nowhere to land. Enable at "
            "least the file logger or the database sink."
        ),
        group_key="audit-logger-and-database-both-off",
        evidence={"audit.logger": "off", "audit.database": "off"},
    )


def _narrowly_scoped_finding(*, narrow: dict[str, tuple[str, ...]]) -> AuditFinding:
    """MEDIUM: an explicitly-configured matrix is narrower than the DHIS2 forensic default."""
    narrow_text = "; ".join(f"{scope} omits {', '.join(missing)}" for scope, missing in narrow.items())
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="Audit scope coverage is narrower than the DHIS2 default",
        detail=(
            "DHIS2 applies {CREATE, UPDATE, DELETE, SECURITY} to every scope by default. One or more "
            "explicitly-configured matrices narrow below that baseline, reducing the forensic trail. "
            f"Scopes with explicit narrowing: {narrow_text}."
        ),
        group_key="audit-scope-narrowly-scoped",
        evidence={"narrow_matrices": narrow_text},
    )
