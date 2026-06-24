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
    CORS_PROBE_ORIGIN,
    CheckStatus,
    Severity,
    TransportHeaders,
    evaluate_transport,
)

TREES = ("v41", "v42", "v43")

# A fully hardened HTTPS posture: a 1-year-plus HSTS, CSP with frame-ancestors, nosniff, the three
# cross-origin isolation headers, and a genericised server.
_SECURE = TransportHeaders(
    base_url="https://mock.example",
    scheme="https",
    strict_transport_security="max-age=63072000; includeSubDomains",
    content_security_policy="frame-ancestors 'self';",
    x_content_type_options="nosniff",
    cross_origin_opener_policy="same-origin",
    cross_origin_embedder_policy="require-corp",
    cross_origin_resource_policy="same-origin",
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
    """A plaintext instance with every header absent yields plaintext, no-CSP, anti-framing, nosniff, cross-origin."""
    findings = evaluate_transport(TransportHeaders(base_url="http://bare.example", scheme="http"))
    titles = _titles(findings)
    assert titles == {
        "Base URL is plaintext HTTP",
        "No Content-Security-Policy header",
        "No anti-framing header",
        "No X-Content-Type-Options: nosniff",
        "Cross-origin isolation headers not configured (COOP/COEP/CORP)",
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


# ---------------------------------------------------------------------------
# HSTS max-age grading (3.5)
# ---------------------------------------------------------------------------


def test_hsts_one_year_or_more_has_no_weak_finding() -> None:
    """A max-age of at least 1 year (the secure fixture has 2 years) raises no weak-HSTS finding."""
    assert "Strict-Transport-Security max-age is weak" not in _titles(evaluate_transport(_SECURE))


def test_hsts_absent_is_medium_only_no_weak_finding() -> None:
    """An absent HSTS header stays the existing MEDIUM and does not also fire the present-but-weak WARN."""
    findings = evaluate_transport(_SECURE.model_copy(update={"strict_transport_security": None}))
    titles = _titles(findings)
    assert "No Strict-Transport-Security header" in titles
    assert "Strict-Transport-Security max-age is weak" not in titles


@pytest.mark.parametrize(
    "value",
    [
        "includeSubDomains",  # max-age missing
        "max-age=31536000abc",  # non-digit tail rejected by the strict regex
        "max-age=0",  # zero
        "max-age=3600",  # below 1 day
        "max-age=100000",  # below 1 year
    ],
)
def test_hsts_present_but_weak_is_one_warn(value: str) -> None:
    """Each present-but-weak max-age sub-case collapses into exactly one WARN with the parsed value in detail."""
    findings = evaluate_transport(_SECURE.model_copy(update={"strict_transport_security": value}))
    weak = [finding for finding in findings if finding.title == "Strict-Transport-Security max-age is weak"]
    assert len(weak) == 1
    assert weak[0].severity is Severity.WARN
    assert value in weak[0].detail
    assert (weak[0].evidence or {}).get("header") == value
    # The "missing HSTS" MEDIUM covers the absent case only -- it must not co-fire with the present-but-weak WARN.
    assert "No Strict-Transport-Security header" not in _titles(findings)


# ---------------------------------------------------------------------------
# CSP directive grading (3.6)
# ---------------------------------------------------------------------------

# A locked-down policy: a self fetch directive, object-src none, base-uri self, frame-ancestors self.
_STRONG_CSP = "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self';"


def _csp_finding(headers: TransportHeaders) -> Any:
    """The single Content-Security-Policy-is-weak finding for a header set, or None when absent."""
    weak = [finding for finding in evaluate_transport(headers) if finding.title == "Content-Security-Policy is weak"]
    return weak[0] if weak else None


def test_strong_csp_has_no_weak_finding() -> None:
    """A locked-down CSP (self fetch, object-src none, base-uri self, frame-ancestors self) raises no weak finding."""
    assert _csp_finding(_SECURE.model_copy(update={"content_security_policy": _STRONG_CSP})) is None


def test_dhis2_default_frame_only_csp_has_no_weak_finding() -> None:
    """DHIS2's stock `frame-ancestors 'self';` is a frame-only policy and must not be graded as content-weak."""
    assert _csp_finding(_SECURE.model_copy(update={"content_security_policy": "frame-ancestors 'self';"})) is None


def test_csp_absent_is_no_csp_medium_only_no_weak_finding() -> None:
    """An absent CSP stays the existing no-CSP MEDIUM; the parser produces no present-but-weak finding."""
    findings = evaluate_transport(
        _SECURE.model_copy(update={"content_security_policy": None, "x_frame_options": "SAMEORIGIN"})
    )
    titles = _titles(findings)
    assert "No Content-Security-Policy header" in titles
    assert "Content-Security-Policy is weak" not in titles


@pytest.mark.parametrize(
    ("policy", "expected_in_detail"),
    [
        ("default-src *; object-src 'none'; base-uri 'self'; frame-ancestors 'self';", "broad source"),
        (
            "script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'self';",
            "'unsafe-inline' allowed",
        ),
        (
            "script-src 'self' 'unsafe-eval'; object-src 'none'; base-uri 'self'; frame-ancestors 'self';",
            "'unsafe-eval' allowed",
        ),
        ("object-src 'self';", "no script-src or default-src directive"),
        (
            "script-src 'self'; object-src 'self' 'unsafe-inline'; base-uri 'self'; frame-ancestors 'self';",
            "object-src is not strictly locked down",
        ),
        ("script-src 'self'; object-src 'none'; frame-ancestors 'self';", "base-uri is unset"),
        (
            "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors *;",
            "frame-ancestors contains a broad source",
        ),
    ],
)
def test_csp_weak_subcase_is_one_medium_with_directive_in_detail(policy: str, expected_in_detail: str) -> None:
    """Each weak CSP sub-case yields exactly one MEDIUM finding naming the failed directive in its detail."""
    findings = evaluate_transport(_SECURE.model_copy(update={"content_security_policy": policy}))
    weak = [finding for finding in findings if finding.title == "Content-Security-Policy is weak"]
    assert len(weak) == 1
    assert weak[0].severity is Severity.MEDIUM
    assert expected_in_detail in (weak[0].evidence or {}).get("weak_directives", "")


def test_csp_report_only_mode_is_one_medium() -> None:
    """A CSP present only via the report-only header is flagged present-but-weak (not the absent no-CSP MEDIUM)."""
    findings = evaluate_transport(
        _SECURE.model_copy(
            update={
                "content_security_policy": None,
                "content_security_policy_report_only": _STRONG_CSP,
                "x_frame_options": "SAMEORIGIN",
            }
        )
    )
    titles = _titles(findings)
    assert "No Content-Security-Policy header" not in titles
    weak = [finding for finding in findings if finding.title == "Content-Security-Policy is weak"]
    assert len(weak) == 1
    assert "report-only" in (weak[0].evidence or {}).get("weak_directives", "")


def test_csp_strict_dynamic_is_annotation_not_a_warning() -> None:
    """A nonce-based policy using 'strict-dynamic' is annotated in detail and never flagged for it alone."""
    policy = "script-src 'self' 'strict-dynamic'; object-src 'none'; base-uri 'self'; frame-ancestors 'self';"
    finding = _csp_finding(_SECURE.model_copy(update={"content_security_policy": policy}))
    assert finding is None


def test_csp_present_without_frame_ancestors_does_not_double_flag() -> None:
    """A present CSP with no frame-ancestors raises only the anti-framing WARN, never a frame-ancestors-missing line."""
    headers = _SECURE.model_copy(
        update={
            "content_security_policy": "default-src 'self'; object-src 'none'; base-uri 'self';",
            "x_frame_options": None,
        }
    )
    findings = evaluate_transport(headers)
    titles = _titles(findings)
    # The anti-framing WARN owns the "frame-ancestors entirely missing" case.
    assert "No anti-framing header" in titles
    # The CSP-weak finding must not appear at all (the content directives are strong and a missing
    # frame-ancestors is NOT a CSP-weak sub-case -- only a present-but-broad one is).
    assert "Content-Security-Policy is weak" not in titles


# MINOR-2: empty source-list edge cases (present-but-empty = block-all = strong)


def test_csp_empty_script_src_is_strong() -> None:
    """A `script-src;` with no sources blocks all scripts and must not be flagged as missing fetch directive."""
    policy = "script-src; object-src 'none'; base-uri 'self'; frame-ancestors 'self';"
    assert _csp_finding(_SECURE.model_copy(update={"content_security_policy": policy})) is None


def test_csp_empty_object_src_is_strong() -> None:
    """A `object-src;` with no sources blocks all plugins and must not fall through to default-src."""
    policy = "script-src 'self'; object-src; base-uri 'self'; frame-ancestors 'self';"
    assert _csp_finding(_SECURE.model_copy(update={"content_security_policy": policy})) is None


# MINOR-3: duplicate-directive last-wins behavior pin


def test_csp_duplicate_directive_last_wins() -> None:
    """Duplicate directives resolve last-wins (mirroring the auditor app), not first-wins (CSP spec)."""
    # First default-src is broad; second is 'self'. Last-wins means the safe 'self' wins -- no broad warning.
    policy = "default-src *; default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self';"
    assert _csp_finding(_SECURE.model_copy(update={"content_security_policy": policy})) is None


# ---------------------------------------------------------------------------
# Cross-origin isolation headers: COOP / COEP / CORP (3.7)
# ---------------------------------------------------------------------------


def test_cross_origin_isolation_all_present_has_no_finding() -> None:
    """When COOP, COEP, and CORP are all set (the secure fixture) no cross-origin finding is raised."""
    assert "Cross-origin isolation headers not configured (COOP/COEP/CORP)" not in _titles(evaluate_transport(_SECURE))


def test_cross_origin_isolation_all_absent_is_one_info() -> None:
    """DHIS2 sets none of COOP/COEP/CORP, so all-absent is a SINGLE INFO listing the three missing headers."""
    findings = evaluate_transport(
        _SECURE.model_copy(
            update={
                "cross_origin_opener_policy": None,
                "cross_origin_embedder_policy": None,
                "cross_origin_resource_policy": None,
            }
        )
    )
    aggregated = [
        finding
        for finding in findings
        if finding.title == "Cross-origin isolation headers not configured (COOP/COEP/CORP)"
    ]
    assert len(aggregated) == 1
    assert aggregated[0].severity is Severity.INFO
    missing = (aggregated[0].evidence or {}).get("missing", "")
    assert "Cross-Origin-Opener-Policy" in missing
    assert "Cross-Origin-Embedder-Policy" in missing
    assert "Cross-Origin-Resource-Policy" in missing


def test_cross_origin_isolation_partial_lists_only_missing() -> None:
    """When only one of the three is set, the single INFO enumerates exactly the two still missing."""
    findings = evaluate_transport(
        _SECURE.model_copy(update={"cross_origin_embedder_policy": None, "cross_origin_resource_policy": None})
    )
    aggregated = [
        finding
        for finding in findings
        if finding.title == "Cross-origin isolation headers not configured (COOP/COEP/CORP)"
    ]
    assert len(aggregated) == 1
    missing = (aggregated[0].evidence or {}).get("missing", "")
    assert "Cross-Origin-Opener-Policy" not in missing
    assert "Cross-Origin-Embedder-Policy" in missing
    assert "Cross-Origin-Resource-Policy" in missing


# ---------------------------------------------------------------------------
# Runtime CORS response headers: ACAO / ACAC graded off the foreign-Origin probe (3.4)
# ---------------------------------------------------------------------------


def _cors_finding(headers: TransportHeaders) -> Any:
    """The single CORS response-header finding for a header set, or None when none is raised."""
    cors = [finding for finding in evaluate_transport(headers) if finding.title.startswith("CORS allows")]
    return cors[0] if cors else None


def test_cors_no_acao_has_no_finding() -> None:
    """A stock instance that does not whitelist the foreign probe origin emits no ACAO, so no finding."""
    assert _cors_finding(_SECURE) is None


def test_cors_wildcard_with_credentials_is_high() -> None:
    """Access-Control-Allow-Origin: * with credentials true is the dangerous wildcard-with-creds HIGH."""
    finding = _cors_finding(
        _SECURE.model_copy(update={"access_control_allow_origin": "*", "access_control_allow_credentials": "true"})
    )
    assert finding is not None
    assert finding.severity is Severity.HIGH
    assert finding.title == "CORS allows credentialed requests from any origin"
    assert (finding.evidence or {}).get("access-control-allow-origin") == "*"


def test_cors_wildcard_without_credentials_is_warn() -> None:
    """Access-Control-Allow-Origin: * with no credentials is the WARN allow-all case."""
    finding = _cors_finding(_SECURE.model_copy(update={"access_control_allow_origin": "*"}))
    assert finding is not None
    assert finding.severity is Severity.WARN
    assert finding.title == "CORS allows requests from any origin"


def test_cors_reflects_foreign_origin_with_credentials_is_high() -> None:
    """A server echoing the untrusted probe origin with credentials is the reflect-any HIGH (the live DHIS2 signal)."""
    finding = _cors_finding(
        _SECURE.model_copy(
            update={
                "access_control_allow_origin": CORS_PROBE_ORIGIN,
                "access_control_allow_credentials": "true",
            }
        )
    )
    assert finding is not None
    assert finding.severity is Severity.HIGH
    assert finding.title == "CORS allows credentialed requests from any origin"
    assert CORS_PROBE_ORIGIN in finding.detail
    assert (finding.evidence or {}).get("probe-origin") == CORS_PROBE_ORIGIN


def test_cors_reflects_foreign_origin_without_credentials_is_warn() -> None:
    """A server that echoes the untrusted probe origin without credentials is the reflect-any WARN."""
    finding = _cors_finding(_SECURE.model_copy(update={"access_control_allow_origin": CORS_PROBE_ORIGIN}))
    assert finding is not None
    assert finding.severity is Severity.WARN
    assert finding.title == "CORS allows requests from any origin"


def test_cors_specific_origin_with_credentials_is_warn() -> None:
    """A specific trusted origin echoed with credentials is the trusted-origin-review WARN."""
    finding = _cors_finding(
        _SECURE.model_copy(
            update={
                "access_control_allow_origin": "https://app.trusted.example",
                "access_control_allow_credentials": "true",
            }
        )
    )
    assert finding is not None
    assert finding.severity is Severity.WARN
    assert finding.title == "CORS allows credentials from a specific origin"
    assert "https://app.trusted.example" in finding.detail


def test_cors_specific_origin_without_credentials_has_no_finding() -> None:
    """A specific origin echoed WITHOUT credentials is a benign same-origin/whitelisted read, so no finding."""
    assert (
        _cors_finding(_SECURE.model_copy(update={"access_control_allow_origin": "https://app.trusted.example"})) is None
    )


def test_cors_credentials_value_is_case_insensitive() -> None:
    """An Access-Control-Allow-Credentials value of `TRUE` (any case) still raises the credentialed ceiling."""
    finding = _cors_finding(
        _SECURE.model_copy(update={"access_control_allow_origin": "*", "access_control_allow_credentials": "TRUE"})
    )
    assert finding is not None
    assert finding.severity is Severity.HIGH


def test_cors_wildcard_with_credentials_false_is_warn_not_high() -> None:
    """ACAO==* with ACAC==\"false\" stays WARN -- only the literal \"true\" (case-insensitive) escalates to HIGH."""
    finding = _cors_finding(
        _SECURE.model_copy(update={"access_control_allow_origin": "*", "access_control_allow_credentials": "false"})
    )
    assert finding is not None
    assert finding.severity is Severity.WARN
    assert finding.title == "CORS allows requests from any origin"


def test_cors_wildcard_with_credentials_empty_is_warn_not_high() -> None:
    """ACAO==* with ACAC==\"\" stays WARN -- an empty credentials value does not escalate to HIGH."""
    finding = _cors_finding(
        _SECURE.model_copy(update={"access_control_allow_origin": "*", "access_control_allow_credentials": ""})
    )
    assert finding is not None
    assert finding.severity is Severity.WARN
    assert finding.title == "CORS allows requests from any origin"


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
            "cross-origin-opener-policy": "same-origin",
            "cross-origin-embedder-policy": "require-corp",
            "cross-origin-resource-policy": "same-origin",
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


@pytest.mark.parametrize("tree", TREES)
async def test_run_transport_sends_foreign_origin_header(tree: str) -> None:
    """The probe sends a synthetic foreign Origin header on its allowlisted GET so DHIS2 emits the CORS headers."""
    client = _mock_client(base_url="https://mock.example", headers={})

    await _audit_module(tree)._run_transport(client)

    client.get_response.assert_awaited_once_with("/api/system/info", extra_headers={"Origin": CORS_PROBE_ORIGIN})


@pytest.mark.parametrize("tree", TREES)
async def test_run_transport_grades_echoed_cors_headers(tree: str) -> None:
    """The wiring reads the echoed ACAO/ACAC off the response and grades the dangerous reflect-with-creds case HIGH."""
    client = _mock_client(
        base_url="https://mock.example",
        headers={
            "strict-transport-security": "max-age=63072000",
            "content-security-policy": "frame-ancestors 'self';",
            "x-content-type-options": "nosniff",
            "cross-origin-opener-policy": "same-origin",
            "cross-origin-embedder-policy": "require-corp",
            "cross-origin-resource-policy": "same-origin",
            "server": "nginx",
            "access-control-allow-origin": CORS_PROBE_ORIGIN,
            "access-control-allow-credentials": "true",
        },
    )

    result = await _audit_module(tree)._run_transport(client)

    assert result.status is CheckStatus.OK
    by_title = _by_title(result.findings)
    finding = by_title["CORS allows credentialed requests from any origin"]
    assert finding.severity is Severity.HIGH
