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

from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "transport"

# A Server header discloses a version when it carries a digit run (e.g. `nginx/1.18.0`, `Jetty(9.4.x)`).
# A bare product token (just `nginx`) carries no version and is genericised enough to not warrant a finding.
_SERVER_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")


class TransportHeaders(BaseModel):
    """The transport posture of one response: the resolved base URL, scheme, and security headers off the wire."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    scheme: str
    strict_transport_security: str | None = None
    content_security_policy: str | None = None
    x_frame_options: str | None = None
    x_content_type_options: str | None = None
    server: str | None = None


def evaluate_transport(headers: TransportHeaders) -> list[AuditFinding]:
    """Findings over the transport scheme and security headers: TLS, HSTS, CSP, anti-framing, nosniff, server."""
    findings: list[AuditFinding] = []
    is_https = headers.scheme.lower() == "https"
    if not is_https:
        findings.append(_no_tls_finding(headers.base_url, headers.scheme))
    elif headers.strict_transport_security is None:
        findings.append(_no_hsts_finding())
    has_csp = headers.content_security_policy is not None
    has_frame_ancestors = has_csp and "frame-ancestors" in (headers.content_security_policy or "").lower()
    if not has_csp:
        findings.append(_no_csp_finding())
    if headers.x_frame_options is None and not has_frame_ancestors:
        findings.append(_no_anti_framing_finding())
    if (headers.x_content_type_options or "").strip().lower() != "nosniff":
        findings.append(_no_nosniff_finding())
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
