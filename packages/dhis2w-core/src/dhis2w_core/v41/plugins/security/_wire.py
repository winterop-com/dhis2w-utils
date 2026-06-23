"""Version-specific wire extraction for the v41 security plugin (2FA + last login + route auth).

v41's generated `oas.Route.auth` is an UNDISCRIMINATED 4-variant union with no `oauth2-client-credentials`
member and no `type` discriminator (BUGS.md #14): the OAS gap upstream omits the Jackson `type` field, so
the codegen spec-patch synthesises a discriminated union only in the `auth_schemes` re-export. The route
auth extractor below re-validates through that adapter, which correctly picks the variant by `type`, and
references only the four schemes v41 carries -- never the OAuth2 variant, which does not exist here.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.v41.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    HttpBasicAuthScheme,
    auth_scheme_from_route,
)
from pydantic import ValidationError

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


def route_auth(route: Any) -> tuple[str | None, str | None]:
    """Extract (auth_type, non-secret identity) from a v41 Route's 4-variant auth union (BUGS.md #14).

    v41 has no `oauth2-client-credentials` scheme, so only the four variants v41 carries are matched. A
    route with auth present but an unrecognizable or missing `type` (including an oauth2 block on the wire
    that v41 cannot model) returns ("unknown", None) so the route-carries-auth INFO finding still fires --
    credentials are present even when we cannot classify the scheme. ValidationError from the adapter is
    caught; it never propagates. Returns (None, None) only when the route has no auth block at all.
    """
    raw_auth = getattr(route, "auth", None)
    if raw_auth is None:
        return None, None
    try:
        scheme = auth_scheme_from_route(route)
    except (ValidationError, Exception):
        scheme = None
    if scheme is None:
        # auth block present but unrecognizable: report "unknown" so the carries-auth INFO fires.
        return "unknown", None
    match scheme:
        case HttpBasicAuthScheme(username=username):
            return "http-basic", username
        case ApiTokenAuthScheme():
            return "api-token", None
        case ApiHeadersAuthScheme():
            return "api-headers", None
        case ApiQueryParamsAuthScheme():
            return "api-query-params", None
    return "unknown", None
