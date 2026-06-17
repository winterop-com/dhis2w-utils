"""Version-specific wire extraction for the v41 security plugin (2FA + last login)."""

from __future__ import annotations

from typing import Any

from dhis2w_core.security_core import TwoFactorSource

# v41 still exposes per-user 2FA state on the User resource, so it is requested inline.
USER_FIELDS = "id,username,disabled,email,lastLogin,twoFactorEnabled,userCredentials[twoFA],userRoles[id]"
TWO_FACTOR_SOURCE: TwoFactorSource = TwoFactorSource.USER_FIELD


def two_factor_enabled(user: dict[str, Any]) -> bool | None:
    """Read v41's per-user 2FA flag from the /api/users record (falls back to userCredentials.twoFA)."""
    value = user.get("twoFactorEnabled")
    if isinstance(value, bool):
        return value
    credentials = user.get("userCredentials")
    if isinstance(credentials, dict) and isinstance(credentials.get("twoFA"), bool):
        return bool(credentials["twoFA"])
    return None


def last_login(user: dict[str, Any]) -> str | None:
    """Read the last-login timestamp from the /api/users record."""
    value = user.get("lastLogin")
    return value if isinstance(value, str) else None
