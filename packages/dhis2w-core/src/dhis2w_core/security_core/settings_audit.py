"""Verdicts over the security-relevant system settings slice."""

from __future__ import annotations

from typing import Protocol

from dhis2w_core.security_core.findings import AuditFinding, Severity

# Below this, DHIS2's configured minimum password length is treated as weak.
MIN_RECOMMENDED_PASSWORD_LENGTH = 8

_CHECK = "settings"


class SettingsLike(Protocol):
    """Structural view of the security settings the verdicts read.

    The per-tree `SecuritySettings` projection satisfies this Protocol, so the
    verdict logic stays version-agnostic without importing a per-tree model.
    """

    minPasswordLength: int | None
    credentialsExpires: int | None
    keyLockMultipleFailedLogins: bool | None
    keySelfRegistrationNoRecaptcha: bool | None


def evaluate_settings(settings: SettingsLike) -> list[AuditFinding]:
    """Turn the security settings slice into audit findings."""
    findings: list[AuditFinding] = []

    minimum = settings.minPasswordLength
    if minimum is not None and minimum < MIN_RECOMMENDED_PASSWORD_LENGTH:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Weak minimum password length",
                detail=(f"minPasswordLength is {minimum}; at least {MIN_RECOMMENDED_PASSWORD_LENGTH} is recommended."),
                evidence={"minPasswordLength": str(minimum)},
            )
        )

    if settings.keyLockMultipleFailedLogins is False:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Failed-login lockout disabled",
                detail="keyLockMultipleFailedLogins is off; repeated wrong passwords are not throttled.",
            )
        )

    if settings.credentialsExpires in (None, 0):
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.WARN,
                title="Passwords never expire",
                detail="credentialsExpires is unset or 0; account passwords are never forced to rotate.",
            )
        )

    if settings.keySelfRegistrationNoRecaptcha is True:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Self-registration captcha disabled",
                detail="keySelfRegistrationNoRecaptcha is on; self-registration is not protected by a captcha.",
            )
        )

    return findings
