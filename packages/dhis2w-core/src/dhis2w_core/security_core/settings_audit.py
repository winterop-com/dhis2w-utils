"""Verdicts over the security-relevant system settings slice plus the CORS whitelist."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.controls import CheckOutcome, ControlLog
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


def evaluate_settings(settings: SettingsLike, *, cors: CorsWhitelist | None = None) -> CheckOutcome:
    """Turn the security settings slice (and optional CORS whitelist) into a CheckOutcome."""
    log = ControlLog(_CHECK)

    minimum = settings.minPasswordLength
    if minimum is None:
        log.mark_skipped("settings-weak-min-password-length", "minPasswordLength not set")
    elif minimum < MIN_RECOMMENDED_PASSWORD_LENGTH:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Weak minimum password length",
                detail=(f"minPasswordLength is {minimum}; at least {MIN_RECOMMENDED_PASSWORD_LENGTH} is recommended."),
                evidence={"minPasswordLength": str(minimum)},
                control="settings-weak-min-password-length",
            )
        )
    else:
        log.mark_passed("settings-weak-min-password-length")

    if settings.keyLockMultipleFailedLogins is False:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Failed-login lockout disabled",
                detail="keyLockMultipleFailedLogins is off; repeated wrong passwords are not throttled.",
                control="settings-lockout-disabled",
            )
        )
    elif settings.keyLockMultipleFailedLogins is True:
        log.mark_passed("settings-lockout-disabled")
    else:
        log.mark_skipped("settings-lockout-disabled", "keyLockMultipleFailedLogins not set")

    if settings.credentialsExpires in (None, 0):
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.WARN,
                title="Passwords never expire",
                detail="credentialsExpires is unset or 0; account passwords are never forced to rotate.",
                control="settings-passwords-never-expire",
            )
        )
    else:
        log.mark_passed("settings-passwords-never-expire")

    if settings.keySelfRegistrationNoRecaptcha is True:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Self-registration captcha disabled",
                detail="keySelfRegistrationNoRecaptcha is on; self-registration is not protected by a captcha.",
                control="settings-self-registration-captcha-off",
            )
        )
    elif settings.keySelfRegistrationNoRecaptcha is False:
        log.mark_passed("settings-self-registration-captcha-off")
    else:
        log.mark_skipped("settings-self-registration-captcha-off", "keySelfRegistrationNoRecaptcha not set")

    if settings.keyCanGrantOwnUserAuthorityGroups is True:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="Users can grant themselves their own authorities",
                detail=(
                    "keyCanGrantOwnUserAuthorityGroups is on; users can grant themselves authorities they "
                    "already hold, a direct privilege-escalation path."
                ),
                control="settings-can-grant-own-authorities",
            )
        )
    elif settings.keyCanGrantOwnUserAuthorityGroups is False:
        log.mark_passed("settings-can-grant-own-authorities")
    else:
        log.mark_skipped("settings-can-grant-own-authorities", "keyCanGrantOwnUserAuthorityGroups not set")

    if settings.enforceVerifiedEmail is False:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.WARN,
                title="Email verification is not enforced",
                detail=(
                    "enforceVerifiedEmail is off; users can act without a verified email address, weakening "
                    "account-recovery and notification trust. Email verification was introduced in DHIS2 v42."
                ),
                control="settings-email-verification-not-enforced",
            )
        )
    elif settings.enforceVerifiedEmail is True:
        log.mark_passed("settings-email-verification-not-enforced")
    else:
        log.mark_skipped(
            "settings-email-verification-not-enforced", "enforceVerifiedEmail not set (feature absent before v42)"
        )

    if cors is None:
        log.mark_skipped("settings-cors-wildcard", "CORS whitelist not fetched")
        log.mark_skipped("settings-cors-allowlist", "CORS whitelist not fetched")
    elif cors.has_wildcard:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="Permissive CORS wildcard origin",
                detail=(
                    "The CORS whitelist contains a `*` origin; any site can make credentialed cross-origin API calls."
                ),
                control="settings-cors-wildcard",
            )
        )
        log.mark_passed("settings-cors-allowlist")
    elif cors.origins:
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.INFO,
                title="CORS origin allowlist configured",
                detail=(
                    "The CORS whitelist permits cross-origin API calls from the listed origins. An origin "
                    "allowlist is the correct mechanism; review that each entry is still trusted."
                ),
                evidence={"origins": ", ".join(cors.origins)},
                control="settings-cors-allowlist",
            )
        )
        log.mark_passed("settings-cors-wildcard")
    else:
        log.mark_passed("settings-cors-wildcard")
        log.mark_passed("settings-cors-allowlist")

    log.record(
        AuditFinding(
            check=_CHECK,
            severity=Severity.INFO,
            title="Two-factor authentication is not globally enforced",
            detail=(
                "DHIS2 has no global enforce-2FA setting; 2FA is enforced per-user or per-role only via the "
                "TWO_FACTOR_AUTH_REQUIRED restriction. This is a property of DHIS2, not of this instance, so it "
                "is reported as INFO. See the hygiene check for the actual per-account 2FA enrolment gaps."
            ),
            control="settings-2fa-not-global",
        )
    )

    recovery_or_verification_on = settings.keyAccountRecovery is True or settings.enforceVerifiedEmail is True
    if recovery_or_verification_on and not _is_email_configured(settings):
        log.record(
            AuditFinding(
                check=_CHECK,
                severity=Severity.WARN,
                title="Email-dependent feature on while SMTP is unconfigured",
                detail=(
                    "Account recovery or email verification is on but keyEmailHostName / keyEmailUsername is "
                    "blank; recovery and verification silently fail without configured SMTP."
                ),
                control="settings-email-feature-without-smtp",
            )
        )
    else:
        log.mark_passed("settings-email-feature-without-smtp")

    return log.result()
