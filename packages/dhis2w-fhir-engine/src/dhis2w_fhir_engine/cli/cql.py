"""CQL library parsing, inspection, evaluation, and measure commands."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from antlr4 import CommonTokenStream, InputStream  # type: ignore[import-untyped]
from antlr4.error.ErrorListener import ErrorListener  # type: ignore[import-untyped]
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from ..engine.cql import CQLEvaluator
from ..engine.exceptions import CQLError
from ..generated.cql.cqlLexer import cqlLexer
from ..generated.cql.cqlParser import cqlParser
from ..r4 import MeasureEvaluator
from .data import DATA_OPTION_HELP, MEASURE_DATA_OPTION_HELP, load_evaluation_data

app = typer.Typer(
    name="cql",
    help="Clinical Quality Language parser and evaluator.",
    no_args_is_help=True,
)
console = Console()

DEFINITION_RULE_LABELS = {
    "libraryDefinition": ("Library", "blue"),
    "usingDefinition": ("Using", "magenta"),
    "valuesetDefinition": ("Valueset", "yellow"),
    "codesystemDefinition": ("Codesystem", "yellow"),
    "expressionDefinition": ("Define", "green"),
    "functionDefinition": ("Function", "cyan"),
    "contextDefinition": ("Context", "red"),
}


class CQLErrorListener(ErrorListener):
    """Collect the syntax errors the CQL parser reports."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def syntaxError(
        self,
        recognizer: object,
        offendingSymbol: object,
        line: int,
        column: int,
        msg: str,
        e: object,
    ) -> None:
        """Record one syntax error."""
        self.errors.append(f"Line {line}:{column} - {msg}")


def parse_cql(text: str) -> tuple[cqlParser.LibraryContext, list[str]]:
    """Parse CQL text and return the parse tree together with any syntax errors."""
    parser = _make_parser(text)
    error_listener = CQLErrorListener()
    parser.removeErrorListeners()
    parser.addErrorListener(error_listener)

    parse_tree = parser.library()
    return parse_tree, error_listener.errors


def build_parse_tree(node: Any, tree: Tree, parser: Any, depth: int = 0, max_depth: int = 50) -> None:
    """Fill a rich tree with the rule names and literals of a CQL parse tree."""
    if depth > max_depth:
        tree.add("[dim]...[/dim]")
        return

    children = getattr(node, "children", None)
    if not children:
        return

    for child in children:
        if hasattr(child, "getRuleIndex"):
            rule_name = parser.ruleNames[child.getRuleIndex()]
            branch = tree.add(f"[cyan]{rule_name}[/cyan]")
            build_parse_tree(child, branch, parser, depth + 1, max_depth)
        elif hasattr(child, "getText"):
            text = child.getText()
            if text.strip():
                tree.add(f"[green]'{text}'[/green]")


def format_result(value: Any) -> str:
    """Render an evaluation result for the terminal."""
    if value is None:
        return "[dim]null[/dim]"
    if isinstance(value, bool):
        return f"[cyan]{value}[/cyan]"
    if isinstance(value, (int, float)):
        return f"[green]{value}[/green]"
    if isinstance(value, str):
        return f"[yellow]'{value}'[/yellow]"
    if isinstance(value, list):
        if not value:
            return "[dim]{}[/dim]"
        items = ", ".join(format_result(item) for item in value)
        return f"{{ {items} }}"
    if isinstance(value, dict):
        entries = ", ".join(f"{key}: {format_result(item)}" for key, item in value.items())
        return f"{{ {entries} }}"
    return str(value)


def _make_parser(text: str) -> cqlParser:
    """Build a CQL parser over the given source text."""
    input_stream = InputStream(text)
    lexer = cqlLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    return cqlParser(token_stream)


def _print_errors(errors: list[str], heading: str = "Parse errors:") -> None:
    """Print a list of parse errors."""
    rprint(f"[red]{heading}[/red]")
    for error in errors:
        rprint(f"  [red]*[/red] {error}")


def _read_existing_file(file: Path) -> str:
    """Read a file, exiting with a message when it does not exist."""
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)
    return file.read_text()


def _bind_repl_data(evaluator: CQLEvaluator, file: Path) -> dict[str, Any] | None:
    """Point the session at a `--data` file and report which half of the rule it took."""
    evaluation_data = load_evaluation_data(file)
    evaluator.data_source = evaluation_data.data_source

    rprint(f"[green]OK[/green] Loaded data: {file}")
    if evaluation_data.data_source is not None:
        rprint("  Bundle, read as the data source for retrieves")
    elif evaluation_data.context_resource is not None:
        rprint(f"  Resource type: {evaluation_data.context_resource.get('resourceType', 'unknown')}")

    return evaluation_data.context_resource


def _library_heading(name: str, version: str | None) -> str:
    """Build the heading line naming a library and its version."""
    return f"[bold blue]Library:[/bold blue] {name}" + (f" v{version}" if version else "")


@app.command()
def parse(
    file: Annotated[Path, typer.Argument(help="CQL file to parse")],
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Only show errors")] = False,
) -> None:
    """Parse a CQL file and report any syntax errors."""
    _, errors = parse_cql(_read_existing_file(file))

    if errors:
        _print_errors(errors, f"Parse errors in {file}:")
        raise typer.Exit(1)

    if not quiet:
        rprint(f"[green]OK[/green] Successfully parsed: {file}")


@app.command()
def ast(
    file: Annotated[Path, typer.Argument(help="CQL file to parse")],
    max_depth: Annotated[int, typer.Option("--depth", "-d", help="Maximum tree depth")] = 50,
) -> None:
    """Display the abstract syntax tree for a CQL file."""
    text = _read_existing_file(file)
    parse_tree, errors = parse_cql(text)

    if errors:
        _print_errors(errors)
        raise typer.Exit(1)

    rich_tree = Tree("[bold blue]library[/bold blue]")
    build_parse_tree(parse_tree, rich_tree, _make_parser(text), max_depth=max_depth)
    rprint(rich_tree)


@app.command()
def tokens(
    file: Annotated[Path, typer.Argument(help="CQL file to tokenize")],
    limit: Annotated[int | None, typer.Option("--limit", "-l", help="Maximum number of tokens to print")] = None,
) -> None:
    """Display the token stream for a CQL file."""
    text = _read_existing_file(file)
    lexer = cqlLexer(InputStream(text))

    rprint(f"[bold]Tokens for {file}:[/bold]\n")

    count = 0
    token: Any = lexer.nextToken()
    while token.type != -1:
        if limit is not None and count >= limit:
            rprint(f"\n[dim]... (limited to {limit} tokens)[/dim]")
            break

        token_name = lexer.symbolicNames[token.type] if token.type < len(lexer.symbolicNames) else "UNKNOWN"
        rprint(
            f"[cyan]{token_name:20}[/cyan] [green]'{token.text}'[/green] [dim](line {token.line}:{token.column})[/dim]"
        )

        count += 1
        token = lexer.nextToken()

    rprint(f"\n[dim]Total: {count} tokens[/dim]")


@app.command()
def show(
    file: Annotated[Path, typer.Argument(help="CQL file to display")],
) -> None:
    """Display a CQL file with syntax highlighting."""
    text = _read_existing_file(file)
    syntax = Syntax(text, "sql", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=str(file), border_style="blue"))


@app.command()
def validate(
    files: Annotated[list[Path], typer.Argument(help="CQL files to validate")],
) -> None:
    """Validate one or more CQL files."""
    total = len(files)
    passed = 0
    failed = 0

    for file in files:
        if not file.exists():
            rprint(f"[yellow]MISSING[/yellow] File not found: {file}")
            failed += 1
            continue

        _, errors = parse_cql(file.read_text())

        if errors:
            rprint(f"[red]FAIL[/red] {file}")
            for error in errors:
                rprint(f"    [red]*[/red] {error}")
            failed += 1
        else:
            rprint(f"[green]OK[/green] {file}")
            passed += 1

    rprint(f"\n[bold]Results:[/bold] {passed}/{total} passed, {failed}/{total} failed")

    if failed > 0:
        raise typer.Exit(1)


@app.command()
def definitions(
    file: Annotated[Path, typer.Argument(help="CQL file to analyze")],
) -> None:
    """List the library, using, valueset, code system, define, function, and context entries in a CQL file."""
    text = _read_existing_file(file)
    parse_tree, errors = parse_cql(text)

    if errors:
        _print_errors(errors)
        raise typer.Exit(1)

    rprint(f"[bold]Definitions in {file}:[/bold]\n")

    rule_names = _make_parser(text).ruleNames

    def walk(node: Any) -> None:
        """Print every labelled definition reachable from a parse tree node."""
        if hasattr(node, "getRuleIndex"):
            rule_name = rule_names[node.getRuleIndex()]
            label = DEFINITION_RULE_LABELS.get(rule_name)
            if label is not None:
                heading, color = label
                node_text = node.getText() if hasattr(node, "getText") else ""
                rprint(f"[{color}]{heading}:[/{color}] {node_text[:60]}")

        for child in getattr(node, "children", None) or []:
            walk(child)

    walk(parse_tree)


@app.command("eval")
def evaluate(
    expression: Annotated[str, typer.Argument(help="CQL expression to evaluate")],
    library: Annotated[Path | None, typer.Option("--library", "-l", help="CQL library file for context")] = None,
    data: Annotated[Path | None, typer.Option("--data", "-d", help=DATA_OPTION_HELP)] = None,
) -> None:
    """Evaluate a single CQL expression, optionally against a library and the data behind `--data`."""
    evaluation_data = load_evaluation_data(data)
    evaluator = CQLEvaluator(data_source=evaluation_data.data_source)

    if library is not None:
        source = _read_existing_file(library)
        try:
            evaluator.compile(source)
        except CQLError as error:
            rprint(f"[red]Error compiling library:[/red] {error}")
            raise typer.Exit(1) from error

    resource = evaluation_data.context_resource

    try:
        current_library = evaluator.current_library
        if current_library is not None and expression in current_library.definitions:
            result = evaluator.evaluate_definition(expression, resource=resource)
        else:
            result = evaluator.evaluate_expression(expression, resource=resource)
    except CQLError as error:
        rprint(f"[red]Evaluation error:[/red] {error}")
        raise typer.Exit(1) from error

    rprint(format_result(result))


@app.command()
def run(
    file: Annotated[Path, typer.Argument(help="CQL library file to run")],
    definition: Annotated[str | None, typer.Option("--definition", "-e", help="Single definition to evaluate")] = None,
    data: Annotated[Path | None, typer.Option("--data", "-d", help=DATA_OPTION_HELP)] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the results to this JSON file")] = None,
) -> None:
    """Run a CQL library and evaluate one definition or all of them."""
    source = _read_existing_file(file)
    evaluation_data = load_evaluation_data(data)
    evaluator = CQLEvaluator(data_source=evaluation_data.data_source)

    try:
        library = evaluator.compile(source)
    except CQLError as error:
        rprint(f"[red]Error compiling library:[/red] {error}")
        raise typer.Exit(1) from error

    resource = evaluation_data.context_resource

    rprint(_library_heading(library.name, library.version))
    rprint()

    try:
        if definition is not None:
            if definition not in library.definitions:
                rprint(f"[red]Error:[/red] Definition not found: {definition}")
                raise typer.Exit(1)

            result = evaluator.evaluate_definition(definition, resource=resource)
            rprint(f"[bold]{definition}:[/bold] {format_result(result)}")
            results: dict[str, Any] = {definition: result}
        else:
            results = evaluator.evaluate_all_definitions(resource=resource)

            table = Table(title="Results", show_header=True, header_style="bold")
            table.add_column("Definition", style="cyan")
            table.add_column("Value")

            for name, value in results.items():
                if isinstance(value, Exception):
                    table.add_row(name, f"[red]Error: {value}[/red]")
                else:
                    table.add_row(name, format_result(value))

            console.print(table)
    except CQLError as error:
        rprint(f"[red]Evaluation error:[/red] {error}")
        raise typer.Exit(1) from error

    if output is not None:
        output.write_text(json.dumps(_serializable_results(results), indent=2, default=str))
        rprint(f"\n[dim]Results written to {output}[/dim]")


@app.command()
def check(
    file: Annotated[Path, typer.Argument(help="CQL library file to check")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Also list every named entry")] = False,
) -> None:
    """Parse and compile a CQL library and summarise what it declares."""
    text = _read_existing_file(file)
    _, parse_errors = parse_cql(text)

    if parse_errors:
        _print_errors(parse_errors, f"Syntax errors in {file}:")
        raise typer.Exit(1)

    rprint("[green]OK[/green] Syntax valid")

    evaluator = CQLEvaluator()
    try:
        library = evaluator.compile(text)
    except CQLError as error:
        rprint(f"[red]FAIL[/red] Compilation error: {error}")
        raise typer.Exit(1) from error

    rprint("[green]OK[/green] Compilation successful")
    rprint()
    rprint(_library_heading(library.name, library.version))

    stats = Table(show_header=False, box=None)
    stats.add_column("Key", style="dim")
    stats.add_column("Value")
    stats.add_row("Definitions", str(len(library.definitions)))
    stats.add_row("Functions", str(len(library.functions)))
    stats.add_row("Value Sets", str(len(library.valuesets)))
    stats.add_row("Code Systems", str(len(library.codesystems)))
    stats.add_row("Codes", str(len(library.codes)))
    stats.add_row("Parameters", str(len(library.parameters)))
    console.print(stats)

    if verbose:
        rprint()

        if library.definitions:
            rprint("[bold]Definitions:[/bold]")
            for name in sorted(library.definitions):
                rprint(f"  [cyan]{name}[/cyan]")

        if library.functions:
            rprint("\n[bold]Functions:[/bold]")
            for name, overloads in sorted(library.functions.items()):
                for function in overloads:
                    parameters = ", ".join(
                        f"{parameter_name}: {parameter_type}" for parameter_name, parameter_type in function.parameters
                    )
                    return_type = f" -> {function.return_type}" if function.return_type else ""
                    rprint(f"  [cyan]{name}[/cyan]({parameters}){return_type}")

        if library.valuesets:
            rprint("\n[bold]Value Sets:[/bold]")
            for name, value_set in sorted(library.valuesets.items()):
                rprint(f"  [yellow]{name}[/yellow]: {value_set.id}")

        if library.codesystems:
            rprint("\n[bold]Code Systems:[/bold]")
            for name, code_system in sorted(library.codesystems.items()):
                rprint(f"  [magenta]{name}[/magenta]: {code_system.id}")

    rprint()
    rprint("[green]OK[/green] [bold]All checks passed[/bold]")


@app.command()
def measure(
    file: Annotated[Path, typer.Argument(help="CQL measure file")],
    data: Annotated[Path | None, typer.Option("--data", "-d", help=MEASURE_DATA_OPTION_HELP)] = None,
    patients: Annotated[Path | None, typer.Option("--patients", "-p", help="Directory of Patient JSON files")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the measure report to this file")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Also show stratifier results")] = False,
) -> None:
    """Evaluate a CQL quality measure against a population of patients."""
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    patient_list: list[dict[str, Any]] = []
    evaluation_data = load_evaluation_data(data)

    if data is not None:
        content = evaluation_data.document or {}
        if evaluation_data.data_source is not None:
            for entry in content.get("entry", []):
                resource = entry.get("resource", {})
                if resource.get("resourceType") == "Patient":
                    patient_list.append(resource)
        elif content.get("resourceType") == "Patient":
            patient_list.append(content)
        else:
            rprint("[red]Error:[/red] Data must be a Patient or a Bundle resource")
            raise typer.Exit(1)

    if patients is not None:
        if not patients.is_dir():
            rprint(f"[red]Error:[/red] Patients directory not found: {patients}")
            raise typer.Exit(1)

        for patient_file in sorted(patients.glob("*.json")):
            try:
                patient_data = json.loads(patient_file.read_text())
            except json.JSONDecodeError:
                rprint(f"[yellow]Warning:[/yellow] Skipping invalid JSON: {patient_file}")
                continue
            if patient_data.get("resourceType") == "Patient":
                patient_list.append(patient_data)

    if not patient_list:
        rprint("[yellow]Warning:[/yellow] No patients provided, using an empty population")

    measure_evaluator = MeasureEvaluator(data_source=evaluation_data.data_source)
    try:
        measure_evaluator.load_measure_file(str(file))

        rprint(f"[bold blue]Measure:[/bold blue] {file.name}")
        rprint(f"[dim]Evaluating {len(patient_list)} patient(s)...[/dim]")
        rprint()

        report = measure_evaluator.evaluate_population(patient_list)
    except Exception as error:
        rprint(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error

    for group in report.groups:
        table = Table(title=f"Group: {group.id or 'default'}", show_header=True, header_style="bold")
        table.add_column("Population", style="cyan")
        table.add_column("Count", justify="right")

        for population_type, population_count in group.populations.items():
            table.add_row(population_type, str(population_count.count))

        if group.measure_score is not None:
            table.add_row("[bold]Score[/bold]", f"[bold]{group.measure_score:.2%}[/bold]")

        console.print(table)

        if verbose and group.stratifiers:
            rprint("\n[bold]Stratifiers:[/bold]")
            for stratifier_name, strata in group.stratifiers.items():
                rprint(f"  [cyan]{stratifier_name}[/cyan]:")
                for stratum in strata:
                    rprint(f"    {stratum.value}: {stratum.populations}")

    if output is not None:
        output.write_text(json.dumps(report.to_fhir(), indent=2, default=str))
        rprint(f"\n[dim]Report written to {output}[/dim]")


@app.command()
def export(
    file: Annotated[Path, typer.Argument(help="CQL file to export")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the ELM JSON to this file")] = None,
    indent: Annotated[int, typer.Option("--indent", "-i", help="JSON indentation level")] = 2,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print only the JSON")] = False,
) -> None:
    """Export a CQL library to Expression Logical Model JSON."""
    source = _read_existing_file(file)

    try:
        elm_json = CQLEvaluator().to_elm_json(source, indent=indent)
    except CQLError as error:
        if quiet:
            print(f"Error: {error}", file=sys.stderr)
        else:
            rprint(f"[red]Error exporting to ELM:[/red] {error}")
        raise typer.Exit(1) from error

    if output is not None:
        output.write_text(elm_json)
        if not quiet:
            rprint(f"[green]OK[/green] Exported {file} -> {output}")
    elif quiet:
        print(elm_json)
    else:
        syntax = Syntax(elm_json, "json", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"ELM: {file}", border_style="blue"))


@app.command()
def repl(
    library: Annotated[Path | None, typer.Option("--library", "-l", help="CQL library file to load")] = None,
    data: Annotated[Path | None, typer.Option("--data", "-d", help=DATA_OPTION_HELP)] = None,
) -> None:
    """Start an interactive CQL evaluation session."""
    rprint("[bold blue]CQL[/bold blue]")
    rprint("Enter CQL expressions to evaluate. Type 'help' for the command list.\n")

    evaluator = CQLEvaluator()
    context_data: dict[str, Any] | None = None

    if library is not None and library.exists():
        try:
            loaded = evaluator.compile(library.read_text())
            rprint(f"[green]OK[/green] Loaded library: {loaded.name}")
            if loaded.definitions:
                rprint(f"  Definitions: {', '.join(loaded.definitions)}")
        except Exception as error:
            rprint(f"[yellow]Warning:[/yellow] Could not load library: {error}")

    if data is not None and data.exists():
        try:
            context_data = _bind_repl_data(evaluator, data)
        except Exception as error:
            rprint(f"[yellow]Warning:[/yellow] Could not load data: {error}")

    if library is not None or data is not None:
        rprint()

    while True:
        try:
            entry = console.input("[bold green]cql>[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            rprint("\nGoodbye!")
            break

        entry = entry.strip()
        if not entry:
            continue

        if entry.lower() in ("quit", "exit", "q"):
            rprint("Goodbye!")
            break

        if entry.lower() == "help":
            rprint(_REPL_HELP)
            continue

        if entry.lower().startswith("load "):
            library_path = Path(entry[5:].strip())
            if not library_path.exists():
                rprint(f"[red]Error:[/red] File not found: {library_path}")
                continue
            try:
                loaded = evaluator.compile(library_path.read_text())
                rprint(f"[green]OK[/green] Loaded: {loaded.name}")
                if loaded.definitions:
                    rprint(f"  Definitions: {', '.join(loaded.definitions)}")
            except Exception as error:
                rprint(f"[red]Error:[/red] {error}")
            continue

        if entry.lower().startswith("data "):
            data_path = Path(entry[5:].strip())
            if not data_path.exists():
                rprint(f"[red]Error:[/red] File not found: {data_path}")
                continue
            try:
                context_data = _bind_repl_data(evaluator, data_path)
            except Exception as error:
                rprint(f"[red]Error:[/red] {error}")
            continue

        if entry.lower() == "defs":
            current_library = evaluator.current_library
            if current_library is None:
                rprint("[yellow]No library loaded[/yellow]")
                continue
            if current_library.definitions:
                rprint(f"[bold]{current_library.name}[/bold] definitions:")
                for name in current_library.definitions:
                    rprint(f"  - {name}")
            if current_library.functions:
                rprint("Functions:")
                for name in current_library.functions:
                    rprint(f"  - {name}")
            if not current_library.definitions and not current_library.functions:
                rprint("[dim]No definitions[/dim]")
            continue

        if entry.lower() == "clear":
            evaluator = CQLEvaluator()
            context_data = None
            rprint("[green]OK[/green] Cleared")
            continue

        if entry.lower().startswith("eval "):
            try:
                rprint(format_result(evaluator.evaluate_definition(entry[5:].strip(), resource=context_data)))
            except Exception as error:
                rprint(f"[red]Error:[/red] {error}")
            continue

        if entry.lower().startswith("ast "):
            expression_text = entry[4:].strip()
            try:
                parser = _make_parser(expression_text)
                rich_tree = Tree("[bold blue]expression[/bold blue]")
                build_parse_tree(parser.expression(), rich_tree, parser)
                rprint(rich_tree)
            except Exception as error:
                rprint(f"[red]Error:[/red] {error}")
            continue

        try:
            rprint(format_result(evaluator.evaluate_expression(entry, resource=context_data)))
        except Exception as error:
            rprint(f"[red]Error:[/red] {error}")


def _serializable_results(results: dict[str, Any]) -> dict[str, Any]:
    """Turn evaluation results into a JSON-serialisable mapping."""
    serializable: dict[str, Any] = {}
    for name, value in results.items():
        if isinstance(value, Exception):
            serializable[name] = {"error": str(value)}
        elif hasattr(value, "model_dump"):
            serializable[name] = value.model_dump()
        else:
            serializable[name] = value
    return serializable


_REPL_HELP = """[dim]Commands:
  load <file>     Load a CQL library file
  data <file>     Load FHIR data for context
  defs            List the loaded definitions
  ast <expr>      Show the syntax tree for an expression
  eval <name>     Evaluate a definition by name
  clear           Drop the loaded library and data
  help            Show this help
  quit            Leave the session

Examples:
  1 + 2 * 3                            Evaluate an expression
  Today()                              Today's date
  Upper('hello')                       String function
  load mylib.cql                       Load a library
  defs                                 List definitions
  eval MyDefinition                    Evaluate a definition[/dim]"""
