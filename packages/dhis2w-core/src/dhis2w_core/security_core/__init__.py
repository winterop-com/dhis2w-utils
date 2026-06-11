"""Version-invariant security domain logic shared by every security plugin tree.

The authority taxonomy, severity model, and guardrail contract are security
opinions, not version concerns: they live once here and are consumed by the
thin per-tree plugin shims under `dhis2w_core.v{41,42,43}.plugins.security`.
Only genuinely version-divergent wire extraction lives per tree.
"""

from __future__ import annotations

from dhis2w_core.security_core.authorities import (
    AUTHORITY_CATEGORIES,
    AuthorityCategory,
    build_account_authorities,
    categorise_authorities,
)
from dhis2w_core.security_core.findings import (
    HIGH_RISK_ROLE_CATEGORIES,
    SEVERITY_ORDER,
    AuditFinding,
    Severity,
    role_severity,
    severity_rank,
)
from dhis2w_core.security_core.guardrails import CONNECT_PATHS, GET_ALLOWLIST
from dhis2w_core.security_core.models import AccountAuthorities, CategoryMatch

__all__ = [
    "AUTHORITY_CATEGORIES",
    "CONNECT_PATHS",
    "GET_ALLOWLIST",
    "HIGH_RISK_ROLE_CATEGORIES",
    "SEVERITY_ORDER",
    "AccountAuthorities",
    "AuditFinding",
    "AuthorityCategory",
    "CategoryMatch",
    "Severity",
    "build_account_authorities",
    "categorise_authorities",
    "role_severity",
    "severity_rank",
]
