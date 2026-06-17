"""Version-specific wire extraction for the v42 security plugin (2FA + last login).

v42 removed every admin-readable per-user 2FA field from the User resource
(BUGS.md #47); 2FA enrolment is read via the superuser-only
`/api/users/twoFactor` audit endpoints instead, so it is not requested here.
"""

from __future__ import annotations

from typing import Any

from dhis2w_core.security_core import TwoFactorSource

USER_FIELDS = "id,username,disabled,email,lastLogin,userRoles[id]"
TWO_FACTOR_SOURCE: TwoFactorSource = TwoFactorSource.AUDIT_ENDPOINT


def two_factor_enabled(user: dict[str, Any]) -> bool | None:
    """v42 does not expose per-user 2FA on /api/users; the audit endpoint supplies it instead."""
    return None


def last_login(user: dict[str, Any]) -> str | None:
    """Read the last-login timestamp from the /api/users record."""
    value = user.get("lastLogin")
    return value if isinstance(value, str) else None
