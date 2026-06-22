"""Typer sub-app for the `query` plugin (mounted under `d2w query`)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_ql import D2qlError, parse, to_jsonable
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import is_json_output
from dhis2w_core.v43.plugins.query import service
from dhis2w_core.v43.plugins.query.models import QueryExplain

app = typer.Typer(help="d2ql query + transform language over DHIS2 metadata.", no_args_is_help=True)
_console = Console()

_TextArg = Annotated[str, typer.Argument(help="A d2ql program (quote it).")]
_DefineOpt = Annotated[str | None, typer.Option("--define", "-d", help="Run/explain this named definition.")]
_OutOpt = Annotated[str | None, typer.Option("--out", "-o", help="Write rows to this file (json/ndjson/csv).")]


@app.command("eval")
def eval_command(text: _TextArg, define: _DefineOpt = None, out: _OutOpt = None) -> None:
    """Run a d2ql program against the active profile and render the rows."""
    result = _run(service.run_query(profile_from_env(), text, define=define, out=out))
    _render_result(result)


@app.command("run")
def run_command(
    file: Annotated[Path, typer.Argument(help="Path to a .d2ql program file.")],
    define: _DefineOpt = None,
    out: _OutOpt = None,
) -> None:
    """Run a d2ql program read from a file."""
    result = _run(service.run_query(profile_from_env(), file.read_text(encoding="utf-8"), define=define, out=out))
    _render_result(result)


@app.command("explain")
def explain_command(text: _TextArg, define: _DefineOpt = None) -> None:
    """Show how a d2ql pipeline splits between DHIS2 pushdown and local evaluation."""
    explain = _run(service.explain_query(profile_from_env(), text, define=define))
    _render_explain(explain)


@app.command("ast")
def ast_command(text: _TextArg) -> None:
    """Print the parsed d2ql AST (no profile needed)."""
    try:
        library = parse(text)
    except D2qlError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(library.model_dump_json(indent=2, exclude_none=True))


@app.command("d2path")
def d2path_command(
    expression: Annotated[str, typer.Argument(help="A d2path expression (quote it).")],
    input_file: Annotated[Path, typer.Option("--input", "-i", help="JSON file to evaluate against.")],
) -> None:
    """Evaluate a bare d2path expression over a local JSON document (no profile needed)."""
    data = json.loads(input_file.read_text(encoding="utf-8"))
    try:
        result = service.evaluate_path(expression, data)
    except D2qlError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("repl")
def repl_command() -> None:
    """Start an interactive d2ql prompt against the active profile."""
    profile = profile_from_env()
    _console.print("[dim]d2ql REPL — one program per line, Ctrl-D to exit.[/dim]")
    while True:
        try:
            line = _console.input("[bold cyan]d2ql>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            _console.print()
            return
        if not line:
            continue
        try:
            _render_result(_run(service.run_query(profile, line)))
        except D2qlError as error:
            _console.print(f"[red]{error}[/red]")


def register(root_app: Any) -> None:
    """Mount under `d2w query`."""
    root_app.add_typer(app, name="query", help="d2ql query + transform language.")


def _run(coroutine: Any) -> Any:
    try:
        return asyncio.run(coroutine)
    except D2qlError as error:
        raise typer.BadParameter(str(error)) from error


def _render_result(result: Any) -> None:
    if result.written_to is not None:
        _console.print(f"[green]wrote {result.count} row(s) to {result.written_to}[/green]")
        return
    if result.scalar:
        typer.echo(str(result.rows[0] if result.rows else 0))
        return
    payload = [to_jsonable(row) for row in result.rows]
    if is_json_output() or not _all_objects(payload):
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    _render_table(payload)


def _all_objects(rows: list[Any]) -> bool:
    return bool(rows) and all(isinstance(row, dict) for row in rows)


def _render_table(rows: list[dict[str, Any]]) -> None:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    table = Table(title=f"{len(rows)} row(s)", pad_edge=False)
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*[_cell(row.get(column)) for column in columns])
    _console.print(table)


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_explain(explain: QueryExplain) -> None:
    if is_json_output():
        typer.echo(explain.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[bold]source[/bold]: {explain.source} ([cyan]{explain.source_kind}[/cyan])")
    if explain.pushed_down is not None:
        native = explain.pushed_down
        filters = ", ".join(f"{f.property}:{f.operator}:{f.value}" for f in native.filters) or "(none)"
        order = ", ".join(f"{o.property}:{'desc' if o.descending else 'asc'}" for o in native.order) or "(none)"
        _console.print(f"[bold]pushed down[/bold]: filter[{native.root_junction}] {filters}")
        _console.print(f"               order {order}; skip {native.skip}; limit {native.limit}")
    _console.print(f"[bold]local stages[/bold]: {', '.join(explain.residual_stages) or '(none)'}")
    if explain.note:
        _console.print(f"[yellow]note[/yellow]: {explain.note}")
