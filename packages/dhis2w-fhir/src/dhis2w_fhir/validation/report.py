"""Markdown and CSV rendering of the FHIR-safety validation report, findings grouped by resource type."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.validation.schemas import FhirValidationReport, SeverityBreakdown, ValidationFinding

if TYPE_CHECKING:
    from datetime import datetime

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
    scope: str
    category: str
    object_label: str
    code: str
    message: str


class _ReportGroup(BaseModel):
    """The findings of one resource type, in report order, under their severity breakdown."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    breakdown: str
    rows: list[_ReportRow] = Field(default_factory=list)


def display_code(code: str | None) -> str:
    r"""Render a DHIS2 code for human eyes: `-` when absent, `(empty)` when blank, invisibles made visible.

    Control characters print as their escape (`BLUE\nBLUE` on one line, not two), and a value with
    a leading or trailing space is wrapped in double quotes so the edge space is on the page. Only
    the human-facing renderers call this: the CSV and the JSON finding carry the raw code.
    """
    if code is None:
        return "-"
    if not code:
        return "(empty)"
    escaped = code.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if code.startswith(" ") or code.endswith(" "):
        return f'"{escaped}"'
    return escaped


def render_validation_markdown(report: FhirValidationReport, target: str, generated_at: datetime) -> str:
    """Render the validation report as Markdown, findings grouped by resource type."""
    return _ENVIRONMENT.get_template("report.md.jinja").render(
        report=report,
        target=target,
        generated_at=generated_at.isoformat(timespec="seconds"),
        groups=_group_findings(report.findings),
    )


#: The CSV header row - one column per `ValidationFinding` field, in declaration order.
CSV_HEADER = ("severity", "scope", "category", "resource_type", "uid", "name", "code", "message")


def render_validation_csv(report: FhirValidationReport) -> str:
    """Render the validation report as CSV, one row per finding in report order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for finding in report.findings:
        writer.writerow(
            [
                finding.severity,
                finding.scope,
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
    grouped: defaultdict[str, list[ValidationFinding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.resource_type].append(finding)
    return [
        _ReportGroup(
            resource_type=resource_type,
            breakdown=SeverityBreakdown.of(grouped[resource_type]).line,
            rows=[_report_row(finding) for finding in grouped[resource_type]],
        )
        for resource_type in sorted(grouped)
    ]


def _report_row(finding: ValidationFinding) -> _ReportRow:
    """Project one finding onto a Markdown table row, its cells already made table-safe."""
    return _ReportRow(
        severity=finding.severity,
        scope=finding.scope,
        category=finding.category,
        object_label=f"{_table_cell(finding.name)} ({_table_cell(finding.uid)})",
        code=_code_cell(finding.code),
        message=_table_cell(finding.message),
    )


def _code_cell(code: str | None) -> str:
    """Render the code column: the human-facing display form, pipes escaped for the table."""
    return display_code(code).replace("|", "\\|")


def _table_cell(value: str) -> str:
    r"""Make one cell safe for a Markdown table: escape pipes, flatten line breaks to a space.

    Every cell carrying DHIS2 text goes through this - the name, the UID, and the message, which
    quotes the offending name back. A DHIS2 name may carry a literal newline (play 2.42 has
    category options such as `BLUE\nBLUE`) or a pipe, either of which would otherwise split the
    row and garble every column after it.
    """
    flattened = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return flattened.replace("|", "\\|")
