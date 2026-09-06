"""Read an IG publisher `qa.json` + `qa.txt` and report the counts, grouping errors by message shape."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.table import Table

console = Console()

#: Substitutions that turn one error line into the shape it shares with its siblings.
#: A resource id, a URL, a quoted literal and a number are what differ between two
#: reports of the same defect, so each is replaced by a placeholder before grouping.
SHAPE_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"'[^']*'"), "'<literal>'"),
    (re.compile(r'"[^"]*"'), '"<literal>"'),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\[[0-9]+\]"), "[<n>]"),
    (re.compile(r"\b[A-Za-z0-9]{11}\b"), "<id>"),
    (re.compile(r"\b[0-9]+\b"), "<n>"),
]


class QaReport(BaseModel):
    """The top level of an IG publisher `qa.json`: the tool version and the finding counts."""

    model_config = ConfigDict(extra="allow")

    tool: str = Field(default="unknown", description="The IG publisher release that wrote this report.")
    errs: int = Field(default=0, description="Error count; anything above zero fails a publisher check.")
    warnings: int = Field(default=0, description="Warning count.")
    hints: int = Field(default=0, description="Hint count.")


class ErrorFamily(BaseModel):
    """One group of error lines that share a message shape, with a verbatim example."""

    model_config = ConfigDict(frozen=True)

    shape: str = Field(description="The error line with ids, URLs, literals and numbers replaced.")
    count: int = Field(description="How many error lines carry this shape.")
    example: str = Field(description="One of those lines, verbatim.")


def read_report(qa_json: Path) -> QaReport:
    """Parse the publisher's `qa.json` into a report model."""
    return QaReport.model_validate(json.loads(qa_json.read_text(encoding="utf-8")))


def error_lines(qa_text: Path) -> list[str]:
    """Return every ERROR line of a publisher `qa.txt`, stripped of its marker and surrounding space."""
    if not qa_text.is_file():
        return []
    lines: list[str] = []
    for raw in qa_text.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if stripped.startswith("ERROR"):
            lines.append(stripped.removeprefix("ERROR").lstrip(": ").strip() or stripped)
    return lines


def message_shape(line: str) -> str:
    """Reduce one error line to the shape it shares with every other report of the same defect."""
    shape = line
    for pattern, placeholder in SHAPE_SUBSTITUTIONS:
        shape = pattern.sub(placeholder, shape)
    return shape


def error_families(lines: list[str]) -> list[ErrorFamily]:
    """Group error lines by message shape, most populous family first."""
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for line in lines:
        shape = message_shape(line)
        counts[shape] += 1
        examples.setdefault(shape, line)
    return [ErrorFamily(shape=shape, count=count, example=examples[shape]) for shape, count in counts.most_common()]


def render(report: QaReport, families: list[ErrorFamily], limit: int) -> None:
    """Print the publisher version, the counts, and — when there are errors — the families behind them."""
    console.print(f"IG publisher: [bold]{report.tool}[/bold]")
    console.print(f"errors: [bold]{report.errs}[/bold]  warnings: {report.warnings}  hints: {report.hints}")
    if not families:
        return
    table = Table(title=f"error families ({len(families)} shapes, showing up to {limit})")
    table.add_column("count", justify="right")
    table.add_column("shape", overflow="fold")
    table.add_column("example", overflow="fold")
    for family in families[:limit]:
        table.add_row(str(family.count), family.shape, family.example)
    console.print(table)


def main(
    qa: Annotated[Path, typer.Option(help="Path to the publisher's qa.json.")] = Path("ig/output/qa.json"),
    limit: Annotated[int, typer.Option(help="How many error families to print.")] = 25,
) -> None:
    """Summarise an IG publisher QA report and exit 1 when it carries any error."""
    if not qa.is_file():
        console.print(f"[red]no QA report at {qa}[/red] - the publisher did not get far enough to write one")
        raise typer.Exit(code=1)
    report = read_report(qa)
    families = error_families(error_lines(qa.with_suffix(".txt"))) if report.errs else []
    render(report, families, limit)
    if report.errs:
        console.print(f"[red]{report.errs} error(s) from IG publisher {report.tool}[/red]")
        raise typer.Exit(code=1)
    console.print("[green]clean build[/green]")


if __name__ == "__main__":
    typer.run(main)
