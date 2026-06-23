"""Routes-check tests: SSRF-target classification, subpath/auth/run-gating findings, and per-tree wiring.

`evaluate_routes` is version-invariant and tested directly with hand-built `RouteTarget` inputs. The
`_run_routes` wiring (which reads `/api/routes` via `get_raw`, wraps the payload into typed `oas.Route`,
and extracts the non-secret auth via the per-tree `_wire` extractor) is exercised against a mock client
across all three version trees, covering the v41 undiscriminated vs v42/v43 discriminated auth union and
asserting no secret ever surfaces in a RouteTarget or finding.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    RouteTarget,
    Severity,
    evaluate_routes,
)

TREES = ("v41", "v42", "v43")

# A public-destination route with no auth and a required authority: only the inventory finding fires.
_PUBLIC = RouteTarget(
    uid="route000001",
    code="public",
    name="Public route",
    url="https://api.partner.example/data",
    host="api.partner.example",
    disabled=False,
    allows_subpaths=False,
    auth_type=None,
    auth_identity=None,
    required_authorities=("F_ROUTE_PUBLIC",),
)


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


def _by_title(findings: list[Any]) -> dict[str, Any]:
    """Index findings by title for severity assertions."""
    return {finding.title: finding for finding in findings}


# ---------------------------------------------------------------------------
# evaluate_routes (version-invariant)
# ---------------------------------------------------------------------------


def test_empty_inventory_emits_only_inventory_finding() -> None:
    """No routes still emits one INFO inventory finding reporting zero registered routes."""
    findings = evaluate_routes([])
    assert _titles(findings) == {"Route inventory"}
    inventory = _by_title(findings)["Route inventory"]
    assert inventory.severity is Severity.INFO
    assert (inventory.evidence or {})["total"] == "0"


def test_public_route_produces_only_inventory() -> None:
    """A public-host route with auth gating and no auth/subpaths yields only the inventory finding."""
    assert _titles(evaluate_routes([_PUBLIC])) == {"Route inventory"}


def test_private_ipv4_host_is_high() -> None:
    """A route to an RFC1918 IPv4 host flags a HIGH private-address SSRF finding."""
    target = _PUBLIC.model_copy(update={"url": "http://10.1.2.3/api", "host": "10.1.2.3"})
    finding = _by_title(evaluate_routes([target]))["Route proxies to a private or internal host"]
    assert finding.severity is Severity.HIGH
    assert (finding.evidence or {})["host"] == "10.1.2.3"


@pytest.mark.parametrize(
    "host",
    ["172.16.5.5", "192.168.0.10", "127.0.0.1", "169.254.1.1", "0.0.0.0", "::1", "fe80::1", "fc00::1"],
)
def test_private_ip_ranges_are_high(host: str) -> None:
    """Every documented private/loopback/link-local IPv4 and IPv6 range flags the HIGH private finding."""
    target = _PUBLIC.model_copy(update={"url": f"http://[{host}]/x", "host": host})
    assert "Route proxies to a private or internal host" in _titles(evaluate_routes([target]))


@pytest.mark.parametrize("host", ["localhost", "db.internal", "svc.local", "box.localdomain"])
def test_private_hostnames_are_high(host: str) -> None:
    """Internal hostnames (localhost and the .internal/.local/.localdomain suffixes) flag HIGH."""
    target = _PUBLIC.model_copy(update={"url": f"http://{host}/x", "host": host})
    assert "Route proxies to a private or internal host" in _titles(evaluate_routes([target]))


@pytest.mark.parametrize("host", ["169.254.169.254", "fd00:ec2::254", "metadata.google.internal"])
def test_metadata_endpoints_are_high_metadata_finding(host: str) -> None:
    """The cloud-metadata addresses flag the metadata HIGH finding, the more specific SSRF target."""
    target = _PUBLIC.model_copy(update={"url": f"http://{host}/latest", "host": host})
    titles = _titles(evaluate_routes([target]))
    assert "Route targets the cloud metadata endpoint" in titles


def test_metadata_endpoint_does_not_double_fire_private_address() -> None:
    """A metadata host emits ONLY the metadata HIGH, never also the generic private-address HIGH."""
    target = _PUBLIC.model_copy(update={"url": "http://169.254.169.254/x", "host": "169.254.169.254"})
    by_title = _by_title(evaluate_routes([target]))
    assert "Route targets the cloud metadata endpoint" in by_title
    assert "Route proxies to a private or internal host" not in by_title
    assert by_title["Route targets the cloud metadata endpoint"].severity is Severity.HIGH


def test_unparseable_host_is_not_flagged() -> None:
    """A route whose host could not be parsed (None) raises no destination finding."""
    target = _PUBLIC.model_copy(update={"url": "not a url", "host": None})
    titles = _titles(evaluate_routes([target]))
    assert "Route proxies to a private or internal host" not in titles
    assert "Route targets the cloud metadata endpoint" not in titles


def test_allows_subpaths_is_medium() -> None:
    """A route flagged allows_subpaths (url ends `/**`) raises a MEDIUM subpath finding."""
    target = _PUBLIC.model_copy(update={"url": "https://api.partner.example/**", "allows_subpaths": True})
    finding = _by_title(evaluate_routes([target]))["Route allows arbitrary subpaths"]
    assert finding.severity is Severity.MEDIUM


def test_carries_auth_is_info_and_shows_identity_not_secret() -> None:
    """A route with an auth block raises an INFO finding carrying the type and non-secret identity only."""
    target = _PUBLIC.model_copy(update={"auth_type": "http-basic", "auth_identity": "svc-user"})
    finding = _by_title(evaluate_routes([target]))["Route carries upstream credentials"]
    assert finding.severity is Severity.INFO
    assert (finding.evidence or {})["auth_type"] == "http-basic"
    assert (finding.evidence or {})["identity"] == "svc-user"


def test_no_required_authorities_on_active_route_is_medium() -> None:
    """An active route with no required authorities raises a MEDIUM run-gating finding."""
    target = _PUBLIC.model_copy(update={"required_authorities": ()})
    finding = _by_title(evaluate_routes([target]))["Route has no required authorities"]
    assert finding.severity is Severity.MEDIUM


def test_no_required_authorities_suppressed_when_disabled() -> None:
    """A disabled route with no authorities does not raise the run-gating finding (it cannot be run)."""
    target = _PUBLIC.model_copy(update={"required_authorities": (), "disabled": True})
    assert "Route has no required authorities" not in _titles(evaluate_routes([target]))


def test_inventory_counts_active_and_disabled() -> None:
    """The inventory finding reports the active vs disabled split across the registered routes."""
    routes = [
        _PUBLIC,
        _PUBLIC.model_copy(update={"uid": "route000002", "disabled": True}),
    ]
    inventory = _by_title(evaluate_routes(routes))["Route inventory"]
    assert (inventory.evidence or {})["active"] == "1"
    assert (inventory.evidence or {})["disabled"] == "1"


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_routes reads /api/routes and extracts non-secret auth
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _mock_client(envelope: dict[str, Any]) -> MagicMock:
    """A client whose get_raw returns the given /api/routes envelope payload."""
    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(return_value=envelope)
    return client


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_flags_private_basic_auth_route(tree: str) -> None:
    """A private-host http-basic route flags HIGH + INFO and carries the username, never the password."""
    envelope = {
        "pager": {"total": 1},
        "routes": [
            {
                "id": "route000001",
                "code": "internal",
                "name": "Internal proxy",
                "url": "http://10.0.0.9/api/**",
                "disabled": False,
                "authorities": [],
                "auth": {"type": "http-basic", "username": "svc-user", "password": "s3cr3t"},
            }
        ],
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    assert "Route proxies to a private or internal host" in titles
    assert "Route allows arbitrary subpaths" in titles
    assert "Route carries upstream credentials" in titles
    assert "Route has no required authorities" in titles
    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["identity"] == "svc-user"
    # The password is WRITE_ONLY upstream; it must never appear anywhere in the findings.
    assert "s3cr3t" not in repr(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_metadata_endpoint_no_double_fire(tree: str) -> None:
    """A metadata-targeting route flags only the metadata HIGH across every tree, not the private one too."""
    envelope = {
        "routes": [
            {
                "id": "route000002",
                "name": "Metadata grab",
                "url": "http://169.254.169.254/latest/meta-data/",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
            }
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    titles = _titles(result.findings)
    assert "Route targets the cloud metadata endpoint" in titles
    assert "Route proxies to a private or internal host" not in titles


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_api_token_carries_no_secret(tree: str) -> None:
    """An api-token route reports the auth type with no identity and never leaks the token value."""
    envelope = {
        "routes": [
            {
                "id": "route000003",
                "name": "Token route",
                "url": "https://api.partner.example/x",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
                "auth": {"type": "api-token", "token": "tok-do-not-leak"},
            }
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["auth_type"] == "api-token"
    assert (auth_finding.evidence or {})["identity"] == "none"
    assert "tok-do-not-leak" not in repr(result.findings)


@pytest.mark.parametrize("tree", ("v42", "v43"))
async def test_run_routes_oauth2_identity_on_v42_v43(tree: str) -> None:
    """v42/v43 carry the 5th oauth2-client-credentials variant: identity is clientId, never clientSecret."""
    envelope = {
        "routes": [
            {
                "id": "route000004",
                "name": "OAuth route",
                "url": "https://api.partner.example/x",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
                "auth": {
                    "type": "oauth2-client-credentials",
                    "clientId": "client-abc",
                    "clientSecret": "oauth-secret",
                    "tokenUri": "https://idp.example/token",
                },
            }
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["auth_type"] == "oauth2-client-credentials"
    assert (auth_finding.evidence or {})["identity"] == "client-abc"
    assert "oauth-secret" not in repr(result.findings)


async def test_run_routes_v41_undiscriminated_basic_auth_resolves() -> None:
    """v41's undiscriminated oas.Route.auth still resolves http-basic by re-validating through the adapter."""
    envelope = {
        "routes": [
            {
                "id": "route000005",
                "name": "v41 basic",
                "url": "https://api.partner.example/x",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
                "auth": {"type": "http-basic", "username": "v41-user", "password": "v41-pass"},
            }
        ]
    }

    result = await _audit_module("v41")._run_routes(_mock_client(envelope))

    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["auth_type"] == "http-basic"
    assert (auth_finding.evidence or {})["identity"] == "v41-user"
    assert "v41-pass" not in repr(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_clean_public_inventory(tree: str) -> None:
    """A single public, gated, no-auth route yields an OK check with only the inventory finding."""
    envelope = {
        "routes": [
            {
                "id": "route000006",
                "name": "Public",
                "url": "https://api.partner.example/data",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
            }
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    assert result.status is CheckStatus.OK
    assert _titles(result.findings) == {"Route inventory"}


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_degrades_on_api_error(tree: str) -> None:
    """A Dhis2ApiError reading /api/routes degrades the check with a note rather than a clean pass."""
    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=Dhis2ApiError(503, "down"))

    result = await _audit_module(tree)._run_routes(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_degrades_on_transport_error(tree: str) -> None:
    """A transport error reading /api/routes degrades the check rather than reporting an empty inventory."""
    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await _audit_module(tree)._run_routes(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note


# ---------------------------------------------------------------------------
# Issue 1 fix: malformed auth blocks never crash the whole check (HIGH security fix)
# ---------------------------------------------------------------------------


async def test_run_routes_v41_oauth2_on_wire_handled_gracefully() -> None:
    """v41 cannot classify oauth2-client-credentials; route_auth returns unknown, check stays OK, no crash.

    The v41 AuthSchemeAdapter has no oauth2-client-credentials variant; its ValidationError is caught in
    route_auth, which returns ("unknown", None). The route itself still validates as an oas.Route (extra=allow),
    so it is included in the check as a route with unknown auth -- not skipped, not crashing.
    """
    envelope = {
        "routes": [
            {
                "id": "route000bad",
                "name": "OAuth2 on v41 wire",
                "url": "http://10.0.0.1/evil",
                "disabled": False,
                "authorities": [],
                # oauth2-client-credentials does not exist in v41's auth_schemes adapter.
                # route_auth must catch the ValidationError and return ("unknown", None).
                "auth": {
                    "type": "oauth2-client-credentials",
                    "clientId": "id",
                    "clientSecret": "s3cr3t",
                    "tokenUri": "https://idp.example/token",
                },
            },
            {
                "id": "route000good",
                "name": "Good public route",
                "url": "https://api.partner.example/data",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
            },
        ]
    }

    result = await _audit_module("v41")._run_routes(_mock_client(envelope))

    # The check must stay OK (not ERROR/DEGRADED from an uncaught exception).
    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    # The private-host route is included with unknown auth and flags HIGH.
    assert "Route proxies to a private or internal host" in titles
    assert "Route carries upstream credentials" in titles
    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["auth_type"] == "unknown"
    # The good public route contributes to the inventory.
    assert "Route inventory" in titles
    # Secrets must not appear anywhere.
    assert "s3cr3t" not in repr(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_no_type_auth_reports_unknown_not_crash(tree: str) -> None:
    """An auth block with no `type` field (or null type) surfaces as auth_type=unknown, never crashes."""
    envelope = {
        "routes": [
            {
                "id": "route000notype",
                "name": "No-type auth route",
                "url": "https://api.partner.example/data",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
                "auth": {"username": "svc", "password": "s3cr3t"},  # no `type` key
            }
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    # The route carries credentials even though we cannot classify the scheme.
    assert "Route carries upstream credentials" in titles
    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["auth_type"] == "unknown"
    assert "s3cr3t" not in repr(result.findings)


@pytest.mark.parametrize("tree", ("v42", "v43"))
async def test_run_routes_unknown_future_auth_type_reports_unknown(tree: str) -> None:
    """An auth block with an unrecognized future `type` is reported as unknown, check stays OK."""
    envelope = {
        "routes": [
            {
                "id": "route000future",
                "name": "Future auth route",
                "url": "https://api.partner.example/data",
                "disabled": False,
                "authorities": ["F_ROUTE_RUN"],
                "auth": {"type": "mtls-client-cert", "certThumbprint": "abc123"},
            }
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    assert "Route carries upstream credentials" in titles
    auth_finding = _by_title(result.findings)["Route carries upstream credentials"]
    assert (auth_finding.evidence or {})["auth_type"] == "unknown"


@pytest.mark.parametrize("tree", TREES)
async def test_run_routes_one_bad_route_does_not_lose_other_findings(tree: str) -> None:
    """A route that cannot be parsed at all (non-dict) is skipped; other routes' HIGH findings still appear."""
    envelope = {
        "routes": [
            "not-a-dict",  # completely malformed -- should be skipped
            {
                "id": "route000priv",
                "name": "Private route",
                "url": "http://192.168.1.1/api",
                "disabled": False,
                "authorities": [],
            },
        ]
    }

    result = await _audit_module(tree)._run_routes(_mock_client(envelope))

    assert result.status is CheckStatus.OK
    assert "Route proxies to a private or internal host" in _titles(result.findings)
    # The skipped count is reflected in the note.
    assert result.note is not None and "skipped" in result.note


# ---------------------------------------------------------------------------
# Issue 2 fix: non-canonical numeric host encodings (HIGH security fix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "label"),
    [
        ("2130706433", "decimal 127.0.0.1"),
        ("0x7f000001", "hex 127.0.0.1"),
        ("0177.0.0.1", "octal-dotted 127.0.0.1"),
        ("017700000001", "octal-packed 127.0.0.1"),
        ("0", "short 0.0.0.0"),
        ("2852039166", "decimal 169.254.169.254"),
    ],
)
def test_numeric_encoded_private_host_is_classified(host: str, label: str) -> None:
    """Non-canonical numeric IP encodings the JVM resolves to private addresses are flagged HIGH."""
    target = _PUBLIC.model_copy(update={"url": f"http://{host}/x", "host": host})
    titles = _titles(evaluate_routes([target]))
    # 2852039166 == int(ipaddress.IPv4Address("169.254.169.254")) -- the AWS/GCP metadata endpoint.
    is_metadata = host == "2852039166"
    if is_metadata:
        assert "Route targets the cloud metadata endpoint" in titles
    else:
        assert "Route proxies to a private or internal host" in titles, f"failed for {label}: {titles}"


@pytest.mark.parametrize(
    ("url", "expected_private"),
    [
        ("http://localhost./", True),
        ("http://10.0.0.1.:8080/", True),
        ("http://api.example.com./data", False),
    ],
)
def test_trailing_fqdn_dot_normalizes_before_classification(url: str, expected_private: bool) -> None:
    """Trailing FQDN dot is stripped before host classification so localhost. and 10.0.0.1. are caught."""
    from dhis2w_core.security_core.routes import _is_private_host, host_from_url

    host = host_from_url(url)
    assert _is_private_host(host) == expected_private, f"url={url!r} host={host!r}"
