"""Verdicts over the security-relevant system settings slice plus the CORS whitelist."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

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
    keyCanGrantOwnUserAuthorityGroups: bool | None
    keyAccountRecovery: bool | None
    enforceVerifiedEmail: bool | None
    keyEmailHostName: str | None
    keyEmailUsername: str | None


class CorsWhitelist(BaseModel):
    """The instance's CORS origin whitelist read from `/api/configuration/corsWhitelist`."""

    model_config = ConfigDict(frozen=True)

    origins: tuple[str, ...]

    @property
    def has_wildcard(self) -> bool:
        """True when a `*` origin lets any site make credentialed cross-origin calls."""
        return "*" in self.origins


def _is_email_configured(settings: SettingsLike) -> bool:
    """SMTP counts as configured only when both host and username are non-blank."""
    host = (settings.keyEmailHostName or "").strip()
    username = (settings.keyEmailUsername or "").strip()
    return bool(host) and bool(username)


def evaluate_settings(settings: SettingsLike, *, cors: CorsWhitelist | None = None) -> list[AuditFinding]:
    """Turn the security settings slice (and optional CORS whitelist) into audit findings."""
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

    if settings.keyCanGrantOwnUserAuthorityGroups is True:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="Users can grant themselves their own authorities",
                detail=(
                    "keyCanGrantOwnUserAuthorityGroups is on; users can grant themselves authorities they "
                    "already hold, a direct privilege-escalation path."
                ),
            )
        )

    if settings.enforceVerifiedEmail is False:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.WARN,
                title="Email verification is not enforced",
                detail=(
                    "enforceVerifiedEmail is off; users can act without a verified email address, weakening "
                    "account-recovery and notification trust. Email verification was introduced in DHIS2 v42."
                ),
            )
        )

    if cors is not None and cors.has_wildcard:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Permissive CORS wildcard origin",
                detail=(
                    "The CORS whitelist contains a `*` origin; any site can make credentialed cross-origin API calls."
                ),
            )
        )
    elif cors is not None and cors.origins:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.INFO,
                title="CORS origin allowlist configured",
                detail=(
                    "The CORS whitelist permits cross-origin API calls from the listed origins. An origin "
                    "allowlist is the correct mechanism; review that each entry is still trusted."
                ),
                evidence={"origins": ", ".join(cors.origins)},
            )
        )

    findings.append(
        AuditFinding(
            check=_CHECK,
            severity=Severity.INFO,
            title="Two-factor authentication is not globally enforced",
            detail=(
                "DHIS2 has no global enforce-2FA setting; 2FA is enforced per-user or per-role only via the "
                "TWO_FACTOR_AUTH_REQUIRED restriction. This is a property of DHIS2, not of this instance, so it "
                "is reported as INFO. See the hygiene check for the actual per-account 2FA enrolment gaps."
            ),
        )
    )

    recovery_or_verification_on = settings.keyAccountRecovery is True or settings.enforceVerifiedEmail is True
    if recovery_or_verification_on and not _is_email_configured(settings):
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.WARN,
                title="Email-dependent feature on while SMTP is unconfigured",
                detail=(
                    "Account recovery or email verification is on but keyEmailHostName / keyEmailUsername is "
                    "blank; recovery and verification silently fail without configured SMTP."
                ),
            )
        )

    return findings
