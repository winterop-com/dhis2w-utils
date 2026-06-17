"""Protocols for security-audit report renderers and progress reporters."""

from __future__ import annotations

from typing import Protocol

from dhis2w_core.security_core.report.model import AuditReport, AuditSummary, CheckResult, RunManifest


class ReportRenderer(Protocol):
    """Renders a complete audit report into one output format."""

    name: str
    suffix: str

    def render(self, report: AuditReport) -> str:
        """Render the whole report as a single string."""
        ...


class StreamingRenderer(ReportRenderer, Protocol):
    """A report renderer that can also emit header/section/footer incrementally."""

    def header(self, manifest: RunManifest) -> str:
        """Render the report preamble shown before any check runs."""
        ...

    def section(self, result: CheckResult) -> str:
        """Render one check result as it completes."""
        ...

    def footer(self, summary: AuditSummary) -> str:
        """Render the closing summary once every check has run."""
        ...


class ProgressReporter(Protocol):
    """Receives step-by-step progress so the CLI can animate a live display."""

    def start(self, total: int) -> None:
        """Announce the total number of steps before the first one runs."""
        ...

    def step(self, index: int, total: int, label: str) -> None:
        """Announce that step `index` of `total` is starting."""
        ...

    def complete(self, index: int, total: int, result: CheckResult) -> None:
        """Announce that step `index` finished with `result`."""
        ...

    def finish(self, summary: AuditSummary) -> None:
        """Announce that the run finished, with the final summary."""
        ...
