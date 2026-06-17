"""Verdict shaping for the default-credential probe (admin/district)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity
from dhis2w_core.security_core.guardrails import DEFAULT_PROBE_PASSWORD, DEFAULT_PROBE_USERNAME

_CHECK = "credential-probe"


class ProbeOutcome(StrEnum):
    """What the single admin/district login attempt resolved to."""

    AUTHENTICATED = "authenticated"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class CredentialProbeResult(BaseModel):
    """Outcome of the one default-credential login attempt against /api/me."""

    model_config = ConfigDict(frozen=True)

    outcome: ProbeOutcome
    username: str = DEFAULT_PROBE_USERNAME
    status_code: int | None = None
    lockout_active: bool = False
    detail: str | None = None


def classify_probe_status(status_code: int) -> ProbeOutcome:
    """Map an HTTP status from GET /api/me to a probe outcome (200 in, 401 out, else unclear)."""
    if status_code == 200:
        return ProbeOutcome.AUTHENTICATED
    if status_code == 401:
        return ProbeOutcome.REJECTED
    return ProbeOutcome.INCONCLUSIVE


def evaluate_credential_probe(result: CredentialProbeResult) -> list[AuditFinding]:
    """Turn a credential-probe result into audit findings (CRITICAL when the default login works)."""
    if result.outcome is ProbeOutcome.AUTHENTICATED:
        return [
            AuditFinding(
                check=_CHECK,
                severity=Severity.CRITICAL,
                title="Default credentials accepted",
                detail=(
                    f"The well-known default login {result.username}/{DEFAULT_PROBE_PASSWORD} authenticated "
                    "against /api/me. Change this password immediately and audit the account's activity."
                ),
                subject=result.username,
                evidence={"username": result.username, "status": str(result.status_code or "")},
            )
        ]
    if result.outcome is ProbeOutcome.INCONCLUSIVE:
        return [
            AuditFinding(
                check=_CHECK,
                severity=Severity.INFO,
                title="Default-credential probe inconclusive",
                detail=(
                    result.detail
                    or (
                        f"GET /api/me as {result.username} returned an unexpected response "
                        f"(status {result.status_code}); could not confirm whether the default login works."
                    )
                ),
                evidence={"status": str(result.status_code or "")},
            )
        ]
    return []
