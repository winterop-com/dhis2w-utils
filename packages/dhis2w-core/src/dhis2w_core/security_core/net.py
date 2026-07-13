"""Shared URL-host parsing and host classification for the security checks.

The routes SSRF check and the auth-methods loose-redirect check both parse a URL host and reason about
internal / loopback destinations. The parsing and classification live here once so the two checks share one
notion of "is this host local" rather than each rolling its own.

Two host views are exposed because the two checks need different normalizations:

- `host_from_url` is the SSRF view: lowercased, trailing-FQDN-dot stripped, IPv6-bracket aware. The routes
  check pairs it with `is_private_host` / `is_metadata_host`, which additionally resolve the non-canonical
  numeric IP encodings (decimal / hex / octal / trailing-dot) the JVM InetAddress accepts so an SSRF filter
  bypass is normalized before classification.
- `redirect_scheme_and_host` is the RFC-8252 view used by the auth-methods loose-redirect check: scheme as-is
  plus the lowercased host only (no trailing-dot strip), compared against the literal loopback-redirect set a
  native app may use over cleartext http:// during the auth flow.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

# Hostnames that always resolve to the local instance or an internal-only zone. The `.internal`
# suffix in `_PRIVATE_HOST_SUFFIXES` already covers `metadata.google.internal` and friends.
_PRIVATE_HOSTNAMES: frozenset[str] = frozenset({"localhost"})

# Hostname suffixes reserved for internal / link-local naming, never a public destination.
_PRIVATE_HOST_SUFFIXES: tuple[str, ...] = (".internal", ".local", ".localdomain")

# The cloud instance-metadata service addresses. The IPv4 link-local 169.254.169.254 is the canonical
# IMDS endpoint; fd00:ec2::254 is its IPv6 form; metadata.google.internal is GCP's named endpoint.
_METADATA_HOSTNAMES: frozenset[str] = frozenset({"metadata.google.internal"})
_METADATA_IPS: frozenset[str] = frozenset({"169.254.169.254", "fd00:ec2::254"})

# Loopback hosts a cleartext http:// redirect URI is allowed to use without being a finding (RFC 8252:
# a native app may use http://127.0.0.1 / http://localhost as a loopback redirect during the auth flow).
LOOPBACK_REDIRECT_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


def host_from_url(url: str) -> str | None:
    """Parse the literal host out of a route url, lowercased, trailing FQDN dot stripped.

    urlsplit().hostname handles bracketed IPv6 (`[::1]` -> `::1`), userinfo (`user@host` -> `host`),
    and host:port splitting. The trailing-dot strip turns FQDN forms like `localhost.` and `10.0.0.1.`
    into their canonical equivalents before classification. Returns None when the host cannot be parsed.
    """
    host = _parse_hostname(url)
    if host is None:
        return None
    # Strip a single trailing FQDN dot so `localhost.` and `10.0.0.1.` classify correctly.
    if host.endswith(".") and len(host) > 1:
        host = host[:-1]
    return host


def redirect_scheme_and_host(uri: str) -> tuple[str, str]:
    """Parse a redirect uri's scheme and lowercased host for the RFC-8252 loopback check (no trailing-dot strip).

    The host is lowercased and empty when absent. Raises ValueError when the uri cannot be split, matching the
    auth-methods loose-redirect check's treatment of an unparseable uri as not-a-loose-redirect.
    """
    parsed = urlsplit(uri)
    return parsed.scheme, (parsed.hostname or "").lower()


def is_metadata_host(host: str | None) -> bool:
    """Return True when the host is a cloud instance-metadata endpoint (the most specific private case)."""
    if host is None:
        return False
    if host in _METADATA_HOSTNAMES:
        return True
    address = _as_ip(host)
    return address is not None and address.compressed in _METADATA_IPS


def is_private_host(host: str | None) -> bool:
    """Return True when the host is a private/internal IP literal or an internal hostname."""
    if host is None:
        return False
    if host in _PRIVATE_HOSTNAMES or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return True
    address = _as_ip(host)
    if address is None:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified


def _parse_hostname(url: str) -> str | None:
    """Return the lowercased hostname of a url, or None when it cannot be parsed."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = parsed.hostname
    if not host:
        return None
    return host.lower()


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
    # Octal-dotted: `0177.0.0.1`; each octet that starts with `0` and is all-digits is base-8.
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
