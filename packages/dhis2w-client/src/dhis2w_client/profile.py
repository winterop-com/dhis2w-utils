"""DHIS2 connection profile — the Pydantic model shared across the workspace.

The model itself lives in `dhis2w-client` so library users can build a
`Profile` and call `open_client(profile)` for PAT, Basic, or session auth
without installing `dhis2w-core`. TOML loading, multi-profile resolution, and
OAuth2 token persistence stay in `dhis2w-core`.
"""

from __future__ import annotations

import os
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from dhis2w_client.generated import Dhis2


class Profile(BaseModel):
    """Resolved DHIS2 connection settings for a single session.

    `version` is a plugin-tree hint, NOT a wire-client pin. When set, CLI
    and MCP bootstraps load the matching `dhis2w_core.v{N}.plugins.*` tree
    (so v43 plugin overrides for BUGS #33/#34/#35 are picked up against a
    v43 stack). The wire `Dhis2Client` always auto-detects the server's
    version on connect and rebinds accessors via `_dispatch.py` —
    `profile.version` doesn't override that. When unset, plugin discovery
    falls back to `DHIS2_VERSION` env var (`41`/`42`/`43`), then to v42.
    """

    model_config = ConfigDict(frozen=True)

    base_url: str
    auth: Literal["pat", "basic", "oauth2", "session"]
    token: str | None = None
    username: str | None = None
    password: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scope: str | None = None
    redirect_uri: str | None = None
    cookie: str | None = None
    """Raw `Cookie` header value for `auth="session"` (e.g. `JSESSIONID=abc123`; the name is included)."""
    version: Dhis2 | None = None
    """Plugin-tree hint (see class docstring). Wire version is auto-detected on connect()."""

    @field_validator("cookie")
    @classmethod
    def _normalize_cookie(cls, value: str | None) -> str | None:
        """Trim surrounding whitespace and reject a cookie carrying ASCII control characters."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("session cookie is empty after trimming whitespace — re-copy the raw Cookie header value")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
            raise ValueError(
                "session cookie contains control characters or stray line breaks — "
                "re-copy the value from the browser without embedded newlines, carriage returns, or tabs"
            )
        return normalized


class NoProfileError(RuntimeError):
    """Raised when no DHIS2 profile can be resolved."""


class UnknownProfileError(LookupError):
    """Raised when a named profile is requested but does not exist in any profile file."""


class InvalidProfileNameError(ValueError):
    """Raised when a profile name does not match the required format."""


PROFILE_NAME_MAX_LEN = 64
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_profile_name(name: str) -> str:
    """Validate and return a profile name.

    Rules:
      - must not be empty
      - first character must be an ASCII letter (A-Z, a-z)
      - remaining characters must be letters, digits, or underscore
      - max length 64 characters

    Typical valid names: `local`, `prod`, `prod_eu`, `test42`, `laohis42`.
    Raises `InvalidProfileNameError` on violation. The constraint keeps names
    safe as env var suffixes, TOML keys, and unquoted shell arguments.
    """
    if not name:
        raise InvalidProfileNameError("profile name must be a non-empty string")
    if len(name) > PROFILE_NAME_MAX_LEN:
        raise InvalidProfileNameError(f"profile name {name!r} exceeds the {PROFILE_NAME_MAX_LEN}-character limit")
    if not _PROFILE_NAME_RE.match(name):
        raise InvalidProfileNameError(
            f"profile name {name!r} is invalid — must start with a letter "
            "and contain only letters, digits, and underscores (a-z, A-Z, 0-9, _)"
        )
    return name


def profile_from_env_raw() -> Profile | None:
    """Build a `Profile` from `DHIS2_URL` + credentials env vars.

    Returns `None` when `DHIS2_URL` is unset or no credential pair is present.
    Recognises `DHIS2_PAT` (PAT auth, wins over Basic) and the
    `DHIS2_USERNAME` + `DHIS2_PASSWORD` pair (Basic auth). Reads
    `DHIS2_VERSION` (`"41"` / `"42"` / `"43"` or `"v41"` / `"v42"` / `"v43"`)
    into `Profile.version` when set.

    Library callers that want full TOML + env precedence resolution (the
    chain the `d2w` CLI uses) should install `dhis2w-core` and call
    `dhis2w_core.profile_from_env()` instead.
    """
    base_url = os.environ.get("DHIS2_URL", "").rstrip("/")
    if not base_url:
        return None
    version = _env_version()
    pat = os.environ.get("DHIS2_PAT")
    if pat:
        return Profile(base_url=base_url, auth="pat", token=pat, version=version)
    username = os.environ.get("DHIS2_USERNAME")
    password = os.environ.get("DHIS2_PASSWORD")
    if username and password:
        return Profile(base_url=base_url, auth="basic", username=username, password=password, version=version)
    return None


def _env_version() -> Dhis2 | None:
    """Read `DHIS2_VERSION` env (`"43"` or `"v43"`) into a `Dhis2` enum member.

    Accepts both the bare major (`"41"` / `"42"` / `"43"`) and the
    v-prefixed form (`"v41"` / `"v42"` / `"v43"`). Returns None when unset
    or malformed — `open_client` then falls back to auto-detect via
    `/api/system/info`.
    """
    raw = os.environ.get("DHIS2_VERSION", "").strip().lower()
    if not raw:
        return None
    key = raw if raw.startswith("v") else f"v{raw}"
    try:
        return Dhis2(key)
    except ValueError:
        return None
