"""Route-target audit: DHIS2 Route API objects whose destination resolves to an internal or metadata host.

A DHIS2 Route is a server-side reverse proxy: DHIS2 fetches the configured `url` on behalf of the caller
and attaches the configured `auth` block, so an operator authorized to run a route can pivot it into an
SSRF primitive against the internal network or a cloud-metadata endpoint. The check inspects the
configured URL host only and NEVER executes a route.

Host classification normalizes two categories of SSRF-filter bypass before checking:
- Trailing FQDN dot: `localhost.` and `10.0.0.1.` strip to `localhost` / `10.0.0.1` before any check.
- Non-canonical numeric IP encodings: decimal (`2130706433`), hex (`0x7f000001`), octal (`0177.0.0.1`,
  `017700000001`), and short-form (`0` for 0.0.0.0) are resolved via `int(host, 0)` / IPv4 range check
  and converted to canonical `ipaddress` addresses before classification. The JVM InetAddress used by
  DHIS2 resolves all these forms, so they are valid SSRF destinations that would pass a naive literal check.

Private/internal address classification then uses the `ipaddress` module for IPv4/IPv6 literals plus
hostname rules (`localhost`, `.internal`/`.local`/`.localdomain` suffixes, and `metadata.google.internal`
-- the GCP named metadata endpoint). The cloud-metadata subset (169.254.169.254, its IPv6 equivalent
fd00:ec2::254, and `metadata.google.internal`) is the highest-value SSRF target and fires the more
specific metadata finding instead of the generic private-address one, so a single root cause never raises
two HIGHs.

Residual limitation: DNS-name hosts that resolve to private IPs at runtime are NOT detected -- the check
inspects only the configured literal host, by design (no DNS resolution). Operators should audit any
hostname that is not a public domain against their internal DNS.

`RouteTarget` carries no secret field by construction: every secret-bearing Route auth field is
WRITE_ONLY upstream and is never serialized, and only the non-secret identity (username / clientId /
tokenUri) is carried, enforcing the redaction contract in the type.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "routes"

# Hostnames that always resolve to the local instance or an internal-only zone.
_PRIVATE_HOSTNAMES: frozenset[str] = frozenset({"localhost", "metadata.google.internal"})

# Hostname suffixes reserved for internal / link-local naming, never a public destination.
_PRIVATE_HOST_SUFFIXES: tuple[str, ...] = (".internal", ".local", ".localdomain")

# The cloud instance-metadata service addresses. The IPv4 link-local 169.254.169.254 is the canonical
# IMDS endpoint; fd00:ec2::254 is its IPv6 form; metadata.google.internal is GCP's named endpoint.
_METADATA_HOSTNAMES: frozenset[str] = frozenset({"metadata.google.internal"})
_METADATA_IPS: frozenset[str] = frozenset({"169.254.169.254", "fd00:ec2::254"})


class RouteTarget(BaseModel):
    """One DHIS2 Route reduced to the non-secret fields the routes audit reasons over."""

    model_config = ConfigDict(frozen=True)

    uid: str | None = None
    code: str | None = None
    name: str
    url: str
    host: str | None = None
    disabled: bool = False
    allows_subpaths: bool = False
    auth_type: str | None = None
    auth_identity: str | None = None
    required_authorities: tuple[str, ...] = ()


def evaluate_routes(targets: list[RouteTarget]) -> list[AuditFinding]:
    """Findings over registered routes: private/metadata destinations, subpath wildcards, auth, run gating."""
    findings: list[AuditFinding] = []
    for target in targets:
        findings.extend(_route_findings(target))
    findings.append(_inventory_finding(targets))
    return findings


def _route_findings(target: RouteTarget) -> list[AuditFinding]:
    """Per-route findings: destination class, subpath wildcard, carried auth, and run gating."""
    findings: list[AuditFinding] = []
    if _is_metadata_host(target.host):
        findings.append(_metadata_finding(target))
    elif _is_private_host(target.host):
        findings.append(_private_address_finding(target))
    if target.allows_subpaths:
        findings.append(_subpaths_finding(target))
    if target.auth_type is not None:
        findings.append(_carries_auth_finding(target))
    if not target.required_authorities and not target.disabled:
        findings.append(_no_required_authorities_finding(target))
    return findings


def _private_address_finding(target: RouteTarget) -> AuditFinding:
    """Flag a route whose destination host is a private, loopback, link-local, or internal name."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Route proxies to a private or internal host",
        detail=(
            f"Route '{target.name}' ({target.code or 'no code'}) proxies to {target.url}, a private/internal "
            "or cloud-metadata host. Any operator authorized to run it makes DHIS2 issue the request from "
            "inside the network -- an SSRF primitive. Detection inspects the configured URL host only; the "
            "audit never executes the route."
        ),
        subject=target.name,
        group_key="route-private-address",
        evidence={"route": target.name, "url": target.url, "host": target.host or "unknown"},
    )


def _metadata_finding(target: RouteTarget) -> AuditFinding:
    """Flag a route pointed at the cloud instance-metadata endpoint, the highest-value SSRF target."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Route targets the cloud metadata endpoint",
        detail=(
            f"Route '{target.name}' targets the cloud instance metadata endpoint; on a misconfigured IMDSv1 "
            "host this exposes temporary IAM/role credentials. The highest-value SSRF target."
        ),
        subject=target.name,
        group_key="route-metadata-endpoint",
        evidence={"route": target.name, "url": target.url, "host": target.host or "unknown"},
    )


def _subpaths_finding(target: RouteTarget) -> AuditFinding:
    """Flag a route whose url ends in the `/**` wildcard, letting callers append arbitrary subpaths."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="Route allows arbitrary subpaths",
        detail=(
            f"Route '{target.name}' ends with `/**`, so callers can append arbitrary paths, widening the "
            "upstream URLs DHIS2 can be made to fetch; combined with a private base host this increases "
            "SSRF reach."
        ),
        subject=target.name,
        group_key="route-allows-subpaths",
        evidence={"route": target.name, "url": target.url},
    )


def _carries_auth_finding(target: RouteTarget) -> AuditFinding:
    """Note that a route stores upstream credentials DHIS2 attaches when proxying (the secret is WRITE_ONLY)."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Route carries upstream credentials",
        detail=(
            f"Route '{target.name}' stores upstream credentials server-side (auth type {target.auth_type}) "
            "that DHIS2 attaches when proxying. The secret is WRITE_ONLY and not exposed; identity shown for "
            "context."
        ),
        subject=target.name,
        group_key="route-carries-auth",
        evidence={
            "route": target.name,
            "auth_type": target.auth_type or "unknown",
            "identity": target.auth_identity or "none",
        },
    )


def _no_required_authorities_finding(target: RouteTarget) -> AuditFinding:
    """Flag an active route with no required authorities, so run access falls back to ACL canRead sharing."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.MEDIUM,
        title="Route has no required authorities",
        detail=(
            f"Route '{target.name}' lists no required authorities, so run access falls back to ACL canRead "
            "(sharing); if broadly shared, a wide set of users can drive a possibly-SSRF-capable destination. "
            "Pair with the sharing check."
        ),
        subject=target.name,
        group_key="route-no-required-authorities",
        evidence={"route": target.name, "url": target.url},
    )


def _inventory_finding(targets: list[RouteTarget]) -> AuditFinding:
    """Record the route inventory: each registered route is a server-side reverse proxy DHIS2 can be made to call."""
    active = sum(1 for target in targets if not target.disabled)
    disabled = len(targets) - active
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Route inventory",
        detail=(
            f"{len(targets)} route(s) registered ({active} active, {disabled} disabled). Each route is a "
            "server-side reverse proxy DHIS2 can be made to call."
        ),
        group_key="route-inventory",
        evidence={"total": str(len(targets)), "active": str(active), "disabled": str(disabled)},
    )


def host_from_url(url: str) -> str | None:
    """Parse the literal host out of a route url, lowercased, trailing FQDN dot stripped.

    urlsplit().hostname handles bracketed IPv6 (`[::1]` -> `::1`), userinfo (`user@host` -> `host`),
    and host:port splitting. The trailing-dot strip turns FQDN forms like `localhost.` and `10.0.0.1.`
    into their canonical equivalents before classification. Returns None when the host cannot be parsed.
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = parsed.hostname
    if not host:
        return None
    host = host.lower()
    # Strip a single trailing FQDN dot so `localhost.` and `10.0.0.1.` classify correctly.
    if host.endswith(".") and len(host) > 1:
        host = host[:-1]
    return host


def _is_metadata_host(host: str | None) -> bool:
    """Return True when the host is a cloud instance-metadata endpoint (the most specific private case)."""
    if host is None:
        return False
    if host in _METADATA_HOSTNAMES:
        return True
    address = _as_ip(host)
    return address is not None and address.compressed in _METADATA_IPS


def _is_private_host(host: str | None) -> bool:
    """Return True when the host is a private/internal IP literal or an internal hostname."""
    if host is None:
        return False
    if host in _PRIVATE_HOSTNAMES or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return True
    address = _as_ip(host)
    if address is None:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified


def _as_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a host as an IP address, handling canonical literals, bracketed IPv6, and numeric encodings.

    Numeric encoding normalization covers the SSRF-bypass forms the JVM InetAddress resolves:
    - Decimal integer: `2130706433` -> 127.0.0.1
    - Hex literal: `0x7f000001` -> 127.0.0.1
    - Octal-dotted: `0177.0.0.1` -> 127.0.0.1 (each leading-zero octet parsed as base-8)
    - Octal-packed: `017700000001` -> 127.0.0.1 (bare leading-zero digit string parsed as base-8)
    - Short form: `0` -> 0.0.0.0

    Returns None when the host is a DNS name, not an address literal.
    """
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    # Fast path: canonical dotted notation or canonical IPv6.
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    # Numeric encoding: try int(candidate, 0) which handles decimal, 0x hex.
    # bare `0` is 0.0.0.0; `2130706433` is 127.0.0.1; `0x7f000001` is 127.0.0.1.
    try:
        value = int(candidate, 0)
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
        if 0 <= value <= 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:
            return ipaddress.IPv6Address(value)
    except (ValueError, TypeError):
        pass
    # Octal-packed: a leading-zero all-digit string that int(x,0) won't accept (Python 3 requires 0o prefix).
    # `017700000001` is octal for 2130706433 = 127.0.0.1. Try base-8 when the string starts with `0`.
    if candidate.startswith("0") and candidate.isdigit():
        try:
            value = int(candidate, 8)
            if 0 <= value <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(value)
        except ValueError:
            pass
    # Octal-dotted: `0177.0.0.1` -- each octet that starts with `0` and is all-digits is base-8.
    result = _parse_octal_dotted(candidate)
    if result is not None:
        return result
    return None


def _parse_octal_dotted(candidate: str) -> ipaddress.IPv4Address | None:
    """Parse an octal-dotted IPv4 like `0177.0.0.1`; returns None when not this form."""
    parts = candidate.split(".")
    if len(parts) != 4:
        return None
    octets: list[int] = []
    has_octal = False
    for part in parts:
        if not part:
            return None
        if part.startswith("0") and len(part) > 1 and part.isdigit():
            # Leading-zero octet: treat as octal.
            try:
                value = int(part, 8)
            except ValueError:
                return None
            if not (0 <= value <= 255):
                return None
            octets.append(value)
            has_octal = True
        elif part.isdigit():
            value = int(part, 10)
            if not (0 <= value <= 255):
                return None
            octets.append(value)
        else:
            return None
    if not has_octal:
        # All decimal: would have been caught by ipaddress.ip_address() already.
        return None
    return ipaddress.IPv4Address(bytes(octets))
