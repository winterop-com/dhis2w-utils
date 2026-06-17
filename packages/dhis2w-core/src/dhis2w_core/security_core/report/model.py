"""Typed report models for the security audit: results, manifest, summary, report."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import (
    SEVERITY_ORDER,
    AuditFinding,
    Severity,
    severity_rank,
)


class CheckStatus(StrEnum):
    """How one audit check's run went."""

    OK = "ok"
    SKIPPED = "skipped"
    DEGRADED = "degraded"
    ERROR = "error"


class CheckResult(BaseModel):
    """Result of one audit check: its findings plus how the run went."""

    model_config = ConfigDict(frozen=True)

    check: str
    label: str
    status: CheckStatus
    findings: list[AuditFinding] = []
    note: str | None = None

    def top_severity(self) -> Severity | None:
        """Return the most urgent severity among the findings, or None when clean."""
        if not self.findings:
            return None
        return min((finding.severity for finding in self.findings), key=severity_rank)


class RunManifest(BaseModel):
    """Identity of one audit run: target, versions, ordered checks, completion flag."""

    model_config = ConfigDict(frozen=True)

    target: str
    profile: str
    scanner_version: str
    started_at: str
    dhis2_version: str | None = None
    check_order: list[str] = []
    completed: bool = False


class AuditSummary(BaseModel):
    """Severity and status rollup across every check result."""

    model_config = ConfigDict(frozen=True)

    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    warn: int = 0
    info: int = 0
    checks_run: int = 0
    checks_ok: int = 0
    checks_degraded: int = 0
    checks_error: int = 0
    checks_skipped: int = 0

    @classmethod
    def from_results(cls, results: list[CheckResult]) -> AuditSummary:
        """Roll up severity counts and per-status check counts from the results."""
        counts: dict[Severity, int] = dict.fromkeys(Severity, 0)
        ok = degraded = error = skipped = 0
        for result in results:
            if result.status is CheckStatus.OK:
                ok += 1
            elif result.status is CheckStatus.DEGRADED:
                degraded += 1
            elif result.status is CheckStatus.ERROR:
                error += 1
            elif result.status is CheckStatus.SKIPPED:
                skipped += 1
            for finding in result.findings:
                counts[finding.severity] += 1
        return cls(
            total_findings=sum(counts.values()),
            critical=counts[Severity.CRITICAL],
            high=counts[Severity.HIGH],
            medium=counts[Severity.MEDIUM],
            warn=counts[Severity.WARN],
            info=counts[Severity.INFO],
            checks_run=len(results),
            checks_ok=ok,
            checks_degraded=degraded,
            checks_error=error,
            checks_skipped=skipped,
        )

    @property
    def worst(self) -> Severity | None:
        """Most urgent severity that occurred at least once, or None when clean."""
        count_by_severity = {
            Severity.CRITICAL: self.critical,
            Severity.HIGH: self.high,
            Severity.MEDIUM: self.medium,
            Severity.WARN: self.warn,
            Severity.INFO: self.info,
        }
        for severity in SEVERITY_ORDER:
            if count_by_severity[severity] > 0:
                return severity
        return None


class AuditReport(BaseModel):
    """Full audit report: manifest, every check result, and the rollup summary."""

    model_config = ConfigDict(frozen=True)

    manifest: RunManifest
    results: list[CheckResult] = []
    summary: AuditSummary
