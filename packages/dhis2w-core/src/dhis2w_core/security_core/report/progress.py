"""The audit's progress vocabulary over the shared `dhis2w_core.progress` reporters.

The reporters render pre-formatted strings, so the security-specific wording —
the per-check outcome line, the closing scorecard, and the severity-derived
Rich style — is formatted here and handed to them.
"""

from __future__ import annotations

from dhis2w_core.progress import PlainLogReporter as PlainLogReporter
from dhis2w_core.progress import ProgressReporter as ProgressReporter
from dhis2w_core.progress import RichProgressReporter as RichProgressReporter
from dhis2w_core.progress import make_reporter as make_reporter
from dhis2w_core.security_core.findings import Severity
from dhis2w_core.security_core.report.model import AuditSummary, CheckResult

#: What one step of an audit is called, for the plain reporter's run header.
AUDIT_ACTIVITY = "security check"

_SEVERITY_STYLE: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.WARN: "yellow",
    Severity.INFO: "dim",
}


def result_summary(result: CheckResult) -> str:
    """One-line outcome for a completed check: status plus finding count and worst severity."""
    if not result.findings:
        return result.status.value
    worst = result.top_severity()
    worst_label = worst.value if worst is not None else "-"
    return f"{result.status.value}, {len(result.findings)} finding(s), worst {worst_label}"


def result_style(result: CheckResult) -> str | None:
    """Rich style for a completed check's line, keyed off its worst severity."""
    worst = result.top_severity()
    if worst is None:
        return None
    return _SEVERITY_STYLE.get(worst)


def scorecard(summary: AuditSummary) -> str:
    """One-line severity scorecard for the end of a run."""
    tally = " ".join(f"{entry.severity.value}={entry.count}" for entry in summary.severity_counts())
    return f"done: {summary.total_findings} finding(s); {tally}"
