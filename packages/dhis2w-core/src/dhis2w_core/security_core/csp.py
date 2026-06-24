"""Content-Security-Policy parsing and grading for the transport check.

A CSP header is graded on its directive *values*, not by substring matching, so a wildly
permissive policy like `default-src *` cannot slip past. The header is parsed into a frozen
`CspDirectives` view-model that lowercases both directive names and source values (keyword
sources such as `'unsafe-inline'` are case-insensitive in practice). The grader returns a list
of human-readable directive failures that the transport reducer aggregates into one MEDIUM
finding. DHIS2's own default policy is `frame-ancestors 'self';` (a clickjacking-only policy,
BUGS.md #49), so the content-source rules (script-src/object-src/base-uri) apply only to a
policy that actually governs content loading: a frame-only / report-only policy is left ungraded
on its content directives so a stock instance is never flagged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# A source that defeats the purpose of the directive it appears in: any origin, any http(s)
# origin, or a data: URI. Mirrors the auditor-app's BROAD_SOURCES set.
_BROAD_SOURCES: frozenset[str] = frozenset({"*", "http:", "https:", "data:"})


class CspDirectives(BaseModel):
    """A parsed Content-Security-Policy: a lowercased directive-name to source-list map with typed accessors."""

    model_config = ConfigDict(frozen=True)

    report_only: bool = False
    directives: dict[str, tuple[str, ...]] = {}

    def sources(self, name: str) -> tuple[str, ...] | None:
        """The source list for one directive (already lowercased), or None when the directive is absent."""
        return self.directives.get(name)

    def has(self, name: str) -> bool:
        """Whether the policy declares the named directive at all."""
        return name in self.directives

    def fetch_sources(self) -> tuple[str, ...] | None:
        """The directive governing scripts: script-src if present, else default-src, else None.

        Uses has()-based lookup so a present-but-empty source list (block-all) is not confused with absent.
        """
        if self.has("script-src"):
            return self.directives["script-src"]
        if self.has("default-src"):
            return self.directives["default-src"]
        return None

    def governs_content(self) -> bool:
        """Whether the policy attempts to govern content loading (has a fetch/object/base-uri directive)."""
        return self.has("script-src") or self.has("default-src") or self.has("object-src") or self.has("base-uri")

    def uses_strict_dynamic(self) -> bool:
        """Whether the script fetch sources opt into 'strict-dynamic' (a nonce/hash-based policy signal)."""
        fetch = self.fetch_sources()
        return fetch is not None and "'strict-dynamic'" in fetch


def parse_csp(value: str, *, report_only: bool) -> CspDirectives:
    """Parse a CSP header value into a `CspDirectives`, lowercasing directive names and source values.

    Duplicate directives resolve last-wins (Python dict overwrite), mirroring the auditor app. The CSP
    spec honors first-wins, but real servers do not emit duplicates so the distinction is moot in practice.
    """
    directives: dict[str, tuple[str, ...]] = {}
    for part in value.split(";"):
        tokens = part.strip().split()
        if not tokens:
            continue
        name, *sources = tokens
        directives[name.lower()] = tuple(source.lower() for source in sources)
    return CspDirectives(report_only=report_only, directives=directives)


def grade_csp(policy: CspDirectives) -> list[str]:
    """Grade a parsed CSP and return the directive failures (empty when the policy is strong)."""
    failures: list[str] = []
    if policy.report_only:
        failures.append("policy is report-only (not enforced)")
    if policy.governs_content():
        failures.extend(_grade_content_sources(policy))
        failures.extend(_grade_object_src(policy))
        failures.extend(_grade_base_uri(policy))
    failures.extend(_grade_frame_ancestors(policy))
    return failures


def _has_broad(sources: tuple[str, ...]) -> bool:
    """Whether any source defeats the directive (a wildcard, http:/https: scheme, or data: URI)."""
    return any(source in _BROAD_SOURCES for source in sources)


def _broad_list(sources: tuple[str, ...]) -> str:
    """The broad sources present, comma-joined, for the failure detail."""
    return ", ".join(source for source in sources if source in _BROAD_SOURCES)


def _grade_content_sources(policy: CspDirectives) -> list[str]:
    """Grade the script fetch sources: missing fetch directive, broad sources, unsafe-inline/eval."""
    failures: list[str] = []
    fetch = policy.fetch_sources()
    if fetch is None:
        failures.append("no script-src or default-src directive")
        return failures
    if _has_broad(fetch):
        failures.append(f"script-src/default-src contains a broad source ({_broad_list(fetch)})")
    if "'unsafe-inline'" in fetch:
        failures.append("'unsafe-inline' allowed in script-src/default-src")
    if "'unsafe-eval'" in fetch:
        failures.append("'unsafe-eval' allowed in script-src/default-src")
    return failures


def _grade_object_src(policy: CspDirectives) -> list[str]:
    """Grade object-src (or its default-src fallback): should be 'none' or otherwise locked down.

    Uses has()-based lookup so a present-but-empty source list (block-all plugins) is not confused with absent.
    """
    if policy.has("object-src"):
        object_src: tuple[str, ...] | None = policy.directives["object-src"]
    else:
        object_src = policy.sources("default-src")
    if object_src is None:
        return ["object-src is unset (recommend object-src 'none')"]
    # An empty source list blocks all plugins (block-all), equivalent to or stronger than 'none'.
    is_none_or_empty = object_src == ("'none'",) or len(object_src) == 0
    is_locked = not _has_broad(object_src) and "'unsafe-inline'" not in object_src and "'unsafe-eval'" not in object_src
    if not is_none_or_empty and not is_locked:
        return ["object-src is not strictly locked down"]
    return []


def _grade_base_uri(policy: CspDirectives) -> list[str]:
    """Grade base-uri: unset (allowing <base> hijacking) or broad is a failure."""
    base_uri = policy.sources("base-uri")
    if base_uri is None:
        return ["base-uri is unset (recommend base-uri 'none' or 'self')"]
    if _has_broad(base_uri):
        return ["base-uri contains a broad source"]
    return []


def _grade_frame_ancestors(policy: CspDirectives) -> list[str]:
    """Grade frame-ancestors only when present-but-broad; the entirely-missing case is the anti-framing WARN."""
    frame_ancestors = policy.sources("frame-ancestors")
    if frame_ancestors is not None and _has_broad(frame_ancestors):
        return ["frame-ancestors contains a broad source"]
    return []
