"""Self-contained HTML renderer for the security audit report."""

from __future__ import annotations

from html import escape

from dhis2w_core.security_core.findings import Severity, finding_sort_key
from dhis2w_core.security_core.guardrails import REPORT_GUARDRAIL_NOTE
from dhis2w_core.security_core.report.model import AuditReport, CheckResult

_SEVERITY_CLASS = {
    Severity.CRITICAL: "sev-critical",
    Severity.HIGH: "sev-high",
    Severity.MEDIUM: "sev-medium",
    Severity.WARN: "sev-warn",
    Severity.INFO: "sev-info",
}

_STYLE = """\
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; color: #1b1b1b; }
h1 { margin-bottom: 0.2rem; }
h2 { margin-top: 1.6rem; }
.meta { color: #555; font-size: 0.9rem; margin-bottom: 1.2rem; }
.scorecard span { display: inline-block; padding: 0.2rem 0.6rem; margin-right: 0.4rem; border-radius: 4px; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; vertical-align: top; }
th { background: #f5f5f5; }
.sev-critical { color: #fff; background: #b00020; padding: 0.1rem 0.4rem; border-radius: 3px; }
.sev-high { color: #b00020; font-weight: bold; }
.sev-medium { color: #8a6d00; }
.sev-warn { color: #8a6d00; }
.sev-info { color: #555; }
.status { font-size: 0.85rem; color: #777; font-weight: normal; }
footer { margin-top: 2rem; color: #555; font-size: 0.85rem; }
"""


class HtmlRenderer:
    """Renders an audit report as a self-contained HTML document with inline CSS."""

    name = "html"
    suffix = "html"

    def render(self, report: AuditReport) -> str:
        """Render the whole report as a standalone HTML page."""
        manifest = report.manifest
        summary = report.summary
        parts = [
            "<!doctype html>",
            '<html lang="en"><head><meta charset="utf-8">',
            f"<title>DHIS2 security audit: {escape(manifest.target)}</title>",
            f"<style>{_STYLE}</style>",
            "</head><body>",
            "<h1>DHIS2 security audit</h1>",
            '<div class="meta">',
            f"Target: {escape(manifest.target)}<br>",
            f"Profile: {escape(manifest.profile)}<br>",
            f"DHIS2 version: {escape(manifest.dhis2_version or 'unknown')}<br>",
            f"Scanner: {escape(manifest.scanner_version)}<br>",
            f"Started: {escape(manifest.started_at)}",
            "</div>",
            '<div class="scorecard">',
            f'<span class="sev-critical">CRITICAL {summary.critical}</span>',
            f'<span class="sev-high">HIGH {summary.high}</span>',
            f'<span class="sev-medium">MEDIUM {summary.medium}</span>',
            f'<span class="sev-warn">WARN {summary.warn}</span>',
            f'<span class="sev-info">INFO {summary.info}</span>',
            "</div>",
        ]
        parts.extend(self._section(result) for result in report.results)
        parts.append(f"<footer>{escape(REPORT_GUARDRAIL_NOTE)}</footer>")
        parts.append("</body></html>")
        return "\n".join(parts)

    def _section(self, result: CheckResult) -> str:
        """Render one check result as a heading plus a findings table."""
        rows = []
        for finding in sorted(result.findings, key=finding_sort_key):
            css = _SEVERITY_CLASS[finding.severity]
            rows.append(
                f'<tr><td class="{css}">{escape(finding.severity.value)}</td>'
                f"<td>{escape(finding.title)}</td>"
                f"<td>{escape(finding.detail)}</td></tr>"
            )
        note = f' <span class="status">({escape(result.note)})</span>' if result.note else ""
        heading = f'<h2>{escape(result.label)} <span class="status">[{escape(result.status.value)}]</span>{note}</h2>'
        if not rows:
            return heading + "<p>No findings.</p>"
        table = (
            "<table><thead><tr><th>Severity</th><th>Finding</th><th>Detail</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        return heading + table
