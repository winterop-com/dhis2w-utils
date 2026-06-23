"""Version-specific wire extraction for the v42 security plugin (2FA + last login).

v42 removed every admin-readable per-user 2FA field from the User resource
(BUGS.md #47); 2FA enrolment is read via the superuser-only
`/api/users/twoFactor` audit endpoints instead, so it is not requested here.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.v42.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    HttpBasicAuthScheme,
    OAuth2ClientCredentialsAuthScheme,
    auth_scheme_from_route,
)
from pydantic import ValidationError

from dhis2w_core.security_core import TwoFactorSource

USER_FIELDS = "id,username,disabled,email,lastLogin,userRoles[id]"
TWO_FACTOR_SOURCE: TwoFactorSource = TwoFactorSource.AUDIT_ENDPOINT


def two_factor_enabled(user: dict[str, Any]) -> bool | None:
    """v42 does not expose per-user 2FA on /api/users; the audit endpoint supplies it instead."""
    return None


def last_login(user: dict[str, Any]) -> str | None:
    """Read the last-login timestamp from the /api/users record."""
    value = user.get("lastLogin")
    return value if isinstance(value, str) else None


def route_auth(route: Any) -> tuple[str | None, str | None]:
    """Extract (auth_type, non-secret identity) from a v42 Route's discriminated 5-variant auth union.

    The identity is the non-secret field of each scheme (username / clientId / tokenUri); the secret
    is WRITE_ONLY upstream and never serialized, so it is never read here. A route with auth present but
    an unrecognizable or missing `type` (e.g. a future 6th variant) returns ("unknown", None) so the
    route-carries-auth INFO finding still fires -- credentials are present even when we cannot classify the
    scheme. ValidationError from the adapter is caught; it never propagates. Returns (None, None) only when
    the route has no auth block at all.
    """
    raw_auth = getattr(route, "auth", None)
    if raw_auth is None:
        return None, None
    try:
        scheme = auth_scheme_from_route(route)
    except (ValidationError, Exception):
        scheme = None
    if scheme is None:
        return "unknown", None
    match scheme:
        case HttpBasicAuthScheme(username=username):
            return "http-basic", username
        case OAuth2ClientCredentialsAuthScheme(clientId=client_id, tokenUri=token_uri):
            return "oauth2-client-credentials", client_id or token_uri
        case ApiTokenAuthScheme():
            return "api-token", None
        case ApiHeadersAuthScheme():
            return "api-headers", None
        case ApiQueryParamsAuthScheme():
            return "api-query-params", None
    return "unknown", None
