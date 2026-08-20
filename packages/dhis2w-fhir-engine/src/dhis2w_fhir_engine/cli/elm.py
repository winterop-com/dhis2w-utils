"""Expression Logical Model loading, inspection, and evaluation commands."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ..engine.elm import ELMEvaluator, ELMSerializer
from ..engine.elm.exceptions import ELMError, ELMExecutionError, ELMValidationError
from .cql import format_result

app = typer.Typer(
    name="elm",
    help="Expression Logical Model loader and evaluator.",
    no_args_is_help=True,
)
console = Console()


def _require_existing_file(file: Path) -> None:
    """Exit with a message when a file does not exist."""
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)


def _load_library(evaluator: ELMEvaluator, file: Path) -> None:
    """Load an ELM library into an evaluator, exiting with a message on failure."""
    try:
        evaluator.load_file(file)
    except ELMError as error:
        rprint(f"[red]Error loading ELM:[/red] {error}")
        raise typer.Exit(1) from error


def _load_context_resource(data: Path | None) -> dict[str, Any] | None:
    """Load the optional JSON context resource."""
    if data is None:
        return None
    if not data.exists():
        rprint(f"[red]Error:[/red] Data file not found: {data}")
        raise typer.Exit(1)
    try:
        resource: dict[str, Any] = json.loads(data.read_text())
    except json.JSONDecodeError as error:
        rprint(f"[red]Error parsing JSON:[/red] {error}")
        raise typer.Exit(1) from error
    return resource


def _parse_parameters(parameter_arguments: list[str] | None) -> dict[str, Any] | None:
    """Turn repeated name=value options into a parameter mapping."""
    if not parameter_arguments:
        return None

    parameters: dict[str, Any] = {}
    for argument in parameter_arguments:
        if "=" not in argument:
            rprint(f"[red]Error:[/red] Invalid parameter: {argument} (expected name=value)")
            raise typer.Exit(1)
        name, raw_value = argument.split("=", 1)
        try:
            parameters[name] = json.loads(raw_value)
        except json.JSONDecodeError:
            parameters[name] = raw_value
    return parameters


def _library_heading(info: dict[str, Any]) -> str:
    """Build the heading line naming a library and its version."""
    version = info.get("version")
    return f"[bold blue]Library:[/bold blue] {info.get('id')}" + (f" v{version}" if version else "")


@app.command()
def load(
    file: Annotated[Path, typer.Argument(help="ELM JSON file to load and validate")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Also list every named entry")] = False,
) -> None:
    """Load an ELM JSON library and summarise what it declares."""
    _require_existing_file(file)

    evaluator = ELMEvaluator()
    try:
        library = evaluator.load_file(file)
    except ELMValidationError as error:
        rprint(f"[red]Validation error:[/red] {error}")
        raise typer.Exit(1) from error
    except ELMError as error:
        rprint(f"[red]Error loading ELM:[/red] {error}")
        raise typer.Exit(1) from error

    rprint(f"[green]OK[/green] Successfully loaded: {file}")
    rprint()

    info = evaluator.get_library_info(library)
    rprint(_library_heading(info))
    rprint()

    stats = Table(show_header=False, box=None)
    stats.add_column("Key", style="dim")
    stats.add_column("Value")
    stats.add_row("Definitions", str(len(info.get("definitions", []))))
    stats.add_row("Functions", str(len(info.get("functions", []))))
    stats.add_row("Parameters", str(len(info.get("parameters", []))))
    stats.add_row("Value Sets", str(len(info.get("valueSets", []))))
    stats.add_row("Code Systems", str(len(info.get("codeSystems", []))))
    stats.add_row("Codes", str(len(info.get("codes", []))))
    console.print(stats)

    if not verbose:
        return

    rprint()

    if info.get("usings"):
        rprint("[bold]Using:[/bold]")
        for using in info["usings"]:
            version = f" v{using['version']}" if using.get("version") else ""
            rprint(f"  [magenta]{using['localIdentifier']}[/magenta]{version}")

    if info.get("includes"):
        rprint("\n[bold]Includes:[/bold]")
        for include in info["includes"]:
            version = f" v{include['version']}" if include.get("version") else ""
            rprint(f"  [magenta]{include['localIdentifier']}[/magenta] ({include['path']}){version}")

    if info.get("definitions"):
        rprint("\n[bold]Definitions:[/bold]")
        for name in sorted(info["definitions"]):
            rprint(f"  [cyan]{name}[/cyan]")

    if info.get("functions"):
        rprint("\n[bold]Functions:[/bold]")
        for name in sorted(info["functions"]):
            rprint(f"  [cyan]{name}[/cyan]")

    if info.get("parameters"):
        rprint("\n[bold]Parameters:[/bold]")
        for name in info["parameters"]:
            rprint(f"  [yellow]{name}[/yellow]")

    if info.get("valueSets"):
        rprint("\n[bold]Value Sets:[/bold]")
        for name in info["valueSets"]:
            rprint(f"  [yellow]{name}[/yellow]")


@app.command("eval")
def evaluate(
    file: Annotated[Path, typer.Argument(help="ELM JSON file")],
    definition: Annotated[str, typer.Argument(help="Definition name to evaluate")],
    data: Annotated[Path | None, typer.Option("--data", "-d", help="JSON data file for context")] = None,
    parameter: Annotated[
        list[str] | None, typer.Option("--param", "-p", help="Parameter in name=value form, repeatable")
    ] = None,
) -> None:
    """Evaluate one definition from an ELM library."""
    _require_existing_file(file)

    evaluator = ELMEvaluator()
    _load_library(evaluator, file)

    resource = _load_context_resource(data)
    parameters = _parse_parameters(parameter)

    try:
        result = evaluator.evaluate_definition(definition, resource=resource, parameters=parameters)
    except ELMExecutionError as error:
        rprint(f"[red]Execution error:[/red] {error}")
        raise typer.Exit(1) from error
    except ELMError as error:
        rprint(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error

    rprint(format_result(result))


@app.command()
def run(
    file: Annotated[Path, typer.Argument(help="ELM JSON file to run")],
    data: Annotated[Path | None, typer.Option("--data", "-d", help="JSON data file for context")] = None,
    parameter: Annotated[
        list[str] | None, typer.Option("--param", "-p", help="Parameter in name=value form, repeatable")
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the results to this JSON file")] = None,
    include_private: Annotated[bool, typer.Option("--private", help="Include private definitions")] = False,
) -> None:
    """Run every definition in an ELM library."""
    _require_existing_file(file)

    evaluator = ELMEvaluator()
    try:
        library = evaluator.load_file(file)
    except ELMError as error:
        rprint(f"[red]Error loading ELM:[/red] {error}")
        raise typer.Exit(1) from error

    resource = _load_context_resource(data)
    parameters = _parse_parameters(parameter)

    rprint(_library_heading(evaluator.get_library_info(library)))
    rprint()

    try:
        results = evaluator.evaluate_all_definitions(
            resource=resource,
            parameters=parameters,
            include_private=include_private,
        )
    except ELMError as error:
        rprint(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error

    errors: dict[str, str] = results.pop("_errors", {})

    table = Table(title="Results", show_header=True, header_style="bold")
    table.add_column("Definition", style="cyan")
    table.add_column("Value")
    for name, value in sorted(results.items()):
        table.add_row(name, format_result(value))
    console.print(table)

    if errors:
        rprint()
        rprint("[red]Errors:[/red]")
        for name, message in errors.items():
            rprint(f"  [red]{name}:[/red] {message}")

    if output is not None:
        serializable: dict[str, Any] = {}
        for name, value in results.items():
            serializable[name] = value.model_dump() if hasattr(value, "model_dump") else value
        if errors:
            serializable["_errors"] = errors
        output.write_text(json.dumps(serializable, indent=2, default=str))
        rprint(f"\n[dim]Results written to {output}[/dim]")


@app.command()
def show(
    file: Annotated[Path, typer.Argument(help="ELM JSON file to display")],
) -> None:
    """Display an ELM JSON file with syntax highlighting."""
    _require_existing_file(file)

    try:
        document = json.loads(file.read_text())
    except json.JSONDecodeError as error:
        rprint(f"[red]Error:[/red] Invalid JSON: {error}")
        raise typer.Exit(1) from error

    syntax = Syntax(json.dumps(document, indent=2), "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=str(file), border_style="blue"))


@app.command()
def validate(
    files: Annotated[list[Path], typer.Argument(help="ELM JSON files to validate")],
) -> None:
    """Validate one or more ELM JSON files."""
    total = len(files)
    passed = 0
    failed = 0

    evaluator = ELMEvaluator()

    for file in files:
        if not file.exists():
            rprint(f"[yellow]MISSING[/yellow] File not found: {file}")
            failed += 1
            continue

        is_valid, errors = evaluator.validate(file)

        if is_valid:
            rprint(f"[green]OK[/green] {file}")
            passed += 1
        else:
            rprint(f"[red]FAIL[/red] {file}")
            for error in errors:
                rprint(f"    [red]*[/red] {error}")
            failed += 1

    rprint(f"\n[bold]Results:[/bold] {passed}/{total} passed, {failed}/{total} failed")

    if failed > 0:
        raise typer.Exit(1)


@app.command()
def convert(
    file: Annotated[Path, typer.Argument(help="CQL file to convert to ELM JSON")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the ELM JSON to this file")] = None,
    indent: Annotated[int, typer.Option("--indent", "-i", help="JSON indentation level")] = 2,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print only the JSON")] = False,
) -> None:
    """Convert a CQL file to ELM JSON."""
    _require_existing_file(file)

    try:
        elm_json = ELMSerializer().serialize_library_json(file.read_text(), indent)
    except Exception as error:
        if quiet:
            print(f"Error: {error}", file=sys.stderr)
        else:
            rprint(f"[red]Error converting to ELM:[/red] {error}")
        raise typer.Exit(1) from error

    if output is not None:
        output.write_text(elm_json)
        if not quiet:
            rprint(f"[green]OK[/green] Converted {file} -> {output}")
    elif quiet:
        print(elm_json)
    else:
        syntax = Syntax(elm_json, "json", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"ELM: {file}", border_style="blue"))
