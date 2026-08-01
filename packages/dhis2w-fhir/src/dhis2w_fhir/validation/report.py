"""Markdown and CSV rendering of the FHIR-safety validation report, findings grouped by resource type."""

from __future__ import annotations

import csv
import io
from collections import defaultdict

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.validation.schemas import FhirValidationReport, ValidationFinding

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.validation", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class _ReportRow(BaseModel):
    """One finding as a Markdown table row, pipes already escaped."""

    model_config = ConfigDict(frozen=True)

    severity: str
    category: str
    object_label: str
    code: str
    message: str


class _ReportGroup(BaseModel):
    """The findings of one resource type, in report order."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    rows: list[_ReportRow] = Field(default_factory=list)


def render_validation_markdown(report: FhirValidationReport, target: str) -> str:
    """Render the validation report as Markdown, findings grouped by resource type."""
    return _ENVIRONMENT.get_template("report.md.jinja").render(
        report=report,
        target=target,
        groups=_group_findings(report.findings),
    )


#: The CSV header row - one column per `ValidationFinding` field, in declaration order.
CSV_HEADER = ("severity", "category", "resource_type", "uid", "name", "code", "message")


def render_validation_csv(report: FhirValidationReport) -> str:
    """Render the validation report as CSV, one row per finding in report order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for finding in report.findings:
        writer.writerow(
            [
                finding.severity,
                finding.category,
                finding.resource_type,
                finding.uid,
                finding.name,
                finding.code or "",
                finding.message,
            ]
        )
    return buffer.getvalue()


def _group_findings(findings: list[ValidationFinding]) -> list[_ReportGroup]:
    """Bucket findings by resource type, sorted by type, each finding rendered as a table row."""
    grouped: defaultdict[str, list[_ReportRow]] = defaultdict(list)
    for finding in findings:
        grouped[finding.resource_type].append(
            _ReportRow(
                severity=finding.severity,
                category=finding.category,
                object_label=f"{_escape_pipes(finding.name)} ({finding.uid})",
                code=_escape_pipes(finding.code) if finding.code else "-",
                message=finding.message,
            )
        )
    return [_ReportGroup(resource_type=resource_type, rows=grouped[resource_type]) for resource_type in sorted(grouped)]


def _escape_pipes(value: str) -> str:
    """Escape the Markdown table cell separator so codes and names cannot break the table."""
    return value.replace("|", "\\|")
