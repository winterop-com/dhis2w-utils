"""Version-specific wire extraction for the v42 security plugin (2FA + last login + route auth + tokens).

v42 removed every admin-readable per-user 2FA field from the User resource
(BUGS.md #58); 2FA enrolment is read via the superuser-only
`/api/users/twoFactor` audit endpoints instead, so it is not requested here.

The generated v42 `ApiToken` carries `type` as the `ApiTokenType` enum and `createdBy` as a `UserDto`
(v41 differs on both); `tokens_from_raw` normalises `type` to a plain str and reads only the owner id, so
`security_core.tokens` stays version-neutral and never imports `ApiTokenType`.

The OAuth2 client wire shape diverges from v41 (BUGS.md #52, cross-referencing #39): v42/v43 have only the
comma-string `Dhis2OAuth2Client` with the `clientId` identifier and the `oAuth2Clients` list envelope, while
v41 has only the array-typed `OAuth2Client` with `cid` and the `data` envelope, and there is no
version-invariant generated schema. `oauth2_clients` validates each `oAuth2Clients[]` record through the v42
`Dhis2OAuth2Client`, splits the comma-string grant types and redirect URIs into lists, normalises grant types
to lowercase, and projects into the version-invariant `OAuth2ClientView`; v42 deliberately never imports
`OAuth2Client`. The secret `clientSecret` field is never read, so no secret reaches a finding.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.generated.v42.oas import ApiToken, Dhis2OAuth2Client
from dhis2w_client.v42.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    HttpBasicAuthScheme,
    OAuth2ClientCredentialsAuthScheme,
    auth_scheme_from_route,
)
from pydantic import ValidationError

from dhis2w_core.security_core import OAuth2ClientView, TokenAllowlists, TokenView, TwoFactorSource
from dhis2w_core.security_core.text import split_delimited

USER_FIELDS = "id,username,disabled,email,lastLogin,passwordLastUpdated,userRoles[id]"
TWO_FACTOR_SOURCE: TwoFactorSource = TwoFactorSource.AUDIT_ENDPOINT

# OAuth2 client fields the auth-methods check reads on v42: the `clientId` identifier, display name, and the
# comma-string grant types and redirect URIs. The secret is never requested, so it never reaches a finding.
OAUTH2_CLIENT_FIELDS = "clientId,displayName,authorizationGrantTypes,redirectUris"


# The three field extractors below intentionally take the raw /api/users record rather than a
# validated generated `User` (unlike `tokens_from_raw` / `oauth2_clients`, which validate each raw
# record through its generated schema): pydantic's default lenient coercion accepts values the wire
# contract must reject outright, e.g. `User.model_validate({"passwordLastUpdated": 123})` silently
# turns the int into a valid epoch timestamp instead of failing, and `{"twoFactorEnabled": "yes"}`
# coerces to `True`. That would defeat the deliberate `isinstance(value, str | bool)` guards below,
# which treat any non-conforming wire value as absent rather than trust a type-coerced guess.
# `test_security_hygiene.py` (test_password_last_updated_v42_v43_*) pins the strict-or-None behaviour
# across all three trees, so these three stay on `dict[str, Any]`.
def two_factor_enabled(user: dict[str, Any]) -> bool | None:
    """v42 does not expose per-user 2FA on /api/users; the audit endpoint supplies it instead."""
    return None


def last_login(user: dict[str, Any]) -> str | None:
    """Read the last-login timestamp from the /api/users record."""
    value = user.get("lastLogin")
    return value if isinstance(value, str) else None


def password_last_updated(user: dict[str, Any]) -> str | None:
    """Read v42's flattened top-level passwordLastUpdated timestamp from the /api/users record."""
    value = user.get("passwordLastUpdated")
    return value if isinstance(value, str) else None


def route_auth(route: Any) -> tuple[str | None, str | None]:
    """Extract (auth_type, non-secret identity) from a v42 Route's discriminated 5-variant auth union.

    The identity is the non-secret field of each scheme (username / clientId / tokenUri); the secret
    is WRITE_ONLY upstream and never serialized, so it is never read here. A route with auth present but
    an unrecognizable or missing `type` (e.g. a future 6th variant) returns ("unknown", None) so the
    route-carries-auth INFO finding still fires; credentials are present even when we cannot classify the
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


def oauth2_clients(raw: dict[str, Any]) -> list[OAuth2ClientView]:
    """Project each v42 `/api/oAuth2Clients` record from the `oAuth2Clients` envelope into an OAuth2ClientView.

    v42 returns the clients under the `oAuth2Clients` key, each with the `clientId` identifier and the
    comma-string `authorizationGrantTypes` / `redirectUris`. The comma-strings are split into lists and grant
    types normalised to lowercase so the version-invariant reducer compares against the canonical OAuth2 grant
    tokens. The secret `clientSecret` field is never read, so no secret is ever carried. A record that fails
    validation is skipped rather than aborting the whole inventory.
    """
    records = raw.get("oAuth2Clients")
    if not isinstance(records, list):
        return []
    views: list[OAuth2ClientView] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            client = Dhis2OAuth2Client.model_validate(record)
        except (ValidationError, ValueError, TypeError):
            continue
        views.append(
            OAuth2ClientView(
                identifier=client.clientId or "",
                display_name=client.displayName,
                grant_types=_grant_types(client),
                redirect_uris=_redirect_uris(client),
            )
        )
    return views


def _grant_types(client: Dhis2OAuth2Client) -> frozenset[str]:
    """Split the v42 comma-string `authorizationGrantTypes` into a lowercase frozenset."""
    return frozenset(split_delimited(client.authorizationGrantTypes, lower=True))


def _redirect_uris(client: Dhis2OAuth2Client) -> tuple[str, ...]:
    """Split the v42 comma-string `redirectUris` into a tuple, preserving case."""
    return tuple(split_delimited(client.redirectUris, lower=False))
