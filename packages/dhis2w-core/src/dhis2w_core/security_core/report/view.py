"""View-models projecting an AuditReport into the window.__REPORT__ shape the HTML report consumes.

The redesigned HTML report is data-driven: a fixed template and runtime read every value from a
`window.__REPORT__` object emitted into `report-data.js`. These models mirror that object exactly,
and `build_report_view` folds the flat per-finding rows into the sections, severity-tally groups,
and collapsible item lists the template renders. Findings carrying the same `group_key` within one
check fold into a single collapsible group; findings with no `group_key` each render as one row.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_core.security_core.findings import AuditFinding, Severity, severity_rank
from dhis2w_core.security_core.guardrails import REPORT_GUARDRAIL_NOTE
from dhis2w_core.security_core.report.model import AuditReport, CheckResult


class ReportMeta(BaseModel):
    """Run identity shown in the report hero and meta strip."""

    model_config = ConfigDict(frozen=True)

    target: str
    profile: str
    version: str
    scanner: str
    started: str


class Scorecard(BaseModel):
    """Verbatim severity totals shown in the hero scorecard (uppercase JSON keys)."""

    model_config = ConfigDict(frozen=True)

    critical: int = Field(0, serialization_alias="CRITICAL")
    high: int = Field(0, serialization_alias="HIGH")
    medium: int = Field(0, serialization_alias="MEDIUM")
    warn: int = Field(0, serialization_alias="WARN")
    info: int = Field(0, serialization_alias="INFO")


class ItemView(BaseModel):
    """One entry in a collapsible group: an account name and an optional last-seen stamp."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    last: str | None = None


class GroupView(BaseModel):
    """One finding row: a single static row when count is 1, else a collapsible list of items."""

    model_config = ConfigDict(frozen=True)

    finding: str
    sev: Severity
    count: int
    sample_detail: str = Field(serialization_alias="sampleDetail")
    items: list[ItemView] = []


class SectionView(BaseModel):
    """One audit check rendered as a section: its label, status pill, and finding groups."""

    model_config = ConfigDict(frozen=True)

    title: str
    status: list[str]
    groups: list[GroupView] = []


class ReportView(BaseModel):
    """The full window.__REPORT__ object: meta, scorecard, sections, and the guardrail footer."""

    model_config = ConfigDict(frozen=True)

    meta: ReportMeta
    scorecard: Scorecard
    sections: list[SectionView] = []
    guardrail: str = REPORT_GUARDRAIL_NOTE

    def to_report_data_js(self) -> str:
        """Render the assignable JavaScript payload written to report-data.js."""
        return f"window.__REPORT__ = {self.model_dump_json(by_alias=True)};\n"


def build_report_view(report: AuditReport) -> ReportView:
    """Project an AuditReport into the window.__REPORT__ view, folding findings into groups."""
    manifest = report.manifest
    summary = report.summary
    meta = ReportMeta(
        target=manifest.target,
        profile=manifest.profile,
        version=manifest.dhis2_version or "unknown",
        scanner=manifest.scanner_version,
        started=manifest.started_at,
    )
    scorecard = Scorecard(
        critical=summary.critical,
        high=summary.high,
        medium=summary.medium,
        warn=summary.warn,
        info=summary.info,
    )
    sections = [_build_section(result) for result in report.results]
    return ReportView(meta=meta, scorecard=scorecard, sections=sections)


def _build_section(result: CheckResult) -> SectionView:
    """Build one section from a check result: status pill, optional note, and grouped findings."""
    status = [f"[{result.status.value}]"]
    if result.note:
        status.append(f"({result.note})")
    return SectionView(title=result.label, status=status, groups=_build_groups(result.findings))


def _build_groups(findings: list[AuditFinding]) -> list[GroupView]:
    """Fold findings sharing a (group_key, severity) into one group; group_key=None stays one row each.

    Folding keys on severity as well as group_key so every group is severity-homogeneous. That keeps
    the hero scorecard (which counts each finding under its own severity) equal to the runtime's
    per-severity sum of group counts, regardless of how a check assigns group_key. Groups sort
    most-urgent first, then by finding title.
    """
    buckets: list[list[AuditFinding]] = []
    index_by_key: dict[tuple[str, Severity], int] = {}
    for finding in findings:
        key = finding.group_key
        if key is None:
            buckets.append([finding])
            continue
        bucket_key = (key, finding.severity)
        existing = index_by_key.get(bucket_key)
        if existing is None:
            index_by_key[bucket_key] = len(buckets)
            buckets.append([finding])
        else:
            buckets[existing].append(finding)
    groups = [_group_from_bucket(bucket) for bucket in buckets]
    groups.sort(key=lambda group: (severity_rank(group.sev), group.finding.lower()))
    return groups


def _group_from_bucket(bucket: list[AuditFinding]) -> GroupView:
    """Build one group from its folded findings: the head finding plus per-item entries when many."""
    head = bucket[0]
    count = len(bucket)
    items = (
        [ItemView(name=finding.subject, last=(finding.evidence or {}).get("last")) for finding in bucket]
        if count > 1
        else []
    )
    return GroupView(finding=head.title, sev=head.severity, count=count, sample_detail=head.detail, items=items)
