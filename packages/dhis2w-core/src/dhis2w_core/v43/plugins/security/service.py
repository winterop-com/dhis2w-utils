"""Service layer for the `security` plugin — reads /api/systemSettings."""

from __future__ import annotations

from dhis2w_core.profile import Profile
from dhis2w_core.v43.client_context import open_client
from dhis2w_core.v43.plugins.security.models import SecuritySettings


async def get_security_settings(profile: Profile) -> SecuritySettings:
    """Fetch the security-relevant system settings for the given profile."""
    async with open_client(profile) as client:
        return await client.get("/api/systemSettings", model=SecuritySettings)
