"""Service layer for the `security` plugin (read-only posture checks)."""

from __future__ import annotations

from dhis2w_client.errors import Dhis2ClientError

from dhis2w_core.profile import Profile
from dhis2w_core.security_core import (
    AccountAuthorities,
    VersionPosture,
    build_account_authorities,
    build_version_posture,
)
from dhis2w_core.v41.client_context import open_client
from dhis2w_core.v41.plugins.security.models import SecuritySettings


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


async def get_version_posture(profile: Profile) -> VersionPosture:
    """Read the DHIS2 version and classify its EOL/advisory posture from a single request.

    Reads `/api/system/info` once and classifies the reported version against the
    static advisory patch floor and EOL line rules. It deliberately passes no
    release feed (`build_version_posture` -> `evaluate_version(feed=None)`), so the
    behind-latest-patch refinement that needs releases.dhis2.org is omitted and this
    read makes no external egress; just the one allowlisted DHIS2 GET. The
    feed-based currency check is the audit's job, not this cheap read.
    """
    async with open_client(profile) as client:
        info = await client.system.info()
    return build_version_posture(info.version)
