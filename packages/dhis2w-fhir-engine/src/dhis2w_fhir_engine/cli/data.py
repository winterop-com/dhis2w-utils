"""What a `--data` file supplies to an evaluation, and the one rule that decides which."""

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict
from rich import print as rprint

from ..r4 import BundleDataSource

DATA_OPTION_HELP = "JSON file: a Bundle becomes the data source retrieves read, any other resource is the context"
"""The `--data` help line, stated once so every command that takes the option says the same rule."""

MEASURE_DATA_OPTION_HELP = (
    "JSON file: a Bundle supplies both the population and the data source, a Patient is one person"
)
"""The `--data` help line for `cql measure`, where a Bundle also names who is evaluated."""


class EvaluationData(BaseModel):
    """The data source and the context resource a `--data` file resolves to."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data_source: BundleDataSource | None = None
    """The Bundle behind `--data`, indexed by resource type, or nothing when the file held one resource."""

    context_resource: dict[str, Any] | None = None
    """The single resource behind `--data`, or nothing when the file held a Bundle."""

    document: dict[str, Any] | None = None
    """The whole document the file held, for a command that reads the Bundle's entries itself."""


def load_evaluation_data(file: Path | None, label: str = "Data") -> EvaluationData:
    """Read a `--data` file: a Bundle becomes the data source, any other resource becomes the context."""
    document = load_json_file(file, label)
    if document is None:
        return EvaluationData()
    if document.get("resourceType") == "Bundle":
        return EvaluationData(data_source=BundleDataSource(document), document=document)
    return EvaluationData(context_resource=document, document=document)


def load_json_file(file: Path | None, label: str = "Data") -> dict[str, Any] | None:
    """Load a JSON document from an optional path."""
    if file is None:
        return None
    if not file.exists():
        rprint(f"[red]Error:[/red] {label} file not found: {file}")
        raise typer.Exit(1)
    try:
        loaded: dict[str, Any] = json.loads(file.read_text())
    except json.JSONDecodeError as error:
        rprint(f"[red]Error parsing JSON:[/red] {error}")
        raise typer.Exit(1) from error
    return loaded
