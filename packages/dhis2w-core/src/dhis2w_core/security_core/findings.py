"""Audit finding model and severity tiers shared by every security check."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Severity(StrEnum):
    """Severity tier of one audit finding."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    WARN = "WARN"
    INFO = "INFO"


# Severity tiers ordered most-to-least urgent; renderers sort by this order.
SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.WARN,
    Severity.INFO,
)

# Role categories worth a HIGH severity even without ALL: these unlock
# privilege paths an attacker can chain into instance takeover. Keys match
# `AUTHORITY_CATEGORIES` in `dhis2w_core.security_core.authorities`.
HIGH_RISK_ROLE_CATEGORIES: frozenset[str] = frozenset(
    {
        "app_management",
        "sql_views",
        "metadata_io",
        "user_management",
    }
)


class AuditFinding(BaseModel):
    """One security audit finding; a single row in audit output."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["instance", "role", "user", "app", "guest"]
    subject: str
    severity: Severity
    details: str


def severity_rank(severity: Severity) -> int:
    """Sort key so CRITICAL sorts ahead of HIGH ahead of MEDIUM and the rest."""
    return SEVERITY_ORDER.index(severity)


def role_severity(categories: Iterable[str], *, has_all: bool) -> Severity:
    """ALL roles are CRITICAL; high-impact categories HIGH; the rest MEDIUM."""
    keys = set(categories)
    if has_all or "superuser" in keys:
        return Severity.CRITICAL
    if keys & HIGH_RISK_ROLE_CATEGORIES:
        return Severity.HIGH
    return Severity.MEDIUM
