"""Transport-check tests: TLS scheme, security headers, server disclosure, and per-tree wiring.

`evaluate_transport` is version-invariant and tested directly with hand-built `TransportHeaders`. The
`_run_transport` wiring (which reads the scheme from `client.base_url` and the headers off one
`get_response("/api/system/info")`) is exercised against a mock client across all three version trees.
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
    Severity,
    TransportHeaders,
    evaluate_transport,
)

TREES = ("v41", "v42", "v43")

# A fully hardened HTTPS posture: HSTS, CSP with frame-ancestors, nosniff, and a genericised server.
_SECURE = TransportHeaders(
    base_url="https://mock.example",
    scheme="https",
    strict_transport_security="max-age=63072000; includeSubDomains",
    content_security_policy="frame-ancestors 'self';",
    x_content_type_options="nosniff",
    server="nginx",
)


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


def _by_title(findings: list[Any]) -> dict[str, Any]:
    """Index findings by title for severity assertions."""
    return {finding.title: finding for finding in findings}


# ---------------------------------------------------------------------------
# evaluate_transport (version-invariant)
# ---------------------------------------------------------------------------


def test_hardened_https_instance_has_no_findings() -> None:
    """HTTPS with HSTS, CSP frame-ancestors, nosniff, and a bare server token is clean."""
    assert evaluate_transport(_SECURE) == []


def test_plaintext_http_base_url_is_high() -> None:
    """A non-https scheme flags the plaintext base URL as HIGH, names it in detail/evidence, skips HSTS."""
    findings = evaluate_transport(_SECURE.model_copy(update={"scheme": "http"}))
    by_title = _by_title(findings)
    finding = by_title["Base URL is plaintext HTTP"]
    assert finding.severity is Severity.HIGH
    assert "https://mock.example" in finding.detail
    assert (finding.evidence or {}).get("base_url") == "https://mock.example"
    assert (finding.evidence or {}).get("scheme") == "http"
    assert "No Strict-Transport-Security header" not in by_title


def test_http_instance_all_headers_none_has_expected_finding_set() -> None:
    """A plaintext instance with every header absent yields exactly plaintext, no-CSP, no-anti-framing, no-nosniff."""
    findings = evaluate_transport(TransportHeaders(base_url="http://bare.example", scheme="http"))
    titles = _titles(findings)
    assert titles == {
        "Base URL is plaintext HTTP",
        "No Content-Security-Policy header",
        "No anti-framing header",
        "No X-Content-Type-Options: nosniff",
    }
    # HSTS fires only on https — must not appear for a plaintext endpoint.
    assert "No Strict-Transport-Security header" not in titles


def test_http_scheme_is_case_insensitive() -> None:
    """An uppercase HTTPS scheme is still treated as TLS, so no plaintext finding is raised."""
    findings = evaluate_transport(_SECURE.model_copy(update={"scheme": "HTTPS"}))
    assert "Base URL is plaintext HTTP" not in _titles(findings)


def test_https_without_hsts_is_medium() -> None:
    """HTTPS with no Strict-Transport-Security header is MEDIUM (an SSL-strip window)."""
    findings = evaluate_transport(_SECURE.model_copy(update={"strict_transport_security": None}))
    by_title = _by_title(findings)
    assert by_title["No Strict-Transport-Security header"].severity is Severity.MEDIUM


def test_missing_csp_is_medium() -> None:
    """No Content-Security-Policy header is MEDIUM, the sole evidence that CSP is off or stripped."""
    findings = evaluate_transport(
        _SECURE.model_copy(update={"content_security_policy": None, "x_frame_options": "SAMEORIGIN"})
    )
    by_title = _by_title(findings)
    assert by_title["No Content-Security-Policy header"].severity is Severity.MEDIUM


def test_anti_framing_suppressed_when_csp_frame_ancestors_present() -> None:
    """With CSP frame-ancestors and no X-Frame-Options, the anti-framing finding is suppressed."""
    findings = evaluate_transport(_SECURE.model_copy(update={"x_frame_options": None}))
    assert "No anti-framing header" not in _titles(findings)


def test_anti_framing_satisfied_by_x_frame_options_when_csp_off() -> None:
    """X-Frame-Options SAMEORIGIN with CSP off (csp.enabled=off) leaves no anti-framing finding."""
    findings = evaluate_transport(
        _SECURE.model_copy(update={"content_security_policy": None, "x_frame_options": "SAMEORIGIN"})
    )
    assert "No anti-framing header" not in _titles(findings)


def test_anti_framing_suppressed_with_mixed_case_frame_ancestors() -> None:
    """A CSP value with mixed-case `Frame-Ancestors` still suppresses the anti-framing finding (case-insensitive)."""
    findings = evaluate_transport(
        _SECURE.model_copy(update={"content_security_policy": "Frame-Ancestors 'self';", "x_frame_options": None})
    )
    assert "No anti-framing header" not in _titles(findings)


def test_no_anti_framing_is_warn_when_both_missing() -> None:
    """Neither X-Frame-Options nor a CSP frame-ancestors directive raises a WARN anti-framing finding."""
    findings = evaluate_transport(
        _SECURE.model_copy(update={"content_security_policy": "default-src 'self';", "x_frame_options": None})
    )
    by_title = _by_title(findings)
    assert by_title["No anti-framing header"].severity is Severity.WARN


def test_missing_nosniff_is_warn() -> None:
    """A missing X-Content-Type-Options header is WARN."""
    findings = evaluate_transport(_SECURE.model_copy(update={"x_content_type_options": None}))
    by_title = _by_title(findings)
    assert by_title["No X-Content-Type-Options: nosniff"].severity is Severity.WARN


def test_non_nosniff_value_is_warn() -> None:
    """An X-Content-Type-Options value other than `nosniff` is treated as missing and flags WARN."""
    findings = evaluate_transport(_SECURE.model_copy(update={"x_content_type_options": "something-else"}))
    assert "No X-Content-Type-Options: nosniff" in _titles(findings)


def test_nosniff_value_is_case_insensitive() -> None:
    """A `NOSNIFF` value (any case, surrounding whitespace) satisfies the nosniff check."""
    findings = evaluate_transport(_SECURE.model_copy(update={"x_content_type_options": "  NOSNIFF "}))
    assert "No X-Content-Type-Options: nosniff" not in _titles(findings)


def test_server_version_token_is_warn() -> None:
    """A Server header carrying a version token (a digit run) is a WARN disclosure finding."""
    findings = evaluate_transport(_SECURE.model_copy(update={"server": "nginx/1.18.0"}))
    by_title = _by_title(findings)
    assert by_title["Server header discloses version"].severity is Severity.WARN
    assert (by_title["Server header discloses version"].evidence or {}).get("server") == "nginx/1.18.0"


def test_bare_server_token_is_not_flagged() -> None:
    """A bare product token (just `nginx`) carries no version and is not flagged."""
    assert "Server header discloses version" not in _titles(evaluate_transport(_SECURE))


def test_missing_server_header_is_not_flagged() -> None:
    """No Server header at all discloses nothing, so no finding."""
    findings = evaluate_transport(_SECURE.model_copy(update={"server": None}))
    assert "Server header discloses version" not in _titles(findings)


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_transport reads the scheme and headers off one response
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _mock_client(*, base_url: str, headers: dict[str, str]) -> MagicMock:
    """A client whose base_url and get_response (one /api/system/info hit) return the given fixtures."""
    client = MagicMock()
    client.base_url = base_url
    client.get_response = AsyncMock(return_value=httpx.Response(200, headers=headers))
    return client


@pytest.mark.parametrize("tree", TREES)
async def test_run_transport_clean_https_instance(tree: str) -> None:
    """A hardened HTTPS instance produces an OK check with no findings across all trees."""
    client = _mock_client(
        base_url="https://mock.example",
        headers={
            "strict-transport-security": "max-age=63072000",
            "content-security-policy": "frame-ancestors 'self';",
            "x-content-type-options": "nosniff",
            "server": "nginx",
        },
    )

    result = await _audit_module(tree)._run_transport(client)

    assert result.status is CheckStatus.OK
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
async def test_run_transport_flags_plaintext_and_missing_headers(tree: str) -> None:
    """A plaintext base URL with no security headers flags TLS, CSP, anti-framing, nosniff, and server."""
    client = _mock_client(base_url="http://mock.example", headers={"server": "Apache/2.4.41"})

    result = await _audit_module(tree)._run_transport(client)

    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    assert "Base URL is plaintext HTTP" in titles
    assert "No Content-Security-Policy header" in titles
    assert "No anti-framing header" in titles
    assert "No X-Content-Type-Options: nosniff" in titles
    assert "Server header discloses version" in titles
    # The scheme is http, so HSTS is not evaluated (the plaintext finding subsumes it).
    assert "No Strict-Transport-Security header" not in titles


@pytest.mark.parametrize("tree", TREES)
async def test_run_transport_degrades_on_transport_error(tree: str) -> None:
    """A transport error fetching /api/system/info degrades the check with a note rather than a false pass."""
    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_response = AsyncMock(side_effect=httpx.ConnectError("boom"))

    result = await _audit_module(tree)._run_transport(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_transport_degrades_on_api_error(tree: str) -> None:
    """A Dhis2ApiError fetching /api/system/info degrades the check rather than reporting a clean posture."""
    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_response = AsyncMock(side_effect=Dhis2ApiError(503, "down"))

    result = await _audit_module(tree)._run_transport(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note
