"""Auth-methods tests: OIDC-provider + OAuth2-client findings, the INFO suppression, and per-tree wiring.

`evaluate_auth_methods` is version-invariant and tested directly with hand-built `LoginProviderView` and
`OAuth2ClientView` inputs: the configured-OIDC-provider INFO, the registered-client INFO (suppressed when a
MEDIUM fires), broad-grant detection (including the device-code URN), and loose-redirect detection (wildcard
plus non-loopback cleartext http://, with loopback http://localhost / 127.0.0.1 not flagged per RFC 8252).
The `_run_auth_methods` wiring (reading `/api/loginConfig` and `/api/oAuth2Clients` via `get_raw`, wrapping
through the per-tree `_wire.oauth2_clients` extractor, and reducing) is exercised against a mock client across
all three version trees: the v41 `data` envelope / `cid` / array-typed fields vs the v42/v43 `oAuth2Clients`
envelope / `clientId` / comma-string fields, the oAuth2Clients-403 degrade-with-note that keeps the OIDC
findings, and the assertion that no client secret ever surfaces in any view or finding.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from dhis2w_client.errors import AuthenticationError, Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    LoginProviderView,
    OAuth2ClientView,
    Severity,
    evaluate_auth_methods,
)

TREES = ("v41", "v42", "v43")


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


def _by_title(findings: list[Any]) -> dict[str, Any]:
    """Index findings by title for severity/detail assertions."""
    return {finding.title: finding for finding in findings}


# A clean client: the recommended authorization_code + refresh_token grants and a single https redirect.
_CLEAN_CLIENT = OAuth2ClientView(
    identifier="clean-app",
    display_name="Clean App",
    grant_types=frozenset({"authorization_code", "refresh_token"}),
    redirect_uris=("https://app.example/callback",),
)


# ---------------------------------------------------------------------------
# evaluate_auth_methods (version-invariant)
# ---------------------------------------------------------------------------


def test_empty_providers_and_clients_emits_nothing() -> None:
    """No OIDC providers and no OAuth2 clients yields no findings at all."""
    assert evaluate_auth_methods(oidc_providers=[], oauth2_clients=[]) == []


def test_configured_oidc_provider_is_info() -> None:
    """Each configured OIDC provider emits an INFO finding subject-scoped to the provider id."""
    provider = LoginProviderView(provider_id="google", login_text="Sign in with Google")
    findings = evaluate_auth_methods(oidc_providers=[provider], oauth2_clients=[])
    assert _titles(findings) == {"External OIDC login provider configured"}
    finding = findings[0]
    assert finding.severity is Severity.INFO
    assert finding.subject == "google"
    assert (finding.evidence or {})["provider"] == "google"


def test_registered_clean_client_is_info() -> None:
    """A clean OAuth2 client (no broad grant, no loose redirect) emits the registered-client INFO."""
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[_CLEAN_CLIENT])
    assert _titles(findings) == {"Registered OAuth2 client"}
    finding = findings[0]
    assert finding.severity is Severity.INFO
    assert finding.subject == "clean-app"


def test_broad_grant_client_is_medium_and_suppresses_registered_info() -> None:
    """A client with client_credentials flags the MEDIUM broad-grant and suppresses the registered INFO."""
    client = _CLEAN_CLIENT.model_copy(
        update={"identifier": "machine", "grant_types": frozenset({"client_credentials"})}
    )
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
    assert _titles(findings) == {"OAuth2 client with broad grant type"}
    finding = findings[0]
    assert finding.severity is Severity.MEDIUM
    assert finding.group_key == "oauth2-broad-grant"


def test_broad_grant_detects_device_code_urn() -> None:
    """The device-authorization grant URN is detected as a broad grant."""
    client = _CLEAN_CLIENT.model_copy(
        update={"identifier": "device", "grant_types": frozenset({"urn:ietf:params:oauth:grant-type:device_code"})}
    )
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
    assert "OAuth2 client with broad grant type" in _titles(findings)


def test_broad_grant_detects_implicit_and_password() -> None:
    """The implicit and resource-owner-password grants are detected as broad grants."""
    for grant in ("implicit", "password"):
        client = _CLEAN_CLIENT.model_copy(update={"identifier": grant, "grant_types": frozenset({grant})})
        findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
        assert "OAuth2 client with broad grant type" in _titles(findings)


def test_wildcard_redirect_is_medium_and_suppresses_registered_info() -> None:
    """A redirect URI containing a wildcard flags the MEDIUM loose-redirect and suppresses the registered INFO."""
    client = _CLEAN_CLIENT.model_copy(update={"identifier": "wild", "redirect_uris": ("https://app.example/*",)})
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
    assert _titles(findings) == {"OAuth2 client with loose redirect URI"}
    finding = findings[0]
    assert finding.severity is Severity.MEDIUM
    assert finding.group_key == "oauth2-wildcard-redirect"


def test_non_loopback_http_redirect_is_flagged() -> None:
    """A non-loopback cleartext http:// redirect URI is flagged as a loose redirect."""
    client = _CLEAN_CLIENT.model_copy(
        update={"identifier": "cleartext", "redirect_uris": ("http://app.example/callback",)}
    )
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
    assert "OAuth2 client with loose redirect URI" in _titles(findings)


def test_loopback_http_redirect_is_not_flagged() -> None:
    """A loopback http://localhost / 127.0.0.1 redirect URI is NOT flagged (RFC 8252)."""
    client = _CLEAN_CLIENT.model_copy(
        update={
            "identifier": "native",
            "redirect_uris": ("http://localhost:8765/callback", "http://127.0.0.1:9000/cb"),
        }
    )
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
    assert _titles(findings) == {"Registered OAuth2 client"}


def test_https_redirect_is_not_flagged() -> None:
    """A plain https redirect URI is not a loose redirect."""
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[_CLEAN_CLIENT])
    assert "OAuth2 client with loose redirect URI" not in _titles(findings)


def test_oauth2_clients_none_keeps_only_oidc_findings() -> None:
    """When the OAuth2-client half is unreadable (None), only the OIDC findings are produced."""
    provider = LoginProviderView(provider_id="okta", login_text="Okta")
    findings = evaluate_auth_methods(oidc_providers=[provider], oauth2_clients=None)
    assert _titles(findings) == {"External OIDC login provider configured"}


def test_client_with_both_broad_grant_and_loose_redirect_fires_both_mediums() -> None:
    """A client that is both broad-grant and loose-redirect fires both MEDIUMs and no registered INFO."""
    client = _CLEAN_CLIENT.model_copy(
        update={
            "identifier": "both",
            "grant_types": frozenset({"implicit"}),
            "redirect_uris": ("https://app.example/*",),
        }
    )
    findings = evaluate_auth_methods(oidc_providers=[], oauth2_clients=[client])
    assert _titles(findings) == {
        "OAuth2 client with broad grant type",
        "OAuth2 client with loose redirect URI",
    }


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_auth_methods reads /api/loginConfig + /api/oAuth2Clients
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _login_payload(providers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a /api/loginConfig payload carrying the given OIDC providers."""
    return {"oidcProviders": providers, "selfRegistrationEnabled": False}


def _client_record(tree: str, *, identifier: str, grants: list[str], redirects: list[str]) -> dict[str, Any]:
    """Build one /api/oAuth2Clients record in the tree's wire shape (v41 cid/arrays vs v42/v43 clientId/comma)."""
    if tree == "v41":
        return {
            "cid": identifier,
            "displayName": f"{identifier} app",
            "grantTypes": grants,
            "redirectUris": redirects,
            # A `secret` must never be read; include one to prove it is never carried.
            "secret": "do-not-leak-secret",
        }
    return {
        "clientId": identifier,
        "displayName": f"{identifier} app",
        "authorizationGrantTypes": ",".join(grants),
        "redirectUris": ",".join(redirects),
        # A `clientSecret` must never be read; include one to prove it is never carried.
        "clientSecret": "do-not-leak-secret",
    }


def _clients_payload(tree: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap client records in the tree's list envelope (v41 `data` vs v42/v43 `oAuth2Clients`)."""
    key = "data" if tree == "v41" else "oAuth2Clients"
    return {key: records}


def _mock_client(*, login: dict[str, Any], clients: dict[str, Any] | Exception) -> MagicMock:
    """A client whose get_raw routes /api/loginConfig and /api/oAuth2Clients to canned payloads or an error."""

    async def _get_raw(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/api/loginConfig":
            return login
        if path == "/api/oAuth2Clients":
            if isinstance(clients, Exception):
                raise clients
            return clients
        raise AssertionError(f"unexpected path: {path}")

    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=_get_raw)
    return client


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_flags_oidc_provider(tree: str) -> None:
    """A configured OIDC provider on /api/loginConfig flags the INFO across all three trees."""
    client = _mock_client(
        login=_login_payload([{"id": "google", "loginText": "Sign in with Google"}]),
        clients=_clients_payload(tree, []),
    )

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.OK
    assert "External OIDC login provider configured" in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_clean_client_is_info(tree: str) -> None:
    """A clean OAuth2 client across the v41 array vs v42/v43 comma-string wire flags the registered INFO."""
    record = _client_record(
        tree,
        identifier="clean",
        grants=["authorization_code", "refresh_token"],
        redirects=["https://app.example/callback"],
    )
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, [record]))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.OK
    assert _titles(result.findings) == {"Registered OAuth2 client"}


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_broad_grant_is_medium(tree: str) -> None:
    """A client_credentials grant is normalized and flagged MEDIUM across the wire-shape divergence."""
    record = _client_record(
        tree,
        identifier="machine",
        grants=["client_credentials"],
        redirects=["https://app.example/callback"],
    )
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, [record]))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert "OAuth2 client with broad grant type" in _titles(result.findings)
    assert "Registered OAuth2 client" not in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_grant_case_is_normalized(tree: str) -> None:
    """An uppercase grant token is lowercased before the broad-grant comparison."""
    record = _client_record(
        tree,
        identifier="shouty",
        grants=["CLIENT_CREDENTIALS"],
        redirects=["https://app.example/callback"],
    )
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, [record]))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert "OAuth2 client with broad grant type" in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_wildcard_redirect_is_medium(tree: str) -> None:
    """A wildcard redirect URI is flagged MEDIUM across the wire-shape divergence."""
    record = _client_record(
        tree,
        identifier="wild",
        grants=["authorization_code"],
        redirects=["https://app.example/*"],
    )
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, [record]))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert "OAuth2 client with loose redirect URI" in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_loopback_http_redirect_is_clean(tree: str) -> None:
    """A loopback http://localhost redirect URI is not flagged; the client reads as a clean registered INFO."""
    record = _client_record(
        tree,
        identifier="native",
        grants=["authorization_code"],
        redirects=["http://localhost:8765/callback"],
    )
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, [record]))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert _titles(result.findings) == {"Registered OAuth2 client"}


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_oauth2_403_degrades_but_keeps_oidc(tree: str) -> None:
    """A 403 on /api/oAuth2Clients degrades the check with a note but keeps the loginConfig OIDC findings."""
    client = _mock_client(
        login=_login_payload([{"id": "okta", "loginText": "Okta"}]),
        clients=Dhis2ApiError(403, "forbidden"),
    )

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.note is not None and "F_OAUTH2_CLIENT_MANAGE" in result.note
    assert "External OIDC login provider configured" in _titles(result.findings)
    assert "Registered OAuth2 client" not in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_oauth2_authentication_error_degrades_but_keeps_oidc(tree: str) -> None:
    """An AuthenticationError on /api/oAuth2Clients degrades with the F_OAUTH2_CLIENT_MANAGE note, not an error."""
    client = _mock_client(
        login=_login_payload([{"id": "keycloak", "loginText": "Keycloak"}]),
        clients=AuthenticationError("401 Unauthorized"),
    )

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.note is not None and "F_OAUTH2_CLIENT_MANAGE" in result.note
    assert "External OIDC login provider configured" in _titles(result.findings)
    assert "Registered OAuth2 client" not in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_oauth2_transport_error_degrades_but_keeps_oidc(tree: str) -> None:
    """A transport error on /api/oAuth2Clients degrades with a note but keeps the OIDC findings."""
    client = _mock_client(
        login=_login_payload([{"id": "azure", "loginText": "Azure AD"}]),
        clients=httpx.ConnectError("boom"),
    )

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.DEGRADED
    assert "External OIDC login provider configured" in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_login_config_error_degrades_whole_check(tree: str) -> None:
    """A failure reading /api/loginConfig (the mandatory half) degrades the whole check with no findings."""

    async def _get_raw(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise Dhis2ApiError(500, "boom")

    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=_get_raw)

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_never_carries_client_secret(tree: str) -> None:
    """No OAuth2ClientView or finding ever carries a secret-like value even when the wire includes one."""
    record = _client_record(
        tree,
        identifier="secretive",
        grants=["client_credentials"],
        redirects=["https://app.example/*"],
    )
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, [record]))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert "do-not-leak-secret" not in repr(result.findings)
    views = _audit_module(tree)._wire.oauth2_clients(_clients_payload(tree, [record]))
    assert len(views) == 1
    dumped = views[0].model_dump()
    assert "secret" not in dumped
    assert "clientSecret" not in dumped
    assert "do-not-leak-secret" not in repr(views)


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_identifier_field_matches_wire(tree: str) -> None:
    """The view identifier reads cid on v41 and clientId on v42/v43, projected into the same field."""
    record = _client_record(
        tree,
        identifier="id-check",
        grants=["authorization_code"],
        redirects=["https://app.example/callback"],
    )

    views = _audit_module(tree)._wire.oauth2_clients(_clients_payload(tree, [record]))

    assert len(views) == 1
    assert views[0].identifier == "id-check"


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_empty_clients_is_clean(tree: str) -> None:
    """No providers and no clients yields an OK check with no findings across all trees."""
    client = _mock_client(login=_login_payload([]), clients=_clients_payload(tree, []))

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.OK
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_login_config_validation_error_degrades(tree: str) -> None:
    """A /api/loginConfig response that passes HTTP but fails pydantic validation degrades the whole check."""

    async def _get_raw(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/api/loginConfig":
            # Return a payload whose oidcProviders is a non-list scalar, which triggers ValidationError.
            return {"oidcProviders": "not-a-list"}
        raise AssertionError(f"unexpected path: {path}")

    mock_client = MagicMock()
    mock_client.base_url = "https://mock.example"
    mock_client.get_raw = AsyncMock(side_effect=_get_raw)

    result = await _audit_module(tree)._run_auth_methods(mock_client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "loginConfig" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_auth_methods_oauth2_transport_error_note_is_generic(tree: str) -> None:
    """A transport error (not 401/403) on /api/oAuth2Clients produces a generic note without F_OAUTH2_CLIENT_MANAGE."""
    client = _mock_client(
        login=_login_payload([]),
        clients=httpx.ConnectTimeout("timed out"),
    )

    result = await _audit_module(tree)._run_auth_methods(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.note is not None
    assert "F_OAUTH2_CLIENT_MANAGE" not in result.note
    assert "OAuth2 clients unreadable" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_wire_oauth2_clients_skips_invalid_record(tree: str) -> None:
    """A mixed payload with one valid and one garbage record produces exactly one OAuth2ClientView."""
    valid = _client_record(
        tree,
        identifier="valid-app",
        grants=["authorization_code"],
        redirects=["https://app.example/callback"],
    )
    # A bare string in the list position: model_validate will raise ValidationError/TypeError.
    garbage: Any = "not-a-dict"
    payload = _clients_payload(tree, [valid, garbage])

    views = _audit_module(tree)._wire.oauth2_clients(payload)

    assert len(views) == 1
    assert views[0].identifier == "valid-app"
