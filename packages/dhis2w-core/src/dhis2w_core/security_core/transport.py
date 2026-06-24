"""Transport-posture audit: TLS scheme and the security headers DHIS2 (or its proxy) returns on the wire.

Credential confidentiality and clickjacking / MIME-sniffing defences are decided at the transport edge,
not in metadata, so this check reads the base-URL scheme and a single response's security headers. A
plaintext base URL leaks every credential and all metadata in clear text. Over HTTPS, a missing
Strict-Transport-Security header leaves an SSL-strip window; DHIS2 emits HSTS via Spring Security only
when the request reaches the app as secure, so a TLS-terminating proxy that forwards plain HTTP commonly
suppresses it. The wire header is the SOLE evidence of CSP state -- there is no `keyCspEnabled` system
setting; a default DHIS2 (csp.enabled=on) always emits at least `frame-ancestors 'self';` via CspFilter,
and switches to `X-Frame-Options: SAMEORIGIN` when CSP is off, so anti-framing is flagged only when both
are absent. X-Content-Type-Options is set unconditionally by Spring Security, so its absence points at
upstream stripping. A Server header carrying a version token is a free CVE-matching fingerprint emitted
by the container or proxy, not DHIS2 code. The wire-only CSP state and the HSTS-behind-proxy
suppression are recorded as BUGS.md #49.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.csp import grade_csp, parse_csp
from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "transport"

# A Server header discloses a version when it carries a digit run (e.g. `nginx/1.18.0`, `Jetty(9.4.x)`).
# A bare product token (just `nginx`) carries no version and is genericised enough to not warrant a finding.
_SERVER_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")

# The max-age directive value must be entirely digits: `parseInt`-style parsing would silently accept
# `max-age=31536000abc`. The full directive is anchored so a trailing garbage tail rejects the whole match.
_HSTS_MAX_AGE_RE = re.compile(r"^max-age=(\d+)$")

# HSTS thresholds in seconds: below 1 year is weak, below 1 day is effectively no protection.
_ONE_YEAR_SECONDS = 31_536_000
_ONE_DAY_SECONDS = 86_400


class TransportHeaders(BaseModel):
    """The transport posture of one response: the resolved base URL, scheme, and security headers off the wire."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    scheme: str
    strict_transport_security: str | None = None
    content_security_policy: str | None = None
    content_security_policy_report_only: str | None = None
    x_frame_options: str | None = None
    x_content_type_options: str | None = None
    cross_origin_opener_policy: str | None = None
    cross_origin_embedder_policy: str | None = None
    cross_origin_resource_policy: str | None = None
    server: str | None = None


def evaluate_transport(headers: TransportHeaders) -> list[AuditFinding]:
    """Findings over the transport scheme and security headers: TLS, HSTS, CSP, anti-framing, nosniff, cross-origin."""
    findings: list[AuditFinding] = []
    is_https = headers.scheme.lower() == "https"
    if not is_https:
        findings.append(_no_tls_finding(headers.base_url, headers.scheme))
    elif headers.strict_transport_security is None:
        findings.append(_no_hsts_finding())
    else:
        weak_hsts = _weak_hsts_finding(headers.strict_transport_security)
        if weak_hsts is not None:
            findings.append(weak_hsts)
    enforced_csp = headers.content_security_policy
    report_only_csp = headers.content_security_policy_report_only
    csp_value = enforced_csp if enforced_csp is not None else report_only_csp
    has_csp = csp_value is not None
    has_frame_ancestors = has_csp and "frame-ancestors" in (csp_value or "").lower()
    if not has_csp:
        findings.append(_no_csp_finding())
    else:
        weak_csp = _weak_csp_finding(csp_value or "", report_only=enforced_csp is None)
        if weak_csp is not None:
            findings.append(weak_csp)
    if headers.x_frame_options is None and not has_frame_ancestors:
        findings.append(_no_anti_framing_finding())
    if (headers.x_content_type_options or "").strip().lower() != "nosniff":
        findings.append(_no_nosniff_finding())
    cross_origin = _cross_origin_isolation_finding(headers)
    if cross_origin is not None:
        findings.append(cross_origin)
    server_finding = _server_disclosure_finding(headers.server)
    if server_finding is not None:
        findings.append(server_finding)
    return findings


def _no_tls_finding(base_url: str, scheme: str) -> AuditFinding:
    """Flag a plaintext base URL: every request carries credentials and metadata in clear text."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Base URL is plaintext HTTP",
        detail=(
            f"Plaintext HTTP at {base_url}; every request carries the operator's credentials "
            "and all metadata in clear text. Terminate TLS in front of DHIS2 and serve only https."
        ),
        evidence={"base_url": base_url, "scheme": scheme},
    )


def _no_hsts_finding() -> AuditFinding:
    """Flag an HTTPS endpoint with no Strict-Transport-Security header, leaving an SSL-strip window."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="No Strict-Transport-Security header",
        detail=(
            "HTTPS endpoint returns no Strict-Transport-Security header, leaving an SSL-strip / downgrade "
            "window. DHIS2 emits HSTS via Spring Security only when the request reaches the app as secure; "
            "a TLS-terminating proxy that forwards plain HTTP commonly suppresses it. Set HSTS at the proxy "
            "or forward the secure flag."
        ),
        evidence={"header": "strict-transport-security"},
    )


def _weak_hsts_finding(value: str) -> AuditFinding | None:
    """Grade a present Strict-Transport-Security header's max-age; flag one WARN when below 1 year."""
    max_age = _parse_hsts_max_age(value)
    if max_age is not None and max_age >= _ONE_YEAR_SECONDS:
        return None
    if max_age is None:
        reason = "max-age is missing or invalid (a digits-only max-age in seconds is required)"
    elif max_age <= 0:
        reason = f"max-age={max_age} provides no protection"
    elif max_age < _ONE_DAY_SECONDS:
        reason = f"max-age={max_age} is below 1 day and provides effectively no protection"
    else:
        reason = f"max-age={max_age} is below the recommended 1 year ({_ONE_YEAR_SECONDS})"
    return AuditFinding(
        check=_CHECK,
        severity=Severity.WARN,
        title="Strict-Transport-Security max-age is weak",
        detail=(
            f"Strict-Transport-Security: {value}. {reason}. Set max-age to at least {_ONE_YEAR_SECONDS} "
            "(1 year) with includeSubDomains for strong protection against downgrade attacks."
        ),
        evidence={"header": value},
    )


def _parse_hsts_max_age(value: str) -> int | None:
    """Parse the max-age directive with a strict digit-only regex; None when absent or non-numeric."""
    for directive in value.split(";"):
        match = _HSTS_MAX_AGE_RE.match(directive.strip().lower())
        if match is not None:
            return int(match.group(1))
    return None


def _weak_csp_finding(value: str, *, report_only: bool) -> AuditFinding | None:
    """Grade a present CSP into one MEDIUM finding listing the failed directives, or None when strong."""
    policy = parse_csp(value, report_only=report_only)
    failures = grade_csp(policy)
    if not failures:
        return None
    annotation = " (uses 'strict-dynamic')" if policy.uses_strict_dynamic() else ""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="Content-Security-Policy is weak",
        detail=(
            f"Content-Security-Policy: {value}{annotation}. Weak directives: {'; '.join(failures)}. "
            "Tighten the policy so it governs script, object, and base-uri sources without broad or unsafe sources."
        ),
        evidence={"header": value, "weak_directives": "; ".join(failures)},
    )


def _cross_origin_isolation_finding(headers: TransportHeaders) -> AuditFinding | None:
    """Flag cross-origin isolation as one INFO when DHIS2 sets none of COOP/COEP/CORP (its stock posture)."""
    missing = [
        name
        for name, value in (
            ("Cross-Origin-Opener-Policy", headers.cross_origin_opener_policy),
            ("Cross-Origin-Embedder-Policy", headers.cross_origin_embedder_policy),
            ("Cross-Origin-Resource-Policy", headers.cross_origin_resource_policy),
        )
        if value is None
    ]
    if not missing:
        return None
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Cross-origin isolation headers not configured (COOP/COEP/CORP)",
        detail=(
            f"Not set: {', '.join(missing)}. DHIS2 calls Spring Security's `defaultsDisabled()` and re-enables "
            "only contentTypeOptions, xssProtection, and HSTS, so it never emits these defence-in-depth headers; "
            "a stock instance is missing all three. Set them at the proxy to harden cross-origin isolation "
            "(COOP: same-origin, COEP: require-corp, CORP: same-origin)."
        ),
        evidence={"missing": ", ".join(missing)},
    )


def _no_csp_finding() -> AuditFinding:
    """Flag a missing Content-Security-Policy header: CSP is disabled in dhis.conf or stripped upstream."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="No Content-Security-Policy header",
        detail=(
            "On a default DHIS2 (csp.enabled=on) the CspFilter always emits at least `frame-ancestors "
            "'self';`. Absence means CSP was disabled in dhis.conf (csp.enabled=off) or stripped upstream. "
            "The header on the wire is the SOLE evidence -- there is no `keyCspEnabled` system setting."
        ),
        evidence={"header": "content-security-policy"},
    )


def _no_anti_framing_finding() -> AuditFinding:
    """Flag missing anti-framing: neither X-Frame-Options nor a CSP frame-ancestors directive is present."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.WARN,
        title="No anti-framing header",
        detail=(
            "DHIS2 supplies one or the other (CSP frame-ancestors when csp.enabled=on, X-Frame-Options "
            "SAMEORIGIN when off); both missing points at upstream stripping. Suppressed when CSP "
            "frame-ancestors is present, to avoid a guaranteed false positive on default instances."
        ),
        evidence={"headers": "x-frame-options, content-security-policy"},
    )


def _no_nosniff_finding() -> AuditFinding:
    """Flag a missing or non-`nosniff` X-Content-Type-Options header, so browsers may MIME-sniff."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.WARN,
        title="No X-Content-Type-Options: nosniff",
        detail=(
            "Browsers may MIME-sniff. DHIS2 sets this unconditionally via Spring Security, so absence "
            "indicates upstream stripping."
        ),
        evidence={"header": "x-content-type-options"},
    )


def _server_disclosure_finding(server: str | None) -> AuditFinding | None:
    """Flag a Server header that reveals a version token; a bare product token discloses nothing useful."""
    if server is None:
        return None
    value = server.strip()
    if not value or not _SERVER_VERSION_RE.search(value):
        return None
    return AuditFinding(
        check=_CHECK,
        severity=Severity.WARN,
        title="Server header discloses version",
        detail=(
            f"The Server header reveals server software and version ({value}), a free fingerprint for CVE "
            "matching. Emitted by the container or proxy, not DHIS2 code; genericize it at the proxy."
        ),
        evidence={"server": value},
    )
