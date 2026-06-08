"""Standard OAuth2 client seeded by `seed_auth.py`. Edit to change the client config.

Deterministic values so tests and manual exploration can rely on them. Re-running
the seed overwrites the existing client (by clientId lookup) instead of creating
duplicates.
"""

from __future__ import annotations

from typing import Any

import bcrypt  # injected via `uv run --with bcrypt` by infra/Makefile

OAUTH2_CLIENT_ID = "dhis2w-utils-local"
OAUTH2_CLIENT_SECRET = "dhis2w-utils-local-secret-do-not-use-in-prod"  # noqa: S105 — local only
OAUTH2_REDIRECT_URI = "http://localhost:8765"
OAUTH2_SCOPES = "ALL"  # DHIS2 only recognises the single scope `ALL`
OAUTH2_GRANT_TYPES = "authorization_code,refresh_token"
# Spring Authorization Server requires this field to know how the client presents
# its credentials at /oauth2/token. client_secret_basic = HTTP Basic; client_secret_post
# = secret in the POST body. Registering both gives clients flexibility.
OAUTH2_CLIENT_AUTH_METHODS = "client_secret_basic,client_secret_post"

# DHIS2 stores Spring Authorization Server ClientSettings / TokenSettings as Jackson-serialized
# JSON TEXT columns. Leaving them empty triggers `IllegalArgumentException: settings cannot be
# empty` inside `Dhis2OAuth2ClientServiceImpl.toObject` when Spring AS tries to rebuild a
# RegisteredClient for /oauth2/authorize. These default values match what DHIS2's built-in
# settings app (/apps/settings#/oauth2) writes when a client is created through the UI.
OAUTH2_CLIENT_SETTINGS_JSON = (
    '{"@class":"java.util.Collections$UnmodifiableMap",'
    '"settings.client.require-proof-key":false,'
    '"settings.client.require-authorization-consent":true}'
)
OAUTH2_TOKEN_SETTINGS_JSON = (
    '{"@class":"java.util.Collections$UnmodifiableMap",'
    '"settings.token.reuse-refresh-tokens":true,'
    '"settings.token.x509-certificate-bound-access-tokens":false,'
    '"settings.token.id-token-signature-algorithm":'
    '["org.springframework.security.oauth2.jose.jws.SignatureAlgorithm","RS256"],'
    '"settings.token.access-token-time-to-live":["java.time.Duration",300.000000000],'
    '"settings.token.access-token-format":'
    '{"@class":"org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat",'
    '"value":"self-contained"},'
    '"settings.token.refresh-token-time-to-live":["java.time.Duration",3600.000000000],'
    '"settings.token.authorization-code-time-to-live":["java.time.Duration",300.000000000],'
    '"settings.token.device-code-time-to-live":["java.time.Duration",300.000000000]}'
)


def _bcrypt_hash(plaintext: str) -> str:
    """Produce a BCrypt hash of `plaintext` compatible with DHIS2's BCryptPasswordEncoder."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def oauth2_payload() -> dict[str, Any]:
    """Return the POST/PUT body accepted by /api/oAuth2Clients.

    `clientSecret` is BCrypt-hashed because DHIS2 wires a `BCryptPasswordEncoder`
    into Spring Authorization Server's client authentication filter (see
    `PasswordEncoderConfig`), so a plaintext value in this TEXT column would
    always fail the `/oauth2/token` credential check with 401 invalid_client.

    Multi-valued fields (`redirectUris`, `scopes`, `authorizationGrantTypes`,
    `clientAuthenticationMethods`) ship as JSON arrays. v42 + v43 also accept
    comma-separated strings and auto-coerce, but v41 strictly rejects strings
    with Jackson `MismatchedInputException` ("no String-argument constructor
    to deserialize from String value"). Arrays work uniformly across all
    three majors.
    """
    return {
        "name": OAUTH2_CLIENT_ID,
        # v41 names the property `cid`, v42 + v43 renamed it to `clientId`. Each
        # version reads the one it knows and ignores the other, so emitting both
        # keeps the payload uniform across the three majors.
        "cid": OAUTH2_CLIENT_ID,
        "clientId": OAUTH2_CLIENT_ID,
        "clientSecret": _bcrypt_hash(OAUTH2_CLIENT_SECRET),
        "clientAuthenticationMethods": [m.strip() for m in OAUTH2_CLIENT_AUTH_METHODS.split(",") if m.strip()],
        "authorizationGrantTypes": [g.strip() for g in OAUTH2_GRANT_TYPES.split(",") if g.strip()],
        "redirectUris": [OAUTH2_REDIRECT_URI],
        "scopes": [OAUTH2_SCOPES],
        "clientSettings": OAUTH2_CLIENT_SETTINGS_JSON,
        "tokenSettings": OAUTH2_TOKEN_SETTINGS_JSON,
    }
