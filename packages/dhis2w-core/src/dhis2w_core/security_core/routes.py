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

Residual limitation: DNS-name hosts that resolve to private IPs at runtime are NOT detected; the check
inspects only the configured literal host, by design (no DNS resolution). Operators should audit any
hostname that is not a public domain against their internal DNS.

`RouteTarget` carries no secret field by construction: every secret-bearing Route auth field is
WRITE_ONLY upstream and is never serialized, and only the non-secret identity (username / clientId /
tokenUri) is carried, enforcing the redaction contract in the type.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity
from dhis2w_core.security_core.net import is_metadata_host, is_private_host

_CHECK = "routes"


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
    if is_metadata_host(target.host):
        findings.append(_metadata_finding(target))
    elif is_private_host(target.host):
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
            "inside the network; an SSRF primitive. Detection inspects the configured URL host only; the "
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
