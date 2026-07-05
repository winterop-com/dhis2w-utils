"""Open a connected `Dhis2Client` from a `Profile` for PAT/Basic auth (v42).

This module is the lightweight library-user entry point: it handles the two
auth schemes that need no persistent state. OAuth2 needs the SQLite-backed
token store that ships in `dhis2w-core` — calling `open_client` with
`profile.auth == "oauth2"` here raises with a clear install hint pointing at
`dhis2w_core.open_client`. Concurrent-refresh safety is built into
`OAuth2Auth` itself (an `asyncio.Lock` serialises the check-refresh-persist
section); the token-store dependency is the only reason OAuth2 lives there.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx

from dhis2w_client.profile import Profile
from dhis2w_client.v42.auth.base import AuthProvider
from dhis2w_client.v42.auth.basic import BasicAuth
from dhis2w_client.v42.auth.pat import PatAuth
from dhis2w_client.v42.client import Dhis2Client
from dhis2w_client.v42.retry import RetryPolicy


def build_auth_for_basic(profile: Profile) -> AuthProvider:
    """Return a `PatAuth` or `BasicAuth` provider for the profile.

    Raises `NotImplementedError` on `profile.auth == "oauth2"` pointing at
    `dhis2w_core` — OAuth2 needs the token-store machinery that lives there.
    Raises `ValueError` when the matching credential fields are missing.
    """
    if profile.auth == "pat":
        if not profile.token:
            raise ValueError("profile.auth == 'pat' but no token is set")
        return PatAuth(token=profile.token)
    if profile.auth == "basic":
        if not (profile.username and profile.password):
            raise ValueError("profile.auth == 'basic' but username/password are missing")
        return BasicAuth(username=profile.username, password=profile.password)
    if profile.auth == "oauth2":
        raise NotImplementedError(
            "OAuth2 auth needs the token store in dhis2w-core. "
            "Install it (`uv add dhis2w-core`) and call `dhis2w_core.open_client(profile)` instead."
        )
    raise ValueError(f"unknown profile.auth value: {profile.auth!r}")


@asynccontextmanager
async def open_client(
    profile: Profile,
    *,
    allow_version_fallback: bool = False,
    retry_policy: RetryPolicy | None = None,
    http_limits: httpx.Limits | None = None,
    system_cache_ttl: float | None = 300.0,
) -> AsyncGenerator[Dhis2Client]:
    """Open a connected `Dhis2Client` for `profile` — PAT or Basic auth only.

    Yields a connected client inside `async with`. Raises `NotImplementedError`
    on OAuth2 profiles — use `dhis2w_core.open_client(profile, scope=..., profile_name=...)`
    for those.

    `allow_version_fallback` (default False) mirrors the `Dhis2Client`
    constructor: a server major with no generated tree raises
    `UnsupportedVersionError`. Pass True to bind the nearest-lower
    generated tree instead (never nearest-higher).

    `retry_policy`, `http_limits`, and `system_cache_ttl` mirror the
    underlying `Dhis2Client` constructor — see its docstring for tuning.
    """
    auth = build_auth_for_basic(profile)
    async with Dhis2Client(
        profile.base_url,
        auth=auth,
        version=None,
        allow_version_fallback=allow_version_fallback,
        retry_policy=retry_policy,
        http_limits=http_limits,
        system_cache_ttl=system_cache_ttl,
    ) as client:
        yield client
