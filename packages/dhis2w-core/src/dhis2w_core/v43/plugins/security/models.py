"""View-models for the `security` plugin."""

from __future__ import annotations

from pydantic import BaseModel


class SecuritySettings(BaseModel):
    """Security-relevant slice of `/api/systemSettings` (password policy, registration, lockout).

    The default `extra="ignore"` drops the rest of the settings object DHIS2
    ships, so this model is exactly the security slice — both in the table and
    under `--json`.
    """

    minPasswordLength: int | None = None
    maxPasswordLength: int | None = None
    credentialsExpires: int | None = None
    credentialsExpiresReminderInDays: int | None = None
    credentialsExpiryAlert: bool | None = None
    keyAccountRecovery: bool | None = None
    keySelfRegistrationNoRecaptcha: bool | None = None
    keyLockMultipleFailedLogins: bool | None = None
    enforceVerifiedEmail: bool | None = None
