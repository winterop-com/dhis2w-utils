"""Helpers for opening a connected Dhis2Client from a resolved Profile (v43).

PAT and Basic auth construction lives in `dhis2w_client.v43.client_context`
(no heavy deps). This module adds the OAuth2 path — which needs the token
store in this package — and keeps the existing `build_auth` / `open_client`
signatures so every v43 caller keeps working.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from dhis2w_client.v43 import AuthProvider, Dhis2, Dhis2Client, RetryPolicy
from dhis2w_client.v43.auth.oauth2 import OAuth2Auth
from dhis2w_client.v43.client_context import build_auth_for_basic

from dhis2w_core.profile import Profile, ResolvedProfile, current_bound_version_tree, resolve
from dhis2w_core.v43.token_store import token_store_for_scope


def build_auth(
    profile: Profile,
    *,
    profile_name: str | None = None,
    scope: str = "global",
    open_browser: bool = True,
) -> AuthProvider:
    """Construct an `AuthProvider` matching the profile's auth kind.

    `profile_name` and `scope` only matter for `auth="oauth2"` — they pick the
    token-store key and the DB file location. When omitted for oauth2, fall
    back to `DHIS2_PROFILE` env var or a synthetic store key.

    `open_browser` only matters for `auth="oauth2"`. When False, the CLI prints
    the authorization URL to stderr instead of launching the system browser —
    useful when running over SSH, in a different browser, or under Playwright.
    """
    if profile.auth == "oauth2":
        return _build_oauth2(profile, profile_name=profile_name, scope=scope, open_browser=open_browser)
    return build_auth_for_basic(profile)


def _build_oauth2(
    profile: Profile,
    *,
    profile_name: str | None,
    scope: str,
    open_browser: bool,
) -> OAuth2Auth:
    if not profile.client_id:
        raise ValueError("profile.auth == 'oauth2' requires client_id")
    if not profile.client_secret:
        raise ValueError("profile.auth == 'oauth2' requires client_secret")
    if not profile.scope:
        raise ValueError("profile.auth == 'oauth2' requires a scope (DHIS2 only recognises 'ALL')")
    if not profile.redirect_uri:
        raise ValueError("profile.auth == 'oauth2' requires redirect_uri")
    name = profile_name or os.environ.get("DHIS2_PROFILE") or "default"
    store = token_store_for_scope(scope)
    return OAuth2Auth(
        base_url=profile.base_url,
        client_id=profile.client_id,
        client_secret=profile.client_secret,
        scope=profile.scope,
        redirect_uri=profile.redirect_uri,
        token_store=store,
        store_key=f"profile:{name}",
        open_browser=open_browser,
    )


def scope_from_resolved(resolved: ResolvedProfile) -> str:
    """Translate a `ResolvedProfile.source` into a 'project' / 'global' scope."""
    if resolved.source == "project-toml":
        return "project"
    return "global"


def build_auth_for_name(
    name: str | None = None,
    *,
    open_browser: bool = True,
) -> tuple[Profile, AuthProvider]:
    """Resolve a profile by name and return (profile, auth). Convenience for the CLI.

    `open_browser=False` is plumbed through to OAuth2 auth so `d2w profile
    login --no-browser` and its kin skip the `webbrowser.open()` call.
    """
    resolved = resolve(name)
    auth = build_auth(
        resolved.profile,
        profile_name=resolved.name,
        scope=scope_from_resolved(resolved),
        open_browser=open_browser,
    )
    return resolved.profile, auth


@asynccontextmanager
async def open_client(
    profile: Profile,
    *,
    profile_name: str | None = None,
    scope: str = "global",
    allow_version_fallback: bool = False,
    retry_policy: RetryPolicy | None = None,
    http_limits: httpx.Limits | None = None,
    system_cache_ttl: float | None = 300.0,
    event_hooks: dict[str, list] | None = None,
) -> AsyncGenerator[Dhis2Client]:
    """Open a connected Dhis2Client for `profile` — yields inside `async with`.

    `allow_version_fallback` (default False) mirrors the `Dhis2Client`
    constructor: a server major with no generated tree raises
    `UnsupportedVersionError` through the CLI / MCP paths too. Pass True
    to bind the nearest-lower generated tree instead (never nearest-higher).

    Pass `retry_policy=RetryPolicy(...)` to enable exponential-backoff retries
    on transient HTTP failures (connection errors, 429/502/503/504). See
    `dhis2w_client.RetryPolicy` for the tuning knobs.

    Pass `http_limits=httpx.Limits(max_connections=..., max_keepalive_connections=...)`
    to tune the connection pool for high-concurrency workloads (or to clamp
    it down against a small DHIS2 instance). See
    `docs/architecture/client.md` for sizing guidance.

    `system_cache_ttl` (default 300 s) caps how long cached system-level
    reads (`client.system.info()`, default categoryCombo UID, per-key
    system settings) stay fresh before the next call refetches. Pass
    `None` to disable the cache entirely.

    `profile.version` is *not* threaded into the wire client — auto-detect
    on connect remains the only source of truth on the wire so a local
    profile pointing at a base URL whose target version drifts between
    sessions can't desync. The field is read at CLI / MCP bootstrap to
    pick which version's plugin tree to load.

    Exception: when MCP has called `bind_version_tree()` (so the server has
    committed to a specific plugin tree for the process lifetime), the
    bound key is threaded into `Dhis2Client(version=...)` so the on-connect
    `/api/system/info` check raises `VersionPinMismatchError` against a
    wrong-major server even when the per-call profile has no `.version`
    field. CLI doesn't trigger this path — it discovers plugins fresh per
    invocation and never binds.

    `event_hooks` (default `None`) passes httpx event hooks through to the
    underlying `Dhis2Client`; the security audit uses a `request` hook to
    enforce its read-only allowlist.
    """
    auth = build_auth(profile, profile_name=profile_name, scope=scope)
    bound_tree = current_bound_version_tree()
    async with Dhis2Client(
        profile.base_url,
        auth=auth,
        version=Dhis2(bound_tree) if bound_tree is not None else None,
        allow_version_fallback=allow_version_fallback,
        retry_policy=retry_policy,
        http_limits=http_limits,
        system_cache_ttl=system_cache_ttl,
        event_hooks=event_hooks,
    ) as client:
        yield client
