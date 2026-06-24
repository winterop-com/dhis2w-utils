"""Version-invariant string helpers shared by the security wire extractors."""

from __future__ import annotations


def split_delimited(value: str | None, *, lower: bool = False) -> list[str]:
    """Split a comma-string into trimmed non-empty tokens, optionally lowercased."""
    if not value:
        return []
    tokens = (token.strip() for token in value.split(","))
    return [token.lower() if lower else token for token in tokens if token]
