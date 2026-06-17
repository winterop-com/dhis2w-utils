"""Progress reporters for the audit: an animated Rich display and a plain-log fallback."""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn

from dhis2w_core.security_core.findings import Severity
from dhis2w_core.security_core.report.base import ProgressReporter
from dhis2w_core.security_core.report.model import AuditSummary, CheckResult

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.WARN: "yellow",
    Severity.INFO: "dim",
}


def _result_summary(result: CheckResult) -> str:
    """One-line outcome for a completed check: status plus finding count and worst severity."""
    if not result.findings:
        return result.status.value
    worst = result.top_severity()
    worst_label = worst.value if worst is not None else "-"
    return f"{result.status.value}, {len(result.findings)} finding(s), worst {worst_label}"


def _scorecard(summary: AuditSummary) -> str:
    """One-line severity scorecard for the end of a run."""
    return (
        f"done: {summary.total_findings} finding(s); "
        f"CRITICAL={summary.critical} HIGH={summary.high} MEDIUM={summary.medium} "
        f"WARN={summary.warn} INFO={summary.info}"
    )


class PlainLogReporter:
    """Emits one plain line per completed step; for non-TTY output, --json, and tests."""

    def __init__(self, console: Console) -> None:
        """Store the stderr console used for plain output."""
        self._console = console

    def start(self, total: int) -> None:
        """Print the run header."""
        self._console.print(f"running {total} security check(s)", markup=False, highlight=False)

    def step(self, index: int, total: int, label: str) -> None:
        """Do nothing; the plain reporter logs on completion only."""

    def complete(self, index: int, total: int, result: CheckResult) -> None:
        """Print the completed-step line."""
        self._console.print(
            f"[{index}/{total}] {result.label}: {_result_summary(result)}", markup=False, highlight=False
        )

    def finish(self, summary: AuditSummary) -> None:
        """Print the final one-line scorecard."""
        self._console.print(_scorecard(summary), markup=False, highlight=False)


class RichProgressReporter:
    """Animates a spinner and a Step k of N counter, printing each completed step above it."""

    def __init__(self, console: Console) -> None:
        """Build the Rich progress display on the given (stderr) console."""
        self._console = console
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            console=console,
            transient=True,
        )
        self._task: TaskID | None = None

    def start(self, total: int) -> None:
        """Start the live display and add the single step-counter task."""
        self._progress.start()
        self._task = self._progress.add_task("starting", total=total)

    def step(self, index: int, total: int, label: str) -> None:
        """Update the spinner caption to the step about to run."""
        if self._task is not None:
            self._progress.update(self._task, description=f"Step {index}/{total}: {label}")

    def complete(self, index: int, total: int, result: CheckResult) -> None:
        """Advance the counter and print the completed-step line above the spinner."""
        if self._task is not None:
            self._progress.advance(self._task)
        worst = result.top_severity()
        style = _SEVERITY_STYLE[worst] if worst is not None else None
        self._console.print(
            f"[{index}/{total}] {result.label}: {_result_summary(result)}",
            style=style,
            markup=False,
            highlight=False,
        )

    def finish(self, summary: AuditSummary) -> None:
        """Stop the live display and print the final scorecard."""
        self._progress.stop()
        self._console.print(_scorecard(summary), markup=False, highlight=False)


def make_reporter(console: Console, *, animated: bool) -> ProgressReporter:
    """Pick the animated Rich reporter for a TTY, else the plain-log reporter."""
    if animated:
        return RichProgressReporter(console)
    return PlainLogReporter(console)
