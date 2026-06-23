"""Version-specific wire extraction for the v42 security plugin (2FA + last login + route auth + tokens).

v42 removed every admin-readable per-user 2FA field from the User resource
(BUGS.md #47); 2FA enrolment is read via the superuser-only
`/api/users/twoFactor` audit endpoints instead, so it is not requested here.

The generated v42 `ApiToken` carries `type` as the `ApiTokenType` enum and `createdBy` as a `UserDto`
(v41 differs on both); `tokens_from_raw` normalises `type` to a plain str and reads only the owner id, so
`security_core.tokens` stays version-neutral and never imports `ApiTokenType`.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.generated.v42.oas import ApiToken
from dhis2w_client.v42.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    HttpBasicAuthScheme,
    OAuth2ClientCredentialsAuthScheme,
    auth_scheme_from_route,
)
from pydantic import ValidationError

from dhis2w_core.security_core import TokenAllowlists, TokenView, TwoFactorSource

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
    except (ValidationError, ValueError, TypeError):
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


def tokens_from_raw(raw: list[Any]) -> list[TokenView]:
    """Validate each raw /api/apiToken record into the v42 generated ApiToken and project a TokenView.

    The generated v42 `ApiToken.type` is the `ApiTokenType` enum; it is normalised to a plain str here so
    `security_core.tokens` stays version-neutral. `createdBy` is a `UserDto`, so the owner id is read off
    `createdBy.id`. The secret `key` is `@JsonIgnore` upstream and absent from the wire, so it is never read
    or carried. A record that fails validation is skipped rather than aborting the whole inventory.
    """
    views: list[TokenView] = []
    for record in raw:
        if not isinstance(record, dict):
            continue
        try:
            token = ApiToken.model_validate(record)
        except (ValidationError, ValueError, TypeError):
            continue
        created = token.created.isoformat() if token.created is not None else None
        owner = token.createdBy.id if token.createdBy is not None else None
        views.append(
            TokenView(
                id=token.id or "",
                name=token.name,
                token_type=str(token.type) if token.type is not None else "unknown",
                expire_epoch_millis=token.expire,
                created=created,
                owner_id=owner,
                allowlists=_token_allowlists(token),
            )
        )
    return views


def _token_allowlists(token: ApiToken) -> TokenAllowlists:
    """Flatten a token's polymorphic attributes list into the IP / method / referer allowlist tuples.

    Each attribute is routed by its `type` discriminator (`IpAllowedList` / `MethodAllowedList` /
    `RefererAllowedList`), not by the Python class: the generated `attributes` union is undiscriminated, so
    pydantic may coerce one shape into a sibling class while the value field rides along in `extra`. Reading
    by the discriminator + `getattr` is therefore robust to that coercion.
    """
    ips: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    referrers: tuple[str, ...] = ()
    for attribute in token.attributes or ():
        kind = getattr(attribute, "type", None)
        if kind == "IpAllowedList":
            ips = tuple(getattr(attribute, "allowedIps", None) or ())
        elif kind == "MethodAllowedList":
            methods = tuple(getattr(attribute, "allowedMethods", None) or ())
        elif kind == "RefererAllowedList":
            referrers = tuple(getattr(attribute, "allowedReferrers", None) or ())
    return TokenAllowlists(ips=ips, methods=methods, referrers=referrers)
