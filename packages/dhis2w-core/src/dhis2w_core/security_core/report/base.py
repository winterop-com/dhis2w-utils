"""Protocols and shared base for security-audit report renderers and progress reporters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol

from dhis2w_core.security_core.report.model import AuditReport, AuditSummary, CheckResult, RunManifest


class ReportRenderer(Protocol):
    """Renders a complete audit report into one output format and writes it to a run folder."""

    name: str
    suffix: str

    def render(self, report: AuditReport) -> str:
        """Render the whole report as a single string."""
        ...

    def emit(self, folder: Path, report: AuditReport) -> None:
        """Write this format's output file or files into the run folder."""
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


class SingleFileRenderer(ABC):
    """Base for renderers whose entire output is one text file named report.<suffix>."""

    name: str
    suffix: str

    @abstractmethod
    def render(self, report: AuditReport) -> str:
        """Render the whole report as a single string."""

    def emit(self, folder: Path, report: AuditReport) -> None:
        """Write the rendered string to report.<suffix> in the run folder."""
        (folder / f"report.{self.suffix}").write_text(self.render(report), encoding="utf-8")


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

    def stop(self) -> None:
        """Tear down any live display without a summary; idempotent, called on every exit path."""
        ...
