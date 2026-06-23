"""External login-surface audit: pre-auth OIDC providers and registered OAuth2 clients.

Two independent signals over the external authentication surface. The login page (GET `/api/loginConfig`)
lists the OIDC providers a pre-auth visitor can federate against; each is a trust path into the instance and
is surfaced as an INFO so an operator can confirm it is intentional (SAML providers are not surfaced here).
The OAuth2 clients DHIS2 acts as an authorization server for (GET `/api/oAuth2Clients`) are each a token
issuance path: a client carrying a broad grant type (client_credentials / implicit / password / the device
flow) or a loose redirect URI (a wildcard, or a non-loopback cleartext http:// target) is a token-theft
vector and is flagged MEDIUM. The check is read-only: two GETs, never a login attempt, never reading secrets.

`OAuth2ClientView` is the hand-rolled version-invariant model bridging the v41 `OAuth2Client` (array-typed
`grantTypes` / `redirectUris`, `cid`, `data` envelope) and the v42/v43 `Dhis2OAuth2Client` (comma-string
`authorizationGrantTypes` / `redirectUris`, `clientId`, `oAuth2Clients` envelope); there is no
version-invariant generated OAuth2-client schema (BUGS.md #52, cross-referencing #39). It deliberately omits
any secret field so a client secret can never reach a finding or evidence; the per-tree `_wire.oauth2_clients`
extractor never reads `secret` / `clientSecret`.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "auth-methods"

# Grant types that hand a client more than the recommended authorization_code + refresh_token pair: the
# client-credentials, implicit, and resource-owner-password grants, plus the OAuth2 device-authorization
# grant (identified by its full URN). On v42/v43 the server rejects these on create, so a client carrying
# one was imported or seeded around REST validation. Compared against the normalized lowercase grant set.
_BROAD_GRANT_TYPES: frozenset[str] = frozenset(
    {
        "client_credentials",
        "implicit",
        "password",
        "urn:ietf:params:oauth:grant-type:device_code",
    }
)

# Loopback hosts a cleartext http:// redirect URI is allowed to use without being a finding (RFC 8252:
# a native app may use http://127.0.0.1 / http://localhost as a loopback redirect during the auth flow).
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


class LoginProviderView(BaseModel):
    """One pre-auth OIDC login provider reduced to the non-secret identity the auth-methods audit reasons over.

    Version-neutral so the reducer never imports a per-tree generated `LoginOidcProvider`; each per-tree
    runner projects its `LoginConfigResponse.oidcProviders` into this shape (the wire fields are uniform
    across v41/v42/v43, so the projection is mechanical).
    """

    model_config = ConfigDict(frozen=True)

    provider_id: str
    login_text: str | None = None


class OAuth2ClientView(BaseModel):
    """One registered OAuth2 client reduced to the non-secret fields the auth-methods audit reasons over.

    Deliberately omits any secret field (`secret` on v41, `clientSecret` on v42/v43) so a client secret can
    never be carried into a finding or evidence; the per-tree `_wire` extractor never reads it.
    """

    model_config = ConfigDict(frozen=True)

    identifier: str
    display_name: str | None = None
    grant_types: frozenset[str] = frozenset()
    redirect_uris: tuple[str, ...] = ()


def evaluate_auth_methods(
    *,
    oidc_providers: list[LoginProviderView],
    oauth2_clients: list[OAuth2ClientView] | None,
) -> list[AuditFinding]:
    """Findings over the external login surface: configured OIDC providers and registered OAuth2 clients.

    `oauth2_clients=None` means `/api/oAuth2Clients` was unreadable (the audited account lacks
    F_OAUTH2_CLIENT_MANAGE, or a transport error); the caller records the degradation as a note and the
    OIDC half still produces its findings.
    """
    findings: list[AuditFinding] = []
    findings.extend(_oidc_provider_findings(oidc_providers))
    if oauth2_clients is not None:
        for client in oauth2_clients:
            findings.extend(_oauth2_client_findings(client))
    return findings


def _oidc_provider_findings(providers: list[LoginProviderView]) -> list[AuditFinding]:
    """Flag each OIDC provider configured on the pre-auth login page as a federated trust path."""
    findings: list[AuditFinding] = []
    for provider in providers:
        provider_id = provider.provider_id or provider.login_text or "unknown"
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.INFO,
                title="External OIDC login provider configured",
                detail=(
                    f"External login provider '{provider.login_text or provider.provider_id or 'unknown'}' "
                    f"({provider_id}) is offered on the login page; the login page trusts this OIDC IdP. "
                    "Verify it is intentional."
                ),
                subject=provider_id,
                group_key="configured-oidc-provider",
                evidence={"provider": provider_id, "login_text": provider.login_text or "unknown"},
            )
        )
    return findings


def _oauth2_client_findings(client: OAuth2ClientView) -> list[AuditFinding]:
    """Per-client findings: broad grant and loose redirect; the clean-client INFO is suppressed when either fires."""
    findings: list[AuditFinding] = []
    broad_grants = sorted(client.grant_types & _BROAD_GRANT_TYPES)
    wildcard_redirects = [uri for uri in client.redirect_uris if _is_loose_redirect(uri)]
    if broad_grants:
        findings.append(_broad_grant_finding(client, broad_grants))
    if wildcard_redirects:
        findings.append(_wildcard_redirect_finding(client, wildcard_redirects))
    if not findings:
        findings.append(_registered_client_finding(client))
    return findings


def _registered_client_finding(client: OAuth2ClientView) -> AuditFinding:
    """Record a clean registered OAuth2 client; suppressed when the same client triggers a MEDIUM."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Registered OAuth2 client",
        detail=(
            f"DHIS2 acts as the authorization server for client '{client.display_name or client.identifier}' "
            f"({client.identifier})."
        ),
        subject=client.identifier,
        group_key="registered-oauth2-client",
        evidence={
            "client": client.identifier,
            "grant_types": ", ".join(sorted(client.grant_types)) or "none",
            "redirect_uris": ", ".join(client.redirect_uris) or "none",
        },
    )


def _broad_grant_finding(client: OAuth2ClientView, broad_grants: list[str]) -> AuditFinding:
    """Flag an OAuth2 client carrying a high-risk grant type (client_credentials / implicit / password / device)."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="OAuth2 client with broad grant type",
        detail=(
            f"High-risk grant on client '{client.identifier}': {', '.join(broad_grants)}. On v42/v43 the "
            "server rejects these on create, so a client carrying one was imported or seeded around REST "
            "validation."
        ),
        subject=client.identifier,
        group_key="oauth2-broad-grant",
        evidence={"client": client.identifier, "grant_types": ", ".join(broad_grants)},
    )


def _wildcard_redirect_finding(client: OAuth2ClientView, loose_redirects: list[str]) -> AuditFinding:
    """Flag an OAuth2 client with a wildcard or non-loopback cleartext redirect URI (auth-code interception)."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="OAuth2 client with loose redirect URI",
        detail=(
            f"Loose redirect target on client '{client.identifier}' enables authorization-code interception "
            f"via open redirect: {', '.join(loose_redirects)}."
        ),
        subject=client.identifier,
        group_key="oauth2-wildcard-redirect",
        evidence={"client": client.identifier, "redirect_uris": ", ".join(loose_redirects)},
    )


def _is_loose_redirect(uri: str) -> bool:
    """True when a redirect URI contains a wildcard, or is a non-loopback cleartext http:// target (RFC 8252)."""
    if "*" in uri:
        return True
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return False
    if parsed.scheme != "http":
        return False
    host = (parsed.hostname or "").lower()
    return host not in _LOOPBACK_HOSTS
