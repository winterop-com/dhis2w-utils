"""Profile resolution for dhis2w-core.

The `Profile` Pydantic model itself lives in `dhis2w-client` so library
users on PAT or Basic can build profiles and call `open_client(profile)`
without dragging in this package's heavier dependencies. This module
re-exports `Profile` and friends for back-compat, and owns the parts that
need TOML I/O and the precedence chain.

Profiles live in either a project-local `.dhis2/profiles.toml` (discovered by
walking up from `$PWD`) or a user-wide `~/.config/dhis2/profiles.toml`.
Environment variables remain supported as a fallback (and as an override via
`DHIS2_PROFILE`).

Resolution precedence (highest wins):
  1. `name` argument to `resolve_profile(name)` — explicit per-call.
  2. `DHIS2_PROFILE` env var — set by CLI `--profile` or MCP server config.
  3. `DHIS2_URL` + credentials env — raw env mode (CI-friendly, no TOML).
  4. Project TOML `default` — nearest `.dhis2/profiles.toml` walking up.
  5. User-wide TOML `default` — `~/.config/dhis2/profiles.toml`.
  6. `NoProfileError` — nothing configured.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

import tomli_w
from dhis2w_client.profile import (
    PROFILE_NAME_MAX_LEN,
    InvalidProfileNameError,
    NoProfileError,
    Profile,
    UnknownProfileError,
    validate_profile_name,
)
from dhis2w_client.profile import (
    profile_from_env_raw as _profile_from_env_raw_client,
)
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "NO_PROFILE_HINT_LINES",
    "PROFILE_NAME_MAX_LEN",
    "InvalidProfileNameError",
    "MergedProfile",
    "NoProfileError",
    "Profile",
    "ProfileCatalog",
    "ProfileSource",
    "ProfileVersionMismatchError",
    "ProfilesFile",
    "ResolvedProfile",
    "UnknownProfileError",
    "bind_version_tree",
    "current_bound_version_tree",
    "find_project_profiles_file",
    "global_profiles_path",
    "load_catalog",
    "load_profiles_file",
    "profile_from_env",
    "resolve",
    "resolve_profile",
    "validate_profile_name",
    "write_profiles_file",
]


#: Actionable follow-up steps for `NoProfileError`, shared by every surface that renders it:
#: the CLI's clean-error hint block and the MCP server's tool-error message both read this, so
#: the guidance (hard requirement 1: point at `d2w profile add <name>` / `d2w profile bootstrap`)
#: lives in exactly one place.
NO_PROFILE_HINT_LINES: tuple[str, ...] = (
    "run `d2w profile --help` for setup options, or try:",
    "  d2w profile list                             # see what's configured",
    "  d2w profile add <name> --scope global \\",
    "      --url https://dhis2.example.org \\",
    "      --auth pat --token d2p_... --default",
    "  d2w profile bootstrap <name>                 # provision a PAT/OAuth2 client + profile in one shot",
    "  d2w profile verify <name>                    # confirm auth works",
)


class ProfileVersionMismatchError(RuntimeError):
    """Raised when a per-call profile pins a different DHIS2 major than the bound tree."""


class ProfileAlreadyExistsError(ValueError):
    """Raised when a rename / create would clobber an existing profile name."""


_bound_version_key: str | None = None


def bind_version_tree(version_key: str | None) -> None:
    """Pin the active plugin tree for subsequent `resolve()` / `resolve_profile()` calls.

    Called once by `dhis2w-mcp`'s `build_server()` at boot so per-call
    profiles that pin a different DHIS2 major fail loud (with a clear
    restart hint) instead of silently parsing v43 wire payloads through
    v42 schemas — and vice versa — when the bound plugin tree doesn't
    match the profile's `version` field.

    The CLI does not call this: it builds the plugin tree fresh per
    invocation, so the bound tree always matches the active profile by
    construction. Pass `None` to clear the binding (used by tests).
    """
    global _bound_version_key  # noqa: PLW0603 — intentional process-wide binding
    _bound_version_key = version_key


def current_bound_version_tree() -> str | None:
    """Return the plugin tree pinned by `bind_version_tree()`, or `None` when unbound.

    Consumed by `open_client()` to thread the bound key into `Dhis2Client`'s
    `version=` pin so the on-connect `/api/system/info` check catches a
    wrong-major server even when the per-call profile has no `.version`
    field of its own.
    """
    return _bound_version_key


def _check_bound_tree(resolved: ResolvedProfile) -> None:
    """Raise `ProfileVersionMismatchError` if the resolved profile pins a different major."""
    if _bound_version_key is None or resolved.profile.version is None:
        return
    profile_key = resolved.profile.version.value
    if profile_key == _bound_version_key:
        return
    target_major = profile_key.removeprefix("v")
    raise ProfileVersionMismatchError(
        f"profile {resolved.name!r} pins version {profile_key!r} but this server booted "
        f"with the {_bound_version_key!r} plugin tree. Tools dispatched against this "
        f"profile would parse a v{target_major} DHIS2 server's payloads through "
        f"{_bound_version_key} schemas, silently round-tripping renamed or added fields wrong. "
        f"Restart with `DHIS2_VERSION={profile_key} dhis2w-mcp` to target this profile."
    )


ProfileSource = Literal["arg", "env-profile", "env-raw", "project-toml", "global-toml"]


class ResolvedProfile(BaseModel):
    """A resolved profile together with its provenance."""

    model_config = ConfigDict(frozen=True)

    name: str
    profile: Profile
    source: ProfileSource
    source_path: Path | None = None


class MergedProfile(BaseModel):
    """An entry in `ProfileCatalog.merged` — a profile plus where it came from."""

    model_config = ConfigDict(frozen=True)

    profile: Profile
    source: ProfileSource
    source_path: Path | None = None


class ProfilesFile(BaseModel):
    """Parsed contents of a `profiles.toml` file."""

    default: str | None = None
    profiles: dict[str, Profile] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_DIRNAME = ".dhis2"
PROFILES_FILENAME = "profiles.toml"


def global_profiles_path() -> Path:
    """Return `~/.config/dhis2/profiles.toml` (does not create it)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "dhis2" / PROFILES_FILENAME


def find_project_profiles_file(start: Path | None = None) -> Path | None:
    """Walk up from `start` (defaulting to `$PWD`) looking for `.dhis2/profiles.toml`."""
    cwd = start or Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / PROJECT_DIRNAME / PROFILES_FILENAME
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def load_profiles_file(path: Path) -> ProfilesFile:
    """Load a `profiles.toml` file. Missing file → empty `ProfilesFile`."""
    if not path.exists():
        return ProfilesFile()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    default = raw.get("default")
    profiles_section = raw.get("profiles", {})
    profiles: dict[str, Profile] = {}
    for name, settings in profiles_section.items():
        if not isinstance(settings, dict):
            continue
        profiles[name] = Profile.model_validate(settings)
    return ProfilesFile(default=default, profiles=profiles)


def write_profiles_file(path: Path, data: ProfilesFile) -> None:
    """Write a `profiles.toml` file with 0600 perms. Creates parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if data.default is not None:
        payload["default"] = data.default
    if data.profiles:
        payload["profiles"] = {
            name: {k: v for k, v in profile.model_dump(exclude_none=True).items()}
            for name, profile in data.profiles.items()
        }
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class ProfileCatalog(BaseModel):
    """Merged profile namespace across project + global TOML files."""

    model_config = ConfigDict(frozen=True)

    project: ProfilesFile
    project_path: Path | None
    global_: ProfilesFile
    global_path: Path

    @property
    def merged(self) -> dict[str, MergedProfile]:
        """Return all profiles keyed by name, project overrides global."""
        merged: dict[str, MergedProfile] = {}
        for name, profile in self.global_.profiles.items():
            merged[name] = MergedProfile(profile=profile, source="global-toml", source_path=self.global_path)
        for name, profile in self.project.profiles.items():
            merged[name] = MergedProfile(profile=profile, source="project-toml", source_path=self.project_path)
        return merged

    @property
    def default_name(self) -> str | None:
        """Return the effective default name (project wins over global)."""
        return self.project.default or self.global_.default


def load_catalog(start: Path | None = None) -> ProfileCatalog:
    """Load and merge profiles from the project and global TOML files."""
    project_path = find_project_profiles_file(start)
    project = load_profiles_file(project_path) if project_path else ProfilesFile()
    global_path = global_profiles_path()
    global_ = load_profiles_file(global_path)
    return ProfileCatalog(project=project, project_path=project_path, global_=global_, global_path=global_path)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_profile(name: str | None = None, *, start: Path | None = None) -> Profile:
    """Resolve a `Profile` using the documented precedence chain."""
    return resolve(name, start=start).profile


def resolve(name: str | None = None, *, start: Path | None = None) -> ResolvedProfile:
    """Return the resolved profile together with its provenance."""
    resolved = _resolve_raw(name, start=start)
    _check_bound_tree(resolved)
    return resolved


def _resolve_raw(name: str | None, *, start: Path | None) -> ResolvedProfile:
    # 1. Explicit name argument.
    if name:
        return _resolve_by_name(name, source="arg", start=start)
    # 2. DHIS2_PROFILE env var.
    env_name = os.environ.get("DHIS2_PROFILE")
    if env_name:
        return _resolve_by_name(env_name, source="env-profile", start=start)
    # 3. Raw env (DHIS2_URL + creds) — CI-friendly, no TOML needed.
    raw = _profile_from_env_raw_client()
    if raw is not None:
        return ResolvedProfile(name="<env>", profile=raw, source="env-raw")
    # 4. Project TOML default.
    # 5. Global TOML default.
    catalog = load_catalog(start=start)
    default_name = catalog.default_name
    if default_name:
        return _resolve_by_name(default_name, source="project-toml", start=start, catalog=catalog)
    raise NoProfileError("no DHIS2 profile is configured")


def _resolve_by_name(
    name: str,
    *,
    source: ProfileSource,
    start: Path | None,
    catalog: ProfileCatalog | None = None,
) -> ResolvedProfile:
    catalog = catalog or load_catalog(start=start)
    merged = catalog.merged
    if name not in merged:
        available = sorted(merged)
        raise UnknownProfileError(
            f"no profile named {name!r} (available: {', '.join(available) if available else 'none'}). "
            "Run `d2w profile list` to see all profiles."
        )
    entry = merged[name]
    # If caller asked by explicit name (`arg`/`env-profile`), report THAT origin rather than TOML layer.
    reported_source = source if source in {"arg", "env-profile"} else entry.source
    return ResolvedProfile(name=name, profile=entry.profile, source=reported_source, source_path=entry.source_path)


def profile_from_env() -> Profile:
    """Resolve a `Profile` through the full precedence chain (TOML + env).

    Alias for `resolve_profile()` that returns only the `Profile` (drops the
    `ResolvedProfile` envelope). For env-only resolution, read `os.environ`
    directly.
    """
    return resolve_profile()
