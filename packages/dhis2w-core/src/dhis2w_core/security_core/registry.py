"""Canonical security-check catalog and the bound-check wrapper the orchestrator runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.report.model import CheckResult


class CheckSpec(BaseModel):
    """One entry in the canonical check catalog: a stable key and a human label."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str


# The full audit running order: cheap and high-signal first, broad and expensive
# last. Checks are implemented incrementally; `IMPLEMENTED_CHECK_KEYS` records
# which specs have a runnable implementation today, and each later check PR adds
# its key there as it lands.
CANONICAL_CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(key="version", label="Version and patch posture"),
    CheckSpec(key="transport", label="Transport and security headers"),
    CheckSpec(key="settings", label="System security settings"),
    CheckSpec(key="authorities", label="Audited account authorities"),
    CheckSpec(key="roles", label="Instance role audit"),
    CheckSpec(key="hygiene", label="User account hygiene"),
    CheckSpec(key="credential-probe", label="Default-credential probe"),
    CheckSpec(key="guest", label="Anonymous access"),
    CheckSpec(key="apps", label="Installed apps"),
    CheckSpec(key="sharing", label="Public metadata sharing"),
    CheckSpec(key="auth-methods", label="External login methods"),
    CheckSpec(key="tokens", label="Personal access tokens"),
    CheckSpec(key="routes", label="Route API targets"),
    CheckSpec(key="audit-config", label="Audit logging configuration"),
)

# Checks with a runnable implementation right now.
IMPLEMENTED_CHECK_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "transport",
        "settings",
        "authorities",
        "credential-probe",
        "roles",
        "hygiene",
        "apps",
        "guest",
        "sharing",
    }
)

_LABEL_BY_KEY: dict[str, str] = {spec.key: spec.label for spec in CANONICAL_CHECKS}


class BoundCheck(BaseModel):
    """A catalog check bound to a zero-argument coroutine that produces its result."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    label: str
    run: Callable[[], Awaitable[CheckResult]]


def canonical_keys() -> list[str]:
    """Return every catalog key in canonical running order."""
    return [spec.key for spec in CANONICAL_CHECKS]


def label_for(key: str) -> str:
    """Return the human label for a check key, or the key itself when unknown."""
    return _LABEL_BY_KEY.get(key, key)


def select_keys(keys: list[str], *, only: list[str] | None = None, skip: list[str] | None = None) -> list[str]:
    """Filter `keys` (already in canonical order) by an optional allow then deny list."""
    selected = keys
    if only is not None:
        allow = set(only)
        selected = [key for key in selected if key in allow]
    if skip is not None:
        deny = set(skip)
        selected = [key for key in selected if key not in deny]
    return selected


def resolve_check_keys(only: list[str] | None = None, skip: list[str] | None = None) -> list[str]:
    """Resolve the implemented check keys to run, validating every requested key.

    Raises ValueError when a requested key is unknown, when `only` names a check
    that has no implementation yet, or when the selection is empty, so a typo or
    a not-yet-built check never silently produces an empty security report.
    """
    valid = set(canonical_keys())
    requested = [*(only or []), *(skip or [])]
    unknown = sorted({key for key in requested if key not in valid})
    if unknown:
        raise ValueError(f"unknown check key(s): {', '.join(unknown)}; valid keys: {', '.join(canonical_keys())}")
    implemented = [key for key in canonical_keys() if key in IMPLEMENTED_CHECK_KEYS]
    if only is not None:
        not_implemented = sorted({key for key in only if key not in IMPLEMENTED_CHECK_KEYS})
        if not_implemented:
            raise ValueError(
                f"check(s) not implemented yet: {', '.join(not_implemented)}; available now: {', '.join(implemented)}"
            )
    selected = select_keys(implemented, only=only, skip=skip)
    if not selected:
        raise ValueError("no checks selected to run")
    return selected
