"""Version-invariant security domain logic shared by every security plugin tree.

The authority taxonomy, severity model, guardrail contract, audit orchestration,
and report rendering are security opinions, not version concerns: they live once
here and are consumed by the thin per-tree plugin shims under
`dhis2w_core.v{41,42,43}.plugins.security`. Only genuinely version-divergent wire
extraction lives per tree.
"""

from __future__ import annotations

from dhis2w_core.security_core.apps import HubApp, InstalledApp, evaluate_apps
from dhis2w_core.security_core.authorities import (
    AUTHORITY_CATEGORIES,
    AuthorityCategory,
    build_account_authorities,
    categorise_authorities,
    evaluate_account_authorities,
)
from dhis2w_core.security_core.credentials import (
    CredentialProbeResult,
    ProbeOutcome,
    classify_probe_status,
    evaluate_credential_probe,
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
from dhis2w_core.security_core.guardrails import (
    CONNECT_PATHS,
    CREDENTIAL_PROBE_PATHS,
    DEFAULT_PROBE_PASSWORD,
    DEFAULT_PROBE_USERNAME,
    GET_ALLOWLIST,
    MAX_PROBE_ATTEMPTS,
    REPORT_GUARDRAIL_NOTE,
)
from dhis2w_core.security_core.hygiene import (
    SEED_USERNAME,
    TwoFactorSource,
    TwoFactorSummary,
    UserHygiene,
    build_user_hygiene,
    evaluate_hygiene,
    evaluate_two_factor_from_endpoint,
    evaluate_two_factor_from_user_field,
)
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
from dhis2w_core.security_core.releases import RELEASES_FEED_URL, ReleaseFeed, ReleaseLine, fetch_release_feed
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
from dhis2w_core.security_core.report.view import (
    GroupView,
    ItemView,
    ReportMeta,
    ReportView,
    Scorecard,
    SectionView,
    build_report_view,
)
from dhis2w_core.security_core.roles import RoleAudit, build_role_audit, evaluate_roles
from dhis2w_core.security_core.settings_audit import MIN_RECOMMENDED_PASSWORD_LENGTH, SettingsLike, evaluate_settings
from dhis2w_core.security_core.streaming import ReportWriter
from dhis2w_core.security_core.versions import (
    ADVISORY_PATCH_FLOOR,
    ADVISORY_PATCH_FLOOR_REVIEWED,
    MIN_SUPPORTED_LINE,
    AdvisoryFloor,
    ParsedVersion,
    evaluate_version,
    parse_dhis2_version,
)

__all__ = [
    "ADVISORY_PATCH_FLOOR",
    "ADVISORY_PATCH_FLOOR_REVIEWED",
    "AUTHORITY_CATEGORIES",
    "CANONICAL_CHECKS",
    "CONNECT_PATHS",
    "CREDENTIAL_PROBE_PATHS",
    "DEFAULT_PROBE_PASSWORD",
    "DEFAULT_PROBE_USERNAME",
    "GET_ALLOWLIST",
    "HIGH_RISK_ROLE_CATEGORIES",
    "IMPLEMENTED_CHECK_KEYS",
    "MAX_PROBE_ATTEMPTS",
    "MIN_RECOMMENDED_PASSWORD_LENGTH",
    "MIN_SUPPORTED_LINE",
    "RELEASES_FEED_URL",
    "REPORT_GUARDRAIL_NOTE",
    "SEED_USERNAME",
    "SEVERITY_ORDER",
    "AccountAuthorities",
    "AdvisoryFloor",
    "AuditFinding",
    "AuditReport",
    "AuditSummary",
    "AuthorityCategory",
    "BoundCheck",
    "CategoryMatch",
    "CheckResult",
    "CheckSpec",
    "CheckStatus",
    "CredentialProbeResult",
    "CsvRenderer",
    "GroupView",
    "HtmlRenderer",
    "HubApp",
    "InstalledApp",
    "ItemView",
    "MarkdownRenderer",
    "ParsedVersion",
    "PlainLogReporter",
    "ProbeOutcome",
    "ProgressReporter",
    "ReleaseFeed",
    "ReleaseLine",
    "ReportMeta",
    "ReportRenderer",
    "ReportView",
    "ReportWriter",
    "RichProgressReporter",
    "RoleAudit",
    "RunManifest",
    "Scorecard",
    "SectionView",
    "Severity",
    "SettingsLike",
    "StreamingRenderer",
    "TextRenderer",
    "TwoFactorSource",
    "TwoFactorSummary",
    "UserHygiene",
    "build_account_authorities",
    "build_report_view",
    "build_role_audit",
    "build_user_hygiene",
    "canonical_keys",
    "categorise_authorities",
    "classify_probe_status",
    "evaluate_account_authorities",
    "evaluate_apps",
    "evaluate_credential_probe",
    "evaluate_hygiene",
    "evaluate_roles",
    "evaluate_settings",
    "evaluate_two_factor_from_endpoint",
    "evaluate_two_factor_from_user_field",
    "evaluate_version",
    "fetch_release_feed",
    "finding_sort_key",
    "label_for",
    "make_reporter",
    "parse_dhis2_version",
    "resolve_check_keys",
    "role_severity",
    "run_audit",
    "select_keys",
    "severity_rank",
]
