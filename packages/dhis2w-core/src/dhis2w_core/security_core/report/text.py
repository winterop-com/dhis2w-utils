"""Plain-text renderer for the security audit report."""

from __future__ import annotations

from dhis2w_core.security_core.findings import finding_sort_key
from dhis2w_core.security_core.report.base import SingleFileRenderer
from dhis2w_core.security_core.report.model import AuditReport


class TextRenderer(SingleFileRenderer):
    """Renders an audit report as plain text for terminals and pipes."""

    name = "text"
    suffix = "txt"

    def render(self, report: AuditReport) -> str:
        """Render the whole report as indented plain text."""
        manifest = report.manifest
        lines = [
            "DHIS2 SECURITY AUDIT",
            f"Target:   {manifest.target}",
            f"Profile:  {manifest.profile}",
            f"Version:  {manifest.dhis2_version or 'unknown'}",
            f"Scanner:  {manifest.scanner_version}",
            f"Started:  {manifest.started_at}",
            "",
        ]
        for result in report.results:
            lines.append(f"[{result.status.value.upper()}] {result.label}")
            if result.note:
                lines.append(f"    note: {result.note}")
            for finding in sorted(result.findings, key=finding_sort_key):
                lines.append(f"    {finding.severity.value:>8}  {finding.title}")
                lines.append(f"              {finding.detail}")
            if not result.findings:
                lines.append("    no findings")
            lines.append("")
        summary = report.summary
        lines.append("SUMMARY")
        tally = " ".join(f"{entry.severity.value}={entry.count}" for entry in summary.severity_counts())
        lines.append(f"    {tally}")
        lines.append(f"    {summary.total_findings} finding(s) across {summary.checks_run} check(s)")
        lines.append("")
        return "\n".join(lines) + "\n"
