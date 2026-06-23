"""View-models for the `security` plugin."""

from __future__ import annotations

from pydantic import BaseModel


class SecuritySettings(BaseModel):
    """Security-relevant slice of `/api/systemSettings` (password policy, registration, lockout).

    A deliberate typed projection of the generated `SystemSettings` OAS model
    (`dhis2w_client.generated.v{41,42,43}.oas`), which already declares every
    field here. We don't reuse the full generated model for this read because it
    can't validate a live `/api/systemSettings` response: the endpoint returns
    `keyAnalysisDisplayProperty` lowercase (`"name"`), which the OAS
    `DisplayProperty` enum rejects (BUGS.md #42). This projection omits that
    field, so it parses cleanly.

    The default `extra="ignore"` drops the rest of the settings object DHIS2
    ships, so this model is exactly the security slice -- both in the table and
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
    keyCanGrantOwnUserAuthorityGroups: bool | None = None
    enforceVerifiedEmail: bool | None = None
    keyEmailHostName: str | None = None
    keyEmailUsername: str | None = None
