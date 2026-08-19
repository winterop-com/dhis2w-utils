"""Version-specific wire extraction for the v41 security plugin (2FA + last login + route auth + tokens).

v41's generated `oas.Route.auth` is an UNDISCRIMINATED 4-variant union with no `oauth2-client-credentials`
member and no `type` discriminator (BUGS.md #14): the OAS gap upstream omits the Jackson `type` field, so
the codegen spec-patch synthesises a discriminated union only in the `auth_schemes` re-export. The route
auth extractor below re-validates through that adapter, which correctly picks the variant by `type`, and
references only the four schemes v41 carries; never the OAuth2 variant, which does not exist here.

The generated v41 `ApiToken` differs from v42/v43: `type` is a `Literal`, not the `ApiTokenType` enum
(which v41 does not have), and `createdBy` is an id-only inline class rather than a `UserDto`.
`tokens_from_raw` normalises `type` to a plain str and reads the owner id off `createdBy.id`, so
`security_core.tokens` stays version-neutral; v41 deliberately never imports `ApiTokenType`.

The OAuth2 client wire shape diverges too (BUGS.md #52, cross-referencing #39): v41 has only the
array-typed `OAuth2Client` with the `cid` identifier, while v42/v43 have only the comma-string
`Dhis2OAuth2Client` with `clientId`, and there is no version-invariant generated schema. The list
envelope key is `oAuth2Clients` on every major. `oauth2_clients` validates each `oAuth2Clients[]`
record through the v41 `OAuth2Client` and projects it into the version-invariant `OAuth2ClientView`;
v41 deliberately never imports `Dhis2OAuth2Client`. The secret `secret` field is never read, so no
secret reaches a finding.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.generated.v41.oas import ApiToken, OAuth2Client
from dhis2w_client.v41.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    HttpBasicAuthScheme,
    auth_scheme_from_route,
)
from pydantic import ValidationError

from dhis2w_core.security_core import OAuth2ClientView, TokenAllowlists, TokenView, TwoFactorSource

# v41 still exposes per-user 2FA state on the User resource, so it is requested inline. v41 nests
# passwordLastUpdated under userCredentials (flattened onto the User from v42; BUGS.md #56).
USER_FIELDS = (
    "id,username,disabled,email,lastLogin,twoFactorEnabled,userCredentials[twoFA,passwordLastUpdated],userRoles[id]"
)
TWO_FACTOR_SOURCE: TwoFactorSource = TwoFactorSource.USER_FIELD

# OAuth2 client fields the auth-methods check reads on v41: the `cid` identifier, display name, and the
# array-typed grant types and redirect URIs. The secret is never requested, so it never reaches a finding.
OAUTH2_CLIENT_FIELDS = "cid,displayName,grantTypes,redirectUris"


# The three field extractors below intentionally take the raw /api/users record rather than a
# validated generated `User` (unlike `tokens_from_raw` / `oauth2_clients`, which validate each raw
# record through its generated schema): pydantic's default lenient coercion accepts values the wire
# contract must reject outright, e.g. `User.model_validate({"passwordLastUpdated": 123})` silently
# turns the int into a valid epoch timestamp instead of failing, and `{"twoFactorEnabled": "yes"}`
# coerces to `True`. That would defeat the deliberate `isinstance(value, str | bool)` guards below,
# which treat any non-conforming wire value as absent rather than trust a type-coerced guess.
# `test_security_hygiene.py` (test_password_last_updated_v41_reads_nested_user_credentials, and the
# v42/v43 counterpart) pins the strict-or-None behaviour across all three trees, so these three stay
# on `dict[str, Any]`; the nested `userCredentials` shape itself is a genuine, separate wire divergence
# (BUGS.md #56), also not representable as a flat top-level read.
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


def password_last_updated(user: dict[str, Any]) -> str | None:
    """Read v41's nested userCredentials.passwordLastUpdated timestamp from the /api/users record (BUGS.md #56)."""
    credentials = user.get("userCredentials")
    if not isinstance(credentials, dict):
        return None
    value = credentials.get("passwordLastUpdated")
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
    except (ValidationError, ValueError, TypeError):
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


def tokens_from_raw(raw: list[Any]) -> list[TokenView]:
    """Validate each raw /api/apiToken record into the v41 generated ApiToken and project a TokenView.

    The generated v41 `ApiToken.type` is a `Literal` (v41 has no `ApiTokenType` enum); `str(token.type)`
    yields the plain token-type string directly so `security_core.tokens` stays version-neutral. `createdBy`
    is an id-only inline class, so the owner id is read off `createdBy.id`. The secret `key` is `@JsonIgnore`
    upstream and absent from the wire, so it is never read or carried. A record that fails validation is
    skipped rather than aborting the whole inventory.
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
    """Project each v41 `/api/oAuth2Clients` record from the `oAuth2Clients` envelope into an OAuth2ClientView.

    v41 returns the clients under the `oAuth2Clients` key, each with the `cid` identifier and array-typed
    `grantTypes` / `redirectUris`. Grant types are normalised to lowercase so the version-invariant reducer
    compares against the canonical OAuth2 grant tokens. The secret `secret` field is never read, so no secret
    is ever carried. A record that fails validation is skipped rather than aborting the whole inventory.
    """
    records = raw.get("oAuth2Clients")
    if not isinstance(records, list):
        return []
    views: list[OAuth2ClientView] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            client = OAuth2Client.model_validate(record)
        except (ValidationError, ValueError, TypeError):
            continue
        views.append(
            OAuth2ClientView(
                identifier=client.cid or "",
                display_name=client.displayName,
                grant_types=_grant_types(client),
                redirect_uris=_redirect_uris(client),
            )
        )
    return views


def _grant_types(client: OAuth2Client) -> frozenset[str]:
    """Normalise the v41 array-typed `grantTypes` to a lowercase frozenset."""
    return frozenset(value.strip().lower() for value in (client.grantTypes or ()) if value.strip())


def _redirect_uris(client: OAuth2Client) -> tuple[str, ...]:
    """Read the v41 array-typed `redirectUris` into a tuple, dropping blanks."""
    return tuple(value.strip() for value in (client.redirectUris or ()) if value.strip())
