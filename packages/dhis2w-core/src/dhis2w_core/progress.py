"""The shared step-progress reporters every long-running CLI command renders through.

A transient spinner on `STDERR_CONSOLE` when animated, plain `[k/N]` lines
otherwise. `make_reporter` picks between the two, `animated_progress` decides
whether animation is appropriate for the current invocation.

The reporters take pre-formatted strings: the caller owns what a step's outcome
reads like and which Rich style it carries, so no domain vocabulary leaks in
here.
"""

from __future__ import annotations

import sys
from typing import Protocol

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn

from dhis2w_core.cli_output import is_json_output


class ProgressReporter(Protocol):
    """Receives step-by-step progress so the CLI can animate a live display."""

    def start(self, total: int, *, activity: str = "step") -> None:
        """Announce the total number of steps, and what one step is called, before the first runs."""
        ...

    def step(self, index: int, total: int, label: str) -> None:
        """Announce that step `index` of `total`, named `label`, is starting."""
        ...

    def complete(self, index: int, total: int, label: str, summary: str, *, style: str | None = None) -> None:
        """Announce that step `index` finished, with a one-line `summary` in an optional Rich `style`."""
        ...

    def finish(self, summary: str) -> None:
        """Announce that the run finished, with the closing one-line summary."""
        ...

    def stop(self) -> None:
        """Tear down any live display without a summary; idempotent, called on every exit path."""
        ...


class PlainLogReporter:
    """Emits one plain line per completed step; for non-TTY output, --json, and tests."""

    def __init__(self, console: Console) -> None:
        """Store the stderr console used for plain output."""
        self._console = console

    def start(self, total: int, *, activity: str = "step") -> None:
        """Print the run header."""
        self._console.print(f"running {total} {activity}(s)", markup=False, highlight=False)

    def step(self, index: int, total: int, label: str) -> None:
        """Do nothing; the plain reporter logs on completion only."""

    def complete(self, index: int, total: int, label: str, summary: str, *, style: str | None = None) -> None:
        """Print the completed-step line, unstyled — plain output carries no colour."""
        self._console.print(f"[{index}/{total}] {label}: {summary}", markup=False, highlight=False)

    def finish(self, summary: str) -> None:
        """Print the final one-line summary."""
        self._console.print(summary, markup=False, highlight=False)

    def stop(self) -> None:
        """Do nothing; the plain reporter holds no live display to tear down."""


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

    def start(self, total: int, *, activity: str = "step") -> None:
        """Start the live display and add the single step-counter task.

        `activity` names one step for the plain reporter's header; the spinner
        caption names each step as it runs, so this display has no use for it.
        """
        self._progress.start()
        self._task = self._progress.add_task("starting", total=total)

    def step(self, index: int, total: int, label: str) -> None:
        """Update the spinner caption to the step about to run."""
        if self._task is not None:
            self._progress.update(self._task, description=f"Step {index}/{total}: {label}")

    def complete(self, index: int, total: int, label: str, summary: str, *, style: str | None = None) -> None:
        """Advance the counter and print the completed-step line above the spinner."""
        if self._task is not None:
            self._progress.advance(self._task)
        self._console.print(
            f"[{index}/{total}] {label}: {summary}",
            style=style,
            markup=False,
            highlight=False,
        )

    def finish(self, summary: str) -> None:
        """Stop the live display and print the final summary."""
        self._progress.stop()
        self._console.print(summary, markup=False, highlight=False)

    def stop(self) -> None:
        """Stop the live display without printing a summary; Rich's stop is idempotent.

        The orchestrator calls this on every exit path (in its `finally`) so a writer error cannot
        leave the Live display's refresh thread running and the terminal corrupted; `finish` still
        owns the success-path summary.
        """
        self._progress.stop()


def make_reporter(console: Console, *, animated: bool) -> ProgressReporter:
    """Pick the animated Rich reporter for a TTY, else the plain-log reporter."""
    if animated:
        return RichProgressReporter(console)
    return PlainLogReporter(console)


def animated_progress(enabled: bool) -> bool:
    """Whether a live progress display should animate: the flag, a stderr TTY, and human output."""
    return enabled and sys.stderr.isatty() and not is_json_output()
