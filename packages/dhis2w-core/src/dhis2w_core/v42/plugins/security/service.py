"""Service layer for the `security` plugin (read-only posture checks)."""

from __future__ import annotations

from dhis2w_client.errors import Dhis2ClientError

from dhis2w_core.profile import Profile
from dhis2w_core.security_core import AccountAuthorities, build_account_authorities
from dhis2w_core.v42.client_context import open_client
from dhis2w_core.v42.plugins.security.models import SecuritySettings


async def get_security_settings(profile: Profile) -> SecuritySettings:
    """Fetch the security-relevant system settings for the given profile."""
    async with open_client(profile) as client:
        return await client.get("/api/systemSettings", model=SecuritySettings)


async def get_account_authorities(profile: Profile) -> AccountAuthorities:
    """Fetch and categorise the authenticated account's effective authorities.

    `/api/me/authorization` returns a bare JSON list of authority strings;
    the client wraps non-dict bodies under a `data` key, unwrapped here and
    immediately re-typed into `AccountAuthorities`. Any other shape raises --
    a security read must never present a parse surprise as "no authorities".
    """
    async with open_client(profile) as client:
        raw = await client.get_raw("/api/me/authorization")
    payload = raw.get("data")
    if not isinstance(payload, list):
        raise Dhis2ClientError(
            "unexpected /api/me/authorization payload shape (expected a JSON list of authority strings)"
        )
    return build_account_authorities([str(item) for item in payload])
