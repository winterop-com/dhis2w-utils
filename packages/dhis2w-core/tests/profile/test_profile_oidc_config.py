"""Tests for `d2w profile oidc-config` — discovery + profile-upsert wiring."""

from __future__ import annotations

import tomllib
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.oauth2_preflight import OidcDiscoveryError, fetch_oidc_discovery
from dhis2w_core.v42.plugins.profile import service
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_tomls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point global + project profile paths at tmp_path so tests don't touch the user's config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    yield


_DISCOVERY_BODY = {
    "issuer": "https://dhis2.example",
    "authorization_endpoint": "https://dhis2.example/oauth2/authorize",
    "token_endpoint": "https://dhis2.example/oauth2/token",
    "jwks_uri": "https://dhis2.example/oauth2/jwks",
    "userinfo_endpoint": "https://dhis2.example/userinfo",
    "scopes_supported": ["openid", "profile"],
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code"],
}


@respx.mock
async def test_fetch_oidc_discovery_parses_required_fields() -> None:
    """Happy path — discovery doc parses into the typed `OidcDiscovery` model."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=_DISCOVERY_BODY),
    )
    discovery = await fetch_oidc_discovery("https://dhis2.example")
    assert discovery.issuer == "https://dhis2.example"
    assert discovery.token_endpoint == "https://dhis2.example/oauth2/token"
    assert "openid" in discovery.scopes_supported


@respx.mock
async def test_fetch_oidc_discovery_accepts_full_discovery_url() -> None:
    """Caller can pass the full /.well-known/... URL; no double-append."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=_DISCOVERY_BODY),
    )
    discovery = await fetch_oidc_discovery("https://dhis2.example/.well-known/openid-configuration")
    assert discovery.issuer == "https://dhis2.example"


@respx.mock
async def test_fetch_oidc_discovery_404_mentions_dhis_conf() -> None:
    """404 → helpful error pointing at `oauth2.server.enabled = on`."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(404),
    )
    with pytest.raises(OidcDiscoveryError, match="oauth2.server.enabled"):
        await fetch_oidc_discovery("https://dhis2.example")


@respx.mock
async def test_fetch_oidc_discovery_missing_fields_raises() -> None:
    """Discovery doc without required fields → OidcDiscoveryError with the missing-field context."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={"issuer": "https://dhis2.example"}),
    )
    with pytest.raises(OidcDiscoveryError, match="missing required fields"):
        await fetch_oidc_discovery("https://dhis2.example")


@respx.mock
async def test_discover_oidc_profile_builds_oauth2_profile() -> None:
    """Service returns a Profile with auth=oauth2 + the client creds + the issuer as base_url."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=_DISCOVERY_BODY),
    )
    discovered = await service.discover_oidc_profile(
        "https://dhis2.example",
        client_id="my-client",
        client_secret="my-secret",
    )
    assert discovered.profile.auth == "oauth2"
    assert discovered.profile.base_url == "https://dhis2.example"
    assert discovered.profile.client_id == "my-client"
    client_secret = discovered.profile.client_secret
    assert client_secret is not None and client_secret == "my-secret"
    # Default scope/redirect_uri mirror DHIS2 + the CLI loopback.
    assert discovered.profile.scope == "ALL"
    assert discovered.profile.redirect_uri == "http://localhost:8765"


@respx.mock
def test_cli_oidc_config_writes_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w profile oidc-config` round-trips: discovery → profile row in the global TOML."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=_DISCOVERY_BODY),
    )
    result = CliRunner().invoke(
        build_app(),
        [
            "profile",
            "oidc-config",
            "https://dhis2.example",
            "--name",
            "example_oidc",
            "--client-id",
            "abc",
            "--client-secret",
            "xyz",
            "--global",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "discovered OIDC config" in result.output
    assert "saved profile 'example_oidc'" in result.output

    # Read the saved TOML back and check the shape.
    toml_path = tmp_path / "xdg" / "dhis2" / "profiles.toml"
    assert toml_path.exists(), f"expected profile to be written to {toml_path}"
    parsed = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    profile = parsed["profiles"]["example_oidc"]
    assert profile["auth"] == "oauth2"
    assert profile["client_id"] == "abc"
    assert profile["client_secret"] == "xyz"
    assert profile["base_url"] == "https://dhis2.example"


@respx.mock
def test_cli_oidc_config_reads_client_secret_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`oidc-config` reads the secret from DHIS2_OAUTH_CLIENT_SECRET when --client-secret is omitted."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=_DISCOVERY_BODY),
    )
    monkeypatch.setenv("DHIS2_OAUTH_CLIENT_SECRET", "env-secret-xyz")
    result = CliRunner().invoke(
        build_app(),
        [
            "profile",
            "oidc-config",
            "https://dhis2.example",
            "--name",
            "env_oidc",
            "--client-id",
            "abc",
            "--global",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "saved profile 'env_oidc'" in result.output

    toml_path = tmp_path / "xdg" / "dhis2" / "profiles.toml"
    parsed = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    profile = parsed["profiles"]["env_oidc"]
    assert profile["client_secret"] == "env-secret-xyz"
    assert profile["client_id"] == "abc"


@respx.mock
def test_cli_oidc_config_reports_discovery_failure_cleanly() -> None:
    """Discovery error → exit 1 with a user-facing message, no traceback."""
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(404),
    )
    result = CliRunner().invoke(
        build_app(),
        [
            "profile",
            "oidc-config",
            "https://dhis2.example",
            "--name",
            "broken",
            "--client-id",
            "abc",
            "--client-secret",
            "xyz",
        ],
    )
    assert result.exit_code != 0
    assert "oauth2.server.enabled" in result.output
    assert "Traceback" not in result.output
