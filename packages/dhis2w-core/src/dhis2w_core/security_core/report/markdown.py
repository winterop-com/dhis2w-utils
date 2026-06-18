"""Markdown renderer for the security audit report (streamed live and re-rendered)."""

from __future__ import annotations

from dhis2w_core.security_core.findings import finding_sort_key
from dhis2w_core.security_core.guardrails import REPORT_GUARDRAIL_NOTE
from dhis2w_core.security_core.report.base import SingleFileRenderer
from dhis2w_core.security_core.report.model import AuditReport, AuditSummary, CheckResult, CheckStatus, RunManifest


class MarkdownRenderer(SingleFileRenderer):
    """Renders an audit report as GitHub-flavoured Markdown."""

    name = "markdown"
    suffix = "md"

    def render(self, report: AuditReport) -> str:
        """Render the whole report from manifest, results, and summary."""
        parts = [self.header(report.manifest)]
        parts.extend(self.section(result) for result in report.results)
        parts.append(self.footer(report.summary))
        return "".join(parts)

    def header(self, manifest: RunManifest) -> str:
        """Render the report preamble (target, versions, run identity)."""
        lines = [
            "# DHIS2 security audit",
            "",
            f"- Target: {manifest.target}",
            f"- Profile: {manifest.profile}",
            f"- DHIS2 version: {manifest.dhis2_version or 'unknown'}",
            f"- Scanner: {manifest.scanner_version}",
            f"- Started: {manifest.started_at}",
            "",
        ]
        return "\n".join(lines) + "\n"

    def section(self, result: CheckResult) -> str:
        """Render one check result, findings sorted most-urgent first."""
        lines = [f"## {result.label}", "", f"Status: {result.status.value}"]
        if result.note:
            lines.append(f"Note: {result.note}")
        lines.append("")
        if result.findings:
            lines.append("| Severity | Finding | Detail |")
            lines.append("| --- | --- | --- |")
            for finding in sorted(result.findings, key=finding_sort_key):
                title = finding.title.replace("|", "\\|")
                detail = finding.detail.replace("|", "\\|")
                lines.append(f"| {finding.severity.value} | {title} | {detail} |")
        elif result.status is CheckStatus.OK:
            lines.append("No findings.")
        lines.append("")
        return "\n".join(lines) + "\n"

    def footer(self, summary: AuditSummary) -> str:
        """Render the severity scorecard and the guardrail statement."""
        lines = [
            "## Summary",
            "",
            f"- CRITICAL: {summary.critical}",
            f"- HIGH: {summary.high}",
            f"- MEDIUM: {summary.medium}",
            f"- WARN: {summary.warn}",
            f"- INFO: {summary.info}",
            "",
            f"{summary.total_findings} finding(s) across {summary.checks_run} check(s) "
            f"({summary.checks_degraded} degraded, {summary.checks_error} error).",
            "",
            f"> {REPORT_GUARDRAIL_NOTE}",
            "",
        ]
        return "\n".join(lines) + "\n"
