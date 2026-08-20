"""FHIRPath expression parsing, inspection, and evaluation commands."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from antlr4 import CommonTokenStream, InputStream  # type: ignore[import-untyped]
from antlr4.error.ErrorListener import ErrorListener  # type: ignore[import-untyped]
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree

from ..engine.exceptions import FHIRPathError
from ..engine.fhirpath import FHIRPathEvaluator, unwrap_primitives
from ..generated.fhirpath.fhirpathLexer import fhirpathLexer
from ..generated.fhirpath.fhirpathParser import fhirpathParser

app = typer.Typer(
    name="fhirpath",
    help="FHIRPath expression parser and evaluator.",
    no_args_is_help=True,
)
console = Console()

MAXIMUM_PREVIEW_LENGTH = 50


class FHIRPathErrorListener(ErrorListener):
    """Collect the syntax errors the FHIRPath parser reports."""

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


def parse_fhirpath(text: str) -> tuple[fhirpathParser.ExpressionContext, list[str]]:
    """Parse FHIRPath text and return the parse tree together with any syntax errors."""
    input_stream = InputStream(text)
    lexer = fhirpathLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = fhirpathParser(token_stream)

    error_listener = FHIRPathErrorListener()
    parser.removeErrorListeners()
    parser.addErrorListener(error_listener)

    parse_tree = parser.expression()
    return parse_tree, error_listener.errors


def build_parse_tree(node: Any, tree: Tree, parser: Any, depth: int = 0, max_depth: int = 50) -> None:
    """Fill a rich tree with the rule names and literals of a FHIRPath parse tree."""
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


def _print_errors(errors: list[str], heading: str = "Parse errors:") -> None:
    """Print a list of parse errors."""
    rprint(f"[red]{heading}[/red]")
    for error in errors:
        rprint(f"  [red]*[/red] {error}")


def _render_ast(expression: str, max_depth: int = 50) -> Tree:
    """Build a rich tree for a FHIRPath expression that is already known to parse."""
    parse_tree, _ = parse_fhirpath(expression)
    input_stream = InputStream(expression)
    lexer = fhirpathLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = fhirpathParser(token_stream)

    rich_tree = Tree("[bold blue]expression[/bold blue]")
    build_parse_tree(parse_tree, rich_tree, parser, max_depth=max_depth)
    return rich_tree


def _print_tokens(expression: str) -> int:
    """Print the token stream of a FHIRPath expression and return the token count."""
    input_stream = InputStream(expression)
    lexer = fhirpathLexer(input_stream)

    count = 0
    token: Any = lexer.nextToken()
    while token.type != -1:
        token_name = lexer.symbolicNames[token.type] if token.type < len(lexer.symbolicNames) else "UNKNOWN"
        rprint(f"[cyan]{token_name:20}[/cyan] [green]'{token.text}'[/green] [dim](col {token.column})[/dim]")
        count += 1
        token = lexer.nextToken()

    return count


def _load_resource(resource: Path | None, json_input: str | None = None) -> dict[str, Any] | None:
    """Load a FHIR resource from a file or an inline JSON string."""
    if resource is not None:
        if not resource.exists():
            rprint(f"[red]Error:[/red] Resource file not found: {resource}")
            raise typer.Exit(1)
        text = resource.read_text()
    elif json_input is not None:
        text = json_input
    else:
        return None

    try:
        loaded: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as error:
        rprint(f"[red]Error:[/red] Invalid JSON resource: {error}")
        raise typer.Exit(1) from error
    return loaded


@app.command()
def parse(
    expression: Annotated[str, typer.Argument(help="FHIRPath expression to parse")],
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Only show errors")] = False,
) -> None:
    """Parse a FHIRPath expression and report any syntax errors."""
    _, errors = parse_fhirpath(expression)

    if errors:
        _print_errors(errors)
        raise typer.Exit(1)

    if not quiet:
        rprint("[green]OK[/green] Valid FHIRPath expression")


@app.command()
def ast(
    expression: Annotated[str, typer.Argument(help="FHIRPath expression to parse")],
    max_depth: Annotated[int, typer.Option("--depth", "-d", help="Maximum tree depth")] = 50,
) -> None:
    """Display the abstract syntax tree for a FHIRPath expression."""
    _, errors = parse_fhirpath(expression)

    if errors:
        _print_errors(errors)
        raise typer.Exit(1)

    rprint(_render_ast(expression, max_depth=max_depth))


@app.command()
def tokens(
    expression: Annotated[str, typer.Argument(help="FHIRPath expression to tokenize")],
) -> None:
    """Display the token stream for a FHIRPath expression."""
    rprint("[bold]Tokens:[/bold]\n")
    count = _print_tokens(expression)
    rprint(f"\n[dim]Total: {count} tokens[/dim]")


@app.command("parse-file")
def parse_file(
    file: Annotated[Path, typer.Argument(help="File holding one FHIRPath expression per line")],
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Only show errors")] = False,
) -> None:
    """Parse every FHIRPath expression in a file, one expression per line."""
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    total = 0
    passed = 0
    failed = 0

    for line_number, raw_line in enumerate(file.read_text().strip().split("\n"), 1):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        total += 1
        _, errors = parse_fhirpath(line)

        if errors:
            rprint(f"[red]FAIL[/red] Line {line_number}: {line[:MAXIMUM_PREVIEW_LENGTH]}...")
            for error in errors:
                rprint(f"    [red]*[/red] {error}")
            failed += 1
        else:
            if not quiet:
                suffix = "..." if len(line) > MAXIMUM_PREVIEW_LENGTH else ""
                rprint(f"[green]OK[/green] Line {line_number}: {line[:MAXIMUM_PREVIEW_LENGTH]}{suffix}")
            passed += 1

    rprint(f"\n[bold]Results:[/bold] {passed}/{total} passed, {failed}/{total} failed")

    if failed > 0:
        raise typer.Exit(1)


@app.command()
def repl() -> None:
    """Start an interactive FHIRPath parsing session."""
    rprint("[bold blue]FHIRPath[/bold blue]")
    rprint("Enter FHIRPath expressions to parse. Type 'quit' or 'exit' to leave.\n")

    while True:
        try:
            entry = console.input("[bold green]fhirpath>[/bold green] ")
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
            rprint("[dim]Commands: ast <expression>, tokens <expression>, quit[/dim]")
            continue

        if entry.lower().startswith("ast "):
            expression = entry[4:]
            _, errors = parse_fhirpath(expression)
            if errors:
                for error in errors:
                    rprint(f"  [red]*[/red] {error}")
            else:
                rprint(_render_ast(expression))
            continue

        if entry.lower().startswith("tokens "):
            _print_tokens(entry[7:])
            continue

        _, errors = parse_fhirpath(entry)
        if errors:
            for error in errors:
                rprint(f"  [red]*[/red] {error}")
        else:
            rprint("[green]OK[/green] Valid")


@app.command()
def show(
    file: Annotated[Path, typer.Argument(help="FHIRPath file to display")],
) -> None:
    """Display a FHIRPath file with syntax highlighting."""
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    syntax = Syntax(file.read_text(), "javascript", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=str(file), border_style="blue"))


@app.command("eval")
def evaluate(
    expression: Annotated[str, typer.Argument(help="FHIRPath expression to evaluate")],
    resource: Annotated[Path | None, typer.Option("--resource", "-r", help="Path to a FHIR JSON resource")] = None,
    json_input: Annotated[str | None, typer.Option("--json", "-j", help="Inline JSON resource")] = None,
    output_json: Annotated[bool, typer.Option("--json-output", help="Print the result as JSON")] = False,
) -> None:
    """Evaluate a FHIRPath expression against a FHIR resource."""
    fhir_resource = _load_resource(resource, json_input)

    try:
        evaluator = FHIRPathEvaluator()
        result = evaluator.evaluate(expression, fhir_resource)
    except FHIRPathError as error:
        rprint(f"[red]FHIRPath error:[/red] {error}")
        raise typer.Exit(1) from error

    values = unwrap_primitives(result)

    if output_json:
        print(json.dumps(values, indent=2, default=str))
    elif not values:
        rprint("[dim]Empty result ([])[/dim]")
    elif len(values) == 1:
        rprint(f"[green]{values[0]!r}[/green]")
    else:
        rprint("[bold]Results:[/bold]")
        for index, item in enumerate(values):
            rprint(f"  [{index}] [green]{item!r}[/green]")


@app.command("eval-file")
def evaluate_file(
    expressions_file: Annotated[Path, typer.Argument(help="File holding one FHIRPath expression per line")],
    resource: Annotated[Path | None, typer.Option("--resource", "-r", help="Path to a FHIR JSON resource")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Only show errors")] = False,
) -> None:
    """Evaluate every FHIRPath expression in a file against a FHIR resource."""
    if not expressions_file.exists():
        rprint(f"[red]Error:[/red] File not found: {expressions_file}")
        raise typer.Exit(1)

    fhir_resource = _load_resource(resource)
    evaluator = FHIRPathEvaluator()

    total = 0
    passed = 0
    failed = 0

    for line_number, raw_line in enumerate(expressions_file.read_text().strip().split("\n"), 1):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        total += 1
        try:
            result = evaluator.evaluate(line, fhir_resource)
        except FHIRPathError as error:
            rprint(f"[red]FAIL[/red] Line {line_number}: {line}")
            rprint(f"    [red]*[/red] {error}")
            failed += 1
            continue

        if not quiet:
            values = unwrap_primitives(result)
            rendered = repr(values[0]) if len(values) == 1 else repr(values)
            if len(rendered) > MAXIMUM_PREVIEW_LENGTH:
                rendered = rendered[: MAXIMUM_PREVIEW_LENGTH - 3] + "..."
            rprint(f"[green]OK[/green] {line[:40]:40} => [cyan]{rendered}[/cyan]")
        passed += 1

    rprint(f"\n[bold]Results:[/bold] {passed}/{total} passed, {failed}/{total} failed")

    if failed > 0:
        raise typer.Exit(1)
