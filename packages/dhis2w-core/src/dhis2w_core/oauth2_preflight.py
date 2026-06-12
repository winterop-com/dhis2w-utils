"""Preflight probes for DHIS2's Spring Authorization Server.

- `check_oauth2_server` returns a user-facing error string (or None on OK) —
  the fast yes/no check the CLI uses before starting an OAuth2 flow.
- `fetch_oidc_discovery` returns the parsed discovery doc — used by
  `d2w profile oidc-config` to populate a profile from the advertised
  endpoints instead of asking the user to type them.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

DISCOVERY_PATH = "/.well-known/openid-configuration"


class OidcDiscovery(BaseModel):
    """Parsed `/.well-known/openid-configuration` response — only the fields we use."""

    model_config = ConfigDict(extra="allow")

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None = None
    scopes_supported: list[str] = Field(default_factory=list)
    response_types_supported: list[str] = Field(default_factory=list)
    grant_types_supported: list[str] = Field(default_factory=list)


class OidcDiscoveryError(RuntimeError):
    """Raised when discovery fails — message is the user-facing reason."""


def _normalise_discovery_url(url: str) -> str:
    """Accept either a DHIS2 base URL or the full discovery URL; return the discovery URL."""
    url = url.rstrip("/")
    if url.endswith(DISCOVERY_PATH):
        return url
    return url + DISCOVERY_PATH


async def fetch_oidc_discovery(url: str, *, timeout: float = 10.0) -> OidcDiscovery:
    """Fetch + parse the OIDC discovery doc. Raises `OidcDiscoveryError` on any failure."""
    discovery_url = _normalise_discovery_url(url)
    base_hint = url.replace(DISCOVERY_PATH, "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(discovery_url)
    except httpx.ConnectError as exc:
        raise OidcDiscoveryError(f"cannot reach {base_hint or url} — is DHIS2 running? ({exc})") from exc
    except httpx.TimeoutException as exc:
        raise OidcDiscoveryError(f"timed out fetching {discovery_url}") from exc
    except httpx.HTTPError as exc:
        raise OidcDiscoveryError(f"error fetching {discovery_url}: {type(exc).__name__}: {exc}") from exc
    if response.status_code == 404:
        raise OidcDiscoveryError(
            f"{discovery_url} returned 404 — enable `oauth2.server.enabled = on` in dhis.conf and restart."
        )
    if response.status_code >= 400:
        raise OidcDiscoveryError(f"{discovery_url} returned HTTP {response.status_code}")
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        content_type = response.headers.get("content-type")
        raise OidcDiscoveryError(f"{discovery_url} did not return JSON (content-type={content_type!r})") from exc
    try:
        return OidcDiscovery.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — pydantic.ValidationError text is clearer than the raw exception
        raise OidcDiscoveryError(f"discovery response missing required fields: {exc}") from exc


async def check_oauth2_server(base_url: str, *, timeout: float = 5.0) -> str | None:
    """Probe `base_url` for an OIDC discovery doc.

    Returns None when DHIS2 looks like a functional OAuth2 Authorization Server.
    Otherwise returns a user-facing error string that explains what's missing
    and how to fix it (typically: enable `oauth2.server.enabled=on` in dhis.conf).
    """
    url = base_url.rstrip("/") + DISCOVERY_PATH
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.ConnectError as exc:
        return f"cannot reach {base_url} — is the DHIS2 instance running? ({exc})"
    except httpx.TimeoutException:
        return f"timed out probing {url} — DHIS2 may be slow or unreachable"
    except httpx.HTTPError as exc:
        return f"error probing {url}: {type(exc).__name__}: {exc}"
    if response.status_code == 404:
        return (
            f"DHIS2 at {base_url} does not expose OAuth2/OIDC endpoints "
            f"(GET {DISCOVERY_PATH} returned 404). "
            "Enable the built-in Authorization Server by adding "
            "`oauth2.server.enabled = on` to dhis.conf, then restart DHIS2."
        )
    if response.status_code >= 400:
        return (
            f"DHIS2 at {base_url} returned HTTP {response.status_code} on {DISCOVERY_PATH}; "
            "the OAuth2 Authorization Server may be misconfigured."
        )
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        return (
            f"unexpected response from {url} (content-type={content_type!r}); "
            "OAuth2 Authorization Server may not be fully configured."
        )
    return None
