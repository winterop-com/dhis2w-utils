"""Service layer for the `profile` plugin — profile CRUD + verification."""

from __future__ import annotations

import time
from pathlib import Path

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_client.v42 import BasicAuth, Dhis2, Dhis2Client, PatAuth, SessionCookieAuth
from dhis2w_client.v42.auth.base import AuthProvider
from dhis2w_client.v42.auth.oauth2 import DEFAULT_REDIRECT_URI, OAuth2Auth
from pydantic import BaseModel, ConfigDict

from dhis2w_core.oauth2_preflight import check_oauth2_server
from dhis2w_core.profile import (
    NoProfileError,
    Profile,
    ProfileAlreadyExistsError,
    ProfileSource,
    ResolvedProfile,
    UnknownProfileError,
    find_project_profiles_file,
    global_profiles_path,
    load_catalog,
    load_profiles_file,
    resolve,
    validate_profile_name,
    write_profiles_file,
)
from dhis2w_core.v42.token_store import token_store_for_scope

# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class ProfileSummary(BaseModel):
    """Profile metadata safe to expose without secrets."""

    model_config = ConfigDict(frozen=True)

    name: str
    base_url: str
    auth: str
    source: str
    source_path: str | None
    is_default: bool
    shadowed: bool = False  # True if this entry is hidden by a higher-precedence entry with the same name


def list_profiles(*, include_shadowed: bool = False, start: Path | None = None) -> list[ProfileSummary]:
    """Return summaries of every known profile across project + global TOML.

    When `include_shadowed=False` (default), profiles with the same name
    in both scopes are collapsed — only the winning (project) entry shows.
    With `include_shadowed=True`, the shadowed global entry is included too,
    marked `shadowed=True`, so the user can see what's being overridden.
    """
    catalog = load_catalog(start=start)
    default_name = catalog.default_name
    summaries: list[ProfileSummary] = []
    for name, entry in sorted(catalog.merged.items()):
        summaries.append(
            ProfileSummary(
                name=name,
                base_url=entry.profile.base_url,
                auth=entry.profile.auth,
                source=entry.source,
                source_path=str(entry.source_path) if entry.source_path else None,
                is_default=(name == default_name),
            )
        )
    if include_shadowed:
        # Surface any global entries that project entries have hidden.
        for name, profile in catalog.global_.profiles.items():
            if name in catalog.project.profiles:
                summaries.append(
                    ProfileSummary(
                        name=name,
                        base_url=profile.base_url,
                        auth=profile.auth,
                        source="global-toml",
                        source_path=str(catalog.global_path),
                        is_default=False,
                        shadowed=True,
                    )
                )
        summaries.sort(key=lambda s: (s.name, s.shadowed))
    return summaries


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class VerifyResult(BaseModel):
    """Outcome of verifying a single profile against a live instance."""

    model_config = ConfigDict(frozen=True)

    name: str
    ok: bool
    base_url: str
    auth: str
    version: str | None = None
    username: str | None = None
    latency_ms: int | None = None
    error: str | None = None


async def verify_profile(name: str, *, start: Path | None = None) -> VerifyResult:
    """Verify a single profile by calling /api/system/info and /api/me."""
    resolved = resolve(name, start=start)
    return await _verify_one(resolved)


async def verify_all_profiles(*, start: Path | None = None) -> list[VerifyResult]:
    """Verify every known profile; returns one result per profile (ok=False on failure)."""
    catalog = load_catalog(start=start)
    results: list[VerifyResult] = []
    for name in sorted(catalog.merged):
        entry = catalog.merged[name]
        resolved = ResolvedProfile(name=name, profile=entry.profile, source=entry.source, source_path=entry.source_path)
        try:
            result = await _verify_one(resolved)
        except Exception as exc:  # noqa: BLE001 — one broken profile must not abort the sweep
            result = VerifyResult(
                name=name,
                ok=False,
                base_url=entry.profile.base_url,
                auth=entry.profile.auth,
                error=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
    return results


async def _verify_one(resolved: ResolvedProfile) -> VerifyResult:
    """Build a client for the resolved profile, probe /api/system/info + /api/me, report."""
    name = resolved.name
    profile = resolved.profile
    if profile.auth == "oauth2":
        preflight_error = await check_oauth2_server(profile.base_url)
        if preflight_error is not None:
            return VerifyResult(
                name=name,
                ok=False,
                base_url=profile.base_url,
                auth=profile.auth,
                error=preflight_error,
            )
        # Verify must never trigger the browser flow — if no token is cached yet, tell the
        # user to run `d2w profile login <name>` rather than silently opening a browser.
        token_store = token_store_for_scope(_scope_for(resolved))
        try:
            cached = await token_store.get(f"profile:{resolved.name}")
        finally:
            await token_store.close()
        if cached is None:
            return VerifyResult(
                name=name,
                ok=False,
                base_url=profile.base_url,
                auth=profile.auth,
                error=(
                    f"no cached OAuth2 tokens for profile {resolved.name!r} — "
                    f"run `d2w profile login {resolved.name}` to complete the browser flow first"
                ),
            )
    auth = _build_probe_auth(profile, profile_name=resolved.name, scope=_scope_for(resolved))
    if auth is None:
        return VerifyResult(
            name=name,
            ok=False,
            base_url=profile.base_url,
            auth=profile.auth,
            error=_probe_unavailable_reason(profile, name),
        )
    start = time.perf_counter()
    try:
        async with Dhis2Client(profile.base_url, auth=auth, allow_version_fallback=True) as client:
            info = await client.system.info()
            me = await client.system.me()
    except Dhis2ClientError as exc:
        return VerifyResult(name=name, ok=False, base_url=profile.base_url, auth=profile.auth, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — network/DNS/timeout surface as plain str
        return VerifyResult(
            name=name,
            ok=False,
            base_url=profile.base_url,
            auth=profile.auth,
            error=f"{type(exc).__name__}: {exc}",
        )
    latency_ms = int((time.perf_counter() - start) * 1000)
    return VerifyResult(
        name=name,
        ok=True,
        base_url=profile.base_url,
        auth=profile.auth,
        version=info.version,
        username=me.username,
        latency_ms=latency_ms,
    )


def _scope_for(resolved: object) -> str:
    """Return 'project' if the resolved profile came from a project TOML, else 'global'."""
    src = getattr(resolved, "source", None)
    return "project" if src == "project-toml" else "global"


def _build_probe_auth(
    profile: Profile,
    *,
    profile_name: str | None = None,
    scope: str = "global",
) -> AuthProvider | None:
    """Return a probe-only AuthProvider, or None if the profile isn't probeable yet."""
    if profile.auth == "pat" and profile.token:
        return PatAuth(token=profile.token)
    if profile.auth == "basic" and profile.username and profile.password:
        return BasicAuth(username=profile.username, password=profile.password)
    if profile.auth == "session" and profile.cookie:
        return SessionCookieAuth(cookie=profile.cookie)
    if profile.auth == "oauth2":
        if not (profile.client_id and profile.client_secret and profile.scope and profile.redirect_uri):
            return None

        # Only probe oauth2 if we already have cached tokens. Running the browser
        # flow during `verify` would be surprising — login is an explicit command,
        # so wire a capturer that raises instead of accidentally opening a browser.
        async def _probe_capturer(_auth_url: str, _expected_state: str) -> str:
            raise Dhis2ClientError("no cached OAuth2 token — run `d2w profile login <name>` to authorise")

        return OAuth2Auth(
            base_url=profile.base_url,
            client_id=profile.client_id,
            client_secret=profile.client_secret,
            scope=profile.scope,
            redirect_uri=profile.redirect_uri,
            token_store=token_store_for_scope(scope),
            store_key=f"profile:{profile_name}" if profile_name else f"oauth2:{profile.base_url}",
            redirect_capturer=_probe_capturer,
        )
    return None


def _missing_material_error(profile: Profile, name: str) -> str | None:
    """Return a remedy-pointing error when a known auth kind lacks its secret, else None."""
    if profile.auth == "pat" and not profile.token:
        return f"profile has no token; re-run `d2w profile add {name} --auth pat` to bind a personal access token"
    if profile.auth == "basic" and not (profile.username and profile.password):
        return (
            f"profile has no username/password; re-run `d2w profile add {name} --auth basic` to bind Basic credentials"
        )
    if profile.auth == "session" and not profile.cookie:
        return f"profile has no cookie; re-run `d2w profile add {name} --auth session` to bind a fresh session cookie"
    return None


def _probe_unavailable_reason(profile: Profile, name: str) -> str:
    """Explain why a profile can't be probed: missing material, uncached oauth2, or an unknown kind."""
    missing = _missing_material_error(profile, name)
    if missing is not None:
        return missing
    if profile.auth == "oauth2":
        return (
            f"oauth2 profile has no cached tokens — run `d2w profile login {name}` first to complete the browser flow"
        )
    return f"verification does not yet support auth type {profile.auth!r}"


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------


def _resolve_target_path(scope: str, *, start: Path | None = None) -> Path:
    if scope == "project":
        existing = find_project_profiles_file(start)
        if existing is not None:
            return existing
        base = start or Path.cwd()
        return base / ".dhis2" / "profiles.toml"
    if scope == "global":
        return global_profiles_path()
    raise ValueError(f"unknown scope {scope!r}; expected 'project' or 'global'")


class AddProfileResult(BaseModel):
    """Return value of `add_profile` with shadowing metadata for the caller."""

    model_config = ConfigDict(frozen=True)

    path: Path
    shadowed_scope: str | None = None  # "global" or "project" if this write shadows an existing profile


def add_profile(
    name: str,
    profile: Profile,
    *,
    scope: str = "global",
    make_default: bool = False,
    start: Path | None = None,
) -> AddProfileResult:
    """Upsert a profile into the chosen scope's `profiles.toml`.

    Default scope is `global` (user-wide). Pass `scope="project"` for a
    project-local override. The returned `AddProfileResult.shadowed_scope`
    is set when the write creates (or updates) a profile that shadows or
    is shadowed by another scope — callers (CLI, MCP) can surface a
    warning so the user isn't surprised.
    """
    validate_profile_name(name)
    catalog = load_catalog(start=start)
    shadowed_scope: str | None = None
    if scope == "project" and name in catalog.global_.profiles:
        shadowed_scope = "global"
    elif scope == "global" and name in catalog.project.profiles:
        shadowed_scope = "project"
    path = _resolve_target_path(scope, start=start)
    data = load_profiles_file(path)
    data.profiles[name] = profile
    if make_default or not data.default:
        data.default = name
    write_profiles_file(path, data)
    return AddProfileResult(path=path, shadowed_scope=shadowed_scope)


def remove_profile(name: str, *, scope: str | None = None, start: Path | None = None) -> Path:
    """Remove a profile. If `scope` is None, remove from whichever file holds it."""
    catalog = load_catalog(start=start)
    if name not in catalog.merged:
        raise UnknownProfileError(f"no profile named {name!r}")
    origin_path = catalog.merged[name].source_path
    target = _resolve_target_path(scope, start=start) if scope else origin_path
    if target is None:
        raise NoProfileError(
            f"cannot remove {name!r} — it has no source file (env-raw profiles are derived from environment variables)"
        )
    data = load_profiles_file(target)
    if name not in data.profiles:
        raise UnknownProfileError(f"profile {name!r} is not in {target}")
    del data.profiles[name]
    if data.default == name:
        data.default = next(iter(data.profiles), None)
    write_profiles_file(target, data)
    return target


def rename_profile(old_name: str, new_name: str, *, start: Path | None = None) -> Path:
    """Rename a profile in-place inside whichever file holds it.

    Preserves scope (project / global) and updates the `default` key if the
    renamed profile was the default. Raises `UnknownProfileError` if `old_name`
    isn't defined, `InvalidProfileNameError` if `new_name` fails validation,
    and `ProfileAlreadyExistsError` if `new_name` already exists elsewhere.
    """
    validate_profile_name(new_name)
    catalog = load_catalog(start=start)
    if old_name not in catalog.merged:
        raise UnknownProfileError(f"no profile named {old_name!r}")
    if new_name != old_name and new_name in catalog.merged:
        raise ProfileAlreadyExistsError(
            f"a profile named {new_name!r} already exists; remove it first or pick another name"
        )
    origin_path = catalog.merged[old_name].source_path
    if origin_path is None:
        raise NoProfileError(
            f"cannot rename {old_name!r} — it has no source file "
            "(env-raw profiles are derived from environment variables)"
        )
    data = load_profiles_file(origin_path)
    if old_name not in data.profiles:
        raise UnknownProfileError(f"profile {old_name!r} is not present in {origin_path}")
    # Rename while preserving insertion order: build a new dict.
    reordered: dict[str, Profile] = {}
    for key, profile in data.profiles.items():
        reordered[new_name if key == old_name else key] = profile
    data.profiles = reordered
    if data.default == old_name:
        data.default = new_name
    write_profiles_file(origin_path, data)
    return origin_path


def set_default_profile(name: str, *, scope: str = "global", start: Path | None = None) -> Path:
    """Set `default = name` in the chosen scope's `profiles.toml`."""
    validate_profile_name(name)
    path = _resolve_target_path(scope, start=start)
    data = load_profiles_file(path)
    catalog = load_catalog(start=start)
    if name not in catalog.merged and name not in data.profiles:
        raise UnknownProfileError(
            f"no profile named {name!r} exists in project or global files; add it first with `d2w profile add`."
        )
    data.default = name
    write_profiles_file(path, data)
    return path


class ProfileMeta(BaseModel):
    """Resolution metadata for a profile — name, source file, precedence layer."""

    model_config = ConfigDict(frozen=True)

    name: str
    source: ProfileSource
    source_path: str | None = None


class ProfileView(Profile):
    """A Profile plus its resolution meta — returned by `show_profile`."""

    meta: ProfileMeta


def show_profile(name: str, *, include_secrets: bool = False, start: Path | None = None) -> ProfileView:
    """Return one profile with its resolution meta. Secrets redacted unless explicitly requested."""
    resolved = resolve(name, start=start)
    profile = resolved.profile
    if not include_secrets:
        profile = profile.model_copy(
            update={
                "token": "***" if profile.token else None,
                "password": "***" if profile.password else None,
                "client_secret": "***" if profile.client_secret else None,
                "cookie": "***" if profile.cookie else None,
            }
        )
    return ProfileView(
        **profile.model_dump(),
        meta=ProfileMeta(
            name=resolved.name,
            source=resolved.source,
            source_path=str(resolved.source_path) if resolved.source_path else None,
        ),
    )


# ---------------------------------------------------------------------------
# OIDC discovery — populate a profile from /.well-known/openid-configuration
# ---------------------------------------------------------------------------


class DiscoveredOidcProfile(BaseModel):
    """Summary of an OIDC discovery round-trip + the Profile that would be saved."""

    model_config = ConfigDict(frozen=True)

    discovery_url: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    scopes_supported: list[str]
    profile: Profile


async def discover_oidc_profile(
    url: str,
    *,
    client_id: str,
    client_secret: str,
    scope: str = "ALL",
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    version: Dhis2 | None = None,
) -> DiscoveredOidcProfile:
    """Fetch `/.well-known/openid-configuration` from `url` and build the profile it implies.

    `url` may be either the DHIS2 base URL or the full discovery URL — the
    preflight normalises. Client credentials can't come from discovery
    (they're per-registration), so `client_id` + `client_secret` are
    required arguments.

    Returns the discovered metadata + an unsaved `Profile` ready to hand
    to `add_profile`. The caller chooses the name and scope.
    """
    from dhis2w_core.oauth2_preflight import DISCOVERY_PATH, fetch_oidc_discovery

    discovery = await fetch_oidc_discovery(url)
    issuer = discovery.issuer.rstrip("/")
    # For DHIS2, the issuer IS the base URL. This is the safest value to
    # store — it's what the server advertises as its own identity.
    profile = Profile(
        base_url=issuer,
        auth="oauth2",
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        redirect_uri=redirect_uri,
        version=version,
    )
    normalised = url.rstrip("/")
    if not normalised.endswith(DISCOVERY_PATH):
        normalised = normalised + DISCOVERY_PATH
    return DiscoveredOidcProfile(
        discovery_url=normalised,
        issuer=discovery.issuer,
        authorization_endpoint=discovery.authorization_endpoint,
        token_endpoint=discovery.token_endpoint,
        jwks_uri=discovery.jwks_uri,
        scopes_supported=list(discovery.scopes_supported),
        profile=profile,
    )
