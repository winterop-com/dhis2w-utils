"""Version-invariant security domain logic shared by every security plugin tree.

The authority taxonomy, severity model, guardrail contract, audit orchestration,
and report rendering are security opinions, not version concerns: they live once
here and are consumed by the thin per-tree plugin shims under
`dhis2w_core.v{41,42,43}.plugins.security`. Only genuinely version-divergent wire
extraction lives per tree.
"""

from __future__ import annotations

from dhis2w_core.security_core.authorities import (
    AUTHORITY_CATEGORIES,
    AuthorityCategory,
    build_account_authorities,
    categorise_authorities,
    evaluate_account_authorities,
)
from dhis2w_core.security_core.findings import (
    HIGH_RISK_ROLE_CATEGORIES,
    SEVERITY_ORDER,
    AuditFinding,
    Severity,
    finding_sort_key,
    role_severity,
    severity_rank,
)
from dhis2w_core.security_core.guardrails import CONNECT_PATHS, GET_ALLOWLIST
from dhis2w_core.security_core.models import AccountAuthorities, CategoryMatch
from dhis2w_core.security_core.orchestrator import run_audit
from dhis2w_core.security_core.registry import (
    CANONICAL_CHECKS,
    IMPLEMENTED_CHECK_KEYS,
    BoundCheck,
    CheckSpec,
    canonical_keys,
    label_for,
    resolve_check_keys,
    select_keys,
)
from dhis2w_core.security_core.report.base import ProgressReporter, ReportRenderer, StreamingRenderer
from dhis2w_core.security_core.report.csv import CsvRenderer
from dhis2w_core.security_core.report.html import HtmlRenderer
from dhis2w_core.security_core.report.markdown import MarkdownRenderer
from dhis2w_core.security_core.report.model import (
    AuditReport,
    AuditSummary,
    CheckResult,
    CheckStatus,
    RunManifest,
)
from dhis2w_core.security_core.report.progress import PlainLogReporter, RichProgressReporter, make_reporter
from dhis2w_core.security_core.report.text import TextRenderer
from dhis2w_core.security_core.settings_audit import MIN_RECOMMENDED_PASSWORD_LENGTH, SettingsLike, evaluate_settings
from dhis2w_core.security_core.streaming import ReportWriter

__all__ = [
    "AUTHORITY_CATEGORIES",
    "CANONICAL_CHECKS",
    "CONNECT_PATHS",
    "GET_ALLOWLIST",
    "HIGH_RISK_ROLE_CATEGORIES",
    "IMPLEMENTED_CHECK_KEYS",
    "MIN_RECOMMENDED_PASSWORD_LENGTH",
    "SEVERITY_ORDER",
    "AccountAuthorities",
    "AuditFinding",
    "AuditReport",
    "AuditSummary",
    "AuthorityCategory",
    "BoundCheck",
    "CategoryMatch",
    "CheckResult",
    "CheckSpec",
    "CheckStatus",
    "CsvRenderer",
    "HtmlRenderer",
    "MarkdownRenderer",
    "PlainLogReporter",
    "ProgressReporter",
    "ReportRenderer",
    "ReportWriter",
    "RichProgressReporter",
    "RunManifest",
    "Severity",
    "SettingsLike",
    "StreamingRenderer",
    "TextRenderer",
    "build_account_authorities",
    "canonical_keys",
    "categorise_authorities",
    "evaluate_account_authorities",
    "evaluate_settings",
    "finding_sort_key",
    "label_for",
    "make_reporter",
    "resolve_check_keys",
    "role_severity",
    "run_audit",
    "select_keys",
    "severity_rank",
]
