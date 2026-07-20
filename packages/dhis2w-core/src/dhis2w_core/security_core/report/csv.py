"""CSV renderer for the security audit report: one row per finding."""

from __future__ import annotations

import csv
import io

from dhis2w_core.security_core.findings import finding_sort_key
from dhis2w_core.security_core.report.base import SingleFileRenderer
from dhis2w_core.security_core.report.model import AuditReport

_COLUMNS = ("check", "severity", "title", "detail", "subject", "evidence", "status")


def _flatten_evidence(evidence: dict[str, str] | None) -> str:
    """Flatten an evidence map into a `key=value; key=value` string for one CSV cell."""
    if not evidence:
        return ""
    return "; ".join(f"{key}={value}" for key, value in evidence.items())


class CsvRenderer(SingleFileRenderer):
    """Renders an audit report as CSV, one row per finding plus a row for clean checks."""

    name = "csv"
    suffix = "csv"

    def render(self, report: AuditReport) -> str:
        """Render every finding as a CSV row; checks with no findings still appear once."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_COLUMNS)
        for result in report.results:
            if result.findings:
                for finding in sorted(result.findings, key=finding_sort_key):
                    writer.writerow(
                        [
                            finding.check,
                            finding.severity.value,
                            finding.title,
                            finding.detail,
                            finding.subject or "",
                            _flatten_evidence(finding.evidence),
                            result.status.value,
                        ]
                    )
            else:
                writer.writerow([result.check, "", "", result.note or "", "", "", result.status.value])
        return buffer.getvalue()
