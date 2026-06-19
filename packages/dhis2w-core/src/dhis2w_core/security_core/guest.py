"""Anonymous-access audit: endpoints readable without a login, plus self-registration and recovery.

The core signal is an unauthenticated probe. `/api/users`, `/api/userRoles`, and `/api/me` require a
login on a default DHIS2, so an anonymous 200 means that endpoint has been opened up — user-list
enumeration is the worst case. `/api/systemSettings` is deliberately NOT probed: DHIS2 serves its
non-confidential settings anonymously by design (the login page needs them) and filters confidential
keys server-side, so an anonymous 200 there is expected, not a finding. Self-registration (a non-null
`/api/configuration/selfRegistrationRole`) lets anyone create an account, and account recovery
(`keyAccountRecovery`) turns on email-based password reset.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "guest"


class GuestProbeTarget(BaseModel):
    """An endpoint that requires a login by default and the severity of finding it anonymously readable."""

    model_config = ConfigDict(frozen=True)

    path: str
    severity: Severity


class AnonymousResult(BaseModel):
    """An unauthenticated GET's outcome: the HTTP status (None on transport error) and content type."""

    model_config = ConfigDict(frozen=True)

    path: str
    status_code: int | None = None
    content_type: str | None = None


# Endpoints a default DHIS2 refuses to serve without a login (401). An anonymous 200 is the finding.
# `/api/systemSettings` is intentionally excluded: it is anonymously readable by design.
ANONYMOUS_PROBE_TARGETS: tuple[GuestProbeTarget, ...] = (
    GuestProbeTarget(path="/api/users", severity=Severity.CRITICAL),
    GuestProbeTarget(path="/api/userRoles", severity=Severity.HIGH),
    GuestProbeTarget(path="/api/me", severity=Severity.HIGH),
)


def evaluate_guest(
    *,
    anonymous: list[AnonymousResult],
    self_registration_role: str | None,
    account_recovery: bool,
) -> list[AuditFinding]:
    """Findings over anonymous-readable endpoints, self-registration state, and account recovery."""
    findings: list[AuditFinding] = []
    findings.extend(_anonymous_findings(anonymous))
    if self_registration_role is not None:
        findings.append(_self_registration_finding(self_registration_role))
    if account_recovery:
        findings.append(_account_recovery_finding())
    return findings


def _anonymous_findings(anonymous: list[AnonymousResult]) -> list[AuditFinding]:
    """Flag each endpoint an unauthenticated GET could read: a 200 with a JSON body.

    The JSON-body requirement avoids a false positive on instances fronted by an SSO proxy that
    answers `/api/*` with a 200 HTML login page; DHIS2 itself returns 401 for these endpoints
    anonymously, so a 200 JSON response is the genuine anonymous-readability signal.
    """
    severity_by_path = {target.path: target.severity for target in ANONYMOUS_PROBE_TARGETS}
    findings: list[AuditFinding] = []
    for result in anonymous:
        if result.status_code != 200 or "json" not in (result.content_type or "").lower():
            continue
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=severity_by_path.get(result.path, Severity.HIGH),
                title="Endpoint readable without authentication",
                detail=(
                    f"An unauthenticated GET to {result.path} returned 200; this endpoint normally "
                    "requires a login, so anonymous clients can read it."
                ),
                subject=result.path,
                evidence={"path": result.path},
            )
        )
    return findings


def _self_registration_finding(role: str) -> AuditFinding:
    """Flag that self-registration is enabled, so anyone reaching the login page can create an account."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Self-registration enabled",
        detail=(
            f"Self-registration is enabled; new accounts receive the '{role}' role. Anyone who can reach "
            "the login page can create an account."
        ),
        subject=role,
        evidence={"role": role},
    )


def _account_recovery_finding() -> AuditFinding:
    """Note that email-based account recovery is enabled."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Account recovery enabled",
        detail=(
            "keyAccountRecovery is on; accounts can be reset by email. This is a supported feature, but it "
            "widens the attack surface if email uniqueness or the mail server is not trusted."
        ),
        evidence={"setting": "keyAccountRecovery"},
    )
